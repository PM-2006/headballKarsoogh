# AI Football Arena — Django/Python

نسخه Django بازی AI Football Arena برای کارگاه دانش‌آموزی.

## معماری

- **فیزیک، Sensorها، Rule Engine و Batch Test همگی با Python** در سمت Django اجرا می‌شوند.
- مرورگر فقط Canvas را رسم می‌کند و فریم‌های شبیه‌سازی‌شده را پخش می‌کند.
- Strategyهای مسابقه روی سرور validate می‌شوند؛ تغییر JavaScript نمی‌تواند قوانین تورنمنت را عوض کند.
- مرز اتصال LLM از الان در `game/services/llm.py` جدا شده، ولی خود LLM هنوز متصل نشده است.

کد از قابلیت اختصاصی Django 6 استفاده نمی‌کند و برای Django 5.2 تا 6.0 نوشته شده است. Django 6.0 نسخه پایدار فعلی است و Python 3.12+ را پشتیبانی می‌کند؛ برای ادغام با پروژه‌های موجود، `requirements.txt` بازه `Django>=5.2,<6.1` را نگه داشته است.

## اجرای مستقل

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py test
python manage.py runserver
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py test
python manage.py runserver
```

بعد برو به:

```text
http://127.0.0.1:8000/
```

## ساختار

```text
headballKarsoogh-django/
├── config/                  # پروژه دموی مستقل Django
├── game/                    # اپ قابل انتقال به سایت اصلی
│   ├── engine.py            # تمام فیزیک و شبیه‌سازی Python
│   ├── strategy.py          # Sensors / Actions / Presets
│   ├── validators.py        # اعتبارسنجی Strategy JSON
│   ├── views.py             # APIهای Django
│   ├── urls.py
│   ├── services/llm.py      # محل اتصال LLM در مرحله بعد
│   ├── templates/game/index.html
│   └── static/game/
│       ├── game.js          # فقط UI و پخش فریم‌ها
│       └── styles.css
├── manage.py
└── requirements.txt
```

## APIها

### `GET /api/vocabulary/`
Sensorها، Operatorها، Actionها و Strategyهای پیش‌فرض.

### `POST /api/validate/`
Strategy سفارشی را قبل از ورود به موتور بازی بررسی می‌کند.

### `POST /api/simulate/`

```json
{
  "blue": {"preset": "aggressive"},
  "red": {"preset": "adaptive"},
  "seed": 1
}
```

خروجی شامل نتیجه و فریم‌های مسابقه است. تمام فریم‌ها در Python محاسبه شده‌اند.

### `POST /api/batch/`

```json
{
  "blue": {"preset": "aggressive"},
  "red": {"preset": "defensive"},
  "matches": 100,
  "seed": 1
}
```

برای Balance Test. در بازی‌های زوج، جای دو Strategy عوض می‌شود تا اثر سمت زمین خنثی شود.

## ادغام با سایت Django موجود

اگر سایت اصلی از قبل Django دارد، پوشه `config` و `manage.py` این پروژه لازم نیست.

1. پوشه `game` را داخل پروژه اصلی کپی کن.
2. در `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "game",
]
```

3. در `urls.py` اصلی:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("ai-football/", include("game.urls")),
]
```

بعد بازی روی `/ai-football/` در دسترس است.

## مرحله بعد: LLM

معماری بعدی بدون تغییر موتور بازی:

```text
متن فارسی دانش‌آموز
        ↓
Django POST /api/strategy/compile/
        ↓
LLM Structured Output
        ↓
Strategy JSON
        ↓
validate_strategy()
        ↓
engine.py
```

LLM فقط هنگام ساخت Strategy فراخوانی می‌شود. **هنگام خود مسابقه هیچ LLMای اجرا نمی‌شود.**

## OrcaRouter + DeepSeek V4 Flash integration

نسخه فعلی می‌تواند متن فارسی دانش‌آموز را از طریق OrcaRouter به مدل زیر بفرستد:

```text
deepseek/deepseek-v4-flash-free
```

معماری:

```text
Persian strategy
    -> Django /api/compile-strategy/
    -> OrcaRouter
    -> DeepSeek V4 Flash
    -> Strategy JSON
    -> validate_strategy()
    -> Python game engine
```

System Prompt از کد اتصال API جدا شده است:

```text
game/prompts/strategy_compiler.py
```

و اتصال API در این فایل است:

```text
game/services/llm.py
```

این جداسازی عمدی است تا بتوان Prompt را بدون دست‌زدن به کد شبکه و API مرتب تست و اصلاح کرد.

### 1) نصب dependencyها

```bash
pip install -r requirements.txt
```

### 2) تنظیم API key

API key را هرگز داخل GitHub قرار ندهید.

PowerShell:

```powershell
$env:ORCAROUTER_API_KEY="sk-orca-YOUR-REAL-KEY"
$env:ORCAROUTER_MODEL="deepseek/deepseek-v4-flash-free"
```

CMD:

```cmd
set ORCAROUTER_API_KEY=sk-orca-YOUR-REAL-KEY
set ORCAROUTER_MODEL=deepseek/deepseek-v4-flash-free
```

macOS / Linux:

```bash
export ORCAROUTER_API_KEY="sk-orca-YOUR-REAL-KEY"
export ORCAROUTER_MODEL="deepseek/deepseek-v4-flash-free"
```

### 3) اجرا

```bash
python manage.py check
python manage.py runserver
```

سپس:

```text
http://127.0.0.1:8000/
```

### API کامپایل Strategy

```text
POST /api/compile-strategy/
```

Request:

```json
{
  "text": "اگر حریف از من به توپ نزدیک‌تر بود برگرد دفاع..."
}
```

Response موفق:

```json
{
  "valid": true,
  "feedback": [],
  "strategy": {},
  "model": "deepseek/deepseek-v4-flash-free",
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

### اصل امنیتی

LLM هیچ‌وقت Python یا JavaScript تولید و اجرا نمی‌کند. خروجی آن فقط Strategy JSON است و قبل از ورود به مسابقه حتماً توسط `validate_strategy()` بررسی می‌شود.
