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
from keep_alive import keep_alive  # Nếu không dùng thì có thể xóa dòng này
from commands import setup_commands

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

# === Account Handling ===

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

def update_note(account, new_note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, new_note)

def update_account_field(account, field_name, new_value):
    col_map = {"note": 2, "otp": 3, "email": 4}
    if field_name not in col_map:
        return False
    cell = sheet.find(account)
    if cell and cell.col == 1:
        sheet.update_cell(cell.row, col_map[field_name], new_value)
        return True
    return False

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
    await channel.send(f"📝 {user} đã dùng lệnh: /{interaction.command.name}\n📘 {action}")

# === Bot Class ===

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
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
        await setup_commands(bot)
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

        try:
            async for m in channel.history(limit=20):
                if m.author == self.user:
                    try:
                        await m.delete()
                    except:
                        pass
        except:
            pass

        lines = [f"`{acc}` | `{info.get('note', '')}`" for acc, info in self.accounts.items()]
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

        for chunk in chunks:
            await channel.send(chunk)

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot sẵn sàng: {bot.user} (ID: {bot.user.id})")

# === Chạy bot ===

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)