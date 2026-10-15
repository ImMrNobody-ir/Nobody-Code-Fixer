import asyncio
import base64
import logging

import aiohttp

log = logging.getLogger(__name__)

# Statuses that mean "this model is unavailable right now": retry once, then try the next model.
SWITCH_STATUSES = {404, 429, 500, 502, 503, 504}
ATTEMPTS_PER_MODEL = 2


class LLMError(Exception):
    """Raised when the model could not produce an answer.

    `switch_model` is True when trying another model may help
    (model removed, overloaded, rate limited, network trouble).
    """

    def __init__(self, message: str, switch_model: bool = False):
        super().__init__(message)
        self.switch_model = switch_model


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        proxy: str | None = None,
        fallback_models: list[str] | None = None,
        max_output_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.proxy = proxy
        self.max_output_tokens = max_output_tokens
        # Primary first, then fallbacks, without duplicates.
        self.models = list(dict.fromkeys([model, *(fallback_models or [])]))
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

    async def _request(self, model: str, payload: dict) -> dict:
        """Call one model, retrying briefly. Raises LLMError (switch_model=True if worth switching)."""
        url = f"{self.base_url}/models/{model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        session = await self._get_session()
        last_error = "unknown error"

        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    proxy=None if self._is_socks else self.proxy,
                ) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status == 200:
                        return body
                    message = ""
                    if isinstance(body, dict):
                        message = body.get("error", {}).get("message", "")
                    last_error = f"HTTP {resp.status}: {message}"
                    if resp.status not in SWITCH_STATUSES:
                        raise LLMError(last_error)  # e.g. 400/401/403: another model won't help
                    if resp.status == 404:
                        raise LLMError(last_error, switch_model=True)  # no point retrying
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = f"network error: {exc!r}"

            log.warning("Gemini %s attempt %s/%s failed: %s", model, attempt, ATTEMPTS_PER_MODEL, last_error)
            if attempt < ATTEMPTS_PER_MODEL:
                await asyncio.sleep(2 * attempt)

        raise LLMError(last_error, switch_model=True)

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

        data: dict | None = None
        last_error: LLMError | None = None
        for index, model in enumerate(self.models):
            try:
                data = await self._request(model, payload)
            except LLMError as exc:
                last_error = exc
                if not exc.switch_model:
                    raise
                if index + 1 < len(self.models):
                    log.warning("Model %s failed (%s); trying %s", model, exc, self.models[index + 1])
                continue
            if index > 0:
                log.info("Answered by fallback model %s", model)
            break

        if data is None:
            raise last_error or LLMError("no model available")

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
