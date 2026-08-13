import os

import asyncio

from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")

CHANNEL = "@vectorautogroup"

bot = Bot(token=TOKEN)

async def main():

    await bot.send_message(

        chat_id=CHANNEL,

        text="🚗 Тестовый пост. Бот работает!"

    )

asyncio.run(main()
