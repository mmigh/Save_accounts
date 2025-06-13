import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, json, random, string, difflib, io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

# === ENV variables ===
TOKEN = os.environ.get("TOKEN")
SHEET_NAME = "RobloxAccounts"
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))

# === Google Sheets setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if not cred_json:
    raise ValueError("Missing GOOGLE_CREDENTIALS_JSON")
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(cred_json), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# === Sheet helpers ===
def read_accounts():
    accs = {}
    for rec in sheet.get_all_records():
        a = rec.get("Account", "").strip()
        if not a: continue
        accs[a] = {
            "note": rec.get("Note", "").strip(),
            "otp": rec.get("otp", "").strip(),
            "email": rec.get("email", "").strip()
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

# === Logging helper ===
async def send_log(bot, interaction, action):
    if not NOTIFY_CHANNEL_ID: return
    ch = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not ch: return
    await ch.send(f"📝 `{interaction.user}` dùng lệnh `/{interaction.command.name}`\n📘 Chi tiết: {action}")

# === Bot ===
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.accounts = {}
        self.refresh_data.start()
        self.post_account_summary.start()

    async def setup_hook(self):
        self.accounts = read_accounts()
        await self.register_commands()
        await self.tree.sync()
        print("✅ Bot ready")

    @tasks.loop(minutes=5)
    async def refresh_data(self):
        print("🔄 Refreshing...")
        self.accounts = read_accounts()

    @tasks.loop(hours=10)
    async def post_account_summary(self):
        print("📤 Posting summary...")
        if not ACCOUNT_NOTI_CHANNEL: return
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch: return
        async for msg in ch.history(limit=50):
            if msg.author == self.user:
                await msg.delete()
        lines = []
        for a, info in self.accounts.items():
            chk = "✅" if info.get("otp") else "❌"
            lines.append(f"{a} | {info.get('note','')} | {chk}")
        chunk = ""
        for l in lines:
            if len(chunk) + len(l) + 1 > 1900:
                await ch.send(chunk)
                chunk = ""
            chunk += l + "\n"
        if chunk: await ch.send(chunk)

    async def register_commands(self):
        # /add
        @self.tree.command(name="add", description="➕ Thêm tài khoản")
        @app_commands.describe(account="Tên", note="Ghi chú")
        async def add(interaction, account: str, note: str = ""):
            a = account.strip()
            if not a:
                return await interaction.response.send_message("⚠️ Nhập tên!", ephemeral=True)
            if a in self.accounts:
                return await interaction.response.send_message("⚠️ Đã có!", ephemeral=True)
            self.accounts[a] = {"note": note, "otp": "", "email": ""}
            save_account(a, note)
            await interaction.response.send_message(f"✅ Added `{a}`", ephemeral=True)
            await send_log(self, interaction, f"Added {a} | {note}")
            await self.post_account_summary()

        # /edit
        @self.tree.command(name="edit", description="✏️ Sửa tài khoản")
        @app_commands.describe(account="Tên", note="Ghi chú", otp="OTP", email="Email")
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
                return await interaction.response.send_message("⚠️ Chưa đổi gì!", ephemeral=True)
            await interaction.response.send_message("✅ Updated: " + ", ".join(changes), ephemeral=True)
            await send_log(self, interaction, f"{a} edited: " + "; ".join(changes))
            await self.post_account_summary()

        # /remove
        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên")
        async def remove(interaction, account: str):
            a = account.strip()
            if a not in self.accounts:
                return await interaction.response.send_message("⚠️ Không tìm thấy!", ephemeral=True)
            delete_account(a)
            del self.accounts[a]
            await interaction.response.send_message(f"🗑️ Removed `{a}`", ephemeral=True)
            await send_log(self, interaction, f"Removed {a}")
            await self.post_account_summary()

        # /generate
        @self.tree.command(name="generate", description="⚙️ Tạo account ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài")
        async def generate(interaction, amount: int=1, length: int=12):
            if not (1 <= amount <= 20):
                return await interaction.response.send_message("⚠️ 1–20 only!", ephemeral=True)
            res = []
            for _ in range(amount):
                n = generate_name(length)
                while n in self.accounts:
                    n = generate_name(length)
                self.accounts[n] = {"note": "generated", "otp": "", "email": ""}
                save_account(n, "generated")
                res.append(n)
            await interaction.response.send_message("✅ Generated:\n" + "\n".join(res), ephemeral=True)
            await send_log(self, interaction, f"Generated: {', '.join(res)}")
            await self.post_account_summary()

        # /restore
        @self.tree.command(name="restore", description="♻️ Khôi phục từ file")
        @app_commands.describe(file=".txt chứa: account | note mỗi dòng")
        async def restore(interaction, file: discord.Attachment):
            if not file.filename.endswith(".txt"):
                return await interaction.response.send_message("⚠️ Chỉ .txt!", ephemeral=True)
            raw = (await file.read()).decode(errors="ignore")
            lines = [l.strip() for l in raw.splitlines() if "|" in l]
            data = []
            for l in lines:
                a, n = [x.strip() for x in l.split("|",1)]
                if a: data.append((a,n))
            if not data:
                return await interaction.response.send_message("⚠️ File không hợp lệ!", ephemeral=True)
            sheet.clear()
            sheet.append_row(["Account","Note","otp","email",""])
            self.accounts.clear()
            for a, n in data:
                self.accounts[a] = {"note": n, "otp": "", "email": ""}
                save_account(a, n)
            await interaction.response.send_message(f"✅ Restored {len(data)} accounts", ephemeral=True)
            await send_log(self, interaction, f"Restored {len(data)} accounts")
            await self.post_account_summary()

        # /show
        @self.tree.command(name="show", description="📋 Tìm account hoặc gợi ý tên")
        @app_commands.describe(account="Tên hoặc từ khoá")
        async def show(interaction, account: str):
            key = account.strip().lower()
            if not key:
                return await interaction.response.send_message("⚠️ Nhập từ khoá cụ thể!", ephemeral=True)
            matched = [(a,info) for a,info in self.accounts.items() if key in a.lower()]
            if matched:
                if len(matched)==1:
                    a, info = matched[0]
                    await interaction.response.send_message(
                        f"🧾 **{a}**\n"
                        f"📝 {info.get('note','')}\n"
                        f"🔑 OTP: {info.get('otp','')}\n"
                        f"📧 Email: {info.get('email','')}",
                        ephemeral=True
                    )
                else:
                    opts=[discord.SelectOption(label=a) for a,_ in matched[:25]]
                    sel=discord.ui.Select(placeholder="Chọn ...", options=opts)
                    async def cb(i):
                        a=sel.values[0]; info=self.accounts.get(a,{})
                        await i.response.send_message(
                            f"🧾 **{a}**\n"
                            f"📝 {info.get('note','')}\n"
                            f"🔑 OTP: {info.get('otp','')}\n"
                            f"📧 Email: {info.get('email','')}",
                            ephemeral=True
                        )
                    sel.callback=cb
                    view=discord.ui.View(); view.add_item(sel)
                    await interaction.response.send_message(f"🔍 {len(matched)} kết quả:", view=view, ephemeral=True)
                return
            # else gợi ý gần đúng
            sug = difflib.get_close_matches(key, list(self.accounts.keys()), n=5, cutoff=0.5)
            if sug:
                return await interaction.response.send_message(
                    f"❌ Không tìm thấy `{account}`.\n🔎 Gợi ý:\n" +
                    "\n".join(f"• {s}" for s in sug),
                    ephemeral=True
                )
            await interaction.response.send_message("❌ Không tìm thấy và không có gợi ý.", ephemeral=True)

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 {bot.user} ready (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
