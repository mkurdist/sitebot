import re
import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states.article_states import ArticleWizard

# استفاده از نشست یکتا و ایمن وردپرس
from services.wordpress import wp_service_instance as wp_service

router = Router()

# ==========================================
# توابع کمکی برای ساخت کیبوردهای شیشه‌ای
# ==========================================
def build_categories_keyboard(categories: list, selected: list) -> InlineKeyboardMarkup:
    kb = []
    for cat in categories:
        icon = "✅" if cat['id'] in selected else "🟩"
        kb.append([InlineKeyboardButton(text=f"{icon} {cat['name']}", callback_data=f"cat_toggle_{cat['id']}")])
    kb.append([InlineKeyboardButton(text="💾 تایید دسته‌بندی‌ها", callback_data="cat_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
    
def build_primary_cat_keyboard(categories: list, selected: list) -> InlineKeyboardMarkup:
    kb = []
    for cat in categories:
        if cat['id'] in selected:
            kb.append([InlineKeyboardButton(text=f"🌟 {cat['name']}", callback_data=f"cat_primary_{cat['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==========================================
# بخش دریافت متن مقاله و پردازش ۵ کادر
# ==========================================
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
    ext = "jpg" 
    
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
    kw = data.get('focus_kw', '').strip()
    
    wait_msg = await message.answer("⏳ در حال دانلود تصویر، اعمال نام‌گذاری سئو و آپلود در سایت...")
    
    try:
        if not kw: kw = f"citysofal-article-{post_id}"
        kw_slug = re.sub(r'[\s_]+', '-', kw)
        
        file_info = await bot.get_file(file_id)
        seo_filename = f"{kw_slug}-{file_info.file_unique_id[-4:]}.{ext}" 
        
        file_bytes = io.BytesIO()
        await bot.download_file(file_info.file_path, file_bytes)
        
        media_id = await wp_service.upload_media(file_bytes.getvalue(), seo_filename, alt_text, image_title)
        await wp_service.update_post(post_id, {"featured_media": media_id})
        
        # تغییر فاز: رفتن به بخش دسته‌بندی‌ها
        await wait_msg.edit_text("⏳ تصویر آپلود شد. در حال دریافت دسته‌بندی‌های وبلاگ...")
        
        cats = await wp_service.get_categories()
        cat_list = [{"id": c["id"], "name": c["name"]} for c in cats]
        await state.update_data(wp_categories=cat_list, selected_cats=[])
        
        kb = build_categories_keyboard(cat_list, [])
        await wait_msg.edit_text(
            f"🗂 <b>انتخاب دسته‌بندی‌های مقاله</b>\n\n"
            f"روی دسته‌های مورد نظر کلیک کنید تا تیک بخورند، سپس دکمه تایید را بزنید:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await state.set_state(ArticleWizard.waiting_for_categories)
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا در بخش تصویر/دسته‌بندی:\n<code>{str(e)[:500]}</code>", parse_mode="HTML")
        await state.clear()

# ==========================================
# سیستم انتخاب دسته‌بندی‌ها و دسته اصلی (Primary)
# ==========================================
@router.callback_query(F.data.startswith("cat_toggle_"), ArticleWizard.waiting_for_categories)
async def toggle_category(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("selected_cats", [])
    
    if cat_id in selected:
        selected.remove(cat_id)
    else:
        selected.append(cat_id)
        
    await state.update_data(selected_cats=selected)
    kb = build_categories_keyboard(data["wp_categories"], selected)
    await callback.message.edit_reply_markup(reply_markup=kb)

@router.callback_query(F.data == "cat_confirm", ArticleWizard.waiting_for_categories)
async def confirm_categories(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_cats", [])
    
    if not selected:
        await callback.answer("❌ حداقل یک دسته‌بندی انتخاب کنید!", show_alert=True)
        return
    
    if len(selected) > 1:
        await state.set_state(ArticleWizard.waiting_for_primary_category)
        kb = build_primary_cat_keyboard(data["wp_categories"], selected)
        await callback.message.edit_text("🌟 از بین دسته‌های انتخاب شده، <b>دسته اصلی (Primary Category)</b> مقاله کدام است؟", reply_markup=kb, parse_mode="HTML")
    else:
        # اگر فقط یک دسته انتخاب شده بود، همان را دسته اصلی در نظر می‌گیریم
        await proceed_to_dashboard(callback.message, state, selected[0])

@router.callback_query(F.data.startswith("cat_primary_"), ArticleWizard.waiting_for_primary_category)
async def select_primary_cat(callback: CallbackQuery, state: FSMContext):
    primary_id = int(callback.data.split("_")[2])
    await proceed_to_dashboard(callback.message, state, primary_id)

async def proceed_to_dashboard(message: Message, state: FSMContext, primary_id: int):
    data = await state.get_data()
    post_id = data['post_id']
    selected_cats = data['selected_cats']
    post_title = data['post_title']
    
    # آپدیت مقاله با دسته‌بندی‌ها و دسته اصلی رنک‌مث
    payload = {
        "categories": selected_cats,
        "meta": {
            "rank_math_primary_category": primary_id
        }
    }
    await wp_service.update_post(post_id, payload)
    
    await state.set_state(ArticleWizard.waiting_for_publish_action)
    
    # ساخت داشبورد نهایی
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 انتشار عمومی در سایت", callback_data="post_action_publish")],
        [InlineKeyboardButton(text="📝 نگهداری در پیش‌نویس", callback_data="post_action_draft")],
        [InlineKeyboardButton(text="📊 استعلام نمره سئو (RankMath)", callback_data="post_action_seoscore")],
        [InlineKeyboardButton(text="🗑 انتقال به زباله‌دان", callback_data="post_action_trash")]
    ])
    
    await message.edit_text(
        f"✅ <b>دسته‌بندی‌ها با موفقیت تنظیم شدند.</b>\n\n"
        f"🎛 <b>داشبورد نهایی مدیریت مقاله:</b>\n"
        f"🏷 عنوان: {post_title}\n"
        f"📌 وضعیت فعلی: پیش‌نویس (Draft)\n\n"
        f"لطفاً عملیات نهایی را انتخاب کنید:", 
        reply_markup=kb, parse_mode="HTML"
    )

# ==========================================
# پردازشگر داشبورد نهایی و نمره سئو
# ==========================================
@router.callback_query(F.data.startswith("post_action_"), ArticleWizard.waiting_for_publish_action)
async def handle_post_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[2]
    data = await state.get_data()
    post_id = data['post_id']
    post_title = data['post_title']
    post_link = data['post_link']
    
    if action == "seoscore":
        await callback.answer("⏳ در حال استعلام نمره از دیتابیس رنک‌مث...", show_alert=False)
        try:
            session = await wp_service.get_session()
            url = f"{wp_service.base_url}/posts/{post_id}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    post_data = await resp.json()
                    score = post_data.get("meta", {}).get("rank_math_seo_score", "نامشخص")
                    if score and score != "نامشخص" and int(score) > 0:
                        await callback.answer(f"📊 نمره سئوی این مقاله: {score} از 100", show_alert=True)
                    else:
                        await callback.answer("⚠️ رنک‌مث هنوز نمره‌ای برای این پیش‌نویس ثبت نکرده است. (نیاز به باز شدن در ویرایشگر سایت)", show_alert=True)
                else:
                    await callback.answer("❌ خطا در ارتباط با سایت.", show_alert=True)
        except Exception:
            await callback.answer("❌ امکان دریافت نمره در این لحظه وجود ندارد.", show_alert=True)
            
    elif action in ["publish", "draft", "trash"]:
        try:
            await wp_service.update_post(post_id, {"status": action})
            status_fa = {"publish": "🚀 منتشر شده", "draft": "📝 پیش‌نویس", "trash": "🗑 زباله‌دان"}[action]
            
            final_msg = (
                f"✅ <b>عملیات با موفقیت انجام شد!</b>\n\n"
                f"🏷 <b>عنوان مقاله:</b> {post_title}\n"
                f"📌 <b>وضعیت نهایی:</b> {status_fa}\n\n"
                f"🌐 <a href='{post_link}'>مشاهده مقاله در سایت</a>"
            )
            await callback.message.edit_text(final_msg, parse_mode="HTML", disable_web_page_preview=True)
            await state.clear()
        except Exception as e:
            await callback.answer(f"❌ خطا: {str(e)[:50]}", show_alert=True)
