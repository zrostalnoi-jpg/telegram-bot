import os

import asyncio

from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

from telegram import Update

from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")

GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "@vectorautogroup")

TIMEZONE = ZoneInfo("Asia/Vladivostok")

ADMIN_IDS = {7458712289, 8596134525}

pending_posts = {}

def is_admin(user_id):

    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):

        return

    await update.message.reply_text(

        "🤖 Бот работает!\n\n"

        "Отправь фото с текстом или просто текст.\n"

        "После этого я попрошу время публикации.\n\n"

        "🕐 Время — Владивосток."

    )
  async def receive_post(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if update.message.photo:

        pending_posts[user_id] = {

            "type": "photo",

            "photo": update.message.photo[-1].file_id,

            "text": update.message.caption or ""

        }

    elif update.message.text:

        pending_posts[user_id] = {

            "type": "text",

            "text": update.message.text

        }

    else:

        return

    await update.message.reply_text(

        "✅ Пост получил.\n\n"

        "Теперь напиши время публикации.\n"

        "Например: 18:30"

    )

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id not in pending_posts:

        return
      try:

        hour, minute = map(

            int,

            update.message.text.strip().split(":")

        )

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:

            raise ValueError

    except ValueError:

        await update.message.reply_text(

            "❌ Неверное время.\n"

            "Напиши в формате 18:30"

        )

        return

    post = pending_posts.pop(user_id)

    now = datetime.now(TIMEZONE)

    publish_at = now.replace(

        hour=hour,

        minute=minute,

        second=0,

        microsecond=0

    )

    if publish_at <= now:

        publish_at += timedelta(days=1)

    delay = (publish_at - now).total_seconds()

    await update.message.reply_text(

        "✅ Пост запланирован!\n\n"

        f"📅 {publish_at.strftime('%d.%m.%Y')}\n"

        f"🕐 {publish_at.strftime('%H:%M')}\n"

        "📍 Владивосток"

    )

    asyncio.create_task(

        publish_later(post, delay)

    )

async def publish_later(post, delay):

    await asyncio.sleep(delay)

    try:

        from telegram import Bot

        bot = Bot(token=BOT_TOKEN)

        if post["type"] == "photo":

            await bot.send_photo(

                chat_id=GROUP_CHAT_ID,

                photo=post["photo"],

                caption=post["text"] or None

            )

        else:

            await bot.send_message(

                chat_id=GROUP_CHAT_ID,

                text=post["text"]

            )

        print("✅ Пост опубликован")

    except Exception as error:

        print(f"❌ Ошибка публикации: {error}")
      async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id in pending_posts:

        await receive_time(update, context)

    else:

        await receive_post(update, context)

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(

            "BOT_TOKEN не найден в Railway Variables"

        )

    application = (

        Application.builder()

        .token(BOT_TOKEN)

        .build()

    )

    application.add_handler(

        CommandHandler("start", start)

    )

    application.add_handler(

        MessageHandler(

            filters.PHOTO,

            receive_post

        )

    )

    application.add_handler(

        MessageHandler(

            filters.TEXT & ~filters.COMMAND,

            handle_text

        )

    )
await application.initialize()

    await application.start()

    await application.updater.start_polling()

    print("🤖 Бот запущен")

    print("🕐 Часовой пояс: Владивосток")

    while True:

        await asyncio.sleep(3600)

if __name__ == "__main__":

    asyncio.run(main())
