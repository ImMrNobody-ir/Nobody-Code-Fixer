import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts as t
from utils.formatting import render, strip_tags

router = Router()


def _title_from(user_text: str | None) -> str:
    first = (user_text or "راه‌حل").strip().splitlines()[0] if (user_text or "").strip() else "راه‌حل"
    first = first.removeprefix("[تصویر]").strip() or "اسکرین‌شات"
    return first[:40]


@router.callback_query(F.data == "save")
async def save_answer(callback: CallbackQuery, db):
    uid = callback.from_user.id
    answer = await db.last_history(uid, "model")
    if not answer:
        await callback.answer("چیزی برای ذخیره پیدا نشد.", show_alert=True)
        return
    title = _title_from(await db.last_history(uid, "user"))
    await db.add_saved(uid, title, answer)
    await callback.answer("💾 ذخیره شد! از «📂 ذخیره‌شده‌ها» ببینش.")


@router.message(Command("saved"))
@router.message(F.text == t.BTN_SAVED)
async def list_saved(message: Message, db):
    items = await db.list_saved(message.from_user.id)
    if not items:
        await message.answer("📂 هنوز چیزی ذخیره نکردی. زیر هر جواب دکمه «💾 ذخیره راه‌حل» هست.")
        return
    await message.answer("📂 <b>راه‌حل‌های ذخیره‌شده</b> (۱۰ مورد آخر):", reply_markup=kb.saved_list_kb(items))


@router.callback_query(F.data.startswith("sv:view:"))
async def view_saved(callback: CallbackQuery, db):
    saved_id = int(callback.data.rsplit(":", 1)[1])
    row = await db.get_saved(callback.from_user.id, saved_id)
    if not row:
        await callback.answer("پیدا نشد.", show_alert=True)
        return
    await callback.answer()
    parts = render(row["content"])
    for i, part in enumerate(parts):
        markup = kb.saved_item_kb(saved_id) if i == len(parts) - 1 else None
        try:
            await callback.message.answer(part, reply_markup=markup)
        except TelegramBadRequest:
            await callback.message.answer(strip_tags(part), parse_mode=None, reply_markup=markup)


@router.callback_query(F.data.startswith("sv:del:"))
async def delete_saved(callback: CallbackQuery, db):
    saved_id = int(callback.data.rsplit(":", 1)[1])
    ok = await db.delete_saved(callback.from_user.id, saved_id)
    await callback.answer("🗑 حذف شد" if ok else "قبلاً حذف شده.")
    if ok and callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
