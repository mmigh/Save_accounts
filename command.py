import discord
from discord import app_commands
from discord.ext import commands
import random
import io

from main import (
    save_logcal, delete_logcal, save_account, delete_account,
    update_account_field, generate_roblox_username,
    send_log, sheet
)

async def setup_commands(bot: commands.Bot):
    # === LOGCAL COMMANDS ===

    @bot.tree.command(name="save", description="➕ Thêm logcal JSON")
    @app_commands.describe(logcal="Dữ liệu logcal")
    async def add_logcal(interaction: discord.Interaction, logcal: str):
        logcal = logcal.strip()
        if logcal in bot.logcals:
            await interaction.response.send_message("⚠️ Đã tồn tại!", ephemeral=True)
            return
        bot.logcals[logcal] = {}
        save_logcal(logcal)
        await interaction.response.send_message("✅ Đã thêm logcal!", ephemeral=True)

    @bot.tree.command(name="get", description="🎲 Rút 1 logcal ngẫu nhiên")
    async def get_logcal(interaction: discord.Interaction):
        if not bot.logcals:
            await interaction.response.send_message("📭 Hết logcal!", ephemeral=True)
            return
        choice = random.choice(list(bot.logcals))
        delete_logcal(choice)
        del bot.logcals[choice]
        await interaction.response.send_message(f"🎯 Logcal:\n```json\n{choice}\n```", ephemeral=True)

    @bot.tree.command(name="add_file", description="📂 Nhập nhiều logcal từ file .txt")
    @app_commands.describe(file="Tệp .txt, mỗi dòng là một logcal JSON hoặc chuỗi")
    async def add_file_logcal(interaction: discord.Interaction, file: discord.Attachment):
        if not file.filename.endswith(".txt"):
            await interaction.response.send_message("⚠️ Chỉ hỗ trợ file .txt!", ephemeral=True)
            return

        content = await file.read()
        lines = [line.strip() for line in content.decode(errors="ignore").splitlines() if line.strip()]
        added = 0
        skipped = 0

        for line in lines:
            if line in bot.logcals:
                skipped += 1
                continue
            bot.logcals[line] = {}
            save_logcal(line)
            added += 1

        await interaction.response.send_message(
            f"✅ Đã thêm **{added}** logcal mới.\n⚠️ Bỏ qua **{skipped}** dòng trùng lặp.",
            ephemeral=True
        )

    @bot.tree.command(name="count_all", description="🔢 Đếm số lượng tài khoản và logcal")
    async def count_all(interaction: discord.Interaction):
        acc_count = len(bot.accounts)
        log_count = len(bot.logcals)
        await interaction.response.send_message(
            f"📦 Tổng tài khoản: {acc_count}\n🗂️ Tổng logcal: {log_count}", ephemeral=True
        )

    # === ACCOUNT COMMANDS ===

    @bot.tree.command(name="add", description="➕ Thêm tài khoản Roblox")
    @app_commands.describe(account="Tên tài khoản", note="Ghi chú (tùy chọn)")
    async def add_account(interaction: discord.Interaction, account: str, note: str = ""):
        account = account.strip()
        if not account:
            await interaction.response.send_message("⚠️ Không được để trống tài khoản!", ephemeral=True)
            return
        if account in bot.accounts:
            await interaction.response.send_message(f"⚠️ Tài khoản {account} đã tồn tại!", ephemeral=True)
            return
        bot.accounts[account] = {"note": note}
        save_account(account, note)

        await interaction.response.send_message(f"✅ Đã thêm: `{account}` với ghi chú: `{note}`", ephemeral=True)
        await bot.send_updated_account_message()
        await send_log(interaction, f"Thêm account: {account} | note: {note}")

    @bot.tree.command(name="edit", description="✏️ Sửa thông tin tài khoản")
    @app_commands.describe(
        account="Tên tài khoản cần sửa",
        note="Ghi chú mới (bỏ trống nếu không sửa)",
        otp="Mã OTP mới (bỏ trống nếu không sửa)",
        email="Email mới (bỏ trống nếu không sửa)"
    )
    async def edit(interaction: discord.Interaction, account: str, note: str = "", otp: str = "", email: str = ""):
        account = account.strip()
        if account not in bot.accounts:
            await interaction.response.send_message("⚠️ Không tìm thấy tài khoản!", ephemeral=True)
            return

        updates = []
        if note:
            bot.accounts[account]["note"] = note
            update_account_field(account, "note", note)
            updates.append(f"note: `{note}`")
        if otp:
            bot.accounts[account]["otp"] = otp
            update_account_field(account, "otp", otp)
            updates.append(f"otp: `{otp}`")
        if email:
            bot.accounts[account]["email"] = email
            update_account_field(account, "email", email)
            updates.append(f"email: `{email}`")

        if not updates:
            await interaction.response.send_message("⚠️ Không có thông tin nào để cập nhật.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Đã cập nhật `{account}`:\n" + "\n".join(updates), ephemeral=True)
        await bot.send_updated_account_message()
        await send_log(interaction, f"✏️ Sửa {account}: " + " | ".join(updates))

    @bot.tree.command(name="remove", description="❌ Xóa tài khoản")
    @app_commands.describe(account="Tên tài khoản")
    async def remove_account(interaction: discord.Interaction, account: str):
        if account not in bot.accounts:
            await interaction.response.send_message("⚠️ Tài khoản không tồn tại.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Đã xóa tài khoản: `{account}`", ephemeral=True)

        delete_account(account)
        del bot.accounts[account]
        await bot.send_updated_account_message()

        log_channel = bot.get_channel(bot.NOTIFY_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🗑️ `{interaction.user}` đã xóa: `{account}`")

    @bot.tree.command(name="generate", description="⚙️ Tạo tài khoản ngẫu nhiên")
    @app_commands.describe(amount="Số lượng", length="Độ dài tên")
    async def generate_account(interaction: discord.Interaction, amount: int = 1, length: int = 12):
        if not (1 <= amount <= 20):
            await interaction.response.send_message("⚠️ Giới hạn 1–20.", ephemeral=True)
            return
        generated = []
        for _ in range(amount):
            while True:
                uname = generate_roblox_username(length)
                if uname not in bot.accounts:
                    break
            bot.accounts[uname] = {"note": "Generated"}
            save_account(uname, "Generated")
            generated.append(uname)
        await interaction.response.send_message("✅ Đã tạo:\n" + "\n".join(f"{g}" for g in generated), ephemeral=True)
        await bot.send_updated_account_message()
        await send_log(interaction, f"Tạo {amount} account: {', '.join(generated)}")

    @bot.tree.command(name="backup_accounts", description="💾 Sao lưu")
    async def backup_accounts(interaction: discord.Interaction):
        content = "\n".join([f"{acc} | {info.get('note','')}" for acc, info in bot.accounts.items()])
        file = discord.File(io.BytesIO(content.encode()), filename="accounts_backup.txt")
        await interaction.response.send_message("🗂️ Dữ liệu sao lưu:", file=file, ephemeral=True)

    @bot.tree.command(name="restore_accounts", description="♻️ Khôi phục từ file")
    @app_commands.describe(file="File .txt")
    async def restore_accounts(interaction: discord.Interaction, file: discord.Attachment):
        if not file.filename.endswith(".txt"):
            await interaction.response.send_message("⚠️ Chỉ .txt!", ephemeral=True)
            return
        text = (await file.read()).decode(errors="ignore")
        lines = [l.strip() for l in text.splitlines() if "|" in l]
        if not lines:
            await interaction.response.send_message("⚠️ Không hợp lệ!", ephemeral=True)
            return
        sheet.clear()
        sheet.append_row(["Account", "Note", "otp", "email", "Logcal"])
        bot.accounts.clear()
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                save_account(parts[0], parts[1])
                bot.accounts[parts[0]] = {"note": parts[1]}
        await interaction.response.send_message(f"✅ Đã khôi phục {len(lines)}!", ephemeral=True)
        await bot.send_updated_account_message()

    @bot.tree.command(name="show", description="📋 Hiển thị thông tin tài khoản")
    async def show(interaction: discord.Interaction):
        if not bot.accounts:
            await interaction.response.send_message("📭 Không có tài khoản nào!", ephemeral=True)
            return

        options = []
        for acc in list(bot.accounts.keys())[:25]:
            options.append(discord.SelectOption(label=acc[:100]))

        select = discord.ui.Select(placeholder="Chọn tài khoản để xem", options=options)

        async def callback(i: discord.Interaction):
            acc = select.values[0]
            info = bot.accounts.get(acc, {})
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
        await interaction.response.send_message("📚 Chọn tài khoản để hiển thị thông tin:", view=view, ephemeral=True)