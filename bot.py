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
# دریافت و بررسی وب‌هوک سفارش از ووکامرس (نسخه فوق‌پیشرفته و ایزوله)
# ==========================================
async def handle_order_webhook(request):
    bot_instance = request.app['bot']
    try:
        # ۱. خواندن متن خام درخواست برای جلوگیری از خطای خالی بودن بادی یا فرمت نامعتبر
        body = await request.text()
        if not body:
            return web.json_response({"status": "ignored", "message": "Empty body"}, status=200)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            # اگر درخواست متنی ووکامرس یا تست پینگ بود، ارور ندهیم
            await bot_instance.send_message(
                chat_id=ADMIN_ID,
                text=f"ℹ️ **تست وب‌هوک / درخواست غیر JSON دریافت شد:**\n<code>{body[:400]}</code>",
                parse_mode="HTML"
            )
            return web.json_response({"status": "received_non_json"}, status=200)

        # ۲. ارسال ساختار خام (Raw JSON) برای تحلیل و بررسی دقیق شما در تلگرام
        raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)
        debug_msg = f"🔍 **[DEBUG] ساختار خام دریافتی از ووکامرس:**\n<pre>{raw_json_str[:3800]}</pre>"
        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=debug_msg,
            parse_mode="HTML"
        )

        # ۳. استخراج عمیق و پیشرفته اطلاعات سفارش
        order_id = data.get("id", "نامشخص")
        status = data.get("status", "نامشخص")
        currency = data.get("currency", "تومان")
        total = data.get("total", "0")
        shipping_total = data.get("shipping_total", "0")
        payment_method_title = data.get("payment_method_title", "نامشخص")
        customer_note = data.get("customer_note", "")

        # اطلاعات مشتری (Billing & Shipping)
        billing = data.get("billing", {})
        first_name = billing.get("first_name", "ثبت‌نشده")
        last_name = billing.get("last_name", "")
        phone = billing.get("phone", "ثبت‌نشده")
        email = billing.get("email", "")
        city = billing.get("city", "")
        address = billing.get("address_1", "")
        state = billing.get("state", "")

        # استخراج اقلام سفارش (Line Items)
        line_items = data.get("line_items", [])
        products_list = ""
        for index, item in enumerate(line_items, 1):
            p_name = item.get("name", "محصول")
            p_qty = item.get("quantity", 1)
            p_subtotal = item.get("subtotal", "0")
            p_total = item.get("total", "0")
            
            products_list += f"{index}. **{p_name}**\n   🔹 تعداد: `{p_qty}` | قیمت کل: `{p_total} {currency}`\n"

        if not products_list:
            products_list = "▫️ (اقلام سفارشی در این پکیج یافت نشد یا تست است)\n"

        # ترجمه وضعیت‌های رایج ووکامرس به فارسی برای خوانایی بهتر
        status_translations = {
            "pending": "⏳ در انتظار پرداخت",
            "processing": "✅ در حال انجام (پرداخت شده)",
            "on-hold": "⏸ در انتظار بررسی",
            "completed": "🎉 تکمیل شده",
            "cancelled": "❌ لغو شده",
            "refunded": " برگشت خورده",
            "failed": "⚠️ ناموفق"
        }
        persian_status = status_translations.get(status, status)

        # ۴. ساخت قالب نهایی فاکتور زیبا و ساختاریافته
        order_text = (
            f"🔔 **ثبت سفارش جدید در شهر سفال!**\n\n"
            f"🆔 **شماره سفارش:** `#{order_id}`\n"
            f"📌 **وضعیت:** {persian_status}\n"
            f"💳 **روش پرداخت:** {payment_method_title}\n\n"
            f"👤 **مشخصات مشتری:**\n"
            f"▫️ نام: {first_name} {last_name}\n"
            f"▫️ تلفن: `{phone}`\n"
            f"▫️ ایمیل: `{email if email else 'ندارد'}`\n"
            f"▫️ آدرس: استان {state}، شهر {city} - {address}\n\n"
            f"🛒 **محصولات خریداری شده:**\n{products_list}\n"
            f"📦 **هزینه ارسال:** `{shipping_total} {currency}`\n"
            f"💰 **مبلغ کل پرداخت‌شده:** `{total} {currency}`"
        )

        if customer_note:
            order_text += f"\n\n📝 **یادداشت مشتری:**\n_{customer_note}_"

        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
            parse_mode="Markdown"
        )

        # بازگرداندن پاسخ موفق به ووکامرس برای ثبت تیک سبز در پنل
        return web.json_response({"status": "success", "order_id": order_id}, status=200)
    
    except Exception as e:
        error_msg = f"❌ خطای پردازش وب‌هوک سفارش: {str(e)}"
        print(error_msg)
        try:
            await bot_instance.send_message(chat_id=ADMIN_ID, text=error_msg)
        except:
            pass
        # بازگرداندن کد 200 به صورت پیش‌فرض تا از قطع شدن وب‌هوک توسط ووکامرس جلوگیری شود
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
