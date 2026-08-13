import os

import asyncio

from datetime import datetime

from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")

CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TOKEN)

posts = [

    {

        "time": "12:00",

        "text": "Тестовый пост от моего бота 🚀"

    },

    {

        "time": "18:00",

        "text": "Второй тестовый пост 🚗"

    }

]

async def main():

    sent_today = set()

    while True:

        now = datetime.now().strftime("%H:%M")

        for post in posts:

            if now == post["time"] and post["time"] not in sent_today:

                await bot.send_message(

                    chat_id=CHAT_ID,

                    text=post["text"]

                )

                sent_today.add(post["time"])

        if now == "00:00":

            sent_today.clear()

        await asyncio.sleep(20)

asyncio.run(main())
