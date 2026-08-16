import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
GROUP = os.getenv("GROUP_CHAT_ID", "@vectorautogroup")
TZ = ZoneInfo("Asia/Vladivostok")
ADMINS = {7458712289, 8596134525}
posts = {}


def admin(uid):
    return uid in ADMINS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if admin(update.effective_user.id):
        await update.message.reply_text("🤖 Бот работает!\n\nОтправь фото или текст.")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not admin(uid):
        return

    if uid in posts:
        try:
            h, m = map(int, update.message.text.split(":"))

            if h > 23 or m > 59:
                raise ValueError

        except:
            await update.message.reply_text("Напиши время в формате 18:30")
            return

        post = posts.pop(uid)
        now = datetime.now(TZ)
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)

        await update.message.reply_text(
            f"✅ Запланировано на {target.strftime('%d.%m.%Y %H:%M')}"
        )

        asyncio.create_task(send_later(post, target))

    elif update.message.photo:
        posts[uid] = {
            "photo": update.message.photo[-1].file_id,
            "text": update.message.caption or ""
        }

        await update.message.reply_text("Фото получил. Напиши время, например 18:30")

    else:
        posts[uid] = {
            "text": update.message.text
        }

        await update.message.reply_text("Текст получил. Напиши время, например 18:30")


async def send_later(post, target):
    wait = (target - datetime.now(TZ)).total_seconds()

    await asyncio.sleep(wait)

    bot = Bot(TOKEN)

    if "photo" in post:
        await bot.send_photo(
            GROUP,
            post["photo"],
            caption=post["text"] or None
        )
    else:
        await bot.send_message(
            GROUP,
            post["text"]
        )

    print("POST SENT")


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не найден")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.PHOTO | (filters.TEXT & ~filters.COMMAND),
            message
        )
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    print("BOT STARTED")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
