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

# === ENV & CONFIG ===
TOKEN = os.environ.get("TOKEN")
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))
SHEET_NAME = "RobloxAccounts"

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("Thiếu GOOGLE_CREDENTIALS_JSON")

creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(cred_json), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# === Logcal Handling ===
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

# === Account Handling ===
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
    row = [account, note or "", ""]
    last_row = len(sheet.get_all_values()) + 1
    sheet.insert_row(row, last_row)

def delete_account(account):
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.delete_rows(cell.row)

def update_note(account, new_note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, new_note)

def generate_roblox_username(length=12):
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    remain = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    result = list(upper + lower + digit + remain)
    random.shuffle(result)
    return ''.join(result)

# === Gửi log sau lệnh ===
async def send_log(interaction: discord.Interaction, action: str):
    if not NOTIFY_CHANNEL_ID:
        return
    channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    user = interaction.user
    await channel.send(f"📝 `{user}` đã dùng lệnh: **/{interaction.command.name}**\n📘 `{action}`")

# === Bot Class ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}
        self.logcals = {}
        self.last_sent_messages = []

    async def setup_hook(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()
        self.refresh_data.start()
        self.update_embed_loop.start()
        await self.tree.sync()
        print("✅ Slash commands đã được đồng bộ!")

    @tasks.loop(minutes=3)
    async def refresh_data(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()

    @tasks.loop(hours=5)
    async def update_embed_loop(self):
        await self.send_updated_account_message()

    async def send_updated_account_message(self):
        if not ACCOUNT_NOTI_CHANNEL:
            return
        channel = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not channel:
            return

        # Xoá các tin nhắn cũ của bot trong kênh
        try:
            async for m in channel.history(limit=20):
                if m.author == self.user:
                    try:
                        await m.delete()
                    except:
                        pass
        except:
            pass

        # Soạn nội dung danh sách tài khoản
        lines = [f"{acc} | {info.get('note', '')}" for acc, info in self.accounts.items()]
        chunks = []
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 > 1900:
                chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += line + "\n"
        if current_chunk:
            chunks.append(current_chunk)

        if not chunks:
            chunks.append("Không có tài khoản nào.")

        # Gửi danh sách mới
        for chunk in chunks:
            await channel.send(chunk)

bot = MyBot()

# === Logcal Commands ===
@bot.tree.command(name="save", description="➕ Thêm logcal JSON")
@app_commands.describe(logcal="Dữ liệu logcal")
async def add_logcal(interaction: discord.Interaction, logcal: str):
    logcal = logcal.strip()
    if logcal in bot.logcals:
        await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
        return
    bot.logcals[logcal] = {}
    save_logcal(logcal)
    await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

@bot.tree.command(name="get", description="🎲 Rút 1 logcal ngẫu nhiên")
async def get_logcal(interaction: discord.Interaction):
    if not bot.logcals:
        await interaction.response.send_message("📭 Hết logcal!", ephemeral=True)
        return
    choice = random.choice(list(bot.logcals))
    delete_logcal(choice)
    del bot.logcals[choice]
    await interaction.response.send_message(f"🎯 Logcal:\n```json\n{choice}```", ephemeral=True)
   
@bot.tree.command(name="add_file", description="📂 Nhập nhiều logcal từ file .txt")
@app_commands.describe(file="Tệp .txt, mỗi dòng là một logcal JSON hoặc chuỗi")
async def add_file_logcal(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ Chỉ hỗ trợ file .txt!", ephemeral=True)
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
        f"✅ Đã thêm **{added}** logcal mới.\n⚠️ Bỏ qua **{skipped}** dòng trùng lặp.",
        ephemeral=True
    )
    
@bot.tree.command(name="count_all", description="🔢 Đếm số lượng tài khoản và logcal")
async def count_all(interaction: discord.Interaction):
    acc_count = len(bot.accounts)
    log_count = len(bot.logcals)
    await interaction.response.send_message(
        f"📦 Tổng tài khoản: `{acc_count}`\n🗂️ Tổng logcal: `{log_count}`", ephemeral=True
    )

# === Slash commands ===
@bot.tree.command(name="add", description="➕ Thêm tài khoản Roblox")
@app_commands.describe(account="Tên tài khoản", note="Ghi chú (tùy chọn)")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    account = account.strip()
    if not account:
        await interaction.response.send_message("⚠️ Không được để trống tài khoản!", ephemeral=True)
        return
    if account in bot.accounts:
        await interaction.response.send_message(f"⚠️ Tài khoản `{account}` đã tồn tại!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message(f"✅ Đã thêm: `{account}` với ghi chú: `{note}`", ephemeral=True)
    await bot.send_or_update_embed()
    await send_log(interaction, f"Thêm account: {account} | note: {note}")

@bot.tree.command(name="edit", description="✏️ Sửa ghi chú")
@app_commands.describe(account="Tên tài khoản", note="Ghi chú mới")
async def edit_note(interaction: discord.Interaction, account: str, note: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tìm thấy tài khoản!", ephemeral=True)
        return
    bot.accounts[account]["note"] = note
    update_note(account, note)
    await interaction.response.send_message(f"✅ Đã cập nhật: `{account}` -> `{note}`", ephemeral=True)
    await bot.send_or_update_embed()
    await send_log(interaction, f"Sửa note account: {account} -> {note}")

@bot.tree.command(name="remove", description="❌ Xóa tài khoản")
@app_commands.describe(account="Tên tài khoản")
async def remove_account(interaction: discord.Interaction, account: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tồn tại.", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message(f"✅ Đã xoá: `{account}`", ephemeral=True)
    await bot.send_or_update_embed()
    await send_log(interaction, f"Xoá account: {account}")

@bot.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
@app_commands.describe(amount="Số lượng", length="Độ dài tên")
async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
    if not (1 <= amount <= 20):
        await interaction.response.send_message("⚠️ Giới hạn 1–20.", ephemeral=True)
        return
    generated = []
    for _ in range(amount):
        while True:
            uname = generate_roblox_username(length)
            if uname not in bot.accounts:
                break
        bot.accounts[uname] = {"note": "Generated"}
        save_account(uname, "Generated")
        generated.append(uname)
    await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(f"`{g}`" for g in generated), ephemeral=True)
    await bot.send_or_update_embed()
    await send_log(interaction, f"Tạo {amount} account: {', '.join(generated)}")

@bot.tree.command(name="backup_accounts", description="💾 Sao lưu")
async def backup_accounts(interaction: discord.Interaction):
    content = "\n".join([f"{acc} | {info.get('note','')}" for acc, info in bot.accounts.items()])
    file = discord.File(io.BytesIO(content.encode()), filename="accounts_backup.txt")
    await interaction.response.send_message("🗂️ Dữ liệu sao lưu:", file=file, ephemeral=True)

@bot.tree.command(name="restore_accounts", description="♻️ Khôi phục từ file")
@app_commands.describe(file="File .txt")
async def restore_accounts(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ Chỉ .txt!", ephemeral=True)
        return
    text = (await file.read()).decode(errors="ignore")
    lines = [l.strip() for l in text.splitlines() if "|" in l]
    if not lines:
        await interaction.response.send_message("⚠️ Không hợp lệ!", ephemeral=True)
        return
    sheet.clear()
    sheet.append_row(["Account", "Note", "Logcal_ugphone"])
    bot.accounts.clear()
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2:
            save_account(parts[0], parts[1])
            bot.accounts[parts[0]] = {"note": parts[1]}
    await interaction.response.send_message(f"✅ Đã khôi phục {len(lines)}!", ephemeral=True)
    await bot.send_updated_account_message()
# === Bot Ready ===
@bot.event
async def on_ready():
    print(f"🤖 Bot sẵn sàng: {bot.user} (ID: {bot.user.id})")

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
