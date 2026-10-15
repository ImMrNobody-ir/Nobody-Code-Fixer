import asyncio
import base64
import logging

import aiohttp

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Raised when the model could not produce an answer."""


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        proxy: str | None = None,
        max_output_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.proxy = proxy
        self.max_output_tokens = max_output_tokens
        self._session: aiohttp.ClientSession | None = None

    @property
    def _is_socks(self) -> bool:
        return bool(self.proxy and self.proxy.lower().startswith("socks"))

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=90)
            if self._is_socks:
                # aiohttp itself only speaks HTTP proxies; SOCKS needs aiohttp-socks.
                from aiohttp_socks import ProxyConnector

                self._session = aiohttp.ClientSession(
                    timeout=timeout, connector=ProxyConnector.from_url(self.proxy)
                )
            else:
                self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate(
        self,
        system: str,
        history: list[tuple[str, str]],
        user_text: str,
        image: bytes | None = None,
        image_mime: str = "image/jpeg",
    ) -> str:
        # Gemini expects the conversation to start with a user turn.
        history = list(history)
        while history and history[0][0] != "user":
            history.pop(0)

        contents = [
            {"role": "user" if role == "user" else "model", "parts": [{"text": text}]}
            for role, text in history
        ]
        parts = []
        if image:
            parts.append(
                {"inline_data": {"mime_type": image_mime, "data": base64.b64encode(image).decode()}}
            )
        parts.append({"text": user_text})
        contents.append({"role": "user", "parts": parts})

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": self.max_output_tokens,
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        session = await self._get_session()
        data: dict | None = None
        last_error = "unknown error"

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    proxy=None if self._is_socks else self.proxy,
                ) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status == 200:
                        data = body
                        break
                    message = ""
                    if isinstance(body, dict):
                        message = body.get("error", {}).get("message", "")
                    last_error = f"HTTP {resp.status}: {message}"
                    if resp.status not in RETRY_STATUSES:
                        raise LLMError(last_error)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = f"network error: {exc!r}"

            log.warning("Gemini attempt %s/%s failed: %s", attempt, MAX_ATTEMPTS, last_error)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(2 * attempt)

        if data is None:
            raise LLMError(last_error)

        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMError(f"blocked or empty: {reason}")

        candidate = candidates[0]
        text = "".join(
            p.get("text", "") for p in (candidate.get("content") or {}).get("parts", [])
        ).strip()
        if not text:
            raise LLMError(f"empty answer (finishReason={candidate.get('finishReason')})")
        if candidate.get("finishReason") == "MAX_TOKENS":
            text += "\n\n…(پاسخ به‌خاطر محدودیت طول ناقص ماند؛ بنویس «ادامه بده»)"
        return text
