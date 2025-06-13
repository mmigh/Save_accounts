import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, string, difflib, io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

TOKEN = os.environ.get("TOKEN")
SHEET_NAME = "RobloxAccounts"
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# ==== Helpers ====
def read_accounts():
    accs = {}
    for row in sheet.get_all_records():
        a = row.get("Account", "").strip()
        if not a: continue
        accs[a] = {
            "note": row.get("Note", "").strip(),
            "otp": row.get("otp", "").strip(),
            "email": row.get("email", "").strip()
        }
    return accs

def save_account(a, note="", otp="", email=""):
    sheet.append_row([a, note, otp, email, ""])

def delete_account(a):
    cell = sheet.find(a)
    if cell and cell.col == 1:
        sheet.delete_rows(cell.row)

def update_account_field(a, field, val):
    col_map = {"note": 2, "otp": 3, "email": 4}
    if field not in col_map: return False
    cell = sheet.find(a)
    if cell and cell.col == 1:
        sheet.update_cell(cell.row, col_map[field], val)
        return True
    return False

def generate_name(n=12):
    while True:
        s = (
            random.choice(string.ascii_uppercase) +
            random.choice(string.ascii_lowercase) +
            random.choice(string.digits) +
            "".join(random.choices(string.ascii_letters + string.digits, k=n-3))
        )
        return "".join(random.sample(s, len(s)))

async def send_log(bot, interaction, action):
    if not NOTIFY_CHANNEL_ID: return
    ch = bot.get_channel(NOTIFY_CHANNEL_ID)
    if ch:
        await ch.send(f"📝 `{interaction.user}` dùng lệnh `/{interaction.command.name}`\n📘 {action}")

# ==== Bot Class ====
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.accounts = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        await self.register_commands()
        await self.tree.sync()
        self.refresh_data.start()
        self.post_account_summary.start()
        print("✅ Bot đã sẵn sàng!")

    @tasks.loop(minutes=5)
    async def refresh_data(self):
        self.accounts = read_accounts()

    @tasks.loop(hours=10)
    async def post_account_summary(self):
        if not ACCOUNT_NOTI_CHANNEL: return
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch: return

        try:
            async for msg in ch.history(limit=50):
                if msg.author == self.user:
                    await msg.delete()
        except: pass

        lines = []
        for a, info in self.accounts.items():
            chk = "✅" if info.get("otp") else "❌"
            lines.append(f"{a} | {info.get('note','')} | {chk}")

        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 1900:
                await ch.send(chunk)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            await ch.send(chunk)

    async def register_commands(self):
        @self.tree.command(name="add", description="➕ Thêm tài khoản")
        @app_commands.describe(account="Tên", note="Ghi chú")
        async def add(interaction, account: str, note: str = ""):
            a = account.strip()
            if not a:
                return await interaction.response.send_message("⚠️ Nhập tên!", ephemeral=True)
            if a in self.accounts:
                return await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
            self.accounts[a] = {"note": note, "otp": "", "email": ""}
            save_account(a, note)
            await interaction.response.send_message(f"✅ Đã thêm `{a}`", ephemeral=True)
            await send_log(self, interaction, f"Thêm `{a}` với ghi chú: `{note}`")
            await self.post_account_summary()

        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên")
        async def remove(interaction, account: str):
            a = account.strip()
            if a not in self.accounts:
                return await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
            delete_account(a)
            del self.accounts[a]
            await interaction.response.send_message(f"🗑️ Đã xoá `{a}`", ephemeral=True)
            await send_log(self, interaction, f"Xoá `{a}`")
            await self.post_account_summary()

        @self.tree.command(name="edit", description="✏️ Sửa thông tin")
        @app_commands.describe(account="Tên", note="Note", otp="OTP", email="Email")
        async def edit(interaction, account: str, note: str = "", otp: str = "", email: str = ""):
            a = account.strip()
            if a not in self.accounts:
                return await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
            changes = []
            if note:
                self.accounts[a]["note"] = note
                update_account_field(a, "note", note)
                changes.append(f"note={note}")
            if otp:
                self.accounts[a]["otp"] = otp
                update_account_field(a, "otp", otp)
                changes.append(f"otp={otp}")
            if email:
                self.accounts[a]["email"] = email
                update_account_field(a, "email", email)
                changes.append(f"email={email}")
            if not changes:
                return await interaction.response.send_message("⚠️ Không có gì để sửa!", ephemeral=True)
            await interaction.response.send_message("✅ Đã cập nhật: " + ", ".join(changes), ephemeral=True)
            await send_log(self, interaction, f"Sửa `{a}`: " + "; ".join(changes))
            await self.post_account_summary()

        @self.tree.command(name="generate", description="⚙️ Tạo account")
        @app_commands.describe(amount="Số lượng", length="Độ dài")
        async def generate(interaction, amount: int = 1, length: int = 12):
            if not (1 <= amount <= 20):
                return await interaction.response.send_message("⚠️ 1–20!", ephemeral=True)
            result = []
            for _ in range(amount):
                name = generate_name(length)
                while name in self.accounts:
                    name = generate_name(length)
                self.accounts[name] = {"note": "generated", "otp": "", "email": ""}
                save_account(name, "generated")
                result.append(name)
            await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(result), ephemeral=True)
            await send_log(self, interaction, f"Tạo {amount} account")
            await self.post_account_summary()

        @self.tree.command(name="show", description="📋 Tìm kiếm tài khoản")
        @app_commands.describe(account="Tên tài khoản hoặc từ khoá")
        async def show(interaction, account: str):
            key = account.lower().strip()
            if not key:
                return await interaction.response.send_message("⚠️ Nhập từ khoá!", ephemeral=True)
            matches = [(a, info) for a, info in self.accounts.items() if key in a.lower()]
            if matches:
                if len(matches) == 1:
                    a, i = matches[0]
                    await interaction.response.send_message(
                        f"🧾 **{a}**\n📝 {i.get('note','')}\n🔑 OTP: {i.get('otp','')}\n📧 Email: {i.get('email','')}",
                        ephemeral=True
                    )
                else:
                    opts = [discord.SelectOption(label=a) for a, _ in matches[:25]]
                    select = discord.ui.Select(placeholder="Chọn", options=opts)
                    async def cb(i): 
                        sel = select.values[0]; info = self.accounts.get(sel, {})
                        await i.response.send_message(
                            f"🧾 **{sel}**\n📝 {info.get('note','')}\n🔑 OTP: {info.get('otp','')}\n📧 Email: {info.get('email','')}",
                            ephemeral=True
                        )
                    select.callback = cb
                    view = discord.ui.View(); view.add_item(select)
                    await interaction.response.send_message("🔍 Kết quả tìm thấy:", view=view, ephemeral=True)
                return
            # Gợi ý gần đúng
            suggestions = difflib.get_close_matches(key, list(self.accounts.keys()), n=5, cutoff=0.5)
            if suggestions:
                return await interaction.response.send_message(
                    f"❌ Không tìm thấy `{account}`. Gợi ý:\n" + "\n".join(f"• {s}" for s in suggestions),
                    ephemeral=True
                )
            await interaction.response.send_message("❌ Không tìm thấy và không có gợi ý.", ephemeral=True)

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot online: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
