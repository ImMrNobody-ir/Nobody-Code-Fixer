import asyncio
import io
import logging
import os
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

import keyboards as kb
import texts as t
from services import limiter
from services.llm import LLMError
from services.prompts import build_system
from utils.formatting import render, strip_tags

log = logging.getLogger(__name__)
router = Router()

_locks: dict[int, asyncio.Lock] = {}

MAX_FILE_BYTES = 200 * 1024
ALLOWED_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".go", ".rs", ".php", ".rb", ".kt", ".swift", ".sh", ".bat", ".ps1", ".sql",
    ".html", ".css", ".scss", ".json", ".yml", ".yaml", ".xml", ".ini", ".toml",
    ".txt", ".log", ".md", ".dart", ".lua", ".r", ".vue",
}


async def process(
    message: Message,
    bot: Bot,
    db,
    llm,
    settings,
    user_row,
    prompt: str,
    stored_user_text: str,
    image: bytes | None = None,
) -> None:
    uid = message.from_user.id
    lock = _locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        await message.answer(t.BUSY)
        return

    async with lock:
        allowed, _used, limit = await limiter.check(db, settings, user_row)
        if not allowed:
            await message.answer(
                t.LIMIT_REACHED.format(limit=limit), reply_markup=kb.account_kb(settings.payments_enabled)
            )
            return

        history = await db.get_history(uid, settings.history_messages)
        system = build_system(user_row["mode"], user_row["task"])

        try:
            async with ChatActionSender.typing(chat_id=message.chat.id, bot=bot):
                answer = await llm.generate(system, history, prompt, image=image)
        except LLMError as exc:
            log.error("LLM failure for user %s: %s", uid, exc)
            await message.answer(t.LLM_FAIL)
            return

        await limiter.consume(db, uid)
        await db.add_history(uid, "user", stored_user_text)
        await db.add_history(uid, "model", answer)
        await db.log_request(uid, user_row["task"])

        parts = render(answer)
        for index, part in enumerate(parts):
            markup = kb.answer_kb() if index == len(parts) - 1 else None
            try:
                await message.answer(part, reply_markup=markup)
            except TelegramBadRequest:
                await message.answer(strip_tags(part), parse_mode=None, reply_markup=markup)


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot, db, llm, settings, user_row):
    buffer = io.BytesIO()
    await bot.download(message.photo[-1], destination=buffer)
    caption = (message.caption or "").strip()
    prompt = caption or t.IMAGE_DEFAULT
    if caption:
        prompt = f"{caption}\n\n(تصویر پیوست شده را هم بررسی کن.)"
    await process(
        message, bot, db, llm, settings, user_row,
        prompt=prompt,
        stored_user_text=f"[تصویر] {caption}".strip(),
        image=buffer.getvalue(),
    )


@router.message(F.document)
async def on_document(message: Message, bot: Bot, db, llm, settings, user_row):
    doc = message.document
    ext = os.path.splitext(doc.file_name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        await message.answer(t.FILE_BAD_TYPE)
        return
    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await message.answer(t.FILE_TOO_BIG)
        return

    buffer = io.BytesIO()
    await bot.download(doc, destination=buffer)
    content = buffer.getvalue().decode("utf-8", errors="replace")
    truncated = len(content) > settings.max_input_chars
    content = content[: settings.max_input_chars]

    caption = (message.caption or "").strip()
    fence = "````" if "```" in content else "```"
    prompt = f"فایل: {doc.file_name}\n{fence}\n{content}\n{fence}"
    if truncated:
        prompt += "\n(فایل به‌خاطر طول زیاد ناقص ارسال شده است.)"
    if caption:
        prompt = f"{caption}\n\n{prompt}"

    stored = f"[فایل {doc.file_name}] {caption}\n{content[:1200]}".strip()
    await process(message, bot, db, llm, settings, user_row, prompt=prompt, stored_user_text=stored)


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot, db, llm, settings, user_row):
    text = message.text.strip()
    if len(text) > settings.max_input_chars:
        await message.answer(t.TOO_LONG.format(limit=settings.max_input_chars))
        return
    if not re.search(r"\S", text):
        return
    await process(message, bot, db, llm, settings, user_row, prompt=text, stored_user_text=text)
