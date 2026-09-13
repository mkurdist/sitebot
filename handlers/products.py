from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from states.product_states import ProductWizard
from services.woocommerce import WooCommerceService

router = Router()
wc_service = WooCommerceService()

# ==========================================
# کیبورد داشبورد شیشه‌ای (ارتقا یافته با گالری)
# ==========================================
def get_dashboard_keyboard(product_id: int, product_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 توضیحات", callback_data=f"edit_desc_{product_id}"),
            InlineKeyboardButton(text="🖼 تصویر اصلی", callback_data=f"edit_img_{product_id}")
        ],
        [
            InlineKeyboardButton(text="🗂 گالری تصاویر", callback_data=f"edit_gallery_{product_id}"),
            InlineKeyboardButton(text="📂 دسته‌بندی", callback_data=f"edit_cat_{product_id}")
        ],
        [
            InlineKeyboardButton(text="💰 قیمت و موجودی", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="🔍 تنظیمات سئو", callback_data=f"edit_seo_{product_id}")
        ],
        [
            InlineKeyboardButton(text="✅ انتشار نهایی", callback_data=f"publish_{product_id}"),
            InlineKeyboardButton(text="❌ حذف", callback_data=f"delete_{product_id}")
        ]
    ])

# ==========================================
# شروع عملیات ثبت محصول (محافظت‌شده با سیستم نگهبان)
# ==========================================
@router.message(F.text == "➕ محصول جدید")
async def start_product_wizard(message: Message, state: FSMContext):
    data = await state.get_data()
    active_product_id = data.get("product_id")
    active_product_name = data.get("product_name")

    # اگر کاربر محصول نیمه‌کاره‌ای در حافظه داشت، به او هشدار می‌دهیم
    if active_product_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 ادامه ویرایش قبلی", callback_data=f"resume_prod_{active_product_id}"),
                InlineKeyboardButton(text="➕ ساخت جدید", callback_data="force_new_prod")
            ]
        ])
        await message.answer(
            f"⚠️ **شما یک محصول در حال ویرایش دارید!**\n\n"
            f"🏷 نام: {active_product_name or 'بدون نام'}\n"
            f"🆔 آیدی: {active_product_id}\n\n"
            f"می‌خواهید کار روی این محصول را ادامه دهید یا محصول جدیدی بسازید؟",
            reply_markup=keyboard
        )
        return

    # در غیر این صورت مستقیماً مراحل ساخت جدید شروع می‌شود
    await state.clear()
    await state.set_state(ProductWizard.waiting_for_name)
    await message.answer("🛒 **ساخت محصول جدید**\n\nلطفاً فقط **نام محصول** را وارد کنید (مثلاً کاسه سفالی میناکاری):")

@router.callback_query(F.data == "force_new_prod")
async def force_new_product(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ProductWizard.waiting_for_name)
    await callback.message.edit_text("🛒 **ساخت محصول جدید**\n\nلطفاً فقط **نام محصول** را وارد کنید (مثلاً کاسه سفالی میناکاری):")
    await callback.answer()

@router.callback_query(F.data.startswith("resume_prod_"))
async def resume_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    try:
        product = await wc_service.get_product(product_id)
        await state.update_data(product_id=product_id, product_name=product['name'])
        await callback.message.edit_text(
            f"📦 **بازگشت به ویرایش محصول**\n\n"
            f"🏷 **نام:** {product['name']}\n"
            f"🆔 **آیدی:** {product_id}\n\n"
            f"👇 از پنل زیر استفاده کنید:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا در بازیابی محصول:\n{str(e)[:500]}")
    await callback.answer()

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
        
        # ذخیره آیدی و نام در State برای محافظت در برابر گم شدن
        await state.update_data(product_id=product_id, product_name=product_name)
        
        text = (
            f"📦 **محصول ایجاد شد (پیش‌نویس)**\n\n"
            f"🏷 **نام:** {product_name}\n"
            f"🆔 **آیدی:** {product_id}\n\n"
            f"👇 حالا از پنل زیر، هر بخشی را که می‌خواهید تکمیل کنید:"
        )
        await wait_msg.edit_text(text, reply_markup=get_dashboard_keyboard(product_id, product_name))
        
        # نکته: state رو کامل پاک نمی‌کنیم تا product_id و product_name برای دکمه‌های شیشه‌ای ذخیره بماند
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ساخت پیش‌نویس:\n{str(e)[:500]}")
        await state.clear()

# ==========================================
# مدیریت دکمه‌های انتشار و حذف
# ==========================================
@router.callback_query(F.data.startswith("publish_"))
async def process_publish(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
    await callback.message.edit_text("⏳ در حال انتشار روی سایت...")
    try:
        result = await wc_service.update_product(product_id, {"status": "publish"})
        await state.clear() # با انتشار موفق، حافظه موقت پاک می‌شود
        await callback.message.edit_text(
            f"✅ **محصول با موفقیت در سایت منتشر شد! 🎉**\n\n"
            f"🌐 [برای مشاهده صفحه محصول کلیک کنید]({result['permalink']})",
            parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا در انتشار:\n{str(e)[:500]}")

@router.callback_query(F.data.startswith("delete_"))
async def process_delete(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
    await callback.message.edit_text("⏳ در حال انتقال به زباله‌دان...")
    try:
        await wc_service.delete_product(product_id)
        await state.clear() # با حذف محصول، حافظه موقت پاک می‌شود
        await callback.message.edit_text(f"🗑 محصول با موفقیت به زباله‌دان سایت منتقل شد.")
    except Exception as e:
        await callback.message.edit_text(f"❌ خطا در حذف:\n{str(e)[:500]}")

# ==========================================
# دکمه: گالری تصاویر 🗂 (نسخه اصلاح‌شده برای اتصال دقیق آیدی به گالری ووکامرس)
# ==========================================
@router.callback_query(F.data.startswith("edit_gallery_"))
async def start_edit_gallery(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_gallery_image)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 اتمام و بازگشت به داشبورد", callback_data=f"finish_gallery_{product_id}")]
    ])
    
    await callback.message.answer(
        "🗂 **افزودن تصویر به گالری محصول**\n\n"
        "لطفاً عکس مورد نظر گالری را بفرستید (عکس معمولی یا فایل WebP).\n"
        "می‌توانید چند عکس به نوبت بفرستید و در نهایت روی دکمه اتمام کلیک کنید:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(ProductWizard.waiting_for_gallery_image, F.photo | F.document)
async def process_gallery_image_file(message: Message, state: FSMContext):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        doc = message.document
        if doc.mime_type and "image" in doc.mime_type or doc.file_name.lower().endswith(('.webp', '.png', '.jpg', '.jpeg')):
            file_id = doc.file_id
            
    if not file_id:
        await message.answer("❌ فرمت فایل ارسالی معتبر نیست. لطفاً یک تصویر ارسال کنید.")
        return

    await state.update_data(gallery_file_id=file_id)
    await state.set_state(ProductWizard.waiting_for_gallery_alt)
    await message.answer("📝 لطفاً **متن جایگزین (Alt Text)** این عکس گالری را وارد کنید:")

@router.message(ProductWizard.waiting_for_gallery_image)
async def process_gallery_image_invalid(message: Message):
    await message.answer("❌ لطفاً یک تصویر یا فایل تصویری معتبر بفرستید.")

@router.message(ProductWizard.waiting_for_gallery_alt)
async def process_gallery_alt(message: Message, state: FSMContext):
    await state.update_data(gallery_alt=message.text)
    await state.set_state(ProductWizard.waiting_for_gallery_title)
    await message.answer("🏷 حالا **عنوان تصویر (Title)** این عکس گالری را وارد کنید:")

@router.message(ProductWizard.waiting_for_gallery_title)
async def process_gallery_title(message: Message, state: FSMContext, bot: Bot):
    title_text = message.text
    data = await state.get_data()
    product_id = data['product_id']
    file_id = data['gallery_file_id']
    alt_text = data['gallery_alt']
    
    wait_msg = await message.answer("⏳ در حال آپلود و اتصال به گالری محصول...")
    try:
        file_info = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        product = await wc_service.get_product(product_id)
        existing_gallery_ids = product.get('gallery_image_ids', [])
        
        current_images = product.get('images', [])
        new_img_payload = {
            "src": file_url,
            "name": title_text,
            "alt": alt_text
        }
        current_images.append(new_img_payload)
        
        update_res = await wc_service.update_product(product_id, {"images": current_images})
        updated_images = update_res.get('images', [])
        if updated_images:
            new_image_id = updated_images[-1].get('id')
            if new_image_id and new_image_id not in existing_gallery_ids:
                existing_gallery_ids.append(new_image_id)
                
            main_image = current_images[0] if current_images else None
            final_images_payload = [main_image] if main_image else []
            
            await wc_service.update_product(product_id, {
                "images": final_images_payload,
                "gallery_image_ids": existing_gallery_ids
            })

        await state.set_state(ProductWizard.waiting_for_gallery_image)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 اتمام و بازگشت به داشبورد", callback_data=f"finish_gallery_{product_id}")]
        ])
        
        await wait_msg.edit_text(
            f"✅ **عکس با موفقیت به گالری محصول متصل شد!**\n\n"
            f"اگر عکس دیگری برای گالری دارید بفرستید، در غیر این صورت روی دکمه زیر کلیک کنید:",
            reply_markup=keyboard
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت گالری:\n{str(e)[:500]}")
        await state.set_state(ProductWizard.waiting_for_gallery_image)

@router.callback_query(F.data.startswith("finish_gallery_"))
async def finish_gallery_selection(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    wait_msg = await callback.message.edit_text("⏳ در حال بارگذاری داشبورد...")
    try:
        product = await wc_service.get_product(product_id)
        await wait_msg.edit_text(
            f"✅ **گالری تصاویر به‌روزرسانی شد.**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
    except:
        pass

# ==========================================
# دکمه: تصویر اصلی 🖼 (با پشتیبانی WebP و Alt/Title)
# ==========================================
@router.callback_query(F.data.startswith("edit_img_"))
async def start_edit_img(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_image)
    await callback.message.answer(
        "🖼 **آپلود تصویر اصلی**\n\n"
        "لطفاً تصویر خود را بفرستید (عکس معمولی یا فایل WebP):"
    )
    await callback.answer()

@router.message(ProductWizard.waiting_for_image, F.photo | F.document)
async def process_image_file(message: Message, state: FSMContext, bot: Bot):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        doc = message.document
        if doc.mime_type and "image" in doc.mime_type or doc.file_name.lower().endswith(('.webp', '.png', '.jpg', '.jpeg')):
            file_id = doc.file_id
            
    if not file_id:
        await message.answer("❌ فرمت فایل ارسالی معتبر نیست. لطفاً یک تصویر ارسال کنید.")
        return

    await state.update_data(file_id=file_id)
    await state.set_state(ProductWizard.waiting_for_image_alt)
    await message.answer("📝 لطفاً **متن جایگزین (Alt Text)** تصویر اصلی را وارد کنید:")

@router.message(ProductWizard.waiting_for_image)
async def process_image_invalid(message: Message):
    await message.answer("❌ لطفاً حتماً یک تصویر یا فایل تصویری ارسال کنید.")

@router.message(ProductWizard.waiting_for_image_alt)
async def process_image_alt(message: Message, state: FSMContext):
    await state.update_data(alt_text=message.text)
    await state.set_state(ProductWizard.waiting_for_image_title)
    await message.answer("🏷 حالا **عنوان تصویر (Title)** تصویر اصلی را وارد کنید:")

@router.message(ProductWizard.waiting_for_image_title)
async def process_image_title(message: Message, state: FSMContext, bot: Bot):
    title_text = message.text
    data = await state.get_data()
    product_id = data['product_id']
    file_id = data['file_id']
    alt_text = data['alt_text']
    
    wait_msg = await message.answer("⏳ در حال آپلود تصویر در سایت...")
    try:
        file_info = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        product = await wc_service.get_product(product_id)
        existing_images = product.get('images', [])
        
        main_image = {
            "src": file_url,
            "name": title_text,
            "alt": alt_text
        }
        
        if existing_images:
            existing_images[0] = main_image
        else:
            existing_images = [main_image]
            
        update_data = {"images": existing_images}
        
        await wc_service.update_product(product_id, update_data)
        updated_product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **تصویر اصلی با مشخصات کامل ثبت شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, updated_product['name'])
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت تصویر:\n{str(e)[:500]}")

# ==========================================
# دکمه: تنظیمات سئو 🔍 (Rank Math پیشرفته + Slug)
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
    await state.set_state(ProductWizard.waiting_for_seo_slug)
    await message.answer("🔗 حالا **پیوند دایمی (Slug / نامک)** را وارد کنید (مثلاً `blue-ceramic-bowl`):")

@router.message(ProductWizard.waiting_for_seo_slug)
async def process_seo_slug(message: Message, state: FSMContext):
    await state.update_data(seo_slug=message.text)
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
    product_id = data['product_id']
    keyword = data['seo_keyword']
    slug = data['seo_slug']
    title = data['seo_title']
    desc = message.text
    
    wait_msg = await message.answer("⏳ در حال ثبت اطلاعات سئو و پیوند دایمی در سایت...")
    try:
        meta_data = [
            {"key": "rank_math_focus_keyword", "value": keyword},
            {"key": "rank_math_title", "value": title},
            {"key": "rank_math_description", "value": desc}
        ]
        
        update_payload = {
            "slug": slug,
            "meta_data": meta_data
        }
        
        await wc_service.update_product(product_id, update_payload)
        product = await wc_service.get_product(product_id)
        
        await wait_msg.edit_text(
            f"✅ **اطلاعات سئو و پیوند دایمی با موفقیت ثبت شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت سئو:\n{str(e)[:500]}")

# ==========================================
# دکمه: دسته‌بندی 📂 (چندتایی + اصلی)
# ==========================================
@router.callback_query(F.data.startswith("edit_cat_"))
async def start_edit_cat(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    wait_msg = await callback.message.edit_text("⏳ در حال دریافت لیست دسته‌بندی‌ها از سایت...")
    try:
        categories = await wc_service.get_categories()
        await state.update_data(product_id=product_id, all_cats=categories, selected_cats=[])
        
        builder = InlineKeyboardBuilder()
        for cat in categories:
            builder.button(text=f"[ ] {cat['name']}", callback_data=f"togglecat_{cat['id']}")
        
        builder.button(text="✅ تایید و ادامه انتخاب دسته اصلی ➡️", callback_data="finish_cat_selection")
        builder.button(text="🔙 بازگشت", callback_data=f"backdash_{product_id}")
        builder.adjust(1)
        
        await wait_msg.edit_text(
            "📂 **انتخاب دسته‌بندی‌ها:**\n\n"
            "روی هر دسته کلیک کنید تا انتخاب شود. پس از اتمام، روی دکمه تایید کلیک کنید:",
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
        
    builder = InlineKeyboardBuilder()
    for cat in all_cats:
        if cat['id'] in selected:
            builder.button(text=cat['name'], callback_data=f"setprimary_{cat['id']}")
            
    builder.adjust(1)
    await callback.message.edit_text(
        "⭐ حالا **دسته اصلی (Primary)** این محصول را مشخص کنید:",
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
            f"✅ **دسته‌بندی‌ها ثبت شد!**\n\n👇 داشبورد محصول:",
            reply_markup=get_dashboard_keyboard(product_id, product['name'])
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت دسته‌بندی:\n{str(e)[:500]}")

@router.callback_query(F.data.startswith("backdash_"))
async def process_backdash(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
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
# دکمه: توضیحات 📝
# ==========================================
@router.callback_query(F.data.startswith("edit_desc_"))
async def start_edit_desc(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_short_desc)
    await callback.message.answer("📝 لطفاً **توضیحات کوتاه** محصول را بفرستید:")
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
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ثبت توضیحات:\n{str(e)[:500]}")

# ==========================================
# دکمه: قیمت و موجودی 💰
# ==========================================
@router.callback_query(F.data.startswith("edit_price_"))
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(ProductWizard.waiting_for_price)
    await callback.message.answer("💰 لطفاً **قیمت اصلی محصول** را به تومان وارد کنید (فقط عدد):")
    await callback.answer()

@router.message(ProductWizard.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ لطفاً قیمت را فقط به صورت عدد وارد کنید!")
        return
    await state.update_data(price=message.text)
    await state.set_state(ProductWizard.waiting_for_stock)
    await message.answer("📦 حالا **موجودی انبار** را وارد کنید (فقط عدد):")

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
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در تنظیم قیمت:\n{str(e)[:500]}")
