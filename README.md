# Nobody Code Fixer 🤖

ربات تلگرامی برای **رفع ارور و بررسی کد** با Gemini. ساخته‌شده با Python، aiogram 3 و SQLite.

## امکانات

- ارسال **متن، فایل کد یا اسکرین‌شات ارور** و دریافت علت، راه‌حل و کد اصلاح‌شده
- پنج نوع کار: تشخیص خودکار، رفع ارور، بررسی کد، توضیح کد، تبدیل کد به زبان دیگر
- سه حالت پاسخ: کوتاه، مفصل، آموزشی
- حافظه گفتگو (مثلاً: «حالا همینو async کن») و دکمه پاک‌کردن حافظه
- ذخیره راه‌حل‌ها و دیدن لیست «ذخیره‌شده‌ها»
- پاسخ‌های بلند خودکار به چند پیام تقسیم می‌شوند و کدها داخل بلوک قابل کپی هستند
- سهمیه روزانه رایگان + اشتراک **VIP** (پرداخت کارت‌به‌کارت با تایید ادمین)
- **Force Join**: عضویت اجباری در کانال‌ها
- پنل ادمین: آمار، VIP، بن و پیام همگانی

## نصب و اجرا

```bash
python -m venv .venv
source .venv/bin/activate        # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # سپس فایل .env را پر کن
python main.py
```

### مقادیر ضروری در `.env`

| متغیر | توضیح |
|---|---|
| `BOT_TOKEN` | توکن ربات از @BotFather |
| `GEMINI_API_KEY` | کلید رایگان از Google AI Studio |
| `ADMIN_IDS` | آیدی عددی ادمین‌ها (از @userinfobot بگیر) |

بقیه تنظیمات (سهمیه، VIP، کانال‌های اجباری، شماره کارت) در `.env.example` توضیح داده شده‌اند.

> **نکته برای سرور ایران:** هم تلگرام و هم Gemini از ایران محدود هستند. ربات را روی سرور خارج از ایران اجرا کن، یا `PROXY_URL` (و در صورت نیاز `GEMINI_BASE_URL`) را در `.env` تنظیم کن.

## دستورهای ادمین

| دستور | کار |
|---|---|
| `/admin` | راهنمای پنل |
| `/stats` | آمار کاربران و درخواست‌ها |
| `/vip user_id [days]` | فعال‌سازی یا تمدید VIP |
| `/unvip user_id` | حذف VIP |
| `/ban user_id` و `/unban user_id` | مسدود و آزاد کردن کاربر |
| `/broadcast متن` | پیام همگانی (یا ریپلای روی یک پیام) |

## Force Join

۱. ربات را در کانال **ادمین** کن.
۲. در `.env` بنویس: `FORCE_JOIN_CHANNELS=@channel1,@channel2`

اگر ربات ادمین نباشد، آن کانال نادیده گرفته می‌شود تا کاربران قفل نشوند.

## فروش VIP

با پر کردن `CARD_NUMBER` (و اختیاری `CARD_HOLDER` و `VIP_PRICE`) دکمه خرید در «حساب من» فعال می‌شود. کاربر عکس رسید می‌فرستد، ادمین پیام همراه دکمه تایید/رد دریافت می‌کند و با تایید، VIP خودکار فعال می‌شود.

## اجرای دائمی روی سرور (systemd)

```ini
# /etc/systemd/system/codefixer.service
[Unit]
Description=Nobody Code Fixer
After=network.target

[Service]
WorkingDirectory=/opt/code-fix-bot
ExecStart=/opt/code-fix-bot/.venv/bin/python main.py
Restart=always
User=bot

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now codefixer
```

## ساختار پروژه

```
main.py            نقطه شروع
config.py          خواندن تنظیمات از .env
texts.py           متن‌های ربات
keyboards.py       دکمه‌ها
middlewares.py     ثبت کاربر، بن، Force Join
handlers/          menu, code, saved, payment, admin
services/          llm (Gemini), prompts, limiter, membership
db/database.py     SQLite
utils/formatting.py  تبدیل Markdown به HTML تلگرام و تقسیم پیام‌ها
```

ساخته‌شده برای برند **nobody** · MrNobody

## دیپلوی روی Railway

۱. پروژه را روی یک ریپوی GitHub (ترجیحاً Private) بگذار. فایل `.env` توسط `.gitignore` آپلود نمی‌شود.
۲. در Railway: **New Project → Deploy from GitHub repo** و ریپو را انتخاب کن.
۳. در تب **Variables** این متغیرها را بساز:
   `BOT_TOKEN`، `GEMINI_API_KEY`، `ADMIN_IDS`، و در صورت نیاز `FREE_DAILY_LIMIT`، `FORCE_JOIN_CHANNELS`، `CARD_NUMBER`، `CARD_HOLDER`، `VIP_PRICE`
۴. **دیتابیس ماندگار (بسیار مهم):** فایل‌سیستم Railway با هر دیپلوی پاک می‌شود. در سرویس، **Volume** بساز (راست‌کلیک روی پروژه یا Ctrl+K و Volume) و آن را روی مسیر `/data` مانت کن، بعد متغیر `DB_PATH=/data/bot.db` را اضافه کن. بدون Volume، کاربران و VIPها با هر دیپلوی از بین می‌روند.
۵. چون ربات polling است، به دامنه یا پورت نیازی نیست. `Procfile` و `railway.json` سرویس را به‌صورت worker اجرا می‌کنند.
۶. لاگ‌ها را در تب **Deployments** ببین؛ باید پیام `Bot started as @...` را ببینی.

نکته: `PROXY_URL` را روی Railway تنظیم نکن، چون سرورهایش خارج از ایران است و تلگرام و Gemini مستقیم کار می‌کنند.
