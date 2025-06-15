import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive

TOKEN = os.environ["TOKEN"]
ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", 0))
SHEET_NAME = "RobloxAccounts"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

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
    s += "".join(random.choices(string.ascii_letters + string.digits, k=n - 3))
    return "".join(random.sample(s, len(s)))

async def send_log(bot, interaction, action):
    if NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(f"📝 `{interaction.user}` dùng lệnh `/{interaction.command.name}`\n📘 {action}")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.accounts = {}
        self.sent_messages = {}

    async def setup_hook(self):
        self.accounts = read_accounts()
        await self.register_commands()
        await self.tree.sync()
        self.refresh_data.start()
        self.auto_send_loop.start()

    @tasks.loop(minutes=5)
    async def refresh_data(self):
        self.accounts = read_accounts()

    @tasks.loop(hours=10)
    async def auto_send_loop(self):
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
                    try: await m.delete()
                    except: pass
        except: pass

        done_lines = []
        pending_lines = []

        for acc, info in self.accounts.items():
            line = f"`{acc}` | {info.get('note','')} | {'✅' if info.get('otp') else '❌'}"
            if info.get("note", "").lower() == "done":
                done_lines.append(line)
            else:
                pending_lines.append(line)

        def split_chunks(lines):
            chunks = []
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > 1900:
                    chunks.append(current)
                    current = ""
                current += line + "\n"
            if current:
                chunks.append(current)
            return chunks

        if done_lines:
            await channel.send("✅ **Đã hoàn tất:**")
            for chunk in split_chunks(done_lines):
                await channel.send(chunk)

        if pending_lines:
            await channel.send("📦 **Chưa hoàn tất:**")
            for chunk in split_chunks(pending_lines):
                await channel.send(chunk)

    async def _upsert_account_line(self, acc, info):
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch: return
        await self._delete_account_line(acc)
        await self._send_account_line(ch, acc, info)

    async def _delete_account_line(self, acc):
        ch = self.get_channel(ACCOUNT_NOTI_CHANNEL)
        if not ch or acc not in self.sent_messages: return
        try:
            msg = await ch.fetch_message(self.sent_messages.pop(acc))
            await msg.delete()
        except: pass

    async def _send_account_line(self, ch, acc, info):
        note = info.get("note", "")
        otp = info.get("otp", "")
        chk = "✅" if otp else "❌"
        content = f"`{acc}` | {note} | {chk}"

        view = discord.ui.View(timeout=None)
        async def cb(inter):
            await inter.response.send_message(
                f"📄 Account: `{acc}`\n📝 Note: `{note}`\n🔑 OTP: `{otp}`\n📧 Email: `{info.get('email','')}`",
                ephemeral=True
            )
        btn = discord.ui.Button(label="📋 Xem", style=discord.ButtonStyle.secondary)
        btn.callback = cb
        view.add_item(btn)

        msg = await ch.send(content, view=view)
        self.sent_messages[acc] = msg.id

    async def register_commands(self):
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
            await self._upsert_account_line(a, self.accounts[a])
            await inter.followup.send(f"✅ Đã thêm `{a}`")
            await send_log(self, inter, f"Thêm `{a}` | `{note}`")

        @self.tree.command(name="remove", description="❌ Xoá tài khoản")
        @app_commands.describe(account="Tên")
        async def remove(inter, account: str):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            a = account.strip()
            if a not in self.accounts: return await inter.followup.send("⚠️ Không tồn tại!")
            delete_account(a)
            del self.accounts[a]
            await self._delete_account_line(a)
            await inter.followup.send(f"🗑️ Đã xoá `{a}`")
            await send_log(self, inter, f"Xoá `{a}`")

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
            if not changes:
                return await inter.followup.send("⚠️ Không có gì để cập nhật.")
            await self._upsert_account_line(a, self.accounts[a])
            await inter.followup.send("✅ Đã cập nhật: " + ", ".join(changes))
            await send_log(self, inter, f"Sửa `{a}`: " + ", ".join(changes))

        @self.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
        @app_commands.describe(amount="Số lượng", length="Độ dài")
        async def generate(inter, amount: int = 1, length: int = 12):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            if not (1 <= amount <= 20):
                return await inter.followup.send("⚠️ Giới hạn 1–20.")
            gen = []
            for _ in range(amount):
                a = generate_name(length)
                while a in self.accounts:
                    a = generate_name(length)
                self.accounts[a] = {"note": "generated", "otp": "", "email": ""}
                save_account(a, "generated")
                await self._upsert_account_line(a, self.accounts[a])
                gen.append(a)
            await inter.followup.send("✅ Đã tạo:\n" + "\n".join(gen))
            await send_log(self, inter, f"Tạo {len(gen)} tài khoản")

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
            embed.add_field(name="📝 Note", value=info.get("note", "-"), inline=False)
            embed.add_field(name="🔑 OTP", value=info.get("otp", "-"), inline=False)
            embed.add_field(name="📧 Email", value=info.get("email", "-"), inline=False)
            await inter.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="refresh_now", description="🔄 Làm mới danh sách account ngay")
        async def refresh_now(inter):
            try: await inter.response.defer(ephemeral=True)
            except discord.NotFound: return
            await self.send_updated_account_message()
            await inter.followup.send("✅ Đã làm mới danh sách tài khoản.")
            await send_log(self, inter, "Làm mới ngay danh sách account")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot online: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author == bot.user or message.content.startswith("/"):
        return
    acc = message.content.strip().split()[0]
    data = bot.accounts.get(acc)
    if data:
        try:
            await message.reply(
                f"📄 Account: `{acc}`\n"
                f"📝 Note: `{data.get('note','')}`\n"
                f"🔑 OTP: `{data.get('otp','')}`\n"
                f"📧 Email: `{data.get('email','')}`"
            )
            await message.delete()
        except:
            pass
    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
