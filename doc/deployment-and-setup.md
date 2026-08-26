# راهنمای نصب، راه‌اندازی و استقرار (Deployment & Setup)

این سند راهنمای گام‌به‌گام راه‌اندازی پروژه در محیط‌های محلی (Local)، توسعه و همچنین استقرار با کانتینرهای Docker را ارائه می‌دهد.

---

## ۱. پیش‌نیازها

- **Python:** نسخه `3.12` یا بالاتر
- **Django:** نسخه‌های `5.2` تا `6.0` (نصب خودکار از طریق `requirements.txt`)
- **مدیر بسته:** `pip` یا `uv`

---

## ۲. راه‌اندازی گام‌به‌گام در محیط محلی

### در سیستم‌عامل ویندوز (PowerShell / CMD):

```powershell
# ۱. ساخت و فعال‌سازی محیط مجازی
python -m venv .venv
.venv\Scripts\activate

# ۲. نصب نیازمندی‌ها
pip install -r requirements.txt

# ۳. اعمال مایگریشن‌های دیتابیس
python manage.py migrate

# ۴. ساخت حساب مدیر برای تعریف کاربران
python manage.py createsuperuser

# ۵. اجرای تست‌ها برای اطمینان از سلامت پروژه
python manage.py test

# ۶. اجرای سرور توسعه
python manage.py runserver
```

---

### در سیستم‌عامل‌های Linux و macOS:

```bash
# ۱. ساخت و فعال‌سازی محیط مجازی
python3 -m venv .venv
source .venv/bin/activate

# ۲. نصب نیازمندی‌ها
pip install -r requirements.txt

# ۳. اعمال مایگریشن‌های دیتابیس
python manage.py migrate

# ۴. ساخت حساب مدیر
python manage.py createsuperuser

# ۵. اجرای تست‌ها
python manage.py test

# ۶. اجرای سرور
python manage.py runserver
```

سپس مرورگر خود را باز کرده و به آدرس زیر بروید:
```text
http://127.0.0.1:8000/
```

---

### الف) تنظیمات سیستم و هوش مصنوعی

| نام متغیر | مقدار پیش‌فرض | توضیح |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | `dev-only-change-me` | کلید امنیتی جنگو (در محیط Production حتماً تغییر کند) |
| `DJANGO_DEBUG` | `False` | وضعیت دیباگ (`True` در توسعه، `False` در سرور اصلی) |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | دامنه‌ها یا IPهای مجاز برای دسترسی |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `""` | آدرس‌های معتبر پروتکل امن HTTPS برای CSRF |
| `DJANGO_BEHIND_PROXY` | `False` | در صورت قرار داشتن پشت Nginx یا Caddy برابر `True` شود |
| `DJANGO_DB_PATH` | `BASE_DIR/db.sqlite3` | مسیر فایل پایگاه داده SQLite |
| `ORCAROUTER_API_KEY` | `None` | کلید اختصاصی اتصال به API مدل DeepSeek در OrcaRouter |
| `ORCAROUTER_MODEL` | `deepseek/deepseek-v4-flash-free` | شناسه مدل هوش مصنوعی برای کامپایلر استراتژی |

### ب) ابعاد زمین و فیزیک بازی (Playground & Physics Variables)

تمامی پارامترهای فیزیکی بازی به صورت متغیرهای محیطی قابل تغییر هستند و به صورت خودکار به فرانت‌اند نیز منتقل می‌شوند (جهت مشاهده توضیحات کامل‌تر به فایل [`.env.example`](../.env.example) مراجعه کنید):

| نام متغیر محیطی | مقدار پیش‌فرض | واحد / مفهوم |
| :--- | :--- | :--- |
| `GAME_PLAYGROUND_WIDTH` | `1280.0` | عرض کل زمین بازی (px) |
| `GAME_PLAYGROUND_HEIGHT` | `720.0` | ارتفاع کل صفحه بازی (px) |
| `GAME_GROUND_Y` | `610.0` | موقعیت عمودی خط سطح زمین (px) |
| `GAME_GOAL_DEPTH` | `105.0` | عمق فرورفتگی دروازه (px) |
| `GAME_GOAL_HEIGHT` | `135.0` | ارتفاع تیر دروازه از زمین (px) |
| `GAME_BALL_RADIUS` | `22.0` | شعاع و اندازه توپ (px) |
| `GAME_GRAVITY` | `1700.0` | شتاب گرانش زمین وارد بر توپ (px/s²) |
| `GAME_BALL_MAX_SPEED` | `1450.0` | سقف حداکثر سرعت توپ (px/s) |
| `GAME_FLOOR_BOUNCE` | `0.58` | ضریب کشسانی و جهش توپ از زمین |
| `GAME_FLOOR_FRICTION` | `0.980` | ضریب اصطکاک لغزشی توپ با چمن |
| `GAME_BALL_AIR_DRAG` | `0.999` | ضریب اصطکاک و مقاومت هوا برای توپ |
| `GAME_BALL_WALL_BOUNCE` | `0.84` | ضریب کشسانی برخورد با دیواره‌ها |
| `GAME_BALL_CEILING_BOUNCE` | `0.82` | ضریب کشسانی برخورد با سقف |
| `GAME_BALL_HEAD_RESTITUTION` | `0.78` | ضریب کشسانی برخورد با سر بازیکن |
| `GAME_BALL_BODY_RESTITUTION` | `0.46` | ضریب کشسانی برخورد با بدن بازیکن |
| `GAME_BALL_IMPULSE_SCALE` | `0.05` | ضریب جرم و وزن موثر توپ در برخورد |
| `GAME_PLAYER_WIDTH` | `58.0` | عرض بازیکن (px) |
| `GAME_PLAYER_HEIGHT` | `72.0` | ارتفاع بازیکن (px) |
| `GAME_PLAYER_SPEED` | `385.0` | سرعت دویدن بازیکن روی زمین (px/s) |
| `GAME_PLAYER_JUMP_SPEED` | `790.0` | سرعت اولیه پرش بازیکن (px/s) |
| `GAME_PLAYER_GRAVITY` | `2050.0` | شتاب گرانش بازیکن (px/s²) |
| `GAME_KICK_REACH` | `126.0` | شعاع برد ضربه شوت به توپ (px) |
| `GAME_KICK_LOW_X` | `850.0` | قدرت افقی شوت زمینی |
| `GAME_KICK_HIGH_X` | `760.0` | قدرت افقی شوت هوایی |
| `GAME_KICK_CLEAR_X` | `1000.0` | قدرت افقی ضربه دفع |
| `GAME_MATCH_TIME` | `60.0` | مدت زمان هر مسابقه (ثانیه) |
| `GAME_PHYSICS_FPS` | `60` | نرخ اجرای فیزیک در ثانیه (Hz) |
| `GAME_RECORD_FPS` | `20` | نرخ ذخیره فریم‌ها برای کلاینت (FPS) |

---

## ۴. استقرار با Docker و Docker Compose

پروژه دارای یک [`Dockerfile`](../Dockerfile) چندمرحله‌ای و [`docker-compose.yml`](../docker-compose.yml) بهینه با وب‌سرور پرسرعت `Gunicorn` و `Whitenoise` برای مدیریت فایل‌های استاتیک است.

### اجرای ساده با Docker Compose:

```bash
# بیلد و اجرای کانتینر در پس‌زمینه
docker compose up -d --build
```

### لاگ‌های کانتینر:
```bash
docker compose logs -f
```

---

## ۵. ادغام اپلیکیشن `game` با پروژه‌های جنگوی موجود

اگر می‌خواهید این بازی را درون یک پورتال آموزشی یا وب‌سایت جنگوی بزرگ‌تر ادغام کنید:

1. پوشه [`game/`](../game/) را در کنار سایر اپلیکیشن‌های پروژه خود کپی کنید.
2. در `settings.py` پروژه اصلی، `"game"` را به `INSTALLED_APPS` اضافه کنید:
   ```python
   INSTALLED_APPS = [
       # ...
       "game",
   ]
   ```
3. در `urls.py` اصلی پروژه، مسیرهای بازی را فراخوانی کنید:
   ```python
   from django.urls import include, path

   urlpatterns = [
       # ...
       path("ai-football/", include("game.urls")),
   ]
   ```

---

## ناوبری مستندات

- ⬅️ **قبلی: [احراز هویت و پنل مدیریت (auth-and-admin.md)](./auth-and-admin.md)**
- 🏠 **[بازگشت به صفحه اصلی مستندات (README.md)](../README.md)**
