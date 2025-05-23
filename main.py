from discord.ext import commands, tasks from discord import app_commands import discord import os import json import csv import io import gspread from oauth2client.service_account import ServiceAccountCredentials from keep_alive import keep_alive from selenium import webdriver from selenium.webdriver.chrome.options import Options from selenium.webdriver.common.by import By

TOKEN = os.environ.get("TOKEN") NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))  # Kênh thông báo

Thiết lập Google Sheets

SHEET_NAME = "RobloxAccounts" scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON") if not cred_json: raise ValueError("Thiếu biến môi trường GOOGLE_CREDENTIALS_JSON!") cred_dict = json.loads(cred_json) creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope) client = gspread.authorize(creds) sheet = client.open(SHEET_NAME).sheet1

def read_accounts(): accounts = {} records = sheet.get_all_records() for record in records: accounts[record['Account']] = {'note': record.get('Note', '')} return accounts

def save_account(account, note): sheet.append_row([account, note])

def delete_account(account): cell = sheet.find(account) if cell: sheet.delete_row(cell.row)

def update_note(account, new_note): cell = sheet.find(account) if cell: sheet.update_cell(cell.row, 2, new_note)

def reset_hwid(): chrome_options = Options() chrome_options.add_argument("--headless") chrome_options.add_argument("--no-sandbox") chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
try:
    driver.get("https://script.banana-hub.xyz/")
    driver.implicitly_wait(10)

    action_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Action')]")
    if not action_btns:
        return "❌ Không tìm thấy nút Action"
    action_btns[0].click()

    reset_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Reset Hwid')]")
    reset_btn.click()

    confirm_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Yes, reset it!')]")
    confirm_btn.click()

    return "✅ Đã reset HWID thành công!"
except Exception as e:
    return f"❌ Lỗi khi reset HWID: {str(e)}"
finally:
    driver.quit()

class MyBot(commands.Bot): def init(self): intents = discord.Intents.default() super().init(command_prefix=commands.when_mentioned, intents=intents) self.accounts = {}

async def setup_hook(self):
    self.accounts = read_accounts()
    self.refresh_accounts.start()
    await self.tree.sync()
    print("Slash commands đã được đồng bộ!")

@tasks.loop(minutes=3)
async def refresh_accounts(self):
    self.accounts = read_accounts()

bot = MyBot()

@bot.tree.command(name="add_account", description="➕ Thêm tài khoản Roblox mới") @app_commands.describe(account="Tên tài khoản Roblox", note="Ghi chú cho tài khoản (không bắt buộc)") async def add_account(interaction: discord.Interaction, account: str, note: str = ""): account = account.strip() if not account: await interaction.response.send_message("⚠️ Tên tài khoản không được để trống!", ephemeral=True) return if account in bot.accounts: await interaction.response.send_message(f"⚠️ Tài khoản {account} đã tồn tại!", ephemeral=True) return bot.accounts[account] = {"note": note} save_account(account, note) await interaction.response.send_message(f"✅ Đã thêm: {account} với ghi chú: {note}", ephemeral=True) if NOTIFY_CHANNEL_ID: channel = bot.get_channel(NOTIFY_CHANNEL_ID) if channel: await channel.send(f"🔔 Đã thêm tài khoản mới: {account}")

@bot.tree.command(name="reset_hwid", description="🔄 Reset HWID trên trang Banana Hub") async def reset_hwid_command(interaction: discord.Interaction): await interaction.response.defer(ephemeral=True, thinking=True) result = reset_hwid() await interaction.followup.send(result, ephemeral=True)

(Các lệnh khác vẫn giữ nguyên như trước)

@bot.event async def on_ready(): print(f"Bot đã đăng nhập với tên: {bot.user} (ID: {bot.user.id})")

if name == "main": 
keep_alive() 
bot.run(TOKEN)

