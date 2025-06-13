import discord
from discord.ext import commands, tasks
from commands import setup_commands
import os
from keep_alive import keep_alive  # Nếu bạn không dùng hosting như Render thì có thể xóa dòng này

TOKEN = os.environ.get("TOKEN")

ACCOUNT_NOTI_CHANNEL = int(os.environ.get("ACCOUNT_NOTI_CHANNEL", 0))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.accounts = {}
        self.logcals = {}

    async def setup_hook(self):
        await setup_commands(self)
        self.refresh_data.start()
        print("✅ Bot đã setup thành công!")

    @tasks.loop(minutes=3)
    async def refresh_data(self):
      

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

if __name__ == '__main__':
    keep_alive()  # Nếu không dùng Flask hoặc host, có thể comment dòng này
    bot.run(TOKEN)
