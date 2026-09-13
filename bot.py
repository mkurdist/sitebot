import asyncio
import os
import json
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, ADMIN_ID

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router
from handlers.products import router as products_router

# یک صفحه ساده برای اینکه رندر متوجه شود سرور وب ما روشن است
async def health_check(request):
    return web.Response(text="🏺 CitySofal Bot is Live and Running!")

# ==========================================
# دریافت و بررسی وب‌هوک سفارش از ووکامرس
# ==========================================
async def handle_order_webhook(request):
    bot_instance = request.app['bot']
    try:
        data = await request.json()
        
        # ۱. ارسال ساختار خام (Raw JSON) برای تحلیل و بررسی شما در تلگرام
        raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)
        # اگر متن خیلی طولانی بود، تلگرام محدودیت پیام دارد، پس آن را تکه تکه یا به عنوان متن ارسال می‌کنیم
        debug_msg = f"🔍 **[DEBUG] ساختار دریافتی از ووکامرس:**\n<pre>{raw_json_str[:3500]}</pre>"
        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=debug_msg,
            parse_mode="HTML"
        )

        # ۲. استخراج اطلاعات اصلی سفارش
        order_id = data.get("id", "تست/نامشخص")
        status = data.get("status", "نامشخص")
        total = data.get("total", "0")
        currency = data.get("currency", "تومان")
        
        billing = data.get("billing", {})
        first_name = billing.get("first_name", "ثبت‌نشده")
        last_name = billing.get("last_name", "")
        phone = billing.get("phone", "ثبت‌نشده")
        city = billing.get("city", "")
        address = billing.get("address_1", "")
        
        line_items = data.get("line_items", [])
        products_list = ""
        for item in line_items:
            p_name = item.get("name", "محصول")
            p_qty = item.get("quantity", 1)
            p_total = item.get("total", "0")
            products_list += f"▫️ {p_name} (تعداد: {p_qty}) - {p_total} {currency}\n"
            
        if not products_list:
            products_list = "▫️ (این درخواست تست یا فاقد لیست محصولات است)\n"

        order_text = (
            f"🔔 **اطلاعیه ووکامرس / سفارش جدید**\n\n"
            f"🆔 **شماره سفارش:** #{order_id}\n"
            f"👤 **مشتری:** {first_name} {last_name}\n"
            f"📞 **شماره تماس:** `{phone}`\n"
            f"📍 **شهر/آدرس:** {city} - {address}\n\n"
            f"🛒 **محصولات خریداری شده:**\n{products_list}\n"
            f"💰 **مبلغ کل:** `{total} {currency}`\n"
            f"📌 **وضعیت:** {status}"
        )

        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
            parse_mode="Markdown"
        )

        # بازگرداندن کد 200 به ووکامرس برای تایید دریافت موفق
        return web.json_response({"status": "success"}, status=200)
    
    except Exception as e:
        error_msg = f"❌ خطای وب‌هوک: {str(e)}"
        print(error_msg)
        try:
            await bot_instance.send_message(chat_id=ADMIN_ID, text=error_msg)
        except:
            pass
        # همیشه کد 200 برمی‌گردانیم تا ووکامرس خطای 400 ندهد
        return web.json_response({"status": "error", "message": str(e)}, status=200)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # فعال‌سازی دیوار آتشین
    dp.message.middleware(AdminOnlyMiddleware())
    dp.callback_query.middleware(AdminOnlyMiddleware())

    # اضافه کردن روترها
    dp.include_router(common_router)
    dp.include_router(products_router)

    # راه‌اندازی سرور وب
    app = web.Application()
    app['bot'] = bot
    
    app.router.add_get('/', health_check)
    app.router.add_post('/webhook/order', handle_order_webhook)
    
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
