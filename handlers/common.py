from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

# ساخت یک روتر برای مدیریت پیام‌های عمومی
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    # طراحی دکمه‌های کیبورد پایین صفحه
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ محصول جدید"), KeyboardButton(text="📝 مقاله جدید")],
            [KeyboardButton(text="🛍 محصولات سایت"), KeyboardButton(text="📦 سفارش‌های اخیر")],
            [KeyboardButton(text="⚙️ تنظیمات")]
        ],
        resize_keyboard=True,
        input_field_placeholder="یک گزینه را انتخاب کنید..."
    )
    
    await message.answer(
        "به پنل مدیریت یکپارچه فروشگاه خوش آمدید! 🏺\n\n"
        "سیستم امنیتی فعال است. لطفاً برای شروع از منوی زیر یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=keyboard
    )
