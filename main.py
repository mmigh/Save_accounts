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

# === ENV ===
TOKEN = os.environ.get("TOKEN")
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))
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

# === Logcal ===
def read_logcals():
    logcals = {}
    values = sheet.col_values(3)[1:]
    for v in values:
        if v:
            logcals[v] = {}
    return logcals

def save_logcal(data):
    try:
        parsed = json.loads(data)
        safe = json.dumps(parsed, ensure_ascii=False)
    except:
        safe = data
    sheet.append_row(["", "", safe])

def delete_logcal(data):
    cell = sheet.find(data)
    if cell and cell.col == 3:
        sheet.delete_rows(cell.row)

# === Account ===
def read_accounts():
    records = sheet.get_all_records()
    return {r['Account']: {"note": r.get('Note', '')} for r in records if r['Account']}

def save_account(account, note):
    sheet.append_row([account, note, ""])

def delete_account(account):
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.delete_rows(cell.row)

def update_note(account, note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, note)

def generate_roblox_username(length=12):
    pool = string.ascii_letters + string.digits
    while True:
        result = random.choice(string.ascii_uppercase) + random.choice(string.ascii_lowercase) + random.choice(string.digits)
        result += ''.join(random.choices(pool, k=length - 3))
        final = ''.join(random.sample(result, len(result)))
        return final

# === Bot ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}
        self.logcals = {}
        self.update_message_id = None

    async def setup_hook(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()
        self.refresh_loop.start()
        self.account_notify_loop.start()
        await self.tree.sync()

    @tasks.loop(minutes=3)
    async def refresh_loop(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()

    @tasks.loop(hours=10)
    async def account_notify_loop(self):
        await self.send_updated_account_message()

    async def send_updated_account_message(self):
        if not ACCOUNT_NOTI_CHANNEL:
            return
        channel = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not channel:
            return
        messages = [m async for m in channel.history(limit=10)]
        for m in messages:
            if m.author == self.user:
                try:
                    await m.delete()
                except:
                    pass
        lines = [f"{acc} | {info.get('note','')}" for acc, info in self.accounts.items()]
        chunks = []
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 1900:
                chunks.append(chunk)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            chunks.append(chunk)
        for c in chunks:
            await channel.send(c or "Không có tài khoản nào.")

bot = MyBot()

# === Logcal Commands ===
@bot.tree.command(name="add_logcal", description="➕ Thêm logcal JSON")
@app_commands.describe(logcal="Dữ liệu logcal")
async def add_logcal(interaction: discord.Interaction, logcal: str):
    logcal = logcal.strip()
    if logcal in bot.logcals:
        await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
        return
    bot.logcals[logcal] = {}
    save_logcal(logcal)
    await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

@bot.tree.command(name="get_logcal", description="🎲 Rút 1 logcal ngẫu nhiên")
async def get_logcal(interaction: discord.Interaction):
    if not bot.logcals:
        await interaction.response.send_message("📭 Hết logcal!", ephemeral=True)
        return
    choice = random.choice(list(bot.logcals))
    delete_logcal(choice)
    del bot.logcals[choice]
    await interaction.response.send_message(f"🎯 Logcal:\n```json\n{choice}```", ephemeral=True)

# === Account Commands ===
@bot.tree.command(name="add_account", description="➕ Thêm tài khoản")
@app_commands.describe(account="Tên", note="Ghi chú")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    if account in bot.accounts:
        await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message(f"✅ Đã thêm `{account}`", ephemeral=True)
    await bot.send_updated_account_message()

@bot.tree.command(name="edit_note", description="✏️ Sửa ghi chú")
@app_commands.describe(account="Tài khoản", note="Ghi chú mới")
async def edit_note(interaction: discord.Interaction, account: str, note: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tồn tại!", ephemeral=True)
        return
    update_note(account, note)
    bot.accounts[account]["note"] = note
    await interaction.response.send_message("✅ Đã cập nhật!", ephemeral=True)
    await bot.send_updated_account_message()

@bot.tree.command(name="remove_account", description="❌ Xoá tài khoản")
@app_commands.describe(account="Tên tài khoản")
async def remove_account(interaction: discord.Interaction, account: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tồn tại!", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message("🗑️ Đã xoá!", ephemeral=True)
    await bot.send_updated_account_message()

@bot.tree.command(name="generate_account", description="⚙️ Tạo nhiều tài khoản")
@app_commands.describe(amount="Số lượng", length="Độ dài tên")
async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
    if not (1 <= amount <= 20):
        await interaction.response.send_message("⚠️ 1–20!", ephemeral=True)
        return
    accs = []
    for _ in range(amount):
        while True:
            uname = generate_roblox_username(length)
            if uname not in bot.accounts:
                break
        save_account(uname, "Generated")
        bot.accounts[uname] = {"note": "Generated"}
        accs.append(uname)
    await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(f"`{a}`" for a in accs), ephemeral=True)
    await bot.send_updated_account_message()

@bot.tree.command(name="show_accounts", description="📋 Danh sách tài khoản")
async def show_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("📭 Trống!", ephemeral=True)
        return
    items = []
    for acc, info in list(bot.accounts.items())[:25]:
        items.append(discord.SelectOption(label=acc, description=info.get("note", "")[:100]))
    select = discord.ui.Select(placeholder="Chọn tài khoản", options=items)
    async def callback(i: discord.Interaction):
        selected = select.values[0]
        note = bot.accounts[selected]["note"]
        await i.response.send_message(f"📌 `{selected}` | `{note}`", ephemeral=True)
    select.callback = callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("📦 Danh sách:", view=view, ephemeral=True)

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

# === Ready ===
@bot.event
async def on_ready():
    print(f"✅ Bot đã sẵn sàng: {bot.user}")

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
