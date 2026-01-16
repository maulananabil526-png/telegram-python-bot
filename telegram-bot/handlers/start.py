from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from services.userbot import get_real_dc, client as userbot
from telethon import functions, types

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Ambil DC ID via Userbot service
    try:
        u = await userbot.get_entity(user.id)
        dc_id = u.photo.dc_id if u.photo else "Unknown"
    except:
        dc_id = "unknow"

    text = (
        f"👋 **Halo!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 » **NAME** : {user.full_name}\n"
        f"🆔 » **USER ID** : `{user.id}`\n"
        f"🗣️ » **USERNAME** : @{user.username or '-'}\n"
        f"🌐 » **DC ID** : `{dc_id}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ _Silakan gunakan menu di bawah untuk fitur lainnya._"
    )

    try:
        photos = await context.bot.get_user_profile_photos(user.id)
        if photos.total_count > 0:
            await update.message.reply_photo(
                photo=photos.photos[0][-1].file_id,
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text, parse_mode="Markdown")


def setup(app):
    app.add_handler(CommandHandler("start", start_cmd))

