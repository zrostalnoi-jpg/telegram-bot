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


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")


# Два администратора
ADMIN_IDS = {
    7458712289,
    8596134525,
}


if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден")

if not GROUP_CHAT_ID:
    raise ValueError("GROUP_CHAT_ID не найден")


# =========================
# TEMPORARY USER DATA
# =========================

user_posts = {}


# =========================
# ACCESS CHECK
# =========================

def is_admin(user_id):
    return user_id in ADMIN_IDS


async def access_denied(update):
    if update.message:
        await update.message.reply_text(
            "⛔ У тебя нет доступа к этому боту."
        )


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
        SELECT
            id,
            chat_id,
            user_id,
            post_text,
            post_time,
            photo_id
        FROM scheduled_posts
        WHERE sent = FALSE
        ORDER BY post_time
        """
    )

    await conn.close()

    return rows


async def get_all_scheduled_posts():

    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
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


async def delete_post(post_id):

    conn = await asyncpg.connect(DATABASE_URL)

    result = await conn.execute(
        """
        DELETE FROM scheduled_posts
        WHERE id = $1
        AND sent = FALSE
        """,
        post_id
    )

    await conn.close()

    return result


# =========================
# /START
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
        "🤖 Бот готов к работе!\n\n"

        "📸 Чтобы поставить пост:\n"
        "Отправь фото с текстом.\n"
        "Я попрошу дату и время.\n\n"

        "📅 Расписание:\n"
        "/schedule\n\n"

        "📋 Все запланированные посты:\n"
        "/list\n\n"

        "🗑 Удалить пост:\n"
        "/cancel НОМЕР\n\n"

        "🆔 Твой ID:\n"
        "/id"
    )


# =========================
# /ID
# =========================

async def id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    await update.message.reply_text(
        "🆔 Твой Telegram ID:\n\n"
        f"{user_id}"
    )


# =========================
# PHOTO HANDLER
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
        "text": caption,
        "waiting_for_datetime": True
    }

    await update.message.reply_text(
        "📸 Фото получил!\n\n"

        "Теперь отправь дату и время публикации:\n\n"

        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"

        "Например:\n"
        "20.08.2026 15:00"
    )


# =========================
# DATE / TIME HANDLER
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

    post_data = user_posts[user_id]

    if not post_data.get("waiting_for_datetime"):
        return

    datetime_text = update.message.text.strip()

    try:

        post_time = datetime.strptime(
            datetime_text,
            "%d.%m.%Y %H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверный формат.\n\n"

            "Используй:\n"
            "20.08.2026 15:00"
        )

        return

    # Не разрешаем ставить пост в прошлое
    if post_time <= datetime.now():

        await update.message.reply_text(
            "❌ Это время уже прошло.\n\n"
            "Укажи будущее время."
        )

        return

    try:

        await add_post(
            chat_id=context.bot_data["group_chat_id"],
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
            f"Ошибка сохранения поста: {e}"
        )

        await update.message.reply_text(
            "❌ Не удалось сохранить пост.\n\n"
            "Попробуй ещё раз."
        )


# =========================
# /SCHEDULE
# =========================

async def schedule_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await access_denied(update)
        return

    await update.message.reply_text(
        "📅 Как запланировать пост:\n\n"

        "1️⃣ Отправь мне фото с текстом.\n\n"

        "2️⃣ Я попрошу дату и время.\n\n"

        "3️⃣ Отправь дату и время.\n\n"

        "Пример:\n"
        "20.08.2026 15:00"
    )


# =========================
# /LIST
# =========================

async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):
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

            message += "📝 Текстовый пост\n"

        if post["user_id"] == 7458712289:

            message += "👤 Автор: ты\n"

        elif post["user_id"] == 8596134525:

            message += "👤 Автор: друг\n"

        message += "\n"

    await update.message.reply_text(
        message
    )


# =========================
# /CANCEL
# =========================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await access_denied(update)
        return

    if not context.args:

        await update.message.reply_text(
            "🗑 Чтобы удалить конкретный пост:\n\n"
            "/cancel НОМЕР\n\n"
            "Например:\n"
            "/cancel 15"
        )

        return

    try:

        post_id = int(
            context.args[0]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Номер поста должен быть числом."
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

            now = datetime.now()

            for post in posts:

                # Если время ещё не наступило
                if post["post_time"] > now:
                    continue

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
                        f"Ошибка отправки "
                        f"поста №{post['id']}: {e}"
                    )

        except Exception as e:

            print(
                f"Ошибка планировщика: {e}"
            )

        await asyncio.sleep(10)


# =========================
# POST INIT
# =========================

async def post_init(application):

    await init_db()

    if GROUP_CHAT_ID.startswith("@"):

        application.bot_data[
            "group_chat_id"
        ] = GROUP_CHAT_ID

    else:

        application.bot_data[
            "group_chat_id"
        ] = int(GROUP_CHAT_ID)

    asyncio.create_task(
        scheduler(application)
    )

    print(
        "🤖 Бот запущен"
    )

    print(
        "👤 Администраторы:",
        ADMIN_IDS
    )

    print(
        "📢 Группа:",
        GROUP_CHAT_ID
    )


# =========================
# ERROR HANDLER
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        f"❌ Ошибка Telegram: {context.error}"
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

    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "id",
            id_command
        )
    )

    application.add_handler(
        CommandHandler(
            "schedule",
            schedule_command
        )
    )

    application.add_handler(
        CommandHandler(
            "list",
            list_command
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
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

    application.add_error_handler(
        error_handler
    )

    application.run_polling()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()
