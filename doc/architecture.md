# معماری سیستم و چرخه حیات (Architecture & Lifecycle)

این سند معماری فنی، نحوه تعامل اجزا و جریان داده‌ها را در پروژه **AI Football Arena** شرح می‌دهد.

---

## ۱. نمای کلی معماری

پروژه به صورت **Server-Authoritative (سرور-محور)** طراحی شده است:

```mermaid
flowchart TD
    subgraph Client ["کلاینت (مرورگر کاربر)"]
        UI["رابط کاربری / Rule Builder"]
        NL["جعبه متن فارسی استراتژی"]
        Canvas["پخش‌کننده انیمیشن Canvas 2D"]
    end

    subgraph Django ["بک‌اند جنگو (Django Backend)"]
        Auth["سیستم احراز هویت و نشست‌ها"]
        Views["ویوهای API و صفحه اصلی"]
        Validator["اعتبارسنج استراتژی (Validators)"]
        Compiler["سرویس کامپایلر هوش مصنوعی (LLM Service)"]
        Engine["موتور فیزیک و شبیه‌سازی (Engine)"]
    end

    subgraph External ["سرویس‌های خارجی"]
        Orca["OrcaRouter / DeepSeek API"]
    end

    NL -->|ارسال متن فارسی| Views
    Views --> Compiler
    Compiler -->|درخواست پرامپت استنتاج| Orca
    Orca -->|بازگشت JSON خام| Compiler
    Compiler --> Validator
    
    UI -->|ارسال استراتژی دستی| Views
    Views --> Validator
    
    Validator --> Engine
    Engine -->|فریم‌های مسابقه و نتایج| Views
    Views -->|پاسخ JSON| Canvas
    
    Auth --> Views
```

### اصول کلیدی معماری:
1. **سرور همه‌چیز را تعیین می‌کند:** تمام محاسبات برداری، برخوردها، منطق استراتژی و امتیازدهی روی سرور پایتون محاسبه می‌شود. جاوااسکریپت در مرورگر صرفاً فریم‌های دریافت شده را روی عنصر `<canvas>` رندر می‌کند.
2. **غیرقابل دستکاری در سمت کلاینت:** دستکاری در کدهای مرورگر یا ارسال مقادیر نادرست نمی‌تواند قوانین یا نتایج فیزیک بازی را تغییر دهد؛ زیرا تمام استراتژی‌ها ابتدا توسط [`validate_strategy`](../game/validators.py) ارزیابی قطعی می‌شوند.
3. **جداسازی کامل هوش مصنوعی از فیزیک بازی:** هوش مصنوعی (LLM) فقط هنگام ترجمه متن فارسی به ساختار قوانین اجرا می‌شود. در حین مسابقه هیچ درخواست شبکه‌ای یا مدل زبانی اجرا نمی‌شود و سرعت شبیه‌سازی فوق‌العاده بالاست (بیش از ۱۰۰ مسابقه در چند ثانیه).

---

## ۲. اجزای سیستم (Components)

| بخش | مسیر فایل | مسئولیت |
| :--- | :--- | :--- |
| **موتور بازی** | [`game/engine.py`](../game/engine.py) | شبیه‌سازی ریاضی ۲ بعدی، محاسبه سنسورها، برخوردها، حرکت بازیکنان و توپ، ضبط فریم‌ها |
| **تعاریف استراتژی** | [`game/strategy.py`](../game/strategy.py) | تعریف سنسورها، عملگرها، اکشن‌ها و استراتژی‌های پیش‌فرض مسابقه |
| **اعتبارسنجی** | [`game/validators.py`](../game/validators.py) | بررسی فرمت، سازگاری انواع داده و محدودیت‌های امنیتی Strategy JSON |
| **کامپایلر LLM** | [`game/services/llm.py`](../game/services/llm.py) | فراخوانی مدل زبانی از طریق OrcaRouter و تبدیل پاسخ به استراتژی استاندارد |
| **پرامپت سیستم** | [`game/prompts/strategy_compiler.py`](../game/prompts/strategy_compiler.py) | پرامپت اختصاصی تبدیل بدون تغییر در هوشمندی و با محافظت ضد تزریق پرامپت |
| **لایه وب و API** | [`game/views.py`](../game/views.py) | کنترل دسترسی با `@login_required` و مدیریت درخواست‌های HTTP |
| **رابط کاربری** | [`game/templates/`](../game/templates/) و [`game/static/`](../game/static/) | صفحات HTML5 راست‌چین، استایل‌های مدرن و کنترلر UI با جاوااسکریپت خالص |

---

## ۳. جریان داده‌ها (Data Flow)

### الف) جریان کامپایل استراتژی با هوش مصنوعی

```mermaid
sequenceDiagram
    autonumber
    actor User as کاربر / دانش‌آموز
    participant Browser as مرورگر (game.js)
    participant View as ویو (views.py)
    participant LLM as سرویس LLM (llm.py)
    participant Model as مدل DeepSeek
    participant Val as اعتبارسنج (validators.py)

    User->>Browser: تایپ استراتژی فارسی و کلیک «تبدیل»
    Browser->>View: POST /api/compile-strategy/
    View->>LLM: compile_persian_strategy(text)
    LLM->>Model: درخواست به همراه System Prompt
    Model-->>LLM: پاسخ ساختاریافته JSON
    LLM->>Val: validate_strategy(strategy)
    Val-->>LLM: تأیید سلامت ساختار
    LLM-->>View: نتیجه معتبر + متادیتای مصرف توکن
    View-->>Browser: پاسخ JSON
    Browser-->>User: نمایش قوانین در رابط کاربری
```

---

### ب) جریان شبیه‌سازی مسابقه (Simulation Lifecycle)

```mermaid
sequenceDiagram
    autonumber
    actor User as کاربر
    participant Browser as مرورگر (game.js)
    participant View as ویو (views.py)
    participant Engine as موتور بازی (engine.py)

    User->>Browser: انتخاب ربات آبی و قرمز + کلیک «اجرای مسابقه»
    Browser->>View: POST /api/simulate/ (شامل استراتژی دو تیم و Seed)
    View->>Engine: simulate_match(blue, red, seed, record_frames=True)
    loop ۶۰ ثانیه زمان مسابقه (با گام‌های زمانی فیزیک)
        Engine->>Engine: ارزیابی سنسورها برای هر دو بازیکن
        Engine->>Engine: اجرای Rule Engine و تعیین اکشن بعدی
        Engine->>Engine: انتگرال‌گیری عددی مکان و سرعت توپ و بازیکنان
        Engine->>Engine: حل برخوردها و تشخیص گل
        Engine->>Engine: ذخیره فریم نمایشی در فواصل مشخص
    end
    Engine-->>View: آبجکت نتیجه (امتیاز نهایی، آمار و آرایه فریم‌ها)
    View-->>Browser: تحویل فریم‌ها
    Browser->>User: پخش انیمیشن روان با Canvas در مرورگر
```

---

## ۴. تکرارپذیری با Seed (Determinism)

یکی از قابلیت‌های کلیدی سیستم، **تکرارپذیری قطعی (Determinism)** است. هر مسابقه یک عدد `seed` می‌پذیرد:
- اگر دو استراتژی یکسان با یک `seed` مشخص اجرا شوند، نتیجه و تمام فریم‌های مسابقه بیت‌به‌بیت یکسان خواهند بود.
- در حالت `Batch Test`، مسابقات به صورت جفت‌های متقارن اجرا می‌شوند (در بازی‌های زوج، سمت زمین دو ربات عوض می‌شود) تا هیچ تیمی به دلیل سمت چپ یا راست بودن زمین برتری ناعادلانه نداشته باشد.

---

## ناوبری مستندات

- 🏠 **[بازگشت به صفحه اصلی مستندات (README.md)](../README.md)**
- ➡️ **گام بعدی: [موتور فیزیک و شبیه‌سازی بازی (game-engine.md)](./game-engine.md)**
- 📑 **سایر بخش‌ها:**
  - [سیستم استراتژی و قوانین (strategy-system.md)](./strategy-system.md)
  - [کامپایلر استراتژی با هوش مصنوعی (ai-compiler.md)](./ai-compiler.md)
  - [مرجع کامل APIها (api-reference.md)](./api-reference.md)
  - [احراز هویت و پنل مدیریت (auth-and-admin.md)](./auth-and-admin.md)
  - [نصب و استقرار (deployment-and-setup.md)](./deployment-and-setup.md)
