import os

import asyncio

from telegram import Update

from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🤖 Бот работает!\n\n"

        "Готов публиковать посты по расписанию."

    )

async def main():

    if not BOT_TOKEN:

        raise RuntimeError("BOT_TOKEN не найден в Railway Variables")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("🤖 Бот запущен")

    await app.initialize()

    await app.start()

    await app.updater.start_polling()

    try:

        while True:

            await asyncio.sleep(3600)

    finally:

        await app.updater.stop()

        await app.stop()

        await app.shutdown()

if __name__ == "__main__":

    asyncio.run(main())
