raise RuntimeError(

            "DATABASE_URL не найден в Railway Variables"

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

        CommandHandler("schedule", show_schedule)

    )

    application.add_handler(

        CommandHandler("cancel", cancel)

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

    asyncio.create_task(

        publish_posts(application)

    )

    print("🤖 Бот запущен")

    print("🕐 Часовой пояс: Asia/Vladivostok")

    try:

        while True:

            await asyncio.sleep(3600)

    finally:

        await application.updater.stop()

        await application.stop()

        await application.shutdown()

async def handle_text(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE

):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        return

    if user_id in pending_posts:

        await receive_time(update, context)

    else:

        await receive_post(update, context)

if __name__ == "__main__":

    asyncio.run(main())
