from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states.product_states import ProductWizard
from services.woocommerce import WooCommerceService

router = Router()
wc_service = WooCommerceService()

# --- تابع کمکی برای ساخت دکمه‌های داشبورد ---
def get_dashboard_keyboard(product_id: int, product_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 توضیحات", callback_data=f"edit_desc_{product_id}"),
            InlineKeyboardButton(text="🖼 تصویر اصلی", callback_data=f"edit_img_{product_id}")
        ],
        [
            InlineKeyboardButton(text="💰 قیمت و موجودی", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="📂 دسته‌بندی", callback_data=f"edit_cat_{product_id}")
        ],
        [
            InlineKeyboardButton(text="🔍 تنظیمات سئو (Rank Math)", callback_data=f"edit_seo_{product_id}")
        ],
        [
            InlineKeyboardButton(text="✅ انتشار نهایی", callback_data=f"publish_{product_id}"),
            InlineKeyboardButton(text="❌ حذف", callback_data=f"delete_{product_id}")
        ]
    ])

# --- شروع ساخت محصول ---
@router.message(F.text == "➕ محصول جدید")
async def start_product_wizard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ProductWizard.waiting_for_name)
    await message.answer("🛒 **ساخت محصول جدید**\n\nلطفاً فقط **نام محصول** را وارد کنید:")

@router.message(F.text == "/cancel")
async def cancel_wizard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ عملیات لغو شد.")

# --- دریافت نام و ساخت پیش‌نویس موقت ---
@router.message(ProductWizard.waiting_for_name)
async def process_initial_name(message: Message, state: FSMContext):
    product_name = message.text
    wait_msg = await message.answer("⏳ در حال ایجاد فضای پیش‌نویس در سایت...")
    
    try:
        # ساخت محصول اولیه فقط با یک نام
        product_data = {
            "name": product_name,
            "type": "simple",
            "status": "draft"
        }
        
        result = await wc_service.create_simple_product(product_data)
        product_id = result['id']
        
        # نمایش داشبورد شیشه‌ای
        text = (
            f"📦 **محصول ایجاد شد (پیش‌نویس)**\n\n"
            f"🏷 **نام:** {product_name}\n"
            f"🆔 **آیدی:** {product_id}\n\n"
            f"👇 حالا از پنل زیر، هر بخشی را که می‌خواهید تکمیل کنید:"
        )
        
        await wait_msg.edit_text(
            text, 
            reply_markup=get_dashboard_keyboard(product_id, product_name)
        )
        await state.clear() # وضعیت را پاک می‌کنیم تا منتظر کلیک روی دکمه‌ها بماند
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ساخت پیش‌نویس:\n{str(e)[:500]}")
        await state.clear()

# --- هندل کردن کلیک روی دکمه‌های داشبورد (تست اولیه) ---
@router.callback_query(F.data.startswith("edit_"))
async def handle_dashboard_clicks(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    product_id = callback.data.split("_")[2]
    
    # فعلاً فقط یک پیام تستی می‌دهیم تا مطمئن شویم دکمه‌ها کار می‌کنند
    actions_map = {
        "desc": "بخش توضیحات",
        "img": "بخش آپلود تصویر",
        "price": "بخش قیمت و موجودی",
        "cat": "بخش دسته‌بندی",
        "seo": "بخش سئو"
    }
    
    part_name = actions_map.get(action, "نامشخص")
    await callback.answer(f"شما روی {part_name} برای محصول {product_id} کلیک کردید!", show_alert=True)
