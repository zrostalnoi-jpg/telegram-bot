import os
import asyncio
import asyncpg
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден")


# =========================
# DATABASE
# =========================

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            post_text TEXT,
            post_time TIMESTAMP NOT NULL,
            sent BOOLEAN DEFAULT FALSE,
            photo_id TEXT
        )
    """)

    # Если таблица уже существовала со старой версией,
    # добавляем колонку photo_id автоматически
    await conn.execute("""
        ALTER TABLE scheduled_posts
        ADD COLUMN IF NOT EXISTS photo_id TEXT
    """)

    await conn.execute("""
        ALTER TABLE scheduled_posts
        ALTER COLUMN post_text DROP NOT NULL
    """)

    await conn.close()


async def add_post(
    chat_id,
    user_id,
    text,
    post_time,
    photo_id=None
):
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO scheduled_posts
        (chat_id, user_id, post_text, post_time, photo_id)
        VALUES ($1, $2, $3, $4, $5)
        """,
        chat_id,
        user_id,
        text,
        post_time,
        photo_id
    )

    await conn.close()


async def get_posts():
    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
        """
        SELECT id, chat_id, post_text, post_time, photo_id
        FROM scheduled_posts
        WHERE sent = FALSE
        AND post_time <= NOW()
        ORDER BY post_time
        """
    )

    await conn.close()

    return rows


async def mark_sent(post_id):
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        UPDATE scheduled_posts
        SET sent = TRUE
        WHERE id = $1
        """,
        post_id
    )

    await conn.close()


async def cancel_posts(user_id):
    conn = await asyncpg.connect(DATABASE_URL)

    result = await conn.execute(
        """
        DELETE FROM scheduled_posts
        WHERE user_id = $1
        AND sent = FALSE
        """,
        user_id
    )

    await conn.close()

    return result


async def get_user_posts(user_id):
    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
        """
        SELECT id, post_text, post_time, photo_id
        FROM scheduled_posts
        WHERE user_id = $1
        AND sent = FALSE
        ORDER BY post_time
        """,
        user_id
    )

    await conn.close()

    return rows


# =========================
# TEMPORARY USER DATA
# =========================

user_posts = {}


# =========================
# PHOTO HANDLER
# =========================

async def photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.photo:
        return

    user_id = update.effective_user.id

    photo = update.message.photo[-1]

    text = update.message.caption or ""

    user_posts[user_id] = {
        "photo_id": photo.file_id,
        "text": text
    }

    await update.message.reply_text(
        "📸 Фото получил!\n\n"
        "Теперь отправь дату и время публикации:\n\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
        "Например:\n"
        "20.08.2026 15:00"
    )


# =========================
# DATE/TIME HANDLER
# =========================

async def datetime_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id

    if user_id not in user_posts:
        return

    text = update.message.text.strip()

    try:
        post_time = datetime.strptime(
            text,
            "%d.%m.%Y %H:%M"
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Напиши так:\n"
            "20.08.2026 15:00"
        )
        return

    post_data = user_posts[user_id]

    await add_post(
        chat_id=context.bot_data["group_chat_id"],
        user_id=user_id,
        text=post_data["text"],
        post_time=post_time,
        photo_id=post_data["photo_id"]
    )

    del user_posts[user_id]

    await update.message.reply_text(
        "✅ Пост запланирован!\n\n"
        f"📅 {post_time.strftime('%d.%m.%Y')}\n"
        f"⏰ {post_time.strftime('%H:%M')}\n\n"
        "Фото + текст будут опубликованы автоматически."
    )


# =========================
# /SCHEDULE
# =========================

async def schedule_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📅 Чтобы запланировать пост:\n\n"
        "1️⃣ Отправь мне фото с текстом.\n"
        "2️⃣ Я попрошу дату и время.\n"
        "3️⃣ Отправь дату и время в формате:\n\n"
        "20.08.2026 15:00"
    )


# =========================
# /CANCEL
# =========================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = await cancel_posts(
        update.effective_user.id
    )

    await update.message.reply_text(
        f"🗑 Удалено запланированных постов: {result}"
    )


# =========================
# /LIST
# =========================

async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    posts = await get_user_posts(
        update.effective_user.id
    )

    if not posts:
        await update.message.reply_text(
            "📭 У тебя нет запланированных постов."
        )
        return

    message = "📅 Твои запланированные посты:\n\n"

    for post in posts:
        message += (
            f"🆔 {post['id']}\n"
            f"📅 {post['post_time'].strftime('%d.%m.%Y')}\n"
            f"⏰ {post['post_time'].strftime('%H:%M')}\n"
        )

        if post["photo_id"]:
            message += "📸 Фото + текст\n"
        else:
            message += f"📝 {post['post_text']}\n"

        message += "\n"

    await update.message.reply_text(message)


# =========================
# SCHEDULER
# =========================

async def scheduler(application):
    while True:

        try:
            posts = await get_posts()

            for post in posts:

                try:

                    if post["photo_id"]:

                        await application.bot.send_photo(
                            chat_id=post["chat_id"],
                            photo=post["photo_id"],
                            caption=post["post_text"] or ""
                        )

                    else:

                        await application.bot.send_message(
                            chat_id=post["chat_id"],
                            text=post["post_text"] or ""
                        )

                    await mark_sent(post["id"])

                except Exception as e:

                    print(
                        f"Ошибка отправки поста "
                        f"{post['id']}: {e}"
                    )

        except Exception as e:

            print(
                f"Ошибка планировщика: {e}"
            )

        await asyncio.sleep(10)


# =========================
# START
# =========================

async def post_init(application):

    await init_db()

    group_chat_id = os.getenv("GROUP_CHAT_ID")

    if not group_chat_id:
        raise ValueError(
            "GROUP_CHAT_ID не найден"
        )

    application.bot_data["group_chat_id"] = int(
        group_chat_id
    )

    asyncio.create_task(
        scheduler(application)
    )


def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "schedule",
            schedule_command
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        )
    )

    application.add_handler(
        CommandHandler(
            "list",
            list_command
        )
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            datetime_handler
        )
    )

    application.run_polling()


if __name__ == "__main__":
    main()
