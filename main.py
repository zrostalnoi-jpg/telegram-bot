import os
import asyncio
import asyncpg
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден")


async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            post_text TEXT NOT NULL,
            post_time TIMESTAMP NOT NULL,
            sent BOOLEAN DEFAULT FALSE
        )
    """)

    await conn.close()


async def add_post(chat_id, user_id, text, post_time):
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO scheduled_posts
        (chat_id, user_id, post_text, post_time)
        VALUES ($1, $2, $3, $4)
        """,
        chat_id,
        user_id,
        text,
        post_time
    )

    await conn.close()


async def get_posts():
    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
        """
        SELECT id, chat_id, post_text, post_time
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


async def schedule_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📅 Чтобы поставить пост в расписание:\n\n"
        "/schedule ДД.ММ.ГГГГ ЧЧ:ММ Текст поста\n\n"
        "Например:\n"
        "/schedule 20.08.2026 15:00 🚗 Новая машина уже в пути!"
    )


async def schedule_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Используй:\n"
            "/schedule ДД.ММ.ГГГГ ЧЧ:ММ Текст"
        )
        return

    date_string = context.args[0]
    time_string = context.args[1]

    text = " ".join(context.args[2:])

    try:
        post_time = datetime.strptime(
            f"{date_string} {time_string}",
            "%d.%m.%Y %H:%M"
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверная дата или время.\n"
            "Пример: 20.08.2026 15:00"
        )
        return

    await add_post(
        update.effective_chat.id,
        update.effective_user.id,
        text,
        post_time
    )

    await update.message.reply_text(
        f"✅ Пост запланирован!\n\n"
        f"📅 {post_time.strftime('%d.%m.%Y')}\n"
        f"⏰ {post_time.strftime('%H:%M')}\n\n"
        f"{text}"
    )


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


async def scheduler(application):
    while True:
        try:
            posts = await get_posts()

            for post in posts:
                try:
                    await application.bot.send_message(
                        chat_id=post["chat_id"],
                        text=post["post_text"]
                    )

                    await mark_sent(post["id"])

                except Exception as e:
                    print(
                        f"Ошибка отправки поста "
                        f"{post['id']}: {e}"
                    )

        except Exception as e:
            print(f"Ошибка планировщика: {e}")

        await asyncio.sleep(10)


async def post_init(application):
    await init_db()
    asyncio.create_task(scheduler(application))


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler("schedule", schedule_command)
    )

    application.add_handler(
        CommandHandler("cancel", cancel_command)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
