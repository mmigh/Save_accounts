import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import random
import string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
from keep_alive import keep_alive  # nếu không dùng Flask thì bạn có thể xóa dòng này

# === CONFIG ===
TOKEN = os.environ.get("TOKEN")
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))
SHEET_NAME = "RobloxAccounts"

# === GOOGLE SHEETS ===
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

# === HÀM XỬ LÝ ===
def read_accounts():
    accounts = {}
    records = sheet.get_all_records()
    for record in records:
        account = record.get("Account", "").strip()
        if account:
            accounts[account] = {
                "note": record.get("Note", "").strip(),
                "otp": record.get("otp", "").strip(),
                "email": record.get("email", "").strip()
            }
    return accounts

def save_account(account, note="", otp="", email=""):
    row = [account, note, otp, email, ""]
    sheet.append_row(row)

def delete_account(account):
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.delete_rows(cell.row)

def update_account_field(account, field_name, new_value):
    col_map = {"note": 2, "otp": 3, "email": 4}
    if field_name not in col_map:
        return False
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.update_cell(cell.row, col_map[field_name], new_value)
        return True
    return False

def read_logcals():
    logcals = {}
    col_values = sheet.col_values(5)[1:]
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
    try:
        sheet.append_row(["", "", "", "", safe_json], value_input_option="RAW")
    except TypeError:
        next_row = len(sheet.col_values(1)) + 1
        sheet.update_cell(next_row, 5, safe_json)

def delete_logcal(logcal_json):
    cell = sheet.find(logcal_json)
    if cell and cell.col == 5:
        sheet.delete_rows(cell.row)

def generate_roblox_username(length=12):
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    remain = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    result = list(upper + lower + digit + remain)
    random.shuffle(result)
    return ''.join(result)

async def send_log(interaction: discord.Interaction, action: str):
    channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID)
    if channel:
        await channel.send(f"📝 {interaction.user} đã dùng lệnh: /{interaction.command.name}\n📘 {action}")

# === BOT CLASS ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.accounts = {}
        self.logcals = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        self.logcals = read_logcals()
        await self.register_commands()
        print("✅ Slash commands đã sẵn sàng!")

    async def register_commands(self):
        @self.tree.command(name="save", description="➕ Thêm logcal JSON")
        @app_commands.describe(logcal="Dữ liệu logcal")
        async def add_logcal(interaction: discord.Interaction, logcal: str):
            logcal = logcal.strip()
            if logcal in self.logcals:
                await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
                return
            self.logcals[logcal] = {}
            save_logcal(logcal)
            await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

        @self.tree.command(name="get", description="🎲 Rút 1 logcal ngẫu nhiên")
        async def get_logcal(interaction: discord.Interaction):
            if not self.logcals:
                await interaction.response.send_message("📭 Hết logcal!", ephemeral=True)
                return
            choice = random.choice(list(self.logcals))
            delete_logcal(choice)
            del self.logcals[choice]
            await interaction.response.send_message(f"🎯 Logcal:\n```json\n{choice}\n```", ephemeral=True)

        @self.tree.command(name="add", description="➕ Thêm tài khoản")
        @app_commands.describe(account="Tên tài khoản", note="Ghi chú (tùy chọn)")
        async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
            account = account.strip()
            if account in self.accounts:
                await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
                return
            self.accounts[account] = {"note": note}
            save_account(account, note)
            await interaction.response.send_message(f"✅ Đã thêm `{account}`", ephemeral=True)
            await send_log(interaction, f"Thêm account: {account}")

        @self.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài tên")
        async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
            if not (1 <= amount <= 20):
                await interaction.response.send_message("⚠️ Giới hạn 1–20.", ephemeral=True)
                return
            result = []
            for _ in range(amount):
                while True:
                    name = generate_roblox_username(length)
                    if name not in self.accounts:
                        break
                self.accounts[name] = {"note": "Generated"}
                save_account(name, "Generated")
                result.append(name)
            await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(result), ephemeral=True)

        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên tài khoản")
        async def remove_account(interaction: discord.Interaction, account: str):
            if account not in self.accounts:
                await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
                return
            delete_account(account)
            del self.accounts[account]
            await interaction.response.send_message(f"🗑️ Đã xoá `{account}`", ephemeral=True)

        @self.tree.command(name="count_all", description="🔢 Đếm số lượng")
        async def count_all(interaction: discord.Interaction):
            await interaction.response.send_message(
                f"📦 Tài khoản: {len(self.accounts)}\n🗂️ Logcal: {len(self.logcals)}",
                ephemeral=True
            )

        await self.tree.sync()

# === KHỞI CHẠY ===
bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot sẵn sàng: {bot.user} (ID: {bot.user.id})")

if __name__ == '__main__':
    keep_alive()  # Có thể bỏ nếu không dùng Render hoặc Replit
    bot.run(TOKEN)
