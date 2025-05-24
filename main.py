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
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("Thiếu biến môi trường GOOGLE_CREDENTIALS_JSON!")
cred_dict = json.loads(cred_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

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

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.accounts = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        self.refresh_accounts.start()
        await self.tree.sync()
        print("Slash commands đã được đồng bộ!")

    @tasks.loop(minutes=3)
    async def refresh_accounts(self):
        self.accounts = read_accounts()

bot = MyBot()

@bot.tree.command(name="add_account", description="➕ Thêm tài khoản Roblox mới")
@app_commands.describe(account="Tên tài khoản Roblox", note="Ghi chú cho tài khoản (không bắt buộc)")
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
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            await channel.send(f"🔔 Đã thêm tài khoản mới: {account}")

@bot.tree.command(name="show_accounts", description="📋 Hiển thị danh sách tài khoản đã lưu")
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

    select = discord.ui.Select(placeholder="🔍 Chọn tài khoản để xem chi tiết", options=options)

    async def select_callback(interaction_select: discord.Interaction):
        selected = select.values[0]
        note = bot.accounts[selected].get("note", "Không có ghi chú")
        await interaction_select.response.send_message(f"🧾 **Tài khoản:** `{selected}`\n📝 **Ghi chú:** {note}", ephemeral=True)

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("📚 Danh sách tài khoản:", view=view, ephemeral=True)

@bot.tree.command(name="remove_account", description="❌ Xóa tài khoản khỏi danh sách")
@app_commands.describe(account="Tên tài khoản muốn xóa")
async def remove_account(interaction: discord.Interaction, account: str):
    account = account.strip()
    if account not in bot.accounts:
        await interaction.response.send_message(f"⚠️ Tài khoản {account} không tồn tại.", ephemeral=True)
        return
    delete_account(account)
    del bot.accounts[account]
    await interaction.response.send_message(f"✅ Đã xóa tài khoản {account} khỏi danh sách.", ephemeral=True)
    if NOTIFY_CHANNEL_ID:
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            await channel.send(f"🗑️ Tài khoản {account} đã bị xóa!")

@bot.tree.command(name="edit_note", description="✏️ Sửa ghi chú tài khoản")
@app_commands.describe(account="Tài khoản cần sửa", note="Ghi chú mới")
async def edit_note(interaction: discord.Interaction, account: str, note: str):
    account = account.strip()
    if account not in bot.accounts:
        await interaction.response.send_message(f"⚠️ Không tìm thấy tài khoản {account}", ephemeral=True)
        return
    bot.accounts[account]["note"] = note
    update_note(account, note)
    await interaction.response.send_message(f"✅ Đã cập nhật ghi chú cho {account} thành: {note}", ephemeral=True)

@bot.tree.command(name="count_accounts", description="🔢 Đếm số lượng tài khoản")
async def count_accounts(interaction: discord.Interaction):
    count = len(bot.accounts)
    await interaction.response.send_message(f"📊 Có tổng cộng {count} tài khoản được lưu.", ephemeral=True)

@bot.tree.command(name="export_accounts", description="📤 Xuất danh sách tài khoản")
async def export_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("⚠️ Không có tài khoản để xuất.", ephemeral=True)
        return

    json_data = json.dumps(bot.accounts, indent=2, ensure_ascii=False)
    json_file = discord.File(fp=io.BytesIO(json_data.encode()), filename="accounts.json")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Account", "Note"])
    for acc, info in bot.accounts.items():
        writer.writerow([acc, info.get("note", "")])
    csv_file = discord.File(fp=io.BytesIO(output.getvalue().encode()), filename="accounts.csv")

    await interaction.response.send_message("📎 Đây là danh sách tài khoản:", files=[json_file, csv_file], ephemeral=True)

@bot.tree.command(name="backup_accounts", description="📥 Sao lưu tài khoản ra file .txt")
async def backup_accounts(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("⚠️ Không có tài khoản để sao lưu.", ephemeral=True)
        return

    lines = [f"{acc} | {info.get('note', '')}" for acc, info in bot.accounts.items()]
    content = "\n".join(lines)
    file = discord.File(fp=io.BytesIO(content.encode()), filename="accounts_backup.txt")
    await interaction.response.send_message("🗂️ Đây là bản sao lưu:", file=file, ephemeral=True)

@bot.tree.command(name="restore_accounts", description="♻️ Khôi phục dữ liệu từ file .txt")
@app_commands.describe(file="Tệp .txt sao lưu")
async def restore_accounts(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("⚠️ Vui lòng gửi file .txt hợp lệ!", ephemeral=True)
        return

    lines = [f"{acc} | {info.get('note', '')}" for acc, info in bot.accounts.items()]
    backup_content = "\n".join(lines)
    backup_file = discord.File(fp=io.BytesIO(backup_content.encode()), filename="accounts_backup_before_restore.txt")
    await interaction.response.send_message("🛡️ Đây là bản sao lưu hiện tại trước khi khôi phục dữ liệu:", file=backup_file, ephemeral=True)

    content = await file.read()
    text = content.decode(errors="ignore")
    lines = [line.strip() for line in text.splitlines() if "|" in line]

    if not lines:
        await interaction.followup.send("⚠️ File không chứa dữ liệu hợp lệ!", ephemeral=True)
        return

    sheet.clear()
    sheet.append_row(["Account", "Note"])
    bot.accounts.clear()

    for line in lines:
        account, note = map(str.strip, line.split("|", 1))
        if account:
            sheet.append_row([account, note])
            bot.accounts[account] = {"note": note}

    await interaction.followup.send(f"✅ Đã khôi phục **{len(lines)}** tài khoản từ file!", ephemeral=True)

@bot.tree.command(name="generate_account", description="⚙️ Tạo tài khoản Roblox ngẫu nhiên và lưu lại")
@app_commands.describe(amount="Số lượng tài khoản muốn tạo (1–20)")
async def generate_account(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 20:
        await interaction.response.send_message("⚠️ Số lượng phải từ 1 đến 20.", ephemeral=True)
        return

    generated = []
    for _ in range(amount):
        while True:
            username = generate_roblox_username()
            if username not in bot.accounts:
                break
        bot.accounts[username] = {"note": "Generated"}
        save_account(username, "Generated")
        generated.append(username)

    message = "\n".join(generated)
    await interaction.response.send_message(f"✅ Đã tạo {amount} tài khoản:\n```{message}```", ephemeral=True)

    if NOTIFY_CHANNEL_ID:
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            await channel.send(f"⚙️ Đã tạo {amount} tài khoản mới:\n```{message}```")

@remove_account.autocomplete("account")
@edit_note.autocomplete("account")
@add_account.autocomplete("account")
async def account_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower()
    return [
        app_commands.Choice(name=acc, value=acc)
        for acc in bot.accounts.keys()
        if current_lower in acc.lower()
    ][:25]
    
def read_accounts():
    accounts = {}
    records = sheet.get_all_records()
    for record in records:
        accounts[record['Account']] = {
            'note': record.get('Note', ''),
            'status': record.get('Status', 'offline').lower()
        }
    return accounts

def save_account(account, note, status="offline"):
    sheet.append_row([account, note, status])

def update_note(account, new_note):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 2, new_note)

def update_status(account, new_status):
    cell = sheet.find(account)
    if cell:
        sheet.update_cell(cell.row, 3, new_status)

# Gửi bảng embed trạng thái
@bot.tree.command(name="status_board", description="📊 Gửi bảng trạng thái tài khoản lên kênh")
async def status_board(interaction: discord.Interaction):
    if not bot.accounts:
        await interaction.response.send_message("⚠️ Không có tài khoản nào để hiển thị.", ephemeral=True)
        return

    embed = discord.Embed(title="📋 Trạng thái tài khoản Roblox", color=discord.Color.blurple())
    status_map = {"farming": "🟢 Đang cày", "banned": "🔴 Banned", "offline": "⚪ Offline"}

    for acc, info in bot.accounts.items():
        status = info.get("status", "offline")
        display = status_map.get(status.lower(), "⚪ Offline")
        embed.add_field(name=acc, value=f"Trạng thái: {display}", inline=False)

    # Dropdown chọn tài khoản và chỉnh trạng thái
    options = [discord.SelectOption(label=acc, value=acc) for acc in list(bot.accounts.keys())[:25]]
    select = discord.ui.Select(placeholder="Chọn tài khoản để cập nhật trạng thái", options=options)

    class StatusView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.selected_account = None

        @discord.ui.select(placeholder="Chọn trạng thái mới", options=[
            discord.SelectOption(label="🟢 Đang cày", value="farming"),
            discord.SelectOption(label="🔴 Banned", value="banned"),
            discord.SelectOption(label="⚪ Offline", value="offline")
        ])
        async def status_select(self, interaction2: discord.Interaction, select_status: discord.ui.Select):
            if not self.selected_account:
                await interaction2.response.send_message("⚠️ Vui lòng chọn tài khoản trước!", ephemeral=True)
                return
            new_status = select_status.values[0]
            bot.accounts[self.selected_account]["status"] = new_status
            update_status(self.selected_account, new_status)
            await interaction2.response.send_message(f"✅ Đã cập nhật {self.selected_account} thành {new_status}", ephemeral=True)

        @discord.ui.select(placeholder="Chọn tài khoản để cập nhật trạng thái", options=options)
        async def account_select(self, interaction3: discord.Interaction, select_account: discord.ui.Select):
            self.selected_account = select_account.values[0]
            await interaction3.response.send_message(f"🔄 Đã chọn **{self.selected_account}**. Giờ hãy chọn trạng thái.", ephemeral=True)

    view = StatusView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập với tên: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
