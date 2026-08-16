import os

import asyncio

from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

import asyncpg

from telegram import Update

from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")

GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "@vectorautogroup")

TIMEZONE = ZoneInfo("Asia/Vladivostok")

ADMIN_IDS = {

    7458712289,

    8596134525,

}

db_pool = None

pending_posts = {}

def is_admin(user_id):

    return user_id in ADMIN_IDS

async def init_database():

    global db_pool

    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:

        await conn.execute("""

            CREATE TABLE IF NOT EXISTS scheduled_posts (

                id SERIAL PRIMARY KEY,

                user_id BIGINT NOT NULL,

                post_type TEXT NOT NULL,

                text TEXT,

                photo_id TEXT,

                publish_at TIMESTAMPTZ NOT NULL,

                published BOOLEAN DEFAULT FALSE,

                created_at TIMESTAMPTZ DEFAULT NOW()

            )

        """)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):

        return

    await update.message.reply_text(

        "🤖 Бот работает!\n\n"

        "Отправь фото с текстом или просто текст.\n"

        "После этого я попрошу время публикации.\n\n"

        "🕐 Время — Владивосток.\n\n"

        "/schedule — расписание\n"

        "/cancel — отменить подготовленный пост"

    )

async def receive_post(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if update.message.photo:

        pending_posts[user_id] = {

            "post_type": "photo",

            "photo_id": update.message.photo[-1].file_id,

            "text": update.message.caption or "",

        }

    elif update.message.text:

        pending_posts[user_id] = {

            "post_type": "text",

            "photo_id": None,

            "text": update.message.text,

        }

    else:

        return

    await update.message.reply_text(

        "✅ Пост получил.\n\n"

        "Напиши время публикации, например:\n"

        "18:30"

    )

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id not in pending_posts:

        return

    try:

        hour, minute = map(int, update.message.text.strip().split(":"))

        if not (0 <= hour <= 23 and 0 <= minute <= 59):

            raise ValueError

    except ValueError:

        await update.message.reply_text(

            "❌ Напиши время в формате HH:MM\n"

            "Например: 18:30"

        )

        return

    now = datetime.now(TIMEZONE)

    publish_at = now.replace(

        hour=hour,

        minute=minute,

        second=0,

        microsecond=0,

    )

    if publish_at <= now:

        publish_at += timedelta(days=1)

    post = pending_posts.pop(user_id)

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow(

            """

            INSERT INTO scheduled_posts

            (user_id, post_type, text, photo_id, publish_at)

            VALUES ($1, $2, $3, $4, $5)

            RETURNING id

            """,

            user_id,

            post["post_type"],

            post["text"],

            post["photo_id"],

            publish_at,

        )

    await update.message.reply_text(

        f"✅ Пост запланирован!\n\n"

        f"🆔 №{row['id']}\n"

        f"📅 {publish_at.strftime('%d.%m.%Y')}\n"

        f"🕐 {publish_at.strftime('%H:%M')}\n"

        f"📍 Владивосток"

    )

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):

        return

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(

            """

            SELECT id, text, publish_at

            FROM scheduled_posts

            WHERE published = FALSE

            ORDER BY publish_at

            LIMIT 50

            """

        )

    if not rows:

        await update.message.reply_text(

            "📭 Запланированных постов нет."

        )

        return

    result = "📅 Расписание:\n\n"

    for row in rows:

        time = row["publish_at"].astimezone(TIMEZONE)

        text = row["text"] or "📸 Фото"

        result += (

            f"🆔 №{row['id']}\n"

            f"🕐 {time.strftime('%d.%m.%Y %H:%M')}\n"

            f"📝 {text[:50]}\n\n"

        )

    await update.message.reply_text(result)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id in pending_posts:

        pending_posts.pop(user_id)

        await update.message.reply_text(

            "❌ Подготовленный пост отменён."

        )

    else:

        await update.message.reply_text(

            "Нет подготовленного поста."

        )

async def publish_loop(application):

    while True:

        try:

            now = datetime.now(TIMEZONE)

            async with db_pool.acquire() as conn:

                rows = await conn.fetch(

                    """

                    SELECT id, post_type, text, photo_id

                    FROM scheduled_posts

                    WHERE published = FALSE

                    AND publish_at <= $1

                    ORDER BY publish_at

                    LIMIT 20

                    """,

                    now,

                )

            for row in rows:

                try:

                    if row["post_type"] == "photo":

                        await application.bot.send_photo(

                            chat_id=GROUP_CHAT_ID,

                            photo=row["photo_id"],

                            caption=row["text"] or None,

                        )

                    else:

                        await application.bot.send_message(

                            chat_id=GROUP_CHAT_ID,

                            text=row["text"],

                        )

                    async with db_pool.acquire() as conn:

                        await conn.execute(

                            """

                            UPDATE scheduled_posts

                            SET published = TRUE

                            WHERE id = $1

                            """,

                            row["id"],

                        )

                    print(f"✅ Пост №{row['id']} опубликован")

                except Exception as error:

                    print(f"❌ Ошибка поста №{row['id']}: {error}")

        except Exception as error:

            print(f"❌ Ошибка планировщика: {error}")

        await asyncio.sleep(15)

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

    if not DATABASE_URL:

        raise RuntimeError(

            "DATABASE_URL не найден в Railway Variables"

        )

    await init_database()

    application = (

        Application.builder()

        .token(BOT_TOKEN)

        .build()

    )

    application.add_handler(

        CommandHandler("start", start)

    )

    application.add_handler(

        CommandHandler("schedule", show_schedule)

    )

    application.add_handler(

        CommandHandler("cancel", cancel)

    )

    application.add_handler(

        MessageHandler(filters.PHOTO, receive_post)

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

    asyncio.create_task(

        publish_loop(application)

    )

    print("🤖 Бот запущен")

    print("🕐 Владивосток: Asia/Vladivostok")

    while True:

        await asyncio.sleep(3600)

if __name__ == "__main__":

    asyncio.run(main())
