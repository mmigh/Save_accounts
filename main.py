import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, string, difflib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

# --- ENV ---
TOKEN = os.environ.get("TOKEN")
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))
SHEET_NAME = "RobloxAccounts"

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# --- Helpers ---
def read_accounts():
    accs = {}
    for row in sheet.get_all_records():
        a = str(row.get("Account", "")).strip()
        if not a: continue
        accs[a] = {
            "note": str(row.get("Note", "")).strip(),
            "otp": str(row.get("otp", "")).strip(),
            "email": str(row.get("email", "")).strip()
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
    cell = sheet.find(a)
    if cell and cell.col == 1 and field in col_map:
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
            await ch.send(f"📝 `{interaction.user}` dùng **/{interaction.command.name}**\n📘 {action}")

# --- Bot class ---
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
        print("✅ Bot ready")

    @tasks.loop(minutes=5)
    async def refresh_data(self):
        self.accounts = read_accounts()

    @tasks.loop(hours=10)
    async def post_account_summary(self):
        if not ACCOUNT_NOTI_CHANNEL: return
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch: return

        # Clean old bot messages
        try:
            async for msg in ch.history(limit=50):
                if msg.author == self.user:
                    await msg.delete()
        except: pass

        # Build groups
        done_lines, other_lines = [], []
        for acc, info in self.accounts.items():
            note = (info.get("note","") or "").strip().lower()
            otp = info.get("otp","")
            chk = "✅" if otp else "❌"
            text = f"`{acc}` | {info.get('note','')} | {chk}"
            btn = discord.ui.Button(label="📋 Xem", style=discord.ButtonStyle.secondary, custom_id=f"btn_show_{acc}")
            view = discord.ui.View()
            async def btn_cb(inter, a=acc):
                info_i = self.accounts.get(a,{})
                await inter.response.send_message(
                    f"📄 Account: `{a}`\n"
                    f"📝 Note: `{info_i.get('note','')}`\n"
                    f"🔑 OTP: `{info_i.get('otp','')}`\n"
                    f"📧 Email: `{info_i.get('email','')}`",
                    ephemeral=True
                )
            btn.callback = btn_cb
            view.add_item(btn)

            if note == "done":
                done_lines.append((text, view))
            else:
                other_lines.append((text, view))

        # Send messages
        if done_lines:
            await ch.send("📂 ✅ **Đã xong:**")
            for t,v in done_lines:
                await ch.send(t, view=v)
        if other_lines:
            await ch.send("📂 📦 **Chưa xong / Xử lý:**")
            for t,v in other_lines:
                await ch.send(t, view=v)

    async def register_commands(self):
        # --- /add ---
        @self.tree.command(name="add", description="➕ Thêm tài khoản")
        @app_commands.describe(account="Tên", note="Ghi chú")
        async def add(inter, account: str, note: str = ""):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            a = account.strip()
            if not a: return await inter.followup.send("⚠️ Nhập tên!")
            if a in self.accounts: return await inter.followup.send("⚠️ Đã tồn tại!")
            self.accounts[a] = {"note": note, "otp": "", "email": ""}
            save_account(a, note)
            await inter.followup.send(f"✅ Đã thêm `{a}`")
            await send_log(self, inter, f"Thêm `{a}` | `{note}`")
            await self.post_account_summary()

        # --- /remove ---
        @self.tree.command(name="remove", description="❌ Xóa tài khoản")
        @app_commands.describe(account="Tên")
        async def remove(inter, account: str):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            a = account.strip()
            if a not in self.accounts: return await inter.followup.send("⚠️ Không tồn tại!")
            delete_account(a)
            del self.accounts[a]
            await inter.followup.send(f"🗑️ Đã xóa `{a}`")
            await send_log(self, inter, f"Xóa `{a}`")
            await self.post_account_summary()

        # --- /edit ---
        @self.tree.command(name="edit", description="✏️ Sửa tài khoản")
        @app_commands.describe(account="Tên", note="Ghi chú", otp="OTP", email="Email")
        async def edit(inter, account: str, note: str = "", otp: str = "", email: str = ""):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            a = account.strip()
            if a not in self.accounts: return await inter.followup.send("⚠️ Không tồn tại!")
            changes = []
            if note:
                self.accounts[a]["note"] = note
                update_account_field(a, "note", note)
                changes.append(f"note=`{note}`")
            if otp:
                self.accounts[a]["otp"] = otp
                update_account_field(a, "otp", otp)
                changes.append(f"otp=`{otp}`")
            if email:
                self.accounts[a]["email"] = email
                update_account_field(a, "email", email)
                changes.append(f"email=`{email}`")
            if not changes: return await inter.followup.send("⚠️ Không có gì để sửa!")
            await inter.followup.send(f"✅ Đã sửa: {', '.join(changes)}")
            await send_log(self, inter, f"Sửa `{a}`: {', '.join(changes)}")
            await self.post_account_summary()

        # --- /generate ---
        @self.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài")
        async def generate(inter, amount: int = 1, length: int = 12):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            if not 1 <= amount <= 20:
                return await inter.followup.send("⚠️ Giới hạn 1–20")
            gen = []
            for _ in range(amount):
                a = generate_name(length)
                while a in self.accounts:
                    a = generate_name(length)
                self.accounts[a] = {"note": "generated", "otp": "", "email": ""}
                save_account(a, "generated")
                gen.append(a)
            await inter.followup.send(f"✅ Đã tạo:\n" + "\n".join(gen))
            await send_log(self, inter, f"Tạo {len(gen)} account")
            await self.post_account_summary()

        # --- /show ---
        @self.tree.command(name="show", description="📋 Xem chi tiết tài khoản")
        @app_commands.describe(account="Tên tài khoản")
        async def show(inter, account: str):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            a = account.strip()
            info = self.accounts.get(a)
            if not info:
                return await inter.followup.send("❌ Không tìm thấy tài khoản này.")
            embed = discord.Embed(title=f"📄 Account: {a}", colour=discord.Color.blue())
            embed.add_field(name="📝 Note", value=info.get("note","-"), inline=False)
            embed.add_field(name="🔑 OTP", value=info.get("otp","-"), inline=False)
            embed.add_field(name="📧 Email", value=info.get("email","-"), inline=False)
            await inter.followup.send(embed=embed, ephemeral=True)

# --- Run Bot ---
bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot online: {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
