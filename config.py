import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _ints(value: str) -> list[int]:
    out = []
    for part in value.replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def _channels(value: str) -> list[str]:
    out = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(part if part.startswith(("@", "-")) else "@" + part)
    return out


@dataclass(frozen=True)
class Settings:
    bot_token: str
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_models: list[str]
    gemini_base_url: str
    proxy_url: str | None
    admin_ids: list[int]
    free_daily_limit: int
    vip_days: int
    force_join_channels: list[str]
    card_number: str
    card_holder: str
    vip_price: str
    history_messages: int
    max_input_chars: int
    db_path: str

    @property
    def payments_enabled(self) -> bool:
        return bool(self.card_number and self.admin_ids)


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN در فایل .env تنظیم نشده است.")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY در فایل .env تنظیم نشده است.")

    return Settings(
        bot_token=token,
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
        gemini_fallback_models=[
            m.strip()
            for m in os.getenv(
                "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite"
            ).split(",")
            if m.strip()
        ],
        gemini_base_url=os.getenv(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/"),
        proxy_url=os.getenv("PROXY_URL", "").strip() or None,
        admin_ids=_ints(os.getenv("ADMIN_IDS", "")),
        free_daily_limit=int(os.getenv("FREE_DAILY_LIMIT", "5")),
        vip_days=int(os.getenv("VIP_DAYS", "30")),
        force_join_channels=_channels(os.getenv("FORCE_JOIN_CHANNELS", "")),
        card_number=os.getenv("CARD_NUMBER", "").strip(),
        card_holder=os.getenv("CARD_HOLDER", "").strip(),
        vip_price=os.getenv("VIP_PRICE", "").strip(),
        history_messages=int(os.getenv("HISTORY_MESSAGES", "6")),
        max_input_chars=int(os.getenv("MAX_INPUT_CHARS", "12000")),
        db_path=os.getenv("DB_PATH", "data/bot.db").strip(),
    )
