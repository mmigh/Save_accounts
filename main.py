import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, string, difflib, io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

# === ENV ===
TOKEN = os.environ.get("TOKEN")
SHEET_NAME = "RobloxAccounts"
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))

# === Google Sheet setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# === Helper ===
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
    s = random.choice(string.ascii_uppercase) + random.choice(string.ascii_lowercase) + random.choice(string.digits)
    s += ''.join(random.choices(string.ascii_letters + string.digits, k=n-3))
    return ''.join(random.sample(s, len(s)))

async def send_log(bot, interaction, action):
    if NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(f"📝 `{interaction.user}` dùng lệnh `/{interaction.command.name}`\n📘 {action}")

# === Bot class ===
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
        if not ACCOUNT_NOTI_CHANNEL:
            return
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch:
            return

        # Xoá tin nhắn cũ
        try:
            async for msg in ch.history(limit=50):
                if msg.author == self.user:
                    await msg.delete()
        except: pass

        # Soạn nội dung mới
        lines = []
        for acc, info in self.accounts.items():
            otp = info.get("otp", "")
            chk = "✅" if otp else "❌"
            lines.append(f"`{acc}` | {info.get('note','')} | {chk}")

        # Gửi từng chunk
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
            await interaction.response.defer(ephemeral=True)
            a = account.strip()
            if not a:
                return await interaction.followup.send("⚠️ Nhập tên!")
            if a in self.accounts:
                return await interaction.followup.send("⚠️ Đã tồn tại!")
            self.accounts[a] = {"note": note, "otp": "", "email": ""}
            save_account(a, note)
            await interaction.followup.send(f"✅ Đã thêm `{a}`")
            await send_log(self, interaction, f"Thêm `{a}` | `{note}`")
            await self.post_account_summary()

        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên")
        async def remove(interaction, account: str):
            await interaction.response.defer(ephemeral=True)
            a = account.strip()
            if a not in self.accounts:
                return await interaction.followup.send("⚠️ Không tồn tại!")
            delete_account(a)
            del self.accounts[a]
            await interaction.followup.send(f"🗑️ Đã xoá `{a}`")
            await send_log(self, interaction, f"Xoá `{a}`")
            await self.post_account_summary()

        @self.tree.command(name="edit", description="✏️ Sửa tài khoản")
        @app_commands.describe(account="Tên", note="Note", otp="OTP", email="Email")
        async def edit(interaction, account: str, note: str = "", otp: str = "", email: str = ""):
            await interaction.response.defer(ephemeral=True)
            a = account.strip()
            if a not in self.accounts:
                return await interaction.followup.send("⚠️ Không tồn tại!")
            updates = []
            if note:
                self.accounts[a]["note"] = note
                update_account_field(a, "note", note)
                updates.append(f"note=`{note}`")
            if otp:
                self.accounts[a]["otp"] = otp
                update_account_field(a, "otp", otp)
                updates.append(f"otp=`{otp}`")
            if email:
                self.accounts[a]["email"] = email
                update_account_field(a, "email", email)
                updates.append(f"email=`{email}`")
            if not updates:
                return await interaction.followup.send("⚠️ Không có gì để sửa!")
            await interaction.followup.send("✅ Đã sửa: " + ", ".join(updates))
            await send_log(self, interaction, f"Sửa `{a}`: " + ", ".join(updates))
            await self.post_account_summary()

        @self.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài")
        async def generate(interaction, amount: int = 1, length: int = 12):
            await interaction.response.defer(ephemeral=True)
            if not (1 <= amount <= 20):
                return await interaction.followup.send("⚠️ Giới hạn 1–20")
            gen = []
            for _ in range(amount):
                a = generate_name(length)
                while a in self.accounts:
                    a = generate_name(length)
                self.accounts[a] = {"note": "generated", "otp": "", "email": ""}
                save_account(a, "generated")
                gen.append(a)
            await interaction.followup.send("✅ Đã tạo:\n" + "\n".join(gen))
            await send_log(self, interaction, f"Tạo {len(gen)} tài khoản")
            await self.post_account_summary()

        @self.tree.command(name="show", description="📋 Tìm tài khoản")
        @app_commands.describe(account="Nhập tên hoặc từ khoá")
        async def show(interaction, account: str):
            await interaction.response.defer(ephemeral=True)
            key = account.lower().strip()
            if not key:
                return await interaction.followup.send("⚠️ Nhập từ khoá!")
            matched = [(a, info) for a, info in self.accounts.items() if key in a.lower()]
            if matched:
                if len(matched) == 1:
                    acc, info = matched[0]
                    return await interaction.followup.send(
                        f"📄 Account: `{acc}`\n🔑 OTP: `{info.get('otp','')}`"
                    )
                options = [discord.SelectOption(label=a) for a, _ in matched[:25]]
                select = discord.ui.Select(placeholder="Chọn tài khoản", options=options)

                async def cb(i: discord.Interaction):
                    acc = select.values[0]
                    info = self.accounts.get(acc, {})
                    await i.response.send_message(
                        f"📄 Account: `{acc}`\n🔑 OTP: `{info.get('otp','')}`",
                        ephemeral=True
                    )

                select.callback = cb
                view = discord.ui.View(); view.add_item(select)
                return await interaction.followup.send("🔍 Chọn tài khoản:", view=view)
            # Không tìm thấy → gợi ý gần đúng
            suggest = difflib.get_close_matches(key, list(self.accounts.keys()), n=5, cutoff=0.5)
            if suggest:
                return await interaction.followup.send(
                    f"❌ Không tìm thấy `{account}`\n🔎 Gợi ý:\n" + "\n".join(f"• {s}" for s in suggest)
                )
            await interaction.followup.send("❌ Không tìm thấy và không có gợi ý.")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot đã online: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
