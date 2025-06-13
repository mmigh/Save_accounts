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
from keep_alive import keep_alive  # Xoá nếu không dùng

TOKEN = os.environ.get("TOKEN")
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

# === Account Functions ===
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
    sheet.append_row([account, note, otp, email, ""])

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

def generate_roblox_username(length=12):
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    remain = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    result = list(upper + lower + digit + remain)
    random.shuffle(result)
    return ''.join(result)

# === Bot Setup ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.accounts = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        await self.register_commands()
        await self.tree.sync()
        print("✅ Bot đã sẵn sàng!")

    async def register_commands(self):
        @self.tree.command(name="add", description="➕ Thêm tài khoản")
        @app_commands.describe(account="Tên tài khoản", note="Ghi chú (tùy chọn)")
        async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
            if account in self.accounts:
                await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
                return
            self.accounts[account] = {"note": note}
            save_account(account, note)
            await interaction.response.send_message(f"✅ Đã thêm `{account}`", ephemeral=True)

        @self.tree.command(name="edit", description="✏️ Sửa tài khoản")
        @app_commands.describe(account="Tên tài khoản", note="Ghi chú", otp="OTP", email="Email")
        async def edit_account(interaction: discord.Interaction, account: str, note: str = "", otp: str = "", email: str = ""):
            if account not in self.accounts:
                await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
                return
            updates = []
            if note:
                self.accounts[account]["note"] = note
                update_account_field(account, "note", note)
                updates.append(f"📝 Note: {note}")
            if otp:
                self.accounts[account]["otp"] = otp
                update_account_field(account, "otp", otp)
                updates.append(f"🔑 OTP: {otp}")
            if email:
                self.accounts[account]["email"] = email
                update_account_field(account, "email", email)
                updates.append(f"📧 Email: {email}")
            if not updates:
                await interaction.response.send_message("⚠️ Không có thay đổi!", ephemeral=True)
                return
            await interaction.response.send_message("✅ Đã cập nhật:\n" + "\n".join(updates), ephemeral=True)

        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên tài khoản")
        async def remove_account(interaction: discord.Interaction, account: str):
            if account not in self.accounts:
                await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
                return
            delete_account(account)
            del self.accounts[account]
            await interaction.response.send_message(f"🗑️ Đã xoá `{account}`", ephemeral=True)

        @self.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài tên")
        async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
            if not (1 <= amount <= 20):
                await interaction.response.send_message("⚠️ Giới hạn 1–20.", ephemeral=True)
                return
            generated = []
            for _ in range(amount):
                while True:
                    uname = generate_roblox_username(length)
                    if uname not in self.accounts:
                        break
                self.accounts[uname] = {"note": "Generated"}
                save_account(uname, "Generated")
                generated.append(uname)
            await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(generated), ephemeral=True)

        @self.tree.command(name="count", description="🔢 Đếm số tài khoản")
        async def count_accounts(interaction: discord.Interaction):
            await interaction.response.send_message(f"📦 Tổng tài khoản: {len(self.accounts)}", ephemeral=True)

        @self.tree.command(name="backup", description="💾 Sao lưu toàn bộ tài khoản")
        async def backup(interaction: discord.Interaction):
            content = "\n".join(f"{acc} | {info['note']}" for acc, info in self.accounts.items())
            file = discord.File(io.BytesIO(content.encode()), filename="accounts_backup.txt")
            await interaction.response.send_message("📤 Dữ liệu sao lưu:", file=file, ephemeral=True)

        @self.tree.command(name="restore", description="♻️ Khôi phục từ file .txt")
        @app_commands.describe(file="Tệp .txt (1 dòng: account | note)")
        async def restore(interaction: discord.Interaction, file: discord.Attachment):
            if not file.filename.endswith(".txt"):
                await interaction.response.send_message("⚠️ Chỉ hỗ trợ .txt", ephemeral=True)
                return
            text = (await file.read()).decode(errors="ignore")
            lines = [l.strip() for l in text.splitlines() if "|" in l]
            if not lines:
                await interaction.response.send_message("⚠️ File không hợp lệ!", ephemeral=True)
                return
            sheet.clear()
            sheet.append_row(["Account", "Note", "otp", "email", ""])
            self.accounts.clear()
            for line in lines:
                acc, note = [s.strip() for s in line.split("|", 1)]
                save_account(acc, note)
                self.accounts[acc] = {"note": note}
            await interaction.response.send_message(f"✅ Đã khôi phục {len(lines)} tài khoản!", ephemeral=True)

        @self.tree.command(name="show", description="📋 Hiển thị thông tin tài khoản")
        async def show(interaction: discord.Interaction):
            if not self.accounts:
                await interaction.response.send_message("📭 Không có tài khoản nào!", ephemeral=True)
                return
            options = [discord.SelectOption(label=acc) for acc in list(self.accounts.keys())[:25]]
            select = discord.ui.Select(placeholder="Chọn tài khoản", options=options)

            async def callback(i: discord.Interaction):
                acc = select.values[0]
                info = self.accounts.get(acc, {})
                await i.response.send_message(
                    f"🧾 Tài khoản: `{acc}`\n"
                    f"📝 Ghi chú: `{info.get('note', '')}`\n"
                    f"🔑 OTP: `{info.get('otp', '')}`\n"
                    f"📧 Email: `{info.get('email', '')}`",
                    ephemeral=True
                )

            select.callback = callback
            view = discord.ui.View()
            view.add_item(select)
            await interaction.response.send_message("📚 Chọn tài khoản để xem:", view=view, ephemeral=True)

        @self.tree.command(name="backup_and_clear_logcal", description="💣 Sao lưu và xoá toàn bộ logcal")
        async def backup_and_clear_logcal(interaction: discord.Interaction):
            values = sheet.col_values(5)[1:]  # Cột E (bỏ header)
            if not values:
               await interaction.response.send_message("📭 Không có logcal nào để xoá!", ephemeral=True)
               return

            content = "\n".join([v for v in values if v.strip()])
            file = discord.File(io.BytesIO(content.encode()), filename="logcal_backup.txt")

    # Ghi rỗng vào từng ô logcal (cột 5)
             for i in range(2, len(values) + 2):  # từ hàng 2 trở đi
                try:
            sheet.update_cell(i, 5, "")
                except:
                pass
    
             await interaction.response.send_message("✅ Đã backup và xoá sạch logcal (chỉ cột E)!", file=file, ephemeral=True)

# === Run Bot ===
bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot đã khởi động: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
