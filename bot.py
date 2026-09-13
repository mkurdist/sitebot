import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart
from config import BOT_TOKEN, ADMIN_ID

async def main():
    # مقداردهی ربات و دیسپچر
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # هندلر تستی برای دستور /start
    @dp.message(CommandStart())
    async def start_handler(message: Message):
        # بررسی اینکه آیا کاربر همان ادمین مجاز است یا خیر
        if message.from_user.id == ADMIN_ID:
            await message.answer("✅ ربات با موفقیت روی سرور روشن شد و سیستم امنیتی فعال است!")
        else:
            await message.answer("⛔ دسترسی غیرمجاز. شما ادمین این ربات نیستید.")

    print("🚀 Bot is starting...")
    
    try:
        # اجرای ربات (Long Polling)
        await dp.start_polling(bot)
    finally:
        # بستن سشن‌ها در زمان خاموش شدن
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
