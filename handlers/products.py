from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from states.product_states import ProductWizard
from services.woocommerce import WooCommerceService

router = Router()
wc_service = WooCommerceService()

# ==========================================
# کیبورد داشبورد شیشه‌ای
# ==========================================
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

# ==========================================
# شروع عملیات ثبت محصول
# ==========================================
@router.message(F.text == "➕ محصول جدید")
async def start_product_wizard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ProductWizard.waiting_for_name)
    await message.answer("🛒 **ساخت محصول جدید**\n\nلطفاً فقط **نام محصول** را وارد کنید (مثلاً کاسه سفالی میناکاری):")

@router.message(F.text == "/cancel")
async def cancel_wizard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ عملیات لغو شد.")

@router.message(ProductWizard.waiting_for_name)
async def process_initial_name(message: Message, state: FSMContext):
    product_name = message.text
    wait_msg = await message.answer("⏳ در حال ایجاد فضای پیش‌نویس در سایت...")
    try:
        product_data = {"name": product_name, "type": "simple", "status": "draft"}
        result = await wc_service.create_simple_product(product_data)
        product_id = result['id']
        text = (
            f"📦 **محصول ایجاد شد (پیش‌نویس)**\n\n"
            f"🏷 **نام:** {product_name}\n"
            f"🆔 **آیدی:** {product_id}\n\n"
            f"👇 حالا از پنل زیر، هر بخشی را که می‌خواهید تکمیل کنید:"
        )
        await wait_msg.edit_text(text, reply_markup=get_dashboard_keyboard(product_id, product_name))
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ساخت پیش‌نویس:\n{str(e)[:500]}")
        await state.clear()

# ==========================================
# مدیریت دکمه‌های انتشار و حذف
# ==========================================
@router.callback_query(F.data.startswith("publish_"))
async def process_publish(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    await callback.message.edit_text("⏳ در حال انتشار روی سایت...")
    try:
        result = await wc_service.update_product(product_id, {"status": "publish"})
        await callback.message.edit_text(
            f"✅ **محصول با موفقیت در سایت منتشر شد! 🎉**\n\n"
            f"🌐 [برای مشاهده صفحه محصول کلیک کنید]({result['permalink']})",
            parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا در انتشار:\n{str(e)[:500]}")

@router.callback_query(F.data.startswith("delete_"))
async def process_delete(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    await callback.message.edit_text("⏳ در حال انتقال به زباله‌دان...")
    try:
        await wc_service.delete_product(product_id)
        await callback.message.edit_text(f"🗑 محصول با موفقیت به زباله‌دان سایت منتقل شد.")
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا در حذف:\n{str(e)[:500]}")

# ==========================================
# سیستم پیشرفته دسته‌بندی (چندتایی + اصلی) 📂
# ==========================================
@router.callback_query(F.data.startswith("edit_cat_"))
async def start_edit_cat(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    wait_msg = await callback.message.edit_text("⏳ در حال دریافت لیست دسته‌بندی‌ها از سایت...")
    try:
        categories = await wc_service.get_categories()
        # ذخیره لیست دسته‌ها در حافظه و شروع با لیست خالی انتخاب‌ها
        await state.update_data(product_id=product_id, all_cats=categories, selected_cats=[])
        
        builder = InlineKeyboardBuilder()
        for cat in categories:
            builder.button(text=f"[ ] {cat['name']}", callback_data=f"togglecat_{cat['id']}")
        
        builder.button(text="✅ تایید و ادامه انتخاب دسته اصلی ➡️", callback_data="finish_cat_selection")
        builder.button(text="🔙 بازگشت", callback_data=f"backdash_{product_id}")
        builder.adjust(1) # هر دسته در یک خط برای خوانایی بهتر چک‌باکس‌ها
        
        await wait_msg.edit_text(
            "📂 **انتخاب دسته‌بندی‌ها:**\n\n"
            "روی هر دسته کلیک کنید تا انتخاب شود (تیک بخورد). پس از اتمام، روی دکمه تایید کلیک کنید:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در دریافت دسته‌بندی:\n{str(e)[:500]}")

@router.callback_query(F.data.startswith("togglecat_"))
async def process_toggle_cat(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    selected = data.get("selected_cats", [])
    all_cats = data.get("all_cats", [])
    product_id = data.get("product_id")
    
    if cat_id in selected:
        selected.remove(cat_id)
    else:
        selected.append(cat_id)
        
    await state.update_data(selected_cats=selected)
    
    # بازسازی کیبورد با آپدیت وضعیت تیک‌ها
    builder = InlineKeyboardBuilder()
    for cat in all_cats:
        status = "✅" if cat['id'] in selected else "[ ]"
        builder.button(text=f"{status} {cat['name']}", callback_data=f"togglecat_{cat['id']}")
        
    builder.button(text="✅ تایید و ادامه انتخاب دسته اصلی ➡️", callback_data="finish_cat_selection")
    builder.button(text="🔙 بازگشت", callback_data=f"backdash_{product_id}")
    builder.adjust(1)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except:
        pass
    await callback.answer()

@router.callback_query(F.data == "finish_cat_selection")
async def process_finish_cat_selection(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_cats", [])
    product_id = data.get("product_id")
    all_cats = data.get("all_cats", [])
    
    if not selected:
        await callback.answer("❌ لطفاً حداقل یک دسته‌بندی انتخاب کنید!", show_alert=True)
        return
        
    # مرحله دوم: انتخاب دسته اصلی (Primary) از بین دسته‌های انتخاب شده
    builder = InlineKeyboardBuilder()
    for cat in all_cats:
        if cat['id'] in selected:
            builder.button(text=cat['name'], callback_data=f"setprimary_{cat['id']}")
            
    builder.adjust(1)
    await callback.message.edit_text(
        "⭐ حالا **دسته اصلی (Primary)** این محصول را از بین موارد انتخاب‌شده مشخص کنید:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("setprimary_"))
async def process_set_primary_cat(callback: CallbackQuery, state: FSMContext):
    primary_cat_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    product_id = data.get("product_id")
    selected_cats = data.get("selected_cats", [])
    
    wait_msg = await callback.message.edit_text("⏳ در حال ثبت دسته‌بندی‌ها و دسته اصلی در سایت...")
    try:
        # ساخت ساختار دسته‌ها برای ووکامرس
        categories_payload = [{"id": cid} for cid in selected_cats]
        
        update_data = {
            "categories": categories_payload,
            "meta_data": [
                {"key": "_yoast_wpseo_primary_product_cat", "value": str(primary_cat_id)},
                {"key": "rank_math_primary_product_cat", "value": str(primary_cat_id)}
            ]
        }
        
        await wc_service.update_product(product_id, update_data)
        product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **دسته‌بندی‌ها و دسته اصلی با موفقیت ثبت شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت دسته‌بندی:\n{str(e)[:500]}")
        await state.clear()

@router.callback_query(F.data.startswith("backdash_"))
async def process_backdash(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
    await state.clear()
    wait_msg = await callback.message.edit_text("⏳ در حال بازگشت...")
    try:
        product = await wc_service.get_product(product_id)
        await wait_msg.edit_text(
            f"👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
    except:
        pass

# ==========================================
# دکمه: تنظیمات سئو 🔍 (Rank Math)
# ==========================================
@router.callback_query(F.data.startswith("edit_seo_"))
async def start_edit_seo(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_seo_keyword)
    await callback.message.answer("🔍 **تنظیمات سئو (Rank Math)**\n\nابتدا **کلمه کلیدی اصلی** (Focus Keyword) را وارد کنید:")
    await callback.answer()

@router.message(ProductWizard.waiting_for_seo_keyword)
async def process_seo_keyword(message: Message, state: FSMContext):
    await state.update_data(seo_keyword=message.text)
    await state.set_state(ProductWizard.waiting_for_seo_title)
    await message.answer("📝 بسیار عالی. حالا **عنوان سئو (SEO Title)** را بفرستید:")

@router.message(ProductWizard.waiting_for_seo_title)
async def process_seo_title(message: Message, state: FSMContext):
    await state.update_data(seo_title=message.text)
    await state.set_state(ProductWizard.waiting_for_seo_desc)
    await message.answer("📄 در نهایت، **توضیحات متا (Meta Description)** را بفرستید:")

@router.message(ProductWizard.waiting_for_seo_desc)
async def process_seo_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id, keyword, title, desc = data['product_id'], data['seo_keyword'], data['seo_title'], message.text
    wait_msg = await message.answer("⏳ در حال ثبت اطلاعات سئو در سایت...")
    try:
        meta_data = [
            {"key": "rank_math_focus_keyword", "value": keyword},
            {"key": "rank_math_title", "value": title},
            {"key": "rank_math_description", "value": desc}
        ]
        await wc_service.update_product(product_id, {"meta_data": meta_data})
        product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **اطلاعات سئو با موفقیت در Rank Math ذخیره شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت سئو:\n{str(e)[:500]}")
        await state.clear()

# ==========================================
# دکمه: تصویر اصلی 🖼
# ==========================================
@router.callback_query(F.data.startswith("edit_img_"))
async def start_edit_img(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_image)
    await callback.message.answer("🖼 لطفاً **عکس محصول** را ارسال کنید (به صورت Photo/تصویر عادی بفرستید):")
    await callback.answer()

@router.message(ProductWizard.waiting_for_image, F.photo)
async def process_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    product_id = data['product_id']
    wait_msg = await message.answer("⏳ در حال انتقال تصویر به رسانه سایت (لطفاً کمی صبر کنید)...")
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        product = await wc_service.get_product(product_id)
        update_data = {"images": [{"src": file_url, "name": f"تصویر {product['name']}"}]}
        await wc_service.update_product(product_id, update_data)
        
        await wait_msg.edit_text(
            f"✅ **تصویر با موفقیت در سایت آپلود و روی محصول تنظیم شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در آپلود عکس:\n{str(e)[:500]}")
        await state.clear()

@router.message(ProductWizard.waiting_for_image)
async def process_image_invalid(message: Message):
    await message.answer("❌ لطفاً یک عکس معتبر ارسال کنید (از ارسال فایل یا متن خودداری کنید).")

# ==========================================
# دکمه: توضیحات 📝
# ==========================================
@router.callback_query(F.data.startswith("edit_desc_"))
async def start_edit_desc(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_short_desc)
    await callback.message.answer("📝 لطفاً **توضیحات کوتاه** محصول را بفرستید:\n(این متن معمولاً کنار عکس قرار می‌گیرد)")
    await callback.answer()

@router.message(ProductWizard.waiting_for_short_desc)
async def process_short_desc(message: Message, state: FSMContext):
    html_text = message.html_text.replace("\n", "<br>")
    await state.update_data(short_desc=html_text)
    await state.set_state(ProductWizard.waiting_for_long_desc)
    await message.answer("📄 بسیار عالی. حالا **توضیحات کامل** محصول را بفرستید:")

@router.message(ProductWizard.waiting_for_long_desc)
async def process_long_desc(message: Message, state: FSMContext):
    html_text = message.html_text.replace("\n", "<br>")
    data = await state.get_data()
    product_id = data['product_id']
    wait_msg = await message.answer("⏳ در حال ثبت توضیحات در سایت...")
    try:
        update_data = {"short_description": data['short_desc'], "description": html_text}
        await wc_service.update_product(product_id, update_data)
        product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **توضیحات محصول ذخیره شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت توضیحات:\n{str(e)[:500]}")
        await state.clear()

# ==========================================
# دکمه: قیمت و موجودی 💰
# ==========================================
@router.callback_query(F.data.startswith("edit_price_"))
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_price)
    await callback.message.answer("💰 لطفاً **قیمت اصلی محصول** را به تومان وارد کنید (فقط عدد انگلیسی، مثلاً 850000):")
    await callback.answer()

@router.message(ProductWizard.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ لطفاً قیمت را فقط به صورت عدد وارد کنید!")
        return
    await state.update_data(price=message.text)
    await state.set_state(ProductWizard.waiting_for_stock)
    await message.answer("📦 حالا **موجودی انبار** را وارد کنید (فقط عدد، مثلاً 10):")

@router.message(ProductWizard.waiting_for_stock)
async def process_stock(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ لطفاً موجودی را فقط به صورت عدد وارد کنید!")
        return
    data = await state.get_data()
    product_id, price, stock = data['product_id'], data['price'], int(message.text)
    wait_msg = await message.answer("⏳ در حال ثبت قیمت و موجودی در سایت...")
    try:
        update_data = {"regular_price": str(price), "manage_stock": True, "stock_quantity": stock}
        await wc_service.update_product(product_id, update_data)
        product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **قیمت و موجودی تنظیم شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در تنظیم قیمت:\n{str(e)[:500]}")
        await state.clear()
