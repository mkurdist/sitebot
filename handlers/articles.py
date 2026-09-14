import re
from aiogram import Router, F
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
        [InlineKeyboardButton(text="✅ پردازش ۵ کادر و ثبت اولیه", callback_data="process_article_buffer")]
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
    
    await message.answer("📥 <i>متن دریافت شد. اگر ادامه دارد بفرستید، در غیر این صورت دکمه «پردازش ۵ کادر» در پیام بالا را بزنید.</i>", parse_mode="HTML")

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
        
        # ==========================================
        # اعمال استایل‌های خودکار (جادوی سئو و ظاهر)
        # ==========================================
        # ۱. تبدیل خطوط جدید به تگ <br> در صورت نیاز (اگر هوش مصنوعی <p> نذاشته بود)
        formatted_content = raw_content.replace('\n', '<br>')
        
        # ۲. تزریق Nofollow و Target Blank به تمام لینک‌ها
        # ابتدا تگ‌های اضافی rel و target قبلی را پاک می‌کنیم تا تداخل پیش نیاید
        formatted_content = re.sub(r'\srel="[^"]*"', '', formatted_content)
        formatted_content = re.sub(r'\starget="[^"]*"', '', formatted_content)
        # سپس استاندارد خودمان را به همه لینک‌ها اضافه می‌کنیم
        formatted_content = formatted_content.replace('<a ', '<a rel="nofollow" target="_blank" ')
        
        # ۳. قرار دادن کل محتوا در یک دایو (Div) برای تراز Justify و راست‌چین
        final_html_content = (
            f'<div style="text-align: justify; text-justify: inter-word; direction: rtl;">\n'
            f'{formatted_content}\n'
            f'</div>'
        )

        # ساخت متا دیتای RankMath
        meta_data = {}
        if focus_kw: meta_data["rank_math_focus_keyword"] = focus_kw
        if meta_desc: meta_data["rank_math_description"] = meta_desc

        # ساخت Payload نهایی برای API وردپرس
        payload = {
            "title": post_title,
            "content": final_html_content,
            "status": "draft",
        }
        
        # اگر نامک انگلیسی داده شده بود، اضافه می‌کنیم
        if post_slug:
            payload["slug"] = post_slug
            
        # اگر دیتای رنک‌مث وجود داشت، اضافه می‌کنیم
        if meta_data:
            payload["meta"] = meta_data
        
        result = await wp_service.create_post(payload)
        post_link = result.get('link', '')
        
        success_msg = (
            f"✅ <b>جادوی سئو انجام شد! پیش‌نویس مقاله ثبت گردید.</b>\n\n"
            f"🏷 <b>عنوان:</b> {post_title}\n"
            f"🔗 <b>نامک:</b> {post_slug or 'خودکار'}\n"
            f"🔑 <b>کلمه کلیدی:</b> {focus_kw or 'ندارد'}\n"
            f"📌 <b>وضعیت:</b> پیش‌نویس (Draft)\n\n"
            f"✨ <i>تمام متون Justify شدند و لینک‌ها به صورت Nofollow درآمدند.</i>\n\n"
            f"🌐 <a href='{post_link}'>لینک پیش‌نمایش در سایت</a>"
        )
        
        await wait_msg.edit_text(success_msg, parse_mode="HTML", disable_web_page_preview=True)
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در پردازش و ایجاد مقاله:\n<code>{str(e)[:500]}</code>", parse_mode="HTML")
        await state.clear()
        await callback.answer()
