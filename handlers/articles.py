import re
import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states.article_states import ArticleWizard

# استفاده از نشست یکتا و ایمن وردپرس
from services.wordpress import wp_service_instance as wp_service

router = Router()

@router.message(F.text == "📝 مقاله جدید")
async def start_article_wizard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ArticleWizard.waiting_for_article_text)
    await state.update_data(article_buffer="")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پردازش ۵ کادر و ادامه", callback_data="process_article_buffer")]
    ])
    
    instruction = (
        "📝 <b>سیستم انتشار هوشمند مقاله (وبلاگ)</b>\n\n"
        "متن مقاله تولید شده توسط AI را اینجا Paste کنید.\n"
        "<i>(نکته: اگر مقاله طولانی است، آن را در چند پیام بفرستید)</i>\n\n"
        "<b>فرمت استاندارد جدید برای هوش مصنوعی:</b>\n"
        "۱. کادر عنوان مقاله:\n"
        "۲. کادر پیوند یکتا (Slug):\n"
        "۳. کادر کلمه کلیدی:\n"
        "۴. کادر توضیحات متا:\n"
        "۵. کادر محتوای مقاله:\n\n"
        "پس از ارسال تمام بخش‌ها، روی دکمه زیر کلیک کنید:"
    )
    await message.answer(instruction, reply_markup=keyboard, parse_mode="HTML")

@router.message(ArticleWizard.waiting_for_article_text)
async def accumulate_article_text(message: Message, state: FSMContext):
    data = await state.get_data()
    current_buffer = data.get("article_buffer", "")
    new_buffer = current_buffer + "\n\n" + message.text
    await state.update_data(article_buffer=new_buffer)
    
    await message.answer("📥 <i>متن دریافت شد. اگر ادامه دارد بفرستید، در غیر این صورت دکمه «پردازش ۵ کادر و ادامه» در پیام بالا را بزنید.</i>", parse_mode="HTML")

@router.callback_query(F.data == "process_article_buffer")
async def process_article(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("article_buffer", "")
    
    if not text.strip():
        await callback.answer("❌ هنوز هیچ متنی نفرستاده‌اید!", show_alert=True)
        return

    wait_msg = await callback.message.answer("⏳ در حال تحلیل متن، اعمال استایل‌ها و ساخت پیش‌نویس در سایت...")
    
    try:
        # استخراج ۵ کادر با Regex
        title_match = re.search(r'۱\.\s*کادر عنوان مقاله:?\s*\n(.*?)(?=\n۲\.)', text, re.DOTALL)
        slug_match = re.search(r'۲\.\s*کادر پیوند یکتا.*?:?\s*\n(.*?)(?=\n۳\.)', text, re.DOTALL)
        kw_match = re.search(r'۳\.\s*کادر کلمه کلیدی:?\s*\n(.*?)(?=\n۴\.)', text, re.DOTALL)
        desc_match = re.search(r'۴\.\s*کادر توضیحات متا:?\s*\n(.*?)(?=\n۵\.)', text, re.DOTALL)
        content_match = re.search(r'۵\.\s*کادر محتوای مقاله:?\s*\n(.*)', text, re.DOTALL)
        
        post_title = title_match.group(1).strip() if title_match else "مقاله جدید"
        post_slug = slug_match.group(1).strip() if slug_match else ""
        focus_kw = kw_match.group(1).strip() if kw_match else ""
        meta_desc = desc_match.group(1).strip() if desc_match else ""
        raw_content = content_match.group(1).strip() if content_match else text
        
        # اعمال استایل‌های خودکار (جادوی سئو و ظاهر)
        formatted_content = raw_content.replace('\n', '<br>')
        formatted_content = re.sub(r'\srel="[^"]*"', '', formatted_content)
        formatted_content = re.sub(r'\starget="[^"]*"', '', formatted_content)
        formatted_content = formatted_content.replace('<a ', '<a rel="nofollow" target="_blank" ')
        
        final_html_content = (
            f'<div style="text-align: justify; text-justify: inter-word; direction: rtl;">\n'
            f'{formatted_content}\n'
            f'</div>'
        )

        meta_data = {}
        if focus_kw: meta_data["rank_math_focus_keyword"] = focus_kw
        if meta_desc: meta_data["rank_math_description"] = meta_desc

        payload = {
            "title": post_title,
            "content": final_html_content,
            "status": "draft",
        }
        if post_slug: payload["slug"] = post_slug
        if meta_data: payload["meta"] = meta_data
        
        result = await wp_service.create_post(payload)
        post_id = result['id']
        post_link = result.get('link', '')
        
        # ذخیره اطلاعات برای آپلود عکس
        await state.update_data(
            post_id=post_id,
            post_title=post_title,
            post_link=post_link,
            focus_kw=focus_kw
        )
        await state.set_state(ArticleWizard.waiting_for_featured_image)
        
        success_msg = (
            f"✅ <b>متن، سئو و استایل‌ها با موفقیت در سایت پیش‌نویس شد!</b>\n\n"
            f"🖼 حالا لطفاً <b>تصویر شاخص (عکس اصلی)</b> مقاله را ارسال کنید (به صورت عکس یا فایل):"
        )
        await wait_msg.edit_text(success_msg, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در پردازش و ایجاد مقاله:\n<code>{str(e)[:500]}</code>", parse_mode="HTML")
        await state.clear()
        await callback.answer()

# ==========================================
# سیستم آپلود عکس، نام‌گذاری سئوشده و Alt
# ==========================================
@router.message(ArticleWizard.waiting_for_featured_image, F.photo | F.document)
async def process_featured_image(message: Message, state: FSMContext):
    file_id = None
    ext = "jpg" # پسوند پیش‌فرض
    
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
        if message.document.file_name:
            ext = message.document.file_name.split('.')[-1].lower()
            
    if not file_id:
        await message.answer("❌ فایل نامعتبر! لطفاً یک عکس معتبر ارسال کنید.")
        return

    await state.update_data(image_file_id=file_id, image_ext=ext)
    await state.set_state(ArticleWizard.waiting_for_image_alt)
    await message.answer("📝 بسیار عالی. لطفاً <b>متن جایگزین (Alt Text)</b> تصویر را برای سئو وارد کنید:", parse_mode="HTML")

@router.message(ArticleWizard.waiting_for_image_alt)
async def process_image_alt(message: Message, state: FSMContext):
    await state.update_data(image_alt=message.text)
    await state.set_state(ArticleWizard.waiting_for_image_title)
    await message.answer("🏷 حالا <b>عنوان (Title)</b> این عکس را وارد کنید:", parse_mode="HTML")

@router.message(ArticleWizard.waiting_for_image_title)
async def process_image_title(message: Message, state: FSMContext, bot: Bot):
    image_title = message.text
    data = await state.get_data()
    
    post_id = data['post_id']
    file_id = data['image_file_id']
    ext = data['image_ext']
    alt_text = data['image_alt']
    post_title = data['post_title']
    post_link = data['post_link']
    kw = data.get('focus_kw', '').strip()
    
    wait_msg = await message.answer("⏳ در حال دانلود تصویر، اعمال نام‌گذاری سئو و آپلود در سایت...")
    
    try:
        # ۱. بهینه‌سازی نام فایل بر اساس کلمه کلیدی
        if not kw:
            kw = f"citysofal-article-{post_id}"
            
        # جایگزینی فاصله‌ها و آندرلاین‌ها با خط تیره (Dash)
        kw_slug = re.sub(r'[\s_]+', '-', kw)
        
        file_info = await bot.get_file(file_id)
        # خروجی نهایی: مثلا خرید-گلدان-سفالی-Ab2c.webp
        seo_filename = f"{kw_slug}-{file_info.file_unique_id[-4:]}.{ext}" 
        
        # ۲. دانلود عکس در حافظه رم
        file_bytes = io.BytesIO()
        await bot.download_file(file_info.file_path, file_bytes)
        
        # ۳. آپلود در رسانه سایت
        media_id = await wp_service.upload_media(file_bytes.getvalue(), seo_filename, alt_text, image_title)
        
        # ۴. اتصال عکس به عنوان تصویر شاخص مقاله
        await wp_service.update_post(post_id, {"featured_media": media_id})
        
        success_msg = (
            f"🎉 <b>جادوی سئوی تصویر انجام شد!</b>\n\n"
            f"📂 <b>نام فایل سئوشده:</b> <code>{seo_filename}</code>\n"
            f"🏷 <b>عنوان مقاله:</b> {post_title}\n"
            f"🌐 <a href='{post_link}'>لینک پیش‌نمایش در سایت</a>\n\n"
            f"<i>نکته: مقاله به همراه تمامی تنظیمات در وضعیت پیش‌نویس قرار گرفت.</i>"
        )
        await wait_msg.edit_text(success_msg, parse_mode="HTML", disable_web_page_preview=True)
        await state.clear()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در آپلود تصویر شاخص:\n<code>{str(e)[:500]}</code>", parse_mode="HTML")
        await state.clear()
