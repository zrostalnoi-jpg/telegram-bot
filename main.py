import os

import asyncio

from telegram import Update, Bot

from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat = update.effective_chat

    print(f"CHAT_ID = {chat.id}")

    print(f"GROUP = {chat.title}")

    await update.message.reply_text(

        f"ID этой группы: {chat.id}"

    )

app = Application.builder().token(TOKEN).build()

app.add_handler(

    MessageHandler(filters.ALL, get_chat_id)

)

app.run_polling(
