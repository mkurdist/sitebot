import asyncio
import os
import json
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, ADMIN_ID  # مطمئن شوید ADMIN_ID در config.py هست یا به جای آن آیدی عددی خود را بگذارید

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router
from handlers.products import router as products_router

# یک صفحه ساده برای اینکه رندر متوجه شود سرور وب ما روشن است
async def health_check(request):
    return web.Response(text="🏺 CitySofal Bot is Live and Running!")

# ==========================================
# دریافت وب‌هوک سفارش از ووکامرس
# ==========================================
async def handle_order_webhook(request):
    try:
        # خواندن اطلاعات ارسال شده از ووکامرس
        data = await request.json()
        
        # استخراج اطلاعات کلیدی سفارش
        order_id = data.get("id")
        status = data.get("status")
        total = data.get("total")
        currency = data.get("currency", "تومان")
        
        billing = data.get("billing", {})
        first_name = billing.get("first_name", "")
        last_name = billing.get("last_name", "")
        phone = billing.get("phone", "ثبت نشده")
        city = billing.get("city", "")
        address = billing.get("address_1", "")
        
        line_items = data.get("line_items", [])
        products_list = ""
        for item in line_items:
            p_name = item.get("name")
            p_qty = item.get("quantity")
            p_total = item.get("total")
            products_list += f"▫️ {p_name} (تعداد: {p_qty}) - {p_total} {currency}\n"

        # ساخت متن فاکتور زیبا برای ارسال به تلگرام
        order_text = (
            f"🔔 **سفارش جدید در سایت ثبت شد! 🎉**\n\n"
            f"🆔 **شماره سفارش:** #{order_id}\n"
            f"👤 **مشتری:** {first_name} {last_name}\n"
            f"📞 **شماره تماس:** `{phone}`\n"
            f"📍 **شهر/آدرس:** {city} - {address}\n\n"
            f"🛒 **محصولات خریداری شده:**\n{products_list}\n"
            f"💰 **مبلغ کل:** `{total} {currency}`\n"
            f"📌 **وضعیت:** {status}"
        )

        # ارسال پیام به ادمین از طریق ربات
        # نکته: برای دسترسی به ربات در این تابع، از متغیر گلوبال یا ساخت نمونه موقت استفاده می‌کنیم
        bot_instance = request.app['bot']
        await bot_instance.send_message(
            chat_id=ADMIN_ID,  # آیدی عددی تلگرام شما
            text=order_text,
            parse_mode="Markdown"
        )

        return web.json_response({"status": "success", "message": "Order notification sent!"}, status=200)
    
    except Exception as e:
        print(f"Webhook Error: {str(e)}")
        return web.json_response({"error": str(e)}, status=400)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # فعال‌سازی دیوار آتشین
    dp.message.middleware(AdminOnlyMiddleware())
    dp.callback_query.middleware(AdminOnlyMiddleware())

    # اضافه کردن روترها
    dp.include_router(common_router)
    dp.include_router(products_router)

    # ==========================================
    # راه‌اندازی سرور وب (همراه با مسیر وب‌هوک سفارش)
    # ==========================================
    app = web.Application()
    
    # ذخیره نمونه ربات در اپلیکیشن برای استفاده در وب‌هوک
    app['bot'] = bot
    
    app.router.add_get('/', health_check)
    app.router.add_post('/webhook/order', handle_order_webhook) # <--- مسیر دریافت سفارشات
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"🌐 Web server started on port {port}")
    print("🚀 Bot is running with Modular Architecture...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
