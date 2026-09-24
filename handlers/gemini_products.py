"""
افزودن محصول با Gemini (ایزوله).

جریان:  /gemini  →  ارسال عکس‌ها + مشخصات  →  «تولید محتوا»  →  پیش‌نمایش  →  «تایید»  →  ساخت پیش‌نویس در ووکامرس
- هیچ‌چیز تا قبل از تایید به سایت ارسال نمی‌شود.
- محصول به‌صورت «پیش‌نویس» ساخته می‌شود و ادمین به داشبورد فعلی (قیمت، موجودی، دسته‌بندی، انتشار) می‌رسد.
- State و callbackها مستقل‌اند (پیشوند gp_)؛ فایل‌های موجود تغییر نمی‌کنند.
- ترتیب ثبت در bot.py: این روتر باید «بعد از common_router و قبل از products_router» ثبت شود؛ وگرنه
  هندلر قدیمی «افزودن خودکار» (که هر پیامی در state خودش را می‌گیرد) دستور /gemini را می‌بلعد.
"""
import asyncio
import html
import io
import time

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from services import gemini as gm
from services.woocommerce import wc_service_instance as wc_service
from services.wordpress import wp_service_instance as wp_service
from handlers.products import get_dashboard_keyboard  # فقط ایمپورت؛ بدون تغییر در فایل اصلی

router = Router()

MAX_IMAGES = 8
MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 18 * 1024 * 1024
DRAFT_TTL = 6 * 3600
DEBOUNCE_SECONDS = 1.5

_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

# دکمه‌های منوی اصلی که هندلر خاصی ندارند و نباید به‌عنوان «متن مشخصات» ثبت شوند
_MENU_TEXTS = {
    "⚙️ تنظیمات", "⚡ افزودن خودکار (AI)", "➕ محصول جدید", "🛍 محصولات سایت",
    "📦 آخرین سفارش‌ها", "📝 مقاله جدید", "✏️ ویرایش مقاله",
}


class GeminiWizard(StatesGroup):
    collecting = State()               # دریافت عکس‌ها و مشخصات
    reviewing = State()                # پیش‌نمایش و تایید
    waiting_for_instruction = State()  # دریافت دستور ویرایش


# حافظه‌ی موقت هر ادمین (تک‌ادمین). عملیات روی dict بدون await در میان، پس بین آپدیت‌های هم‌زمان آلبوم امن است.
_drafts: dict = {}


def _new_draft(chat_id: int) -> dict:
    return {
        "chat_id": chat_id, "ts": time.time(),
        "images": [],          # [{"file_id","ext","mime","bytes"}]
        "texts": [],
        "status_msg_id": None, "status_task": None,
        "busy": False,
        "result": None,        # GenResult
        "review_msg_id": None,  # پیام پیش‌نمایشی که دکمه‌های تایید دارد
        "existing": None,
        "media": {},           # index -> media_id (برای تلاش مجدد بدون آپلود تکراری)
        "created_id": None,
    }


def _drop_draft(uid: int):
    d = _drafts.pop(uid, None)
    if d and d.get("status_task"):
        d["status_task"].cancel()


def _gc():
    now = time.time()
    for uid in [u for u, d in _drafts.items() if not d["busy"] and now - d["ts"] > DRAFT_TTL]:
        _drop_draft(uid)


def _get_draft(uid: int):
    _gc()
    d = _drafts.get(uid)
    if d:
        d["ts"] = time.time()
    return d


async def _safe_edit(msg, text: str, **kw):
    try:
        return await msg.edit_text(text, **kw)
    except Exception:
        return None


async def _set_kb(bot: Bot, chat_id: int, message_id, kb):
    """حذف یا جایگزینی کیبورد شیشه‌ای یک پیام (خطاها بی‌اهمیت‌اند)."""
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=kb)
    except Exception:
        pass


# ==========================================
# کیبوردها
# ==========================================
def _collect_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 تولید محتوا با Gemini", callback_data="gp_generate")],
        [
            InlineKeyboardButton(text="🧹 پاک‌کردن ورودی‌ها", callback_data="gp_reset"),
            InlineKeyboardButton(text="❌ لغو", callback_data="gp_cancel"),
        ],
    ])


def _review_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و ساخت محصول در سایت", callback_data="gp_confirm")],
        [
            InlineKeyboardButton(text="🔄 تولید مجدد", callback_data="gp_regen"),
            InlineKeyboardButton(text="✏️ اصلاح با دستور", callback_data="gp_edit"),
        ],
        [InlineKeyboardButton(text="❌ لغو", callback_data="gp_cancel")],
    ])


# ==========================================
# شروع
# ==========================================
@router.message(Command("gemini"))
@router.message(F.text == "🤖 محصول با Gemini")
async def gp_start(message: Message, state: FSMContext):
    if not gm.is_configured():
        await message.answer("❌ متغیر محیطی <code>GEMINI_API_KEY</code> تنظیم نشده است.", parse_mode="HTML")
        return
    uid = message.from_user.id
    _drop_draft(uid)
    await state.clear()
    _drafts[uid] = _new_draft(message.chat.id)
    await state.set_state(GeminiWizard.collecting)
    await message.answer(
        "🤖 <b>افزودن محصول با Gemini</b>\n\n"
        "۱) عکس(های) محصول را بفرستید (تا ۸ عکس؛ آلبوم هم قبول است).\n"
        "۲) مشخصات خام محصول را به‌صورت متن یا کپشن بفرستید (رنگ، تزئین، نوع رنگ، ابعاد، وزن، نحوه فروش، ارسال، تضمین…).\n\n"
        "⚠️ هر چیزی که ننویسید، Gemini حدس نمی‌زند و «اعلام نشده» می‌گذارد.\n"
        "این جریان مخصوص <b>یک محصول در هر بار</b> است. برای خروج: /cancel",
        parse_mode="HTML",
    )


@router.message(F.text == "/cancel", StateFilter(GeminiWizard))
async def gp_cancel_command(message: Message, state: FSMContext):
    d = _drafts.get(message.from_user.id)
    if d and d["busy"]:
        await message.answer("⏳ در حال انجام عملیات هستم؛ چند لحظه بعد /cancel را بزنید.")
        return
    _drop_draft(message.from_user.id)
    await state.clear()
    await message.answer("❌ افزودن محصول با Gemini لغو شد. هیچ‌چیزی در سایت ثبت نشد.")


# ==========================================
# دریافت ورودی‌ها
# ==========================================
def _status_text(d: dict) -> str:
    n = len(d["images"])
    words = sum(len(t.split()) for t in d["texts"])
    lines = [
        "📥 <b>ورودی‌های دریافت‌شده</b>",
        f"🖼 عکس: <b>{n}</b> (حداکثر {MAX_IMAGES})",
        f"📝 متن مشخصات: <b>{len(d['texts'])}</b> پیام ({words} کلمه)",
        "",
    ]
    if n == 0:
        lines.append("⚠️ حداقل یک عکس لازم است.")
    elif not d["texts"]:
        lines.append("ℹ️ مشخصاتی نفرستاده‌اید؛ اگر ادامه دهید فقط از روی عکس‌ها نوشته می‌شود.")
    else:
        lines.append("اگر چیز دیگری مانده بفرستید؛ وگرنه دکمه‌ی تولید را بزنید.")
    return "\n".join(lines)


def _schedule_status(bot: Bot, uid: int):
    """یک پیام وضعیت برای کل آلبوم (به‌جای یک پاسخ برای هر عکس)."""
    d = _drafts.get(uid)
    if not d:
        return
    if d["status_task"]:
        d["status_task"].cancel()
    d["status_task"] = asyncio.create_task(_send_status_later(bot, uid))


async def _send_status_later(bot: Bot, uid: int):
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return
    d = _drafts.get(uid)
    if not d:
        return
    old = d["status_msg_id"]
    try:
        sent = await bot.send_message(d["chat_id"], _status_text(d), reply_markup=_collect_kb(), parse_mode="HTML")
        d["status_msg_id"] = sent.message_id
        if old:
            try:
                await bot.delete_message(d["chat_id"], old)
            except Exception:
                pass
    except Exception:
        pass


@router.message(GeminiWizard.collecting, F.photo | F.document)
async def gp_collect_media(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    d = _get_draft(uid)
    if not d:
        await state.clear()
        await message.answer("⌛ جلسه منقضی شده (احتمالاً ربات ریستارت شد). دوباره /gemini را بزنید.")
        return

    if len(d["images"]) >= MAX_IMAGES:
        await message.answer(f"❌ حداکثر {MAX_IMAGES} عکس مجاز است.")
        return

    if message.photo:
        ph = message.photo[-1]
        item = {"file_id": ph.file_id, "ext": "jpg", "mime": "image/jpeg", "bytes": None}
    else:
        doc = message.document
        name = (doc.file_name or "").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in _MIME and doc.mime_type in ("image/jpeg", "image/png", "image/webp"):
            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[doc.mime_type]
        if ext not in _MIME:
            await message.answer("❌ فقط تصویر JPG / PNG / WebP قابل قبول است.")
            return
        if (doc.file_size or 0) > MAX_DOC_BYTES:
            await message.answer("❌ حجم این فایل بیشتر از ۱۰ مگابایت است.")
            return
        item = {"file_id": doc.file_id, "ext": ext, "mime": _MIME[ext], "bytes": None}

    d["images"].append(item)
    if message.caption and message.caption.strip() and message.caption.strip() not in d["texts"]:
        d["texts"].append(message.caption.strip())
    d["result"] = None  # ورودی عوض شد؛ نتیجه‌ی قبلی بی‌اعتبار
    _schedule_status(bot, uid)


@router.message(GeminiWizard.collecting, F.text, ~F.text.in_(_MENU_TEXTS))
async def gp_collect_text(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    d = _get_draft(uid)
    if not d:
        await state.clear()
        await message.answer("⌛ جلسه منقضی شده (احتمالاً ربات ریستارت شد). دوباره /gemini را بزنید.")
        return
    text = message.text.strip()
    if text.startswith("/"):
        await message.answer("ℹ️ شما در حالت «افزودن با Gemini» هستید. برای خروج /cancel را بزنید.")
        return
    d["texts"].append(text)
    d["result"] = None
    _schedule_status(bot, uid)


@router.message(GeminiWizard.collecting, ~F.text)
async def gp_collect_invalid(message: Message):
    await message.answer("❌ فقط عکس یا متن مشخصات بفرستید.")


@router.callback_query(F.data == "gp_reset", GeminiWizard.collecting)
async def gp_reset(callback: CallbackQuery):
    d = _get_draft(callback.from_user.id)
    if not d:
        await callback.answer("⌛ جلسه منقضی شده.", show_alert=True)
        return
    if d["busy"]:
        await callback.answer("⏳ در حال انجام عملیات هستم.", show_alert=True)
        return
    d["images"].clear()
    d["texts"].clear()
    d["result"] = None
    await callback.answer("🧹 پاک شد.")
    await _safe_edit(callback.message, "🧹 ورودی‌ها پاک شد. عکس و مشخصات جدید را بفرستید.")


# ==========================================
# ابزارهای کمکی تولید
# ==========================================
async def _download(bot: Bot, file_id: str) -> bytes:
    info = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(info.file_path, buf)
    return buf.getvalue()


async def _ensure_downloaded(bot: Bot, d: dict):
    for item in d["images"]:
        if item["bytes"] is None:
            item["bytes"] = await _download(bot, item["file_id"])
    if sum(len(i["bytes"]) for i in d["images"]) > MAX_TOTAL_BYTES:
        raise gm.GeminiError("مجموع حجم عکس‌ها بیش از حد مجاز است؛ تعداد یا حجم عکس‌ها را کم کنید.")


async def _existing_products() -> list:
    """عنوان و کلمه‌ی کلیدی محصولات اخیر، برای جلوگیری از تکراری‌شدن (خطا نادیده گرفته می‌شود)."""
    try:
        items = await wc_service.get_latest_products(per_page=30)
    except Exception:
        return []
    out = []
    for p in items or []:
        kw = ""
        for m in p.get("meta_data", []) or []:
            if m.get("key") == "rank_math_focus_keyword":
                kw = str(m.get("value") or "")
        out.append({"name": p.get("name", ""), "keyword": kw})
    return out


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _summary_text(res: "gm.GenResult") -> str:
    p, st = res.product, res.stats
    e = html.escape
    ok = lambda cond: "✅" if cond else "⚠️"
    lines = [
        "🤖 <b>پیش‌نویس Gemini آماده است</b>",
        "",
        f"🏷 <b>عنوان:</b> {e(p['title'])}",
        f"🔑 <b>کلمه کلیدی:</b> {e(p['focus_keyword'])}",
        f"   تکرار در توضیحات کامل: <b>{st['kw_count']}</b>/۹ {ok(st['kw_count'] == 9)}",
        f"📝 کلمات توضیحات کامل: <b>{st['full_words']}</b> {ok(850 <= st['full_words'] <= 1000)} | تیترها: {st['headings']}",
        f"✂️ توضیح کوتاه: {st['short_words']} کلمه | متن محاوره‌ای: {st['conv_words']} کلمه",
        f"🔗 <b>Slug:</b> <code>{e(p['slug'])}</code>",
        f"📌 <b>Meta Title</b> ({st['meta_title_len']} کاراکتر): {e(p['meta_title'])}",
        f"📄 <b>Meta Description</b> ({st['meta_desc_len']} کاراکتر): {e(p['meta_description'])}",
        f"🏷 <b>برچسب‌ها:</b> {e('، '.join(p['tags']))}",
        "🖼 <b>Alt عکس‌ها:</b>",
    ]
    lines += [f"   {i}) {e(_clip(a, 140))}" for i, a in enumerate(p["image_alt_texts"], 1)]
    if res.hard_issues:
        lines += ["", f"❗ <b>پس از {res.attempts} تلاش هنوز این موارد رفع نشده:</b>"]
        lines += [f"• {e(_clip(i, 200))}" for i in res.hard_issues[:6]]
        lines.append("می‌توانید «✏️ اصلاح با دستور» یا «🔄 تولید مجدد» را بزنید.")
    if res.warnings:
        lines += ["", "⚠️ <b>برای بررسی شما:</b>"] + [f"• {e(_clip(w, 200))}" for w in res.warnings[:6]]
    lines += ["", "📎 متن کامل و جدول مشخصات در فایل بالا است. اگر مورد تایید است، دکمه‌ی تایید را بزنید:"]
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3990] + "…"


async def _send_preview(bot: Bot, d: dict):
    res = d["result"]
    await bot.send_document(
        d["chat_id"],
        BufferedInputFile(gm.build_preview_document(res.product), filename="preview.html"),
        caption="📄 پیش‌نمایش کامل محتوا (فایل را در مرورگر باز کنید)",
    )
    old_id = d["review_msg_id"]
    sent = await bot.send_message(d["chat_id"], _summary_text(res), reply_markup=_review_kb(), parse_mode="HTML")
    d["review_msg_id"] = sent.message_id
    if old_id and old_id != sent.message_id:
        await _set_kb(bot, d["chat_id"], old_id, None)  # دکمه‌های نسخه‌ی قبلی غیرفعال شود


async def _after_failure(bot: Bot, state: FSMContext, uid: int, d: dict):
    """بعد از خطا، کاربر همیشه یک مسیر ادامه‌ی مشخص با دکمه دارد."""
    if d.get("result"):
        await state.set_state(GeminiWizard.reviewing)
        await bot.send_message(d["chat_id"], "می‌خواهید با نسخه‌ی قبلی چه کنید؟", reply_markup=_review_kb())
    else:
        await state.set_state(GeminiWizard.collecting)
        _schedule_status(bot, uid)


async def _run_generation(bot: Bot, state: FSMContext, uid: int, wait_msg: Message,
                          *, instruction=None, previous=None, avoid=None):
    d = _drafts[uid]
    d["busy"] = True
    try:
        await _ensure_downloaded(bot, d)
        existing = list(await _existing_products())
        if avoid:
            existing.append(avoid)

        async def progress(text: str):
            await _safe_edit(wait_msg, f"⏳ {text}")

        res = await gm.generate_product(
            "\n\n".join(d["texts"]),
            [(i["bytes"], i["mime"]) for i in d["images"]],
            existing=existing, instruction=instruction, previous=previous, on_progress=progress,
        )
        d["result"] = res
        d["existing"] = existing
        d["media"] = {}          # محتوا عوض شد؛ Alt/عنوان عکس‌ها هم عوض شده است
        await state.set_state(GeminiWizard.reviewing)
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await _send_preview(bot, d)
    except gm.GeminiError as e:
        await _safe_edit(wait_msg, f"❌ <b>خطا در تولید محتوا</b>\n<code>{html.escape(str(e)[:600])}</code>", parse_mode="HTML")
        await _after_failure(bot, state, uid, d)
    except Exception as e:  # خطای غیرمنتظره؛ ربات نباید بی‌صدا بماند
        await _safe_edit(wait_msg, f"❌ خطای غیرمنتظره:\n<code>{html.escape(str(e)[:500])}</code>", parse_mode="HTML")
        await _after_failure(bot, state, uid, d)
    finally:
        d["busy"] = False


# ==========================================
# تولید / تولید مجدد / ویرایش با دستور
# ==========================================
@router.callback_query(F.data == "gp_generate", GeminiWizard.collecting)
async def gp_generate(callback: CallbackQuery, state: FSMContext, bot: Bot):
    uid = callback.from_user.id
    d = _get_draft(uid)
    if not d:
        await callback.answer("⌛ جلسه منقضی شده. دوباره /gemini را بزنید.", show_alert=True)
        return
    if d["busy"]:
        await callback.answer("⏳ در حال انجام عملیات هستم.", show_alert=True)
        return
    if not d["images"]:
        await callback.answer("❌ هنوز هیچ عکسی نفرستاده‌اید!", show_alert=True)
        return
    await callback.answer()
    if d["status_task"]:
        d["status_task"].cancel()
    d["busy"] = True  # همین حالا قفل شود تا کلیک دوباره وارد نشود
    wait_msg = await callback.message.answer("⏳ در حال آماده‌سازی عکس‌ها…")
    d["busy"] = False
    await _run_generation(bot, state, uid, wait_msg)


@router.callback_query(F.data == "gp_regen", StateFilter(GeminiWizard.reviewing, GeminiWizard.waiting_for_instruction))
async def gp_regen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    uid = callback.from_user.id
    d = _get_draft(uid)
    if not d or not d.get("result"):
        await callback.answer("⌛ جلسه منقضی شده. دوباره /gemini را بزنید.", show_alert=True)
        return
    if d["busy"]:
        await callback.answer("⏳ در حال انجام عملیات هستم.", show_alert=True)
        return
    await callback.answer()
    old = d["result"].product
    avoid = {"name": old["title"], "keyword": old["focus_keyword"]}  # نسخه‌ی قبلی تکرار نشود
    wait_msg = await callback.message.answer("⏳ در حال آماده‌سازی…")
    await _run_generation(bot, state, uid, wait_msg, avoid=avoid)


@router.callback_query(F.data == "gp_edit", StateFilter(GeminiWizard.reviewing, GeminiWizard.waiting_for_instruction))
async def gp_edit(callback: CallbackQuery, state: FSMContext):
    d = _get_draft(callback.from_user.id)
    if not d or not d.get("result"):
        await callback.answer("⌛ جلسه منقضی شده. دوباره /gemini را بزنید.", show_alert=True)
        return
    await state.set_state(GeminiWizard.waiting_for_instruction)
    await callback.answer()
    await callback.message.answer(
        "✏️ <b>دستور ویرایش را بنویسید</b>\n"
        "مثلاً: «عنوان کوتاه‌تر شود» یا «در توضیحات روی هدیه‌دادن بیشتر تمرکز کن».\n"
        "قوانین (۹ بار کلمه کلیدی، حجم متن، …) همچنان خودکار کنترل می‌شود.",
        parse_mode="HTML",
    )


@router.message(GeminiWizard.waiting_for_instruction, F.text, ~F.text.in_(_MENU_TEXTS))
async def gp_instruction(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    d = _get_draft(uid)
    if not d or not d.get("result"):
        await state.clear()
        await message.answer("⌛ جلسه منقضی شده. دوباره /gemini را بزنید.")
        return
    text = message.text.strip()
    if text.startswith("/"):
        await message.answer("ℹ️ لطفاً دستور ویرایش را به‌صورت متن معمولی بنویسید (یا از دکمه‌های پیش‌نمایش استفاده کنید).")
        return
    if d["busy"]:
        await message.answer("⏳ در حال انجام عملیات هستم.")
        return
    wait_msg = await message.answer("⏳ در حال اعمال دستور…")
    await _run_generation(bot, state, uid, wait_msg, instruction=text, previous=d["result"].product)


@router.message(StateFilter(GeminiWizard.reviewing), ~F.text.in_(_MENU_TEXTS))
async def gp_review_hint(message: Message):
    await message.answer("ℹ️ از دکمه‌های پیش‌نمایش استفاده کنید (تایید / تولید مجدد / اصلاح با دستور) یا /cancel بزنید.")


# ==========================================
# تایید: آپلود عکس‌ها + ساخت پیش‌نویس محصول
# ==========================================
def _build_payload(p: dict, media_ids: dict, n_images: int) -> dict:
    images = []
    slug = p["slug"]
    for i in range(n_images):
        img_title = slug if i == 0 else f"{slug}-{i + 1}"
        images.append({
            "id": media_ids[i],
            "name": img_title,
            "alt": p["image_alt_texts"][i],
        })
    return {
        "name": p["title"],
        "type": "simple",
        "status": "draft",
        "slug": p["slug"],
        "short_description": gm.build_short_html(p),
        "description": gm.build_description_html(p),
        "tags": [{"name": t} for t in p["tags"]],
        "images": images,
        "meta_data": [
            {"key": "rank_math_focus_keyword", "value": p["focus_keyword"]},
            {"key": "rank_math_title", "value": p["meta_title"]},
            {"key": "rank_math_description", "value": p["meta_description"]},
        ],
    }


@router.callback_query(F.data == "gp_confirm", StateFilter(GeminiWizard.reviewing, GeminiWizard.waiting_for_instruction))
async def gp_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    uid = callback.from_user.id
    d = _get_draft(uid)
    if not d or not d.get("result"):
        await callback.answer("⌛ جلسه منقضی شده. دوباره /gemini را بزنید.", show_alert=True)
        return
    if d["busy"]:
        await callback.answer("⏳ در حال انجام عملیات هستم.", show_alert=True)
        return
    d["busy"] = True
    await callback.answer()
    p = d["result"].product
    n = len(d["images"])
    await _set_kb(bot, d["chat_id"], callback.message.message_id, None)
    wait_msg = await callback.message.answer("⏳ در حال ارسال به سایت…")

    try:
        # ۱) آپلود عکس‌ها با نام و عنوان یکپارچه بر اساس نامک انگلیسی (slug) بدون دستکاری فرمت
        if d["created_id"] is None:
            slug = p["slug"]
            for i, img in enumerate(d["images"]):
                if i in d["media"]:
                    continue
                await _safe_edit(wait_msg, f"⏳ آپلود عکس {i + 1} از {n} در کتابخانه‌ی رسانه…")
                img_title = slug if i == 0 else f"{slug}-{i + 1}"
                fname = f"{img_title}.{img['ext']}"
                d["media"][i] = await wp_service.upload_media(img["bytes"], fname, p["image_alt_texts"][i], img_title)

            # ۲) ساخت محصول (پیش‌نویس) با تمام اطلاعات در یک درخواست
            await _safe_edit(wait_msg, "⏳ در حال ساخت محصول (پیش‌نویس) در ووکامرس…")
            result = await wc_service.create_simple_product(_build_payload(p, d["media"], n))
            d["created_id"] = result["id"]

        product_id = d["created_id"]
        title = p["title"]
        await state.clear()
        await state.update_data(product_id=product_id, product_name=title)
        _drop_draft(uid)
        await _safe_edit(
            wait_msg,
            f"✅ <b>محصول به‌صورت پیش‌نویس ساخته شد!</b>\n\n"
            f"🏷 <b>نام:</b> {html.escape(title)}\n"
            f"🆔 <b>آیدی:</b> <code>{product_id}</code>\n"
            f"🖼 عکس‌ها، توضیحات، جدول مشخصات، برچسب‌ها و سئو ثبت شد.\n\n"
            f"👇 حالا <b>قیمت و موجودی</b> و <b>دسته‌بندی</b> را از پنل تنظیم کنید و «انتشار نهایی» را بزنید:",
            reply_markup=get_dashboard_keyboard(product_id, title), parse_mode="HTML",
        )
    except Exception as e:
        await _safe_edit(wait_msg, f"❌ <b>خطا در ارسال به سایت</b>\n<code>{html.escape(str(e)[:500])}</code>\n\n"
                                   "چیزی منتشر نشد. می‌توانید دوباره «تایید» را بزنید (عکس‌های آپلودشده تکراری آپلود نمی‌شوند).",
                         parse_mode="HTML")
        await _set_kb(bot, d["chat_id"], callback.message.message_id, _review_kb())
    finally:
        if uid in _drafts:
            _drafts[uid]["busy"] = False


# ==========================================
# لغو
# ==========================================
@router.callback_query(F.data == "gp_cancel", StateFilter(GeminiWizard.collecting, GeminiWizard.reviewing, GeminiWizard.waiting_for_instruction))
async def gp_cancel(callback: CallbackQuery, state: FSMContext):
    d = _drafts.get(callback.from_user.id)
    if d and d["busy"]:
        await callback.answer("⏳ در حال انجام عملیات هستم؛ چند لحظه بعد دوباره امتحان کنید.", show_alert=True)
        return
    _drop_draft(callback.from_user.id)
    await state.clear()
    await callback.answer("لغو شد.")
    await callback.message.answer("❌ افزودن محصول با Gemini لغو شد. هیچ‌چیزی در سایت ثبت نشد.")


# ==========================================
# دکمه‌های قدیمی/بی‌اثر (بعد از ریستارت یا تغییر مرحله) — باید آخرین هندلر باشد
# ==========================================
@router.callback_query(F.data.startswith("gp_"))
async def gp_stale_button(callback: CallbackQuery):
    await callback.answer("⌛ این دکمه دیگر فعال نیست. برای شروع دوباره /gemini را بزنید.", show_alert=True)
