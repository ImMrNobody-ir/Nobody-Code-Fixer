import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts as t
from services import limiter
from services.membership import missing_channels

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        t.WELCOME.format(name=html.escape(message.from_user.full_name)),
        reply_markup=kb.main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(t.HELP, reply_markup=kb.main_menu())


@router.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery, bot, settings):
    missing = await missing_channels(
        bot, settings.force_join_channels, callback.from_user.id, use_cache=False
    )
    if missing:
        await callback.answer(t.JOIN_STILL_MISSING, show_alert=True)
        return
    await callback.answer("✅ عضویتت تایید شد")
    if callback.message:
        await callback.message.delete()
        await callback.message.answer(
            t.WELCOME.format(name=html.escape(callback.from_user.full_name)),
            reply_markup=kb.main_menu(),
        )


@router.message(F.text.in_(set(t.TASK_BUTTONS)))
async def set_task(message: Message, db):
    task = t.TASK_BUTTONS[message.text]
    await db.set_field(message.from_user.id, "task", task)
    await message.answer(f"{t.task_label(task)}\n{t.TASK_HINTS[task]}")


@router.message(F.text == t.BTN_CONVERT)
async def ask_convert_lang(message: Message):
    await message.answer("🔁 کدت رو به کدوم زبان تبدیل کنم؟", reply_markup=kb.convert_kb())


@router.callback_query(F.data.startswith("cv:"))
async def pick_convert_lang(callback: CallbackQuery, db):
    lang = callback.data.split(":", 1)[1]
    if lang not in t.CONVERT_LANGS:
        await callback.answer()
        return
    await db.set_field(callback.from_user.id, "task", f"convert:{lang}")
    await callback.answer(f"تبدیل به {lang}")
    if callback.message:
        await callback.message.edit_text(
            f"🔁 تبدیل به <b>{html.escape(lang)}</b> فعال شد.\nحالا کدت رو بفرست."
        )


@router.message(F.text == t.BTN_MODE)
async def ask_mode(message: Message, user_row):
    await message.answer("⚙️ حالت پاسخ رو انتخاب کن:", reply_markup=kb.mode_kb(user_row["mode"]))


@router.callback_query(F.data.startswith("mode:"))
async def pick_mode(callback: CallbackQuery, db):
    mode = callback.data.split(":", 1)[1]
    if mode not in t.MODE_LABELS:
        await callback.answer()
        return
    await db.set_field(callback.from_user.id, "mode", mode)
    await callback.answer(f"حالت: {t.MODE_LABELS[mode]}")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=kb.mode_kb(mode))


@router.message(Command("account"))
@router.message(F.text == t.BTN_ACCOUNT)
async def account(message: Message, db, settings, user_row):
    allowed, used, limit = await limiter.check(db, settings, user_row)
    if message.from_user.id in settings.admin_ids:
        status = "👑 ادمین (نامحدود)"
        usage = f"{used} (بدون محدودیت)"
    elif limiter.is_vip(user_row):
        status = f"💎 VIP — {limiter.vip_days_left(user_row)} روز مانده"
        usage = f"{used} (بدون محدودیت)"
    else:
        status = "🆓 رایگان"
        usage = f"{used} از {limit}"

    text = (
        "💎 <b>حساب من</b>\n\n"
        f"وضعیت: {status}\n"
        f"درخواست‌های امروز: {usage}\n"
        f"نوع کار فعلی: {t.task_label(user_row['task'])}\n"
        f"حالت پاسخ: {t.MODE_LABELS.get(user_row['mode'], '-')}"
    )
    await message.answer(text, reply_markup=kb.account_kb(settings.payments_enabled))


@router.message(Command("clear"))
@router.message(F.text == t.BTN_CLEAR)
async def clear_memory(message: Message, db):
    await db.clear_history(message.from_user.id)
    await message.answer("🧹 حافظه گفتگو پاک شد؛ از اول شروع می‌کنیم.")
