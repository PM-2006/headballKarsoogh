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

## ۳. متغیرهای محیطی (Environment Variables)

پروژه به گونه‌ای طراحی شده که تمامی تنظیمات حساس و عملیاتی را از متغیرهای محیطی دریافت کند:

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
