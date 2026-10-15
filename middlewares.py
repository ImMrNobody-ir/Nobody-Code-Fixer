import html
import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts as t
from services.membership import missing_channels

log = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Registers the user, blocks banned users and enforces Force Join."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        db = data["db"]
        settings = data["settings"]
        bot = data["bot"]

        row = await db.upsert_user(user.id, user.username, user.full_name)
        data["user_row"] = row

        is_admin = user.id in settings.admin_ids

        if row["banned"] and not is_admin:
            await self._reply(event, t.BANNED, alert=True)
            return None

        is_join_check = isinstance(event, CallbackQuery) and event.data == "check_join"
        if settings.force_join_channels and not is_admin and not is_join_check:
            missing = await missing_channels(bot, settings.force_join_channels, user.id)
            if missing:
                await self._reply(
                    event, t.JOIN_REQUIRED, alert=True, markup=kb.join_kb(missing)
                )
                return None

        return await handler(event, data)

    @staticmethod
    async def _reply(event, text: str, alert: bool = False, markup=None) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(html.unescape(text)[:180], show_alert=alert)
            if markup is not None and event.message:
                await event.message.answer(text, reply_markup=markup)
        elif isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
