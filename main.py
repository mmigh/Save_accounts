from discord.ext import commands
from discord import app_commands
import discord
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

TOKEN = os.environ.get("TOKEN")

# Thiết lập Google Sheets
SHEET_NAME = "RobloxAccounts"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("Thiếu biến môi trường GOOGLE_CREDENTIALS_JSON!")
cred_dict = json.loads(cred_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1  # Sheet đầu tiên

# Các hàm xử lý Google Sheets
def read_accounts():
    accounts = {}
    records = sheet.get_all_records()
    for record in records:
        accounts[record['Account']] = {'note': record.get('Note', '')}
    return accounts

def save_account(account, note):
    sheet.append_row([account, note])

def delete_account(account):
    cell = sheet.find(account)
    if cell:
        sheet.delete_row(cell.row)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        await self.tree.sync()
        print("Slash commands đã được đồng bộ!")

bot = MyBot()

@bot.tree.command(name="add_account", description="Thêm tài khoản Roblox mới")
@app_commands.describe(account="Tên tài khoản Roblox", note="Ghi chú cho tài khoản (không bắt buộc)")
async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
    account = account.strip()
    if not account:
        await interaction.response.send_message("Tên tài khoản không được để trống!", ephemeral=True)
        return
    if account in bot.accounts:
        await interaction.response.send_message(f"Tài khoản `{account}` đã tồn tại rồi!", ephemeral=True)
        return
    bot.accounts[account] = {"note": note}
    save_account(account, note)
    await interaction.response.send_message(f"Đã thêm tài khoản: `{account}` với ghi chú: `{note}`", ephemeral=True)

@bot.tree.command(name="show_accounts", description="Hiển thị danh sách tài khoản đã lưu")
async def show_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("Chưa có tài khoản nào được lưu.", ephemeral=True)
        return
    options = []
    for name in list(bot.accounts.keys())[:25]:
        note = bot.accounts[name].get("note", "")
        label = name if len(name) <= 100 else name[:97] + "..."
        description = note if note and len(note) <= 100 else (note[:97] + "..." if note else "Không có ghi chú")
        options.append(discord.SelectOption(label=label, description=description))
    select = discord.ui.Select(placeholder="Chọn tài khoản để xem chi tiết", options=options)

    async def select_callback(interaction_select: discord.Interaction):
        selected = select.values[0]
        note = bot.accounts[selected].get("note", "Không có ghi chú")
        await interaction_select.response.send_message(
            f"**Tài khoản:** `{selected}`\n**Ghi chú:** {note}", ephemeral=True
        )

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("Danh sách tài khoản:", view=view, ephemeral=True)

@bot.tree.command(name="remove_account", description="Xóa tài khoản khỏi danh sách")
@app_commands.describe(account="Tên tài khoản muốn xóa")
async def remove_account(interaction: discord.Interaction, account: str):
    account = account.strip()
    if account not in bot.accounts:
        await interaction.response.send_message(f"Tài khoản `{account}` không tồn tại.", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message(f"Đã xóa tài khoản `{account}` khỏi danh sách.", ephemeral=True)

@remove_account.autocomplete("account")
@add_account.autocomplete("account")
async def account_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower()
    return [
        app_commands.Choice(name=acc, value=acc)
        for acc in bot.accounts.keys()
        if current_lower in acc.lower()
    ][:25]

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập với tên: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
