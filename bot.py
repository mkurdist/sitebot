import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router

# یک صفحه ساده برای اینکه رندر متوجه شود سرور وب ما روشن است
async def health_check(request):
    return web.Response(text="🏺 CitySofal Bot is Live and Running!")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # فعال‌سازی دیوار آتشین
    dp.message.middleware(AdminOnlyMiddleware())
    dp.callback_query.middleware(AdminOnlyMiddleware())

    # اضافه کردن روتر منوی اصلی
    dp.include_router(common_router)

    # ==========================================
    # راه‌اندازی سرور وب (برای رفع خطای پورت رندر)
    # ==========================================
    app = web.Application()
    app.router.add_get('/', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # رندر پورت اختصاصی خود را از طریق متغیر محیطی PORT ارسال می‌کند
    # اگر پورتی نبود، از 8080 استفاده می‌کنیم
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"🌐 Web server started on port {port}")
    print("🚀 Bot is running with Modular Architecture...")
    
    try:
        # اجرای ربات (Long Polling) همزمان با سرور وب
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
