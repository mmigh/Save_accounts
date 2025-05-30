from discord.ext import commands, tasks
from discord import app_commands
import discord
import os
import json
import csv
import io
import random
import string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

TOKEN = os.environ.get("TOKEN")
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))

SHEET_NAME = "RobloxAccounts"
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("Thiếu biến môi trường GOOGLE_CREDENTIALS_JSON!")

cred_dict = json.loads(cred_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# ===== Logcal_ugphone Handling =====
def read_logcals():
    logcals = {}
    col_values = sheet.col_values(3)[1:]
    for value in col_values:
        if value:
            logcals[value] = {}
    return logcals

def save_logcal(logcal_json):
    try:
        parsed = json.loads(logcal_json)
        safe_json = json.dumps(parsed, ensure_ascii=False)
    except Exception:
        safe_json = logcal_json

    sheet.append_row(["", "", safe_json])
    
def delete_logcal(logcal_json):
    cell = sheet.find(logcal_json)
    if cell and cell.col == 3:
        sheet.delete_rows(cell.row)
        
# ===== Account Handling =====
def read_accounts():
    accounts = {}
    records = sheet.get_all_records()
    for record in records:
        account = record.get('Account', '')
        note = record.get('Note', '')
        if account:
            accounts[account] = {'note': note}
    return accounts

def save_account(account, note):
    last_row = len(sheet.get_all_values()) + 1
    sheet.insert_row([account, note, ""], last_row)
    
def delete_account(account):
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.delete_rows(cell.row)

def update_note(account, new_note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, new_note)

def generate_roblox_username(length=12):
    if length < 3 or length > 20:
        raise ValueError("Username length must be giữa 3 và 20.")
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    remaining = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    result = list(upper + lower + digit + remaining)
    random.shuffle(result)
    return ''.join(result)

# ===== Bot Setup =====
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}
        self.logcals = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()
        self.refresh_data.start()
        await self.tree.sync()
        print("✅ Slash commands đã được đồng bộ!")

    @tasks.loop(minutes=3)
    async def refresh_data(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()

bot = MyBot()

# ===== Logcal Commands =====
@bot.tree.command(name="add", description="➕ Thêm JSON logcal_ugphone")
@app_commands.describe(logcal="Dòng JSON logcal cần thêm")
async def add_logcal(interaction: discord.Interaction, logcal: str):
    logcal = logcal.strip()
    if logcal in bot.logcals:
        await interaction.response.send_message("⚠️ Dòng này đã tồn tại.", ephemeral=True)
        return
    bot.logcals[logcal] = {}
    save_logcal(logcal)
    await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

@bot.tree.command(name="file", description="📂 Nhập nhiều logcal từ file .txt")
@app_commands.describe(file="File .txt mỗi dòng là một logcal JSON")
async def add_file_logcal(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ Chỉ nhận file .txt!", ephemeral=True)
        return

    content = await file.read()
    lines = [line.strip() for line in content.decode(errors="ignore").splitlines() if line.strip()]
    added = 0
    skipped = 0

    for line in lines:
        if line in bot.logcals:
            skipped += 1
            continue
        bot.logcals[line] = {}
        save_logcal(line)
        added += 1

    await interaction.response.send_message(
        f"✅ Đã thêm {added} dòng logcal mới.\n⚠️ Bỏ qua {skipped} dòng trùng lặp.",
        ephemeral=True
    )

@bot.tree.command(name="count", description="🔢 Đếm số lượng logcal_ugphone đang lưu")
async def count_logcal(interaction: discord.Interaction):
    count = len(bot.logcals)
    await interaction.response.send_message(f"📊 Hiện có {count} dòng logcal_ugphone trong danh sách.", ephemeral=True)

@bot.tree.command(name="get", description="🎲 Lấy và xóa 1 dòng logcal ngẫu nhiên")
async def get_logcal(interaction: discord.Interaction):
    try:
        if not bot.logcals:
            await interaction.response.send_message("📭 Không còn dòng logcal nào để rút.", ephemeral=True)
            return
        logcal = random.choice(list(bot.logcals.keys()))
        delete_logcal(logcal)
        del bot.logcals[logcal]
        await interaction.response.send_message(f"🎯 Đã lấy:\n```json\n{logcal}```", ephemeral=True)
        if NOTIFY_CHANNEL_ID:
            channel = bot.get_channel(NOTIFY_CHANNEL_ID)
            if channel:
                await channel.send(f"🎯 Đã rút logcal:\n```json\n{logcal}```")
    except Exception as e:
        await interaction.response.send_message(f"❌ Lỗi khi xử lý: `{e}`", ephemeral=True)

# ===== Account Commands =====
@bot.tree.command(name="account", description="➕ Thêm tài khoản Roblox mới")
@app_commands.describe(account="Tên tài khoản Roblox", note="Ghi chú cho tài khoản")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    account = account.strip()
    if not account:
        await interaction.response.send_message("⚠️ Tên tài khoản không được để trống!", ephemeral=True)
        return
    if account in bot.accounts:
        await interaction.response.send_message(f"⚠️ Tài khoản {account} đã tồn tại!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message(f"✅ Đã thêm: {account} với ghi chú: {note}", ephemeral=True)
    if NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(f"🔔 Đã thêm tài khoản mới: {account}")

@bot.tree.command(name="remove", description="❌ Xóa tài khoản khỏi danh sách")
@app_commands.describe(account="Tên tài khoản cần xóa")
async def remove_account(interaction: discord.Interaction, account: str):
    account = account.strip()
    if account not in bot.accounts:
        await interaction.response.send_message(f"⚠️ Tài khoản {account} không tồn tại.", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message(f"✅ Đã xóa tài khoản {account} khỏi danh sách.", ephemeral=True)

@bot.tree.command(name="show", description="📋 Hiển thị danh sách tài khoản đã lưu")
async def show_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("📭 Chưa có tài khoản nào được lưu.", ephemeral=True)
        return
    options = []
    for name in list(bot.accounts.keys())[:25]:
        note = bot.accounts[name].get("note", "")
        options.append(discord.SelectOption(
            label=name[:100],
            description=(note[:97] + "..." if len(note) > 100 else note) or "Không có ghi chú"
        ))
    select = discord.ui.Select(placeholder="🔍 Chọn tài khoản để xem", options=options)
    async def select_callback(i: discord.Interaction):
        selected = select.values[0]
        note = bot.accounts[selected].get("note", "Không có ghi chú")
        await i.response.send_message(f"🧾 **Tài khoản:** `{selected}`\n📝 **Ghi chú:** `{note}`", ephemeral=True)
    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("📚 Danh sách tài khoản:", view=view, ephemeral=True)

@bot.tree.command(name="counts", description="🔢 Đếm số lượng tài khoản")
async def count_accounts(interaction: discord.Interaction):
    count = len(bot.accounts)
    await interaction.response.send_message(f"📊 Có tổng cộng {count} tài khoản được lưu.", ephemeral=True)

@bot.tree.command(name="generate", description="⚙️ Tạo tài khoản Roblox ngẫu nhiên và lưu lại")
@app_commands.describe(amount="Số lượng tạo", length="Độ dài tên (3–20)")
async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
    if not (1 <= amount <= 20):
        await interaction.response.send_message("⚠️ Số lượng từ 1–20.", ephemeral=True)
        return
    if not (3 <= length <= 20):
        await interaction.response.send_message("⚠️ Độ dài tên phải từ 3–20.", ephemeral=True)
        return

    generated = []
    for _ in range(amount):
        while True:
            username = generate_roblox_username(length)
            if username not in bot.accounts:
                break
        bot.accounts[username] = {"note": "Generated"}
        save_account(username, "Generated")
        generated.append(username)

    message = ", ".join(generated)
    await interaction.response.send_message(f"✅ Đã tạo {amount} tài khoản:\n```{message}```", ephemeral=True)

    if NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(f"⚙️ Tạo {amount} tài khoản mới: ```{message}```")

@bot.tree.command(name="backup", description="📥 Sao lưu tài khoản ra file .txt")
async def backup_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("⚠️ Không có tài khoản để sao lưu.", ephemeral=True)
        return
    lines = [f"{acc} | {info.get('note', '')}" for acc, info in bot.accounts.items()]
    content = "\n".join(lines)
    file = discord.File(fp=io.BytesIO(content.encode()), filename="accounts_backup.txt")
    await interaction.response.send_message("🗂️ Đây là bản sao lưu:", file=file, ephemeral=True)

@bot.tree.command(name="restore", description="♻️ Khôi phục tài khoản từ file .txt")
@app_commands.describe(file="Tệp sao lưu")
async def restore_accounts(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ File phải .txt!", ephemeral=True)
        return
    content = await file.read()
    lines = [l.strip() for l in content.decode(errors="ignore").splitlines() if "|" in l]
    if not lines:
        await interaction.response.send_message("⚠️ File không hợp lệ!", ephemeral=True)
        return
    sheet.clear()
    sheet.append_row(["Account", "Note", "Logcal_ugphone"])
    bot.accounts.clear()
    for l in lines:
        parts = [p.strip() for p in l.split("|")]
        if len(parts) >= 2 and parts[0]:
            sheet.append_row([parts[0], parts[1], ""])
            bot.accounts[parts[0]] = {"note": parts[1]}
    await interaction.response.send_message(f"✅ Đã khôi phục {len(lines)} tài khoản!", ephemeral=True)

@bot.tree.command(name="edit", description="✏️ Sửa ghi chú tài khoản")
@app_commands.describe(account="Tên tài khoản cần sửa", note="Ghi chú mới")
async def edit_note(interaction: discord.Interaction, account: str, note: str):
    account = account.strip()

    if account not in bot.accounts:
        await interaction.response.send_message(
            f"⚠️ Không tìm thấy tài khoản `{account}`.", ephemeral=True)
        return

    bot.accounts[account]["note"] = note
    update_note(account, note)

    await interaction.response.send_message(
        f"✅ Đã cập nhật ghi chú cho `{account}` thành: `{note}`", ephemeral=True)

# ===== On Ready =====
@bot.event
async def on_ready():
    print(f"✅ Bot đã đăng nhập: {bot.user} (ID: {bot.user.id})")

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
