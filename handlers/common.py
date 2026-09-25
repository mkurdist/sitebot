from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

# استفاده از نشست یکتا و سراسری
from services.woocommerce import wc_service_instance as wc_service

# ساخت یک روتر برای مدیریت پیام‌های عمومی
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    # طراحی دکمه‌های کیبورد پایین صفحه با چیدمان جدید (۸ دکمه)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            # ردیف اول: ابزارهای هوش مصنوعی و اتوماسیون
            [KeyboardButton(text="🤖 محصول با Gemini"), KeyboardButton(text="⚡ افزودن خودکار (AI)")],
            # ردیف دوم: مدیریت دستی محصولات
            [KeyboardButton(text="➕ محصول جدید"), KeyboardButton(text="🛍 محصولات سایت")],
            # ردیف سوم: مدیریت مقالات
            [KeyboardButton(text="📝 مقاله جدید"), KeyboardButton(text="✏️ ویرایش مقاله")],
            # ردیف چهارم: سفارشات و تنظیمات
            [KeyboardButton(text="📦 آخرین سفارش‌ها"), KeyboardButton(text="⚙️ تنظیمات")]
        ],
        resize_keyboard=True,
        input_field_placeholder="یک گزینه را انتخاب کنید..."
    )
    
    await message.answer(
        "به پنل مدیریت یکپارچه فروشگاه خوش آمدید! 🏺\n\n"
        "سیستم امنیتی فعال است. لطفاً برای شروع از منوی زیر یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=keyboard
    )

# این هندلر زمانی اجرا می‌شود که متن پیام شامل کلمه "محصولات سایت" باشد
@router.message(F.text.contains("محصولات سایت"))
async def test_get_products(message: Message):
    # پیام انتظار
    wait_msg = await message.answer("⏳ در حال ارتباط با سایت شهر سفال و دریافت محصولات...")
    
    try:
        # دریافت ۳ محصول آخر از سایت
        products = await wc_service.get_latest_products(per_page=3)
        
        if not products:
            await wait_msg.edit_text("محصولی یافت نشد.")
            return
            
        text = "🛍 ۳ محصول آخر سایت شما:\n\n"
        for p in products:
            # بررسی اینکه آیا محصول قیمت دارد یا خیر
            price = p.get('price', 'نامشخص')
            text += f"▪️ {p['name']} - {price} تومان\n"
            
        await wait_msg.edit_text(text)
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در اتصال به سایت:\n{str(e)[:500]}")
