import asyncio
import os
import json
import hmac
import hashlib
import base64
from aiohttp import web
from aiogram import Bot, Dispatcher

# اضافه شدن کد محرمانه وب‌هوک به ایمپورت‌ها
from config import BOT_TOKEN, ADMIN_ID, WC_WEBHOOK_SECRET

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router
from handlers.products import router as products_router
from handlers.orders import router as orders_router  

# یک صفحه ساده برای اینکه رندر متوجه شود سرور وب ما روشن است
async def health_check(request):
    return web.Response(text="🏺 CitySofal Bot is Live and Running!")

# ==========================================
# دریافت و بررسی وب‌هوک سفارش از ووکامرس (ایمن‌شده با HMAC)
# ==========================================
async def handle_order_webhook(request):
    bot_instance = request.app['bot']
    body = ""
    try:
        # ۱. خواندن متن خام درخواست
        body = await request.text()
        if not body:
            return web.json_response({"status": "ignored", "message": "Empty body"}, status=200)

        # ==========================================
        # لایه امنیتی: بررسی امضای دیجیتال ووکامرس
        # ==========================================
        received_signature = request.headers.get("x-wc-webhook-signature")
        if not received_signature:
            return web.json_response({"status": "unauthorized", "message": "Missing signature"}, status=401)

        # محاسبه هش با استفاده از کلید محرمانه
        expected_signature = base64.b64encode(
            hmac.new(
                WC_WEBHOOK_SECRET.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        # مقایسه ایمن دو امضا (برای جلوگیری از حملات تایمینگ)
        if not hmac.compare_digest(received_signature, expected_signature):
            await bot_instance.send_message(
                chat_id=ADMIN_ID,
                text="⚠️ <b>هشدار امنیتی:</b> تلاش مسدود شد! یک ریکوئست فیک و بدون امضای معتبر به وب‌هوک ارسال شد.",
                parse_mode="HTML"
            )
            return web.json_response({"status": "unauthorized", "message": "Invalid signature"}, status=401)
        # ==========================================

        try:
            data = json.loads(body)
        except json.JSONDecodeError as json_err:
            await bot_instance.send_message(
                chat_id=ADMIN_ID,
                text=f"ℹ️ <b>خطای ساختار JSON (غیر معتبر):</b>\n<code>{str(json_err)}</code>\n\n📦 <b>متن دریافتی:</b>\n<code>{body[:2000]}</code>",
                parse_mode="HTML"
            )
            return web.json_response({"status": "received_non_json"}, status=200)

        # استخراج اطلاعات سفارش
        order_id = str(data.get("id", "نامشخص"))
        status = data.get("status", "نامشخص")
        total = str(data.get("total", "0"))
        shipping_total = str(data.get("shipping_total", "0"))
        payment_method_title = data.get("payment_method_title", "نامشخص")
        customer_note = data.get("customer_note", "")

        # مشخصات مشتری و آدرس دقیق
        billing = data.get("billing", {})
        first_name = billing.get("first_name", "ثبت‌نشده")
        last_name = billing.get("last_name", "")
        phone = billing.get("phone", "ثبت‌نشده")
        email = billing.get("email", "")
        city = billing.get("city", "")
        address_1 = billing.get("address_1", "")
        address_2 = billing.get("address_2", "")
        postcode = billing.get("postcode", "")
        state = billing.get("state", "")

        # ترکیب هوشمند خطوط آدرس
        full_address = address_1
        if address_2:
            full_address += f" - واحد {address_2}"
        if postcode:
            full_address += f" (کد پستی: {postcode})"

        # روش ارسال
        shipping_lines = data.get("shipping_lines", [])
        shipping_method = "پیش‌فرض"
        if shipping_lines:
            shipping_method = shipping_lines[0].get("method_title", "پست/تیپاکس")

        # اقلام سفارش
        line_items = data.get("line_items", [])
        products_list = ""
        for index, item in enumerate(line_items, 1):
            p_name = item.get("name", "محصول")
            p_qty = str(item.get("quantity", 1))
            p_total = str(item.get("total", "0"))
            products_list += f"{index}. {p_name}\n   - تعداد: {p_qty} | مبلغ: {p_total} تومان\n"

        if not products_list:
            products_list = "- اقلام سفارشی ثبت نشده است\n"

        # ترجمه وضعیت‌ها به فارسی
        status_translations = {
            "pending": "⏳ در انتظار پرداخت (ثبت اولیه)",
            "processing": "💳✅ پرداخت موفق و در حال انجام",
            "on-hold": "⏸ در انتظار بررسی",
            "completed": "🎉 تکمیل‌شده و ارسال شده",
            "cancelled": "❌ لغو شده",
            "refunded": "‌برگشت خورده",
            "failed": "⚠️ پرداخت ناموفق / خطا"
        }
        persian_status = status_translations.get(status, status)

        # هدر پیام بر اساس وضعیت
        if status in ["processing", "completed"]:
            header_title = "💰 گزارش واریز وجه و ثبت سفارش قطعی در شهر سفال!"
        elif status == "failed":
            header_title = "⚠️ هشدار: تلاش ناموفق برای پرداخت در سایت!"
        else:
            header_title = "🔔 ثبت سفارش جدید (در انتظار پرداخت):"

        # ساخت فاکتور نهایی
        order_text = (
            f"<b>{header_title}</b>\n\n"
            f"🆔 شماره سفارش: #{order_id}\n"
            f"📌 وضعیت: {persian_status}\n"
            f"💳 روش پرداخت: {payment_method_title}\n"
            f"🚚 روش ارسال: {shipping_method}\n\n"
            f"👤 مشخصات مشتری:\n"
            f"- نام: {first_name} {last_name}\n"
            f"- تلفن: <code>{phone}</code>\n"
            f"- ایمیل: {email if email else 'ندارد'}\n"
            f"- آدرس: استان {state}، شهر {city}\n"
            f"  {full_address}\n\n"
            f"🛒 محصولات خریداری شده:\n{products_list}\n"
            f"📦 هزینه ارسال: {shipping_total} تومان\n"
            f"💰 مبلغ کل: {total} تومان"
        )

        if customer_note:
            order_text += f"\n\n📝 یادداشت مشتری:\n{customer_note}"

        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
            parse_mode="HTML"
        )

        return web.json_response({"status": "success", "order_id": order_id}, status=200)
    
    except Exception as e:
        # کاهش سقف برش متن به ۲۰۰۰ کاراکتر برای جلوگیری از سرریز شدن پیام در تلگرام
        error_msg = (
            f"❌ <b>خطای پردازش وب‌هوک سفارش:</b>\n"
            f"<code>{str(e)}</code>\n\n"
            f"📦 <b>متن کامل جیسون دریافتی که باعث خطا شد:</b>\n"
            f"<code>{body[:2000]}</code>"
        )
        print(error_msg)
        try:
            await bot_instance.send_message(
                chat_id=ADMIN_ID, 
                text=error_msg, 
                parse_mode="HTML"
            )
        except Exception as telegram_err:
            print(f"Failed to send error log to Telegram: {telegram_err}")
            
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
    dp.include_router(orders_router)

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
