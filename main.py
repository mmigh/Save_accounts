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

# Google Sheets setup
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

# ========== Hàm xử lý Logcal_ugphone (cột C) ==========
def read_logcals():
    logcals = {}
    col_values = sheet.col_values(3)[1:]  # Bỏ header
    for value in col_values:
        if value:
            logcals[value] = {}
    return logcals

def save_logcal(logcal_json):
    sheet.append_row(["", "", logcal_json])

def delete_logcal(logcal_json):
    cell = sheet.find(logcal_json)
    if cell and cell.col == 3:
        sheet.delete_row(cell.row)

# ========== Hàm xử lý Account ==========
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
        sheet.delete_row(cell.row)

def update_note(account, new_note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, new_note)

def generate_roblox_username(length=12):
    if length < 3 or length > 20:
        raise ValueError("Username length must be between 3 and 20 characters.")
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    remaining = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    result = list(upper + lower + digit + remaining)
    random.shuffle(result)
    return ''.join(result)

# ========== Khởi tạo bot ==========
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
        print("Slash commands đã được đồng bộ!")

    @tasks.loop(minutes=3)
    async def refresh_data(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()

bot = MyBot()

# ========== Slash Command cho logcal_ugphone ==========
@bot.tree.command(name="add_logcal", description="➕ Thêm một dòng JSON Logcal_ugphone")
@app_commands.describe(logcal="Dòng JSON cần thêm")
async def add_logcal(interaction: discord.Interaction, logcal: str):
    logcal = logcal.strip()
    if logcal in bot.logcals:
        await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
        return
    bot.logcals[logcal] = {}
    save_logcal(logcal)
    await interaction.response.send_message("✅ Đã thêm logcal_ugphone", ephemeral=True)

@bot.tree.command(name="add_file_logcal", description="📂 Thêm nhiều dòng JSON từ file .txt")
@app_commands.describe(file="File .txt chứa từng dòng là JSON")
async def add_file_logcal(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ File phải là .txt", ephemeral=True)
        return

    content = await file.read()
    lines = [line.strip() for line in content.decode(errors="ignore").splitlines() if line.strip()]
    count = 0
    for line in lines:
        if line not in bot.logcals:
            bot.logcals[line] = {}
            save_logcal(line)
            count += 1
    await interaction.response.send_message(f"✅ Đã thêm {count} dòng.", ephemeral=True)

@bot.tree.command(name="get_logcal", description="🎲 Lấy ngẫu nhiên và xóa 1 dòng Logcal_ugphone")
async def get_logcal(interaction: discord.Interaction):
    if not bot.logcals:
        await interaction.response.send_message("📭 Danh sách trống!", ephemeral=True)
        return
    logcal = random.choice(list(bot.logcals.keys()))
    delete_logcal(logcal)
    del bot.logcals[logcal]
    await interaction.response.send_message(f"🎯 `{logcal}`", ephemeral=True)

    if NOTIFY_CHANNEL_ID:
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            await channel.send(f"🎯 Đã rút một logcal:\n```json\n{logcal}\n```")

# ========== Slash Command cho account ==========
@bot.tree.command(name="add_account", description="➕ Thêm tài khoản Roblox")
@app_commands.describe(account="Tên tài khoản", note="Ghi chú")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    account = account.strip()
    if not account:
        await interaction.response.send_message("⚠️ Tên không được để trống!", ephemeral=True)
        return
    if account in bot.accounts:
        await interaction.response.send_message("⚠️ Tài khoản đã tồn tại!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message(f"✅ Đã thêm `{account}`", ephemeral=True)

@bot.tree.command(name="remove_account", description="❌ Xóa tài khoản Roblox")
@app_commands.describe(account="Tên tài khoản cần xóa")
async def remove_account(interaction: discord.Interaction, account: str):
    if account not in bot.accounts:
        await interaction.response.send_message("⚠️ Không tồn tại!", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message(f"✅ Đã xóa `{account}`", ephemeral=True)

@bot.tree.command(name="get_account_count", description="🔢 Đếm số tài khoản Roblox")
async def get_account_count(interaction: discord.Interaction):
    await interaction.response.send_message(f"📊 Tổng cộng: {len(bot.accounts)} tài khoản", ephemeral=True)

# ========== Ready ==========
@bot.event
async def on_ready():
    print(f"✅ Bot đã đăng nhập: {bot.user} (ID: {bot.user.id})")

keep_alive()
bot.run(TOKEN)
