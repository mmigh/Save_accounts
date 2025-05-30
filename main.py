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
    sheet.append_row([account, note, ""])

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

# === Bot Class ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}
        self.logcals = {}
        self.update_embed_message = None

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

    @tasks.loop(hours=10)
    async def update_embed_loop(self):
        await self.send_or_update_embed()

    async def send_or_update_embed(self):
        if not NOTIFY_CHANNEL_ID:
            return
        channel = self.get_channel(NOTIFY_CHANNEL_ID)
        if not channel:
            return

        lines = [f"`acc` `{acc}` | `{info.get('note', '')}`" for acc, info in self.accounts.items()]
        content = "\n".join(lines[:50]) or "Không có tài khoản nào."
        embed = discord.Embed(
            title="📦 Danh sách tài khoản (Auto cập nhật)",
            description=content,
            color=discord.Color.green()
        )
        if self.update_embed_message:
            try:
                await self.update_embed_message.edit(embed=embed)
                return
            except:
                pass
        self.update_embed_message = await channel.send(embed=embed)

bot = MyBot()

# === Logcal Commands ===
@bot.tree.command(name="add_logcal", description="➕ Thêm logcal JSON")
@app_commands.describe(logcal="Chuỗi logcal cần thêm")
async def add_logcal(interaction: discord.Interaction, logcal: str):
    logcal = logcal.strip()
    if logcal in bot.logcals:
        await interaction.response.send_message("⚠️ Logcal đã tồn tại!", ephemeral=True)
        return
    bot.logcals[logcal] = {}
    save_logcal(logcal)
    await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

@bot.tree.command(name="add_file_logcal", description="📂 Nhập nhiều logcal từ file .txt")
@app_commands.describe(file="Tệp .txt, mỗi dòng 1 logcal JSON")
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
        f"✅ Đã thêm {added} logcal.\n⚠️ Bỏ qua {skipped} dòng trùng lặp.",
        ephemeral=True
    )

@bot.tree.command(name="count_logcal", description="🔢 Đếm logcal đang lưu")
async def count_logcal(interaction: discord.Interaction):
    await interaction.response.send_message(f"📊 Tổng cộng {len(bot.logcals)} logcal.", ephemeral=True)

@bot.tree.command(name="get_logcal", description="🎲 Lấy ngẫu nhiên 1 logcal")
async def get_logcal(interaction: discord.Interaction):
    if not bot.logcals:
        await interaction.response.send_message("📭 Không có logcal!", ephemeral=True)
        return
    logcal = random.choice(list(bot.logcals))
    delete_logcal(logcal)
    del bot.logcals[logcal]
    await interaction.response.send_message(f"🎯 Logcal:\n```json\n{logcal}```", ephemeral=True)

# === Account Commands ===
@bot.tree.command(name="add_account", description="➕ Thêm tài khoản")
@app_commands.describe(account="Tên tài khoản", note="Ghi chú")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    account = account.strip()
    if account in bot.accounts:
        await interaction.response.send_message("⚠️ Tài khoản đã tồn tại!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message("✅ Đã thêm tài khoản!", ephemeral=True)
    await bot.send_or_update_embed()

@bot.tree.command(name="edit_note", description="✏️ Sửa ghi chú")
@app_commands.describe(account="Tên tài khoản", note="Ghi chú mới")
async def edit_note(interaction: discord.Interaction, account: str, note: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tìm thấy tài khoản!", ephemeral=True)
        return
    bot.accounts[account]["note"] = note
    update_note(account, note)
    await interaction.response.send_message(f"✅ Ghi chú mới: `{note}`", ephemeral=True)
    await bot.send_or_update_embed()

@bot.tree.command(name="remove_account", description="❌ Xóa tài khoản")
@app_commands.describe(account="Tên tài khoản")
async def remove_account(interaction: discord.Interaction, account: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Tài khoản không tồn tại.", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message("✅ Đã xóa tài khoản.", ephemeral=True)
    await bot.send_or_update_embed()

@bot.tree.command(name="show_accounts", description="📋 Xem danh sách tài khoản")
async def show_accounts(interaction: discord.Interaction):
    options = []
    for acc in list(bot.accounts.keys())[:25]:
        note = bot.accounts[acc].get("note", "")
        options.append(discord.SelectOption(
            label=acc[:100],
            description=(note[:97] + "...") if len(note) > 100 else note
        ))

    select = discord.ui.Select(placeholder="Chọn tài khoản", options=options)

    async def callback(i: discord.Interaction):
        selected = select.values[0]
        note = bot.accounts[selected].get("note", "")
        await i.response.send_message(f"📌 `{selected}` | `{note}`", ephemeral=True)

    select.callback = callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("🧾 Danh sách tài khoản:", view=view, ephemeral=True)

@bot.tree.command(name="generate_account", description="⚙️ Tạo tài khoản ngẫu nhiên")
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
    await interaction.response.send_message(
        f"✅ Đã tạo:\n" + "\n".join(f"`acc` `{g}`" for g in generated),
        ephemeral=True
    )
    await bot.send_or_update_embed()

@bot.tree.command(name="backup_accounts", description="📥 Sao lưu tài khoản ra file .txt")
async def backup_accounts(interaction: discord.Interaction):
    lines = [f"{acc} | {info.get('note', '')}" for acc, info in bot.accounts.items()]
    content = "\n".join(lines)
    file = discord.File(io.BytesIO(content.encode()), filename="accounts_backup.txt")
    await interaction.response.send_message("🗂️ Sao lưu:", file=file, ephemeral=True)

@bot.tree.command(name="restore_accounts", description="♻️ Khôi phục từ file .txt")
@app_commands.describe(file="File sao lưu")
async def restore_accounts(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ Gửi file .txt!", ephemeral=True)
        return
    content = await file.read()
    lines = [line.strip() for line in content.decode(errors="ignore").splitlines() if "|" in line]
    if not lines:
        await interaction.response.send_message("⚠️ Không hợp lệ!", ephemeral=True)
        return
    sheet.clear()
    sheet.append_row(["Account", "Note", "Logcal_ugphone"])
    bot.accounts.clear()
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and parts[0]:
            sheet.append_row([parts[0], parts[1], ""])
            bot.accounts[parts[0]] = {"note": parts[1]}
    await interaction.response.send_message(f"✅ Khôi phục {len(lines)} tài khoản!", ephemeral=True)
    await bot.send_or_update_embed()

# === Bot Ready ===
@bot.event
async def on_ready():
    print(f"🤖 Bot sẵn sàng: {bot.user} (ID: {bot.user.id})")

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
