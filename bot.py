import asyncio
import os
import json
import hmac
import hashlib
import base64
import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

# اضافه شدن کانکشن استرینگ دیتابیس به ایمپورت‌ها
from config import BOT_TOKEN, ADMIN_ID, WC_WEBHOOK_SECRET, DATABASE_URL

# ایمپورت کردن ماژول‌هایی که ساختیم
from utils.security import AdminOnlyMiddleware
from handlers.common import router as common_router
from handlers.gemini_products import router as gemini_router   # روتر جدید محصولات جمینای
from handlers.products import router as products_router
from handlers.orders import router as orders_router
from handlers.articles import router as articles_router

from services.woocommerce import wc_service_instance as wc_service
from services.wordpress import wp_service_instance as wp_service

# ساخت یک روتر داخلی فقط برای دکمه‌های مربوط به وب‌هوک
webhook_router = Router()

# ==========================================
# میدلور هوشمند برای خروج خودکار از وضعیت‌ها (FSM) 
# هنگام کلیک روی دکمه‌های منوی اصلی
# ==========================================
MENU_BUTTONS = {
    "🤖 محصول با Gemini", "⚡ افزودن خودکار (AI)", "➕ محصول جدید", 
    "🛍 محصولات سایت", "📝 مقاله جدید", "✏️ ویرایش مقاله", 
    "📦 آخرین سفارش‌ها", "⚙️ تنظیمات", "/start", "/cancel"
}

class ClearStateOnMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if event.text and event.text in MENU_BUTTONS:
            state = data.get("state")
            if state:
                await state.clear()
        return await handler(event, data)

# ==========================================
# دکمه: سفارش رو گرفتم ✅
# ==========================================
@webhook_router.callback_query(F.data.startswith("ack_order_"))
async def ack_order_callback(callback: CallbackQuery):
    order_id = callback.data.split("_")[2]
    
    # اضافه کردن مهر تایید به انتهای پیام فعلی
    new_text = callback.message.html_text + "\n\n✅ <b>توسط ادمین تایید و دریافت شد! (بسته‌بندی)</b>"
    
    # ویرایش پیام و حذف کردن دکمه شیشه‌ای تا دیگر قابل کلیک نباشد
    await callback.message.edit_text(text=new_text, parse_mode="HTML", reply_markup=None)
    await callback.answer(f"سفارش #{order_id} بسته شد!", show_alert=True)

# یک صفحه ساده برای بررسی سلامت سرور وب
async def health_check(request):
    return web.Response(text="🏺 CitySofal Bot is Live and Connected to Supabase!")

# ==========================================
# دریافت و بررسی وب‌هوک سفارش از ووکامرس (همراه با Supabase)
# ==========================================
async def handle_order_webhook(request):
    bot_instance = request.app['bot']
    db_pool = request.app['db_pool']
    body = ""
    
    try:
        body = await request.text()
        if not body:
            return web.json_response({"status": "ignored", "message": "Empty body"}, status=200)

        # لایه امنیتی HMAC
        received_signature = request.headers.get("x-wc-webhook-signature")
        if not received_signature:
            return web.json_response({"status": "unauthorized", "message": "Missing signature"}, status=401)

        expected_signature = base64.b64encode(
            hmac.new(WC_WEBHOOK_SECRET.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()
        ).decode('utf-8')

        if not hmac.compare_digest(received_signature, expected_signature):
            await bot_instance.send_message(
                chat_id=ADMIN_ID,
                text="⚠️ <b>هشدار امنیتی:</b> تلاش مسدود شد! ریکوئست فیک مسدود گردید.",
                parse_mode="HTML"
            )
            return web.json_response({"status": "unauthorized"}, status=401)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return web.json_response({"status": "received_non_json"}, status=200)

        order_id = str(data.get("id", "نامشخص"))
        status = data.get("status", "نامشخص")
        
        # ==========================================
        # منطق دیتابیس (جلوگیری از تکرار + پاک کردن پیام قبلی)
        # ==========================================
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow('SELECT status, message_id FROM order_notifications WHERE order_id = $1', order_id)
            
            old_message_id = None
            if row:
                old_status = row['status']
                old_message_id = row['message_id']
                
                if old_status == status:
                    print(f"🔄 Ignored duplicate webhook for Order #{order_id} (Status: {status})")
                    return web.json_response({"status": "ignored_duplicate"}, status=200)
                
                if old_message_id:
                    try:
                        await bot_instance.delete_message(chat_id=ADMIN_ID, message_id=old_message_id)
                    except Exception as e:
                        print(f"Could not delete old message {old_message_id}: {e}")

        # استخراج سایر اطلاعات سفارش
        total = str(data.get("total", "0"))
        shipping_total = str(data.get("shipping_total", "0"))
        payment_method_title = data.get("payment_method_title", "نامشخص")
        customer_note = data.get("customer_note", "")
        billing = data.get("billing", {})
        first_name = billing.get("first_name", "ثبت‌نشده")
        last_name = billing.get("last_name", "")
        phone = billing.get("phone", "ثبت‌نشده")
        city = billing.get("city", "")
        address_1 = billing.get("address_1", "")
        state = billing.get("state", "")

        shipping_lines = data.get("shipping_lines", [])
        shipping_method = shipping_lines[0].get("method_title", "پست/تیپاکس") if shipping_lines else "پیش‌فرض"

        line_items = data.get("line_items", [])
        products_list = ""
        for index, item in enumerate(line_items, 1):
            p_name = item.get("name", "محصول")
            p_qty = str(item.get("quantity", 1))
            p_total = str(item.get("total", "0"))
            products_list += f"{index}. {p_name}\n   - تعداد: {p_qty} | مبلغ: {p_total} تومان\n"

        status_translations = {
            "pending": "⏳ در انتظار پرداخت (ثبت اولیه)",
            "processing": "💳✅ پرداخت موفق و قطعی",
            "on-hold": "⏸ در انتظار بررسی",
            "completed": "🎉 تکمیل‌شده و ارسال شده",
            "cancelled": "❌ لغو شده",
            "failed": "⚠️ پرداخت ناموفق"
        }
        persian_status = status_translations.get(status, status)

        if status in ["processing", "completed"]:
            header_title = "💰 گزارش واریز وجه و ثبت سفارش قطعی در شهر سفال!"
        elif status == "failed":
            header_title = "⚠️ هشدار: تلاش ناموفق برای پرداخت در سایت!"
        else:
            header_title = "🔔 ثبت سفارش جدید (در انتظار پرداخت):"

        order_text = (
            f"<b>{header_title}</b>\n\n"
            f"🆔 شماره سفارش: #{order_id}\n"
            f"📌 وضعیت: {persian_status}\n"
            f"💳 پرداخت: {payment_method_title}\n"
            f"🚚 ارسال: {shipping_method}\n\n"
            f"👤 مشتری: {first_name} {last_name}\n"
            f"📞 تلفن: <code>{phone}</code>\n"
            f"📍 آدرس: {state}، {city}، {address_1}\n\n"
            f"🛒 اقلام:\n{products_list}\n"
            f"💰 کل (با هزینه ارسال): {total} تومان"
        )
        if customer_note:
            order_text += f"\n\n📝 یادداشت: {customer_note}"

        reply_markup = None
        if status in ["processing", "completed"]:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 سفارش رو گرفتم (بستن)", callback_data=f"ack_order_{order_id}")]
            ])

        sent_msg = await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO order_notifications (order_id, status, message_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (order_id) DO UPDATE 
                SET status = $2, message_id = $3
            ''', order_id, status, sent_msg.message_id)

        return web.json_response({"status": "success", "order_id": order_id}, status=200)
    
    except Exception as e:
        print(f"Webhook Error: {str(e)}")
        return web.json_response({"status": "error", "message": str(e)}, status=200)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    print("🔌 Connecting to Supabase Database...")
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS order_notifications (
                order_id VARCHAR(50) PRIMARY KEY,
                status VARCHAR(50),
                message_id BIGINT
            )
        ''')
    print("✅ Database ready!")

    dp.message.middleware(AdminOnlyMiddleware())
    dp.callback_query.middleware(AdminOnlyMiddleware())
    
    # 🌟 ثبت میدلور خروج از وضعیت 🌟
    dp.message.middleware(ClearStateOnMenuMiddleware())

    dp.include_router(common_router)
    dp.include_router(gemini_router)
    dp.include_router(products_router)
    dp.include_router(orders_router)
    dp.include_router(articles_router)
    dp.include_router(webhook_router)

    app = web.Application()
    app['bot'] = bot
    app['db_pool'] = db_pool
    
    app.router.add_get('/', health_check)
    app.router.add_post('/webhook/order', handle_order_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"🌐 Web server started on port {port}")
    print("🚀 Bot is running with Supabase & Modular Architecture...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()
        await db_pool.close()
        await wc_service.close()
        await wp_service.close()

if __name__ == "__main__":
    asyncio.run(main())
