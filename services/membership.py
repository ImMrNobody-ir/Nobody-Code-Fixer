import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

CACHE_TTL = 120
_cache: dict[tuple[int, str], tuple[float, bool]] = {}


async def missing_channels(
    bot: Bot, channels: list[str], user_id: int, use_cache: bool = True
) -> list[str]:
    """Return the channels the user has NOT joined yet.

    If Telegram refuses the check (bot isn't admin there, wrong username, ...)
    the channel is skipped so a bad config never locks everybody out.
    """
    now = time.time()
    missing = []
    for channel in channels:
        key = (user_id, channel)
        hit = _cache.get(key)
        if use_cache and hit and hit[1] and now - hit[0] < CACHE_TTL:
            continue
        try:
            member = await bot.get_chat_member(channel, user_id)
            joined = member.status in ("member", "administrator", "creator") or (
                member.status == "restricted" and getattr(member, "is_member", False)
            )
        except TelegramAPIError as exc:
            log.warning("Cannot verify membership in %s: %s", channel, exc)
            joined = True
        _cache[key] = (now, joined)
        if not joined:
            missing.append(channel)
    return missing
