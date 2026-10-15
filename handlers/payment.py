import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts as t

log = logging.getLogger(__name__)
router = Router()


class Pay(StatesGroup):
    waiting_receipt = State()


@router.callback_query(F.data == "buy_vip")
async def buy_vip(callback: CallbackQuery, state: FSMContext, settings):
    if not settings.payments_enabled:
        await callback.answer("پرداخت فعلاً فعال نیست.", show_alert=True)
        return
    await callback.answer()
    price = f"مبلغ: <b>{html.escape(settings.vip_price)}</b>\n" if settings.vip_price else ""
    holder = f"به نام: {html.escape(settings.card_holder)}\n" if settings.card_holder else ""
    await state.set_state(Pay.waiting_receipt)
    await callback.message.answer(
        t.PAY_INFO.format(
            days=settings.vip_days,
            price=price,
            card=html.escape(settings.card_number),
            holder=holder,
        ),
        reply_markup=kb.cancel_pay_kb(),
    )


@router.callback_query(F.data == "pay:cancel")
async def cancel_pay(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(t.PAY_CANCELLED)


@router.message(Pay.waiting_receipt)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot, settings):
    # A menu button or command means the user changed their mind.
    if message.text and (message.text in t.ALL_BUTTONS or message.text.startswith("/")):
        await state.clear()
        await message.answer(t.PAY_CANCELLED + "\nدوباره دکمه موردنظرت رو بزن.", reply_markup=kb.main_menu())
        return
    if not (message.photo or message.document):
        await message.answer(t.PAY_NEED_RECEIPT, reply_markup=kb.cancel_pay_kb())
        return

    user = message.from_user
    sent = 0
    for admin_id in settings.admin_ids:
        try:
            await bot.copy_message(admin_id, message.chat.id, message.message_id)
            username = f"@{user.username}" if user.username else "-"
            await bot.send_message(
                admin_id,
                f"💎 درخواست VIP\nکاربر: {html.escape(user.full_name)}\n"
                f"یوزرنیم: {html.escape(username)}\nآیدی: <code>{user.id}</code>",
                reply_markup=kb.review_kb(user.id, settings.vip_days),
            )
            sent += 1
        except TelegramAPIError as exc:
            log.warning("Cannot notify admin %s: %s", admin_id, exc)

    await state.clear()
    if sent:
        await message.answer(t.PAY_SENT, reply_markup=kb.main_menu())
    else:
        await message.answer("⚠️ ارسال رسید به ادمین ناموفق بود. بعداً دوباره امتحان کن.", reply_markup=kb.main_menu())
