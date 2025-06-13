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

    
bot = MyBot()

@bot.event
async def on_ready():
    print(f"🤖 Bot sẵn sàng: {bot.user} (ID: {bot.user.id})")

if __name__ == '__main__':
    keep_alive()  # Nếu không dùng Flask hoặc host, có thể comment dòng này
    bot.run(TOKEN)
