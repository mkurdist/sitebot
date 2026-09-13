from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from states.product_states import ProductWizard
from services.woocommerce import WooCommerceService

router = Router()
wc_service = WooCommerceService()

# شروع فرآیند
@router.message(F.text == "➕ محصول جدید")
async def start_product_wizard(message: Message, state: FSMContext):
    await state.clear() # پاک کردن وضعیت‌های قبلی
    await state.set_state(ProductWizard.name)
    await message.answer("🛒 عالی! بیایید یک محصول جدید اضافه کنیم.\n\nابتدا **نام محصول** را وارد کنید (مثلاً: پیاله سفالی طرح گل):")

# لغو فرآیند در هر مرحله
@router.message(F.text == "/cancel")
async def cancel_wizard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ فرآیند ثبت محصول لغو شد.")

# مرحله ۱: دریافت نام و درخواست توضیحات کوتاه
@router.message(ProductWizard.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProductWizard.short_description)
    await message.answer("📝 حالا **توضیحات کوتاه** محصول را بفرستید:")

# مرحله ۲: دریافت توضیحات کوتاه و درخواست توضیحات کامل
@router.message(ProductWizard.short_description)
async def process_short_desc(message: Message, state: FSMContext):
    # تبدیل خطوط جدید به تگ <br> برای وردپرس
    html_text = message.html_text.replace("\n", "<br>")
    await state.update_data(short_description=html_text)
    await state.set_state(ProductWizard.long_description)
    await message.answer("📄 بسیار عالی. حالا **توضیحات کامل** محصول را بفرستید:")

# مرحله ۳: دریافت توضیحات کامل و درخواست قیمت
@router.message(ProductWizard.long_description)
async def process_long_desc(message: Message, state: FSMContext):
    html_text = message.html_text.replace("\n", "<br>")
    await state.update_data(long_description=html_text)
    await state.set_state(ProductWizard.price)
    await message.answer("💰 **قیمت محصول** را به تومان وارد کنید (فقط عدد انگلیسی، مثلاً 850000):")

# مرحله ۴: دریافت قیمت و درخواست موجودی انبار
@router.message(ProductWizard.price)
async def process_price(message: Message, state: FSMContext):
    try:
        # بررسی اینکه کاربر حتماً عدد فرستاده باشد
        price = int(message.text.replace(",", "")) 
        await state.update_data(price=str(price))
        await state.set_state(ProductWizard.stock)
        await message.answer("📦 **موجودی انبار** را وارد کنید (فقط عدد، مثلاً 10):")
    except ValueError:
        await message.answer("❌ لطفاً قیمت را فقط به صورت عدد وارد کنید!")

# مرحله ۵: دریافت موجودی و ثبت نهایی در سایت
@router.message(ProductWizard.stock)
async def process_stock(message: Message, state: FSMContext):
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer("❌ لطفاً موجودی را فقط به صورت عدد وارد کنید!")
        return

    await state.update_data(stock=stock)
    data = await state.get_data()
    
    wait_msg = await message.answer("⏳ در حال ثبت محصول با جزئیات کامل در سایت...")
    
    try:
        product_data = {
            "name": data['name'],
            "type": "simple",
            "short_description": data['short_description'],
            "description": data['long_description'],
            "regular_price": data['price'],
            "manage_stock": True,
            "stock_quantity": data['stock'],
            "status": "draft" # فعلاً همچنان پیش‌نویس ثبت می‌کنیم
        }
        
        result = await wc_service.create_simple_product(product_data)
        
        text = (
            "✅ **محصول با موفقیت در سایت ثبت شد!**\n\n"
            f"🏷 **نام:** {result['name']}\n"
            f"💰 **قیمت:** {result.get('price', '0')} تومان\n"
            f"📦 **موجودی:** {data['stock']} عدد\n"
            f"🔗 **آیدی در سایت:** {result['id']}"
        )
        await wait_msg.edit_text(text)
        await state.clear()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت محصول:\n{str(e)[:500]}")
        await state.clear()
