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
        [InlineKeyboardButton(text="✅ پردازش و ارسال به سایت", callback_data="process_article_buffer")]
    ])
    
    instruction = (
        "📝 <b>سیستم انتشار هوشمند مقاله (وبلاگ)</b>\n\n"
        "متن مقاله تولید شده توسط AI را اینجا Paste کنید.\n"
        "<i>(نکته: اگر مقاله طولانی است، آن را در چند پیام بفرستید)</i>\n\n"
        "<b>فرمت استاندارد برای هوش مصنوعی:</b>\n"
        "۱. کادر عنوان مقاله:\n"
        "۲. کادر محتوای مقاله (با تگ‌های HTML):\n\n"
        "پس از ارسال تمام بخش‌ها، روی دکمه زیر کلیک کنید:"
    )
    await message.answer(instruction, reply_markup=keyboard, parse_mode="HTML")

@router.message(ArticleWizard.waiting_for_article_text)
async def accumulate_article_text(message: Message, state: FSMContext):
    data = await state.get_data()
    current_buffer = data.get("article_buffer", "")
    new_buffer = current_buffer + "\n\n" + message.text
    await state.update_data(article_buffer=new_buffer)
    
    await message.answer("📥 <i>متن دریافت شد. اگر ادامه دارد بفرستید، در غیر این صورت دکمه «پردازش و ارسال» در پیام بالا را بزنید.</i>", parse_mode="HTML")

@router.callback_query(F.data == "process_article_buffer")
async def process_article(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("article_buffer", "")
    
    if not text.strip():
        await callback.answer("❌ هنوز هیچ متنی نفرستاده‌اید!", show_alert=True)
        return

    wait_msg = await callback.message.answer("⏳ در حال تحلیل متن و ساخت مقاله در سایت...")
    
    try:
        # استخراج عنوان و محتوا با Regex
        title_match = re.search(r'۱\.\s*کادر عنوان مقاله:?\s*\n(.*?)(?=\n۲\.)', text, re.DOTALL)
        content_match = re.search(r'۲\.\s*کادر محتوای مقاله:?\s*\n(.*)', text, re.DOTALL)
        
        post_title = title_match.group(1).strip() if title_match else "مقاله جدید تولید شده توسط AI"
        post_content = content_match.group(1).strip().replace('\n', '<br>') if content_match else text.replace('\n', '<br>')
        
        # ساخت Payload برای API وردپرس
        payload = {
            "title": post_title,
            "content": post_content,
            "status": "draft"  # مقاله به عنوان پیش‌نویس ذخیره می‌شود تا ایمن باشد
        }
        
        result = await wp_service.create_post(payload)
        post_link = result.get('link', '')
        
        success_msg = (
            f"✅ <b>مقاله با موفقیت به وبلاگ فرستاده شد!</b>\n\n"
            f"🏷 <b>عنوان:</b> {post_title}\n"
            f"📌 <b>وضعیت:</b> پیش‌نویس (Draft)\n\n"
            f"🌐 <a href='{post_link}'>لینک پیش‌نمایش مقاله در سایت</a>\n\n"
            f"<i>نکته: برای رعایت احتیاط، مقاله پیش‌نویس شد. می‌توانید وارد پیشخوان وردپرس شوید و پس از بررسی، آن را منتشر کنید.</i>"
        )
        
        await wait_msg.edit_text(success_msg, parse_mode="HTML", disable_web_page_preview=True)
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در ایجاد مقاله:\n<code>{str(e)[:500]}</code>", parse_mode="HTML")
        await state.clear()
        await callback.answer()
