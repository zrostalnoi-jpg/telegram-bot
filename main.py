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
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

ADMIN_IDS = {
    7458712289,
    8596134525,
}

user_posts = {}


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

    try:

        await conn.execute(
            """
            INSERT INTO scheduled_posts
            (
                chat_id,
                user_id,
                post_text,
                post_time,
                sent,
                photo_id
            )
            VALUES ($1, $2, $3, $4, FALSE, $5)
            """,
            chat_id,
            user_id,
            text,
            post_time,
            photo_id
        )

    finally:

        await conn.close()


async def get_posts():

    conn = await asyncpg.connect(DATABASE_URL)

    try:

        return await conn.fetch(
            """
            SELECT
                id,
                chat_id,
                user_id,
                post_text,
                post_time,
                photo_id
            FROM scheduled_posts
            WHERE sent = FALSE
            AND post_time <= NOW()
            ORDER BY post_time
            """
        )

    finally:

        await conn.close()


async def get_all_scheduled_posts():

    conn = await asyncpg.connect(DATABASE_URL)

    try:

        return await conn.fetch(
            """
            SELECT
                id,
                user_id,
                post_text,
                post_time,
                photo_id
            FROM scheduled_posts
            WHERE sent = FALSE
            ORDER BY post_time
            """
        )

    finally:

        await conn.close()


async def mark_sent(post_id):

    conn = await asyncpg.connect(DATABASE_URL)

    try:

        await conn.execute(
            """
            UPDATE scheduled_posts
            SET sent = TRUE
            WHERE id = $1
            """,
            post_id
        )

    finally:

        await conn.close()


async def delete_post(post_id):

    conn = await asyncpg.connect(DATABASE_URL)

    try:

        return await conn.execute(
            """
            DELETE FROM scheduled_posts
            WHERE id = $1
            AND sent = FALSE
            """,
            post_id
        )

    finally:

        await conn.close()


# =========================
# ACCESS
# =========================

def is_admin(user_id):

    return user_id in ADMIN_IDS


async def access_denied(update):

    if update.message:

        await update.message.reply_text(
            "⛔ У тебя нет доступа к этому боту."
        )


# =========================
# DEBUG GROUP ID
# =========================

async def debug_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    print(
        "=============================="
    )

    print(
        "CHAT ID:",
        chat.id
    )

    print(
        "CHAT TYPE:",
        chat.type
    )

    print(
        "CHAT TITLE:",
        chat.title
    )

    print(
        "CHAT USERNAME:",
        chat.username
    )

    print(
        "=============================="
    )


# =========================
# START
# =========================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await access_denied(update)

        return

    await update.message.reply_text(
        "🤖 Бот готов!\n\n"

        "📸 Отправь фото с текстом.\n"
        "Я попрошу дату и время.\n\n"

        "📋 /list — расписание\n"
        "🗑 /cancel НОМЕР — удалить\n"
        "🆔 /id — твой ID"
    )


# =========================
# ID
# =========================

async def id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🆔 Твой Telegram ID:\n\n"
        f"{update.effective_user.id}"
    )


# =========================
# PHOTO
# =========================

async def photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await access_denied(update)

        return

    if not update.message.photo:

        return

    photo_id = update.message.photo[-1].file_id

    caption = update.message.caption or ""

    user_posts[user_id] = {
        "photo_id": photo_id,
        "text": caption
    }

    await update.message.reply_text(
        "📸 Фото получил!\n\n"

        "Теперь отправь дату и время:\n\n"

        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"

        "Например:\n"
        "18.08.2026 15:00"
    )


# =========================
# DATE / TIME
# =========================

async def datetime_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id not in user_posts:

        return

    try:

        post_time = datetime.strptime(
            update.message.text.strip(),
            "%d.%m.%Y %H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Пример:\n"
            "18.08.2026 15:00"
        )

        return

    if post_time <= datetime.now():

        await update.message.reply_text(
            "❌ Это время уже прошло."
        )

        return

    if not GROUP_CHAT_ID:

        await update.message.reply_text(
            "❌ GROUP_CHAT_ID не установлен."
        )

        return

    try:

        group_id = int(GROUP_CHAT_ID)

    except ValueError:

        await update.message.reply_text(
            "❌ GROUP_CHAT_ID сейчас указан неправильно.\n\n"
            "Нужно заменить @vectorautogroup "
            "на числовой ID группы.\n\n"
            "Например:\n"
            "-1001234567890"
        )

        return

    post_data = user_posts[user_id]

    try:

        await add_post(
            chat_id=group_id,
            user_id=user_id,
            text=post_data["text"],
            post_time=post_time,
            photo_id=post_data["photo_id"]
        )

        del user_posts[user_id]

        await update.message.reply_text(
            "✅ ПОСТ ЗАПЛАНИРОВАН!\n\n"

            f"📅 {post_time.strftime('%d.%m.%Y')}\n"
            f"⏰ {post_time.strftime('%H:%M')}\n\n"

            "📸 Фото + текст будут опубликованы "
            "автоматически."
        )

    except Exception as e:

        print(
            "ОШИБКА СОХРАНЕНИЯ:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Ошибка сохранения:\n\n"
            f"{repr(e)}"
        )


# =========================
# SCHEDULE
# =========================

async def schedule_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):

        await access_denied(update)

        return

    await update.message.reply_text(
        "📅 Отправь фото с текстом.\n\n"
        "После этого я попрошу дату и время."
    )


# =========================
# LIST
# =========================

async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):

        await access_denied(update)

        return

    posts = await get_all_scheduled_posts()

    if not posts:

        await update.message.reply_text(
            "📭 Запланированных постов нет."
        )

        return

    message = (
        "📅 ЗАПЛАНИРОВАННЫЕ ПОСТЫ:\n\n"
    )

    for post in posts:

        message += (
            f"🆔 №{post['id']}\n"
            f"📅 "
            f"{post['post_time'].strftime('%d.%m.%Y')}\n"
            f"⏰ "
            f"{post['post_time'].strftime('%H:%M')}\n"
        )

        if post["photo_id"]:

            message += "📸 Фото + текст\n"

        else:

            message += "📝 Текст\n"

        message += "\n"

    await update.message.reply_text(
        message
    )


# =========================
# CANCEL
# =========================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):

        await access_denied(update)

        return

    if not context.args:

        await update.message.reply_text(
            "🗑 Пример:\n"
            "/cancel 15"
        )

        return

    try:

        post_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Номер должен быть числом."
        )

        return

    result = await delete_post(
        post_id
    )

    if result == "DELETE 1":

        await update.message.reply_text(
            f"🗑 Пост №{post_id} удалён."
        )

    else:

        await update.message.reply_text(
            f"❌ Пост №{post_id} не найден."
        )


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

                    await mark_sent(
                        post["id"]
                    )

                    print(
                        f"Пост №{post['id']} опубликован"
                    )

                except Exception as e:

                    print(
                        f"Ошибка публикации: {repr(e)}"
                    )

        except Exception as e:

            print(
                f"Ошибка планировщика: {repr(e)}"
            )

        await asyncio.sleep(10)


# =========================
# POST INIT
# =========================

async def post_init(application):

    await init_db()

    asyncio.create_task(
        scheduler(application)
    )

    print(
        "🤖 Бот запущен"
    )


# =========================
# ERROR
# =========================

async def error_handler(
    update,
    context
):

    print(
        "TELEGRAM ERROR:",
        repr(context.error)
    )


# =========================
# MAIN
# =========================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Сначала ловим любое сообщение
    # и выводим ID чата в Railway Logs
    application.add_handler(
        MessageHandler(
            filters.ALL,
            debug_group
        ),
        group=0
    )

    application.add_handler(
        CommandHandler(
            "start",
            start_command
        ),
        group=1
    )

    application.add_handler(
        CommandHandler(
            "id",
            id_command
        ),
        group=1
    )

    application.add_handler(
        CommandHandler(
            "schedule",
            schedule_command
        ),
        group=1
    )

    application.add_handler(
        CommandHandler(
            "list",
            list_command
        ),
        group=1
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        ),
        group=1
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler
        ),
        group=1
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            datetime_handler
        ),
        group=1
    )

    application.add_error_handler(
        error_handler
    )

    application.run_polling()


if __name__ == "__main__":
    main()
