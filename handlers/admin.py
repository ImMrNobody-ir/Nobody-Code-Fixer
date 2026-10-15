import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message

import texts as t
from services import limiter

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings) -> bool:
        user = event.from_user
        return bool(user and user.id in settings.admin_ids)


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

ADMIN_HELP = (
    "🛠 <b>پنل ادمین</b>\n\n"
    "/stats — آمار ربات\n"
    "/vip user_id [days] — فعال‌سازی یا تمدید VIP\n"
    "/unvip user_id — حذف VIP\n"
    "/ban user_id — مسدود کردن\n"
    "/unban user_id — رفع مسدودی\n"
    "/broadcast متن — پیام همگانی (یا روی یک پیام ریپلای کن و /broadcast بزن)"
)


def _parse_ints(args: str | None) -> list[int]:
    out = []
    for part in (args or "").split():
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


async def _notify(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except TelegramAPIError as exc:
        log.info("Could not notify %s: %s", user_id, exc)


@router.message(Command("admin"))
async def admin_panel(message: Message):
    await message.answer(ADMIN_HELP)


@router.message(Command("stats"))
async def stats(message: Message, db):
    s = await db.stats(limiter.day_start_ts())
    await message.answer(
        "📊 <b>آمار ربات</b>\n\n"
        f"👥 کل کاربران: {s['users']}\n"
        f"🟢 فعال امروز: {s['active_today']}\n"
        f"💎 VIP فعال: {s['vip']}\n"
        f"🚫 مسدود: {s['banned']}\n"
        f"📨 درخواست امروز: {s['requests_today']}\n"
        f"📦 کل درخواست‌ها: {s['requests_total']}"
    )


@router.message(Command("vip"))
async def give_vip(message: Message, command: CommandObject, db, bot: Bot, settings):
    nums = _parse_ints(command.args)
    if not nums:
        await message.answer("استفاده: /vip user_id [days]")
        return
    uid = nums[0]
    days = nums[1] if len(nums) > 1 else settings.vip_days
    if await db.add_vip(uid, days) is None:
        await message.answer("❌ این کاربر هنوز ربات رو استارت نکرده.")
        return
    await message.answer(f"✅ VIP برای <code>{uid}</code> به مدت {days} روز فعال شد.")
    await _notify(bot, uid, t.VIP_ACTIVATED.format(days=days))


@router.message(Command("unvip"))
async def remove_vip(message: Message, command: CommandObject, db):
    nums = _parse_ints(command.args)
    if not nums:
        await message.answer("استفاده: /unvip user_id")
        return
    ok = await db.remove_vip(nums[0])
    await message.answer("✅ VIP حذف شد." if ok else "❌ کاربر پیدا نشد.")


@router.message(Command("ban"))
async def ban(message: Message, command: CommandObject, db, settings):
    nums = _parse_ints(command.args)
    if not nums:
        await message.answer("استفاده: /ban user_id")
        return
    if nums[0] in settings.admin_ids:
        await message.answer("❌ ادمین رو نمی‌شه مسدود کرد.")
        return
    ok = await db.set_banned(nums[0], True)
    await message.answer("🚫 مسدود شد." if ok else "❌ کاربر پیدا نشد.")


@router.message(Command("unban"))
async def unban(message: Message, command: CommandObject, db):
    nums = _parse_ints(command.args)
    if not nums:
        await message.answer("استفاده: /unban user_id")
        return
    ok = await db.set_banned(nums[0], False)
    await message.answer("✅ رفع مسدودی شد." if ok else "❌ کاربر پیدا نشد.")


@router.message(Command("broadcast"))
async def broadcast(message: Message, command: CommandObject, db, bot: Bot):
    source = message.reply_to_message
    text = (command.args or "").strip()
    if not source and not text:
        await message.answer("استفاده: /broadcast متن پیام\nیا روی یک پیام ریپلای کن و /broadcast بزن.")
        return

    ids = await db.all_user_ids()
    await message.answer(f"📣 ارسال برای {len(ids)} کاربر شروع شد...")
    ok = failed = 0
    for uid in ids:
        for _attempt in range(2):
            try:
                if source:
                    await bot.copy_message(uid, source.chat.id, source.message_id)
                else:
                    await bot.send_message(uid, text, parse_mode=None)
                ok += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramAPIError:
                failed += 1
                break
        await asyncio.sleep(0.05)
    await message.answer(f"✅ پایان ارسال همگانی\nموفق: {ok}\nناموفق: {failed}")


@router.callback_query(F.data.startswith("vipok:"))
async def approve_vip(callback: CallbackQuery, db, bot: Bot):
    _, uid, days = callback.data.split(":")
    uid, days = int(uid), int(days)
    if await db.add_vip(uid, days) is None:
        await callback.answer("کاربر پیدا نشد.", show_alert=True)
        return
    await callback.answer("✅ تایید شد")
    if callback.message:
        await callback.message.edit_text(
            f"{html.escape(callback.message.text or '')}\n\n✅ تایید شد ({days} روز) توسط {html.escape(callback.from_user.full_name)}",
            reply_markup=None,
        )
    await _notify(bot, uid, t.VIP_ACTIVATED.format(days=days))


@router.callback_query(F.data.startswith("vipno:"))
async def reject_vip(callback: CallbackQuery, bot: Bot):
    uid = int(callback.data.split(":")[1])
    await callback.answer("رد شد")
    if callback.message:
        await callback.message.edit_text(
            f"{html.escape(callback.message.text or '')}\n\n❌ رد شد توسط {html.escape(callback.from_user.full_name)}",
            reply_markup=None,
        )
    await _notify(bot, uid, t.VIP_REJECTED)
