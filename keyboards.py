from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import texts as t


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [t.BTN_AUTO],
        [t.BTN_FIX, t.BTN_REVIEW],
        [t.BTN_EXPLAIN, t.BTN_CONVERT],
        [t.BTN_MODE, t.BTN_ACCOUNT],
        [t.BTN_CLEAR, t.BTN_SAVED],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b) for b in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder="کد یا ارورت رو بفرست...",
    )


def mode_kb(current: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in t.MODE_LABELS.items():
        mark = "✅ " if key == current else ""
        kb.button(text=mark + label, callback_data=f"mode:{key}")
    kb.adjust(3)
    return kb.as_markup()


def convert_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lang in t.CONVERT_LANGS:
        kb.button(text=lang, callback_data=f"cv:{lang}")
    kb.adjust(3)
    return kb.as_markup()


def answer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💾 ذخیره راه‌حل", callback_data="save")]]
    )


def account_kb(show_buy: bool) -> InlineKeyboardMarkup | None:
    if not show_buy:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💎 خرید / تمدید VIP", callback_data="buy_vip")]]
    )


def join_kb(channels: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        if ch.startswith("@"):
            kb.row(InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch[1:]}"))
    kb.row(InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join"))
    return kb.as_markup()


def saved_list_kb(items) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(InlineKeyboardButton(text=f"📄 {item['title']}", callback_data=f"sv:view:{item['id']}"))
    return kb.as_markup()


def saved_item_kb(saved_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗑 حذف", callback_data=f"sv:del:{saved_id}")]]
    )


def cancel_pay_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data="pay:cancel")]]
    )


def review_kb(user_id: int, days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✅ تایید ({days} روز)", callback_data=f"vipok:{user_id}:{days}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"vipno:{user_id}"),
            ]
        ]
    )
