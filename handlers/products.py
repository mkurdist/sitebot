from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from states.product_states import ProductWizard
from services.woocommerce import WooCommerceService

router = Router()
wc_service = WooCommerceService()

# شروع فرآیند با کلیک روی دکمه یا دستور
@router.message(F.text == "➕ محصول جدید")
async def start_product_wizard(message: Message, state: FSMContext):
    await state.set_state(ProductWizard.name)
    await message.answer("🛒 عالی! بیایید یک محصول جدید اضافه کنیم.\n\nابتدا **نام محصول** را وارد کنید (مثلاً: پیاله سفالی طرح گل):")

# لغو فرآیند در هر مرحله
@router.message(F.text == "/cancel")
async def cancel_wizard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ فرآیند ثبت محصول لغو شد.")

# دریافت نام و رفتن به مرحله بعد
@router.message(ProductWizard.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProductWizard.short_description)
    await message.answer("📝 حالا **توضیحات کوتاه** محصول را بفرستید:")

# دریافت توضیحات و ثبت تستی محصول
@router.message(ProductWizard.short_description)
async def process_short_desc(message: Message, state: FSMContext):
    await state.update_data(short_description=message.html_text)
    data = await state.get_data()
    
    wait_msg = await message.answer("⏳ در حال ثبت اولیه محصول در سایت...")
    
    try:
        # ساخت یک دیکشنری ساده برای ثبت محصول در سایت
        product_data = {
            "name": data['name'],
            "type": "simple",
            "short_description": data['short_description'],
            "status": "draft" # فعلاً پیش‌نویس می‌کنیم تا تست کنیم
        }
        
        result = await wc_service.create_simple_product(product_data)
        await wait_msg.edit_text(f"✅ محصول با موفقیت به عنوان پیش‌نویس ثبت شد!\nآیدی محصول: {result['id']}")
        
        # پاک کردن وضعیت کاربر
        await state.clear()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت محصول:\n{str(e)[:500]}")
        await state.clear()
