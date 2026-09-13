import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ۱. فعال‌سازی دیوار آتشین روی تمام پیام‌ها و دکمه‌های شیشه‌ای
    dp.message.middleware(AdminOnlyMiddleware())
    dp.callback_query.middleware(AdminOnlyMiddleware())

    # ۲. اضافه کردن روتر منوی اصلی به دیسپچر
    dp.include_router(common_router)

    print("🚀 Bot is running with Modular Architecture...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
