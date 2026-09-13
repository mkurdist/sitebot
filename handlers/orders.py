import base64
import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID

router = Router()

# تنظیمات اتصال به WooCommerce REST API (مطمئن شوید در config.py این مقادیر را دارید یا اینجا وارد کنید)
from config import WC_URL, WC_CONSUMER_KEY, WC_CONSUMER_SECRET

def get_woo_headers():
    credentials = f"{WC_CONSUMER_KEY}:{WC_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json"
    }

# ۱. نمایش لیست ۱۰ سفارش آخر
@router.message(F.text == "📦 آخرین سفارش‌ها")
async def show_recent_orders(message: Message):
    if message.from_user.id != int(ADMIN_ID):
        return

    url = f"{WC_URL}/wp-json/wc/v3/orders?per_page=10&orderby=date&order=desc"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=get_woo_headers()) as response:
            if response.status != 200:
                await message.answer("❌ خطا در ارتباط با وب‌سایت برای دریافت سفارش‌ها.")
                return
            orders = await response.json()

    if not orders:
        await message.answer("📭 هیچ سفارشی در سایت ثبت نشده است.")
        return

    text = "📦 **۱۰ سفارش اخیر فروشگاه شهر سفال:**\nبرای مدیریت و تغییر وضعیت، روی سفارش مورد نظر کلیک کنید:"
    
    keyboard_builder = []
    
    status_emoji = {
        "pending": "⏳",
        "processing": "💳",
        "completed": "✅",
        "cancelled": "❌",
        "on-hold": "⏸"
    }

    for order in orders:
        o_id = order.get("id")
        total = order.get("total")
        status = order.get("status")
        billing = order.get("billing", {})
        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        
        emoji = status_emoji.get(status, "📌")
        btn_text = f"{emoji} #{o_id} | {name} | {total} تومان"
        
        keyboard_builder.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_order_{o_id}")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_builder)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")


# ۲. نمایش جزئیات کامل یک سفارش و دکمه‌های تغییر وضعیت
@router.callback_query(F.data.startswith("view_order_"))
async def order_details_callback(callback: CallbackQuery):
    order_id = callback.data.split("_")[2]
    url = f"{WC_URL}/wp-json/wc/v3/orders/{order_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=get_woo_headers()) as response:
            if response.status != 200:
                await callback.answer("❌ خطا در دریافت اطلاعات سفارش!", show_alert=True)
                return
            order = await response.json()

    status = order.get("status")
    total = order.get("total", "0")
    payment_title = order.get("payment_method_title", "نامشخص")
    billing = order.get("billing", {})
    
    line_items = order.get("line_items", [])
    products_str = ""
    for item in line_items:
        products_str += f"▪️ {item.get('name')} (تعداد: {item.get('quantity')})\n"

    details_text = (
        f"🔍 **جزئیات سفارش #{order_id}**\n\n"
        f"👤 مشتری: {billing.get('first_name')} {billing.get('last_name')}\n"
        f"📞 تلفن: `{billing.get('phone')}`\n"
        f"📍 آدرس: {billing.get('city')} - {billing.get('address_1')}\n\n"
        f"🛒 اقلام:\n{products_str}\n"
        f"💰 مبلغ کل: `{total} تومان`\n"
        f"📌 وضعیت فعلی: `{status}`"
    )

    # دکمه‌های شیشه‌ای برای تغییر وضعیت سفارش
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و تکمیل سفارش", callback_data=f"set_status_{order_id}_completed"),
        ],
        [
            InlineKeyboardButton(text="💳 در حال انجام (پرداخت شده)", callback_data=f"set_status_{order_id}_processing"),
            InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"set_status_{order_id}_cancelled")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست سفارش‌ها", callback_data="back_to_orders_list")
        ]
    ])

    await callback.message.edit_text(text=details_text, reply_markup=markup, parse_mode="Markdown")
    await callback.answer()


# ۳. اعمال تغییر وضعیت در ووکامرس
@router.callback_query(F.data.startswith("set_status_"))
async def change_order_status_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = parts[2]
    new_status = parts[3]

    url = f"{WC_URL}/wp-json/wc/v3/orders/{order_id}"
    payload = {"status": new_status}

    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=get_woo_headers(), json=payload) as response:
            if response.status == 200:
                status_fa = {
                    "completed": "تکمیل‌شده ✅",
                    "processing": "در حال انجام 💳",
                    "cancelled": "لغو شده ❌"
                }.get(new_status, new_status)
                
                await callback.answer(f"وضعیت سفارش #{order_id} به '{status_fa}' تغییر یافت!", show_alert=True)
                # بازگشت به روزرسانی پیام
                await order_details_callback(callback)
            else:
                await callback.answer("❌ خطا در بروزرسانی وضعیت سفارش در سایت!", show_alert=True)


# ۴. دکمه بازگشت به لیست
@router.callback_query(F.data == "back_to_orders_list")
async def back_to_list_callback(callback: CallbackQuery):
    # پاک کردن پیام جزئیات و درخواست لیست جدید
    await callback.message.delete()
    await show_recent_orders(callback.message)
    await callback.answer()
