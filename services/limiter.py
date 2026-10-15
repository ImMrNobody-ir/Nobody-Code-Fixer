import time
from datetime import datetime, timedelta, timezone

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def today() -> str:
    return datetime.now(IRAN_TZ).strftime("%Y-%m-%d")


def day_start_ts() -> int:
    now = datetime.now(IRAN_TZ)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def is_vip(row) -> bool:
    return row["vip_until"] > time.time()


def is_unlimited(row, settings) -> bool:
    return is_vip(row) or row["user_id"] in settings.admin_ids


def vip_days_left(row) -> int:
    remaining = row["vip_until"] - time.time()
    return max(0, int(remaining // 86400) + (1 if remaining % 86400 else 0))


async def check(db, settings, row) -> tuple[bool, int, int]:
    """Return (allowed, used_today, limit)."""
    used = await db.usage_today(row["user_id"], today())
    if is_unlimited(row, settings):
        return True, used, 0
    return used < settings.free_daily_limit, used, settings.free_daily_limit


async def consume(db, user_id: int) -> None:
    await db.add_usage(user_id, today())
