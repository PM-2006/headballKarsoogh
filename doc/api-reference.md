# مرجع کامل APIهای سامانه (REST API Reference)

این سند جزییات تمامی اندپوینت‌های ارائه‌شده توسط جنگو در فایل‌های [`game/urls.py`](../game/urls.py) و [`game/views.py`](../game/views.py) را شرح می‌دهد.

---

## ۱. نکات امنیتی و عمومی APIها

- **احراز هویت:** تمام اندپوینت‌های این پروژه تحت دکوراتور `@login_required` محافظت می‌شوند. کاربر باید ابتدا لاگین کرده و کوکی نشست (`sessionid`) معتبر داشته باشد.
- **محافظت CSRF:** در درخواست‌های `POST`، باید هدر `X-CSRFToken` با مقدار توکن CSRF معتبر ارسال شود.
- **فرمت داده:** تمام درخواست‌ها و پاسخ‌ها از فرمت استاندارد `JSON` با `Content-Type: application/json` استفاده می‌کنند.

---

## ۲. لیست کامل اندپوینت‌ها

```text
GET   /api/vocabulary/            # دریافت واژگان مجاز (سنسورها، اکشن‌ها، پریست‌ها)
POST  /api/validate/              # اعتبارسنجی ساختار استراتژی
POST  /api/simulate/              # شبیه‌سازی یک مسابقه ۱ به ۱ با فریم‌ها
POST  /api/batch/                 # شبیه‌سازی چندگانه (Balance Test)
POST  /api/compile-strategy/      # ترجمه متن فارسی به استراتژی با هوش مصنوعی
```

---

### ۱) دریافت واژگان بازی — `GET /api/vocabulary/`

واژگان رسمی شامل لیست سنسورها، عملگرها، اعمال حرکتی و نام استراتژی‌های پیش‌فرض را برمی‌گرداند.

#### نمونه پاسخ (Response `200 OK`):
```json
{
  "sensors": {
    "my_x": "number",
    "ball_x": "number",
    "can_kick": "boolean",
    "ball_above_me": "boolean"
  },
  "operators": ["<", "<=", ">", ">=", "==", "!="],
  "actions": [
    "MOVE_LEFT", "MOVE_RIGHT", "MOVE_TO_BALL", "MOVE_TO_GOAL", 
    "MOVE_TO_CENTER", "JUMP", "KICK_LOW", "KICK_HIGH", "KICK_CLEAR", "IDLE"
  ],
  "presets": {
    "aggressive": "Aggressive",
    "defensive": "Defensive",
    "predictive": "Predictive",
    "counter": "Counter Attack",
    "adaptive": "Adaptive",
    "goalie": "Goal Keeper"
  }
}
```

---

### ۲) اعتبارسنجی استراتژی — `POST /api/validate/`

یک استراتژی خام را قبل از اجرای بازی اعتبارسنجی می‌کند.

#### نمونه بدنه درخواست (Request Body):
```json
{
  "strategy": {
    "label": "Custom Bot",
    "rules": [
      {
        "priority": 1,
        "conditions": [
          {"left": "can_kick", "operator": "==", "rightType": "value", "right": true}
        ],
        "action": "KICK_LOW"
      }
    ],
    "default_action": "IDLE"
  }
}
```

#### نمونه پاسخ موفق (`200 OK`):
```json
{
  "valid": true,
  "strategy": { ... }
}
```

#### نمونه پاسخ خطا (`400 Bad Request`):
```json
{
  "valid": false,
  "error": "سنسور ناشناخته: invalid_sensor_name"
}
```

---

### ۳) شبیه‌سازی مسابقه — `POST /api/simulate/`

یک بازی ۶۰ ثانیه‌ای بین دو ربات را شبیه‌سازی کرده و تمامی فریم‌های حرکتی را برای پخش در Canvas بازمی‌گرداند.

#### نمونه بدنه درخواست (Request Body):
```json
{
  "blue": { "preset": "aggressive" },
  "red": { 
    "strategy": {
      "label": "My Bot",
      "rules": [ ... ],
      "default_action": "IDLE"
    }
  },
  "seed": 42
}
```

#### نمونه پاسخ موفق (`200 OK`):
```json
{
  "duration": 60.0,
  "score": [3, 2],
  "physics_fps": 60,
  "record_fps": 20,
  "frames": [
    {
      "time": 0.0,
      "score": [0, 0],
      "players": [
        {"x": 255.0, "y": 538.0, "vx": 0.0, "vy": 0.0, "face": 1},
        {"x": 967.0, "y": 538.0, "vx": 0.0, "vy": 0.0, "face": -1}
      ],
      "ball": {"x": 640.0, "y": 150.0, "vx": 32.5, "vy": 18.2},
      "debug": [
        {"rule": "1", "action": "MOVE_TO_BALL"},
        {"rule": "2", "action": "MOVE_TO_GOAL"}
      ]
    }
  ]
}
```

---

### ۴) شبیه‌سازی دسته‌ای — `POST /api/batch/`

تعداد مشخصی بازی (مثلاً ۱۰۰ بازی متوالی) بدون ضبط فریم و با سرعت بسیار بالا را برای مقایسه عملکرد دو استراتژی و تست توازن اجرا می‌کند.

#### نمونه بدنه درخواست (Request Body):
```json
{
  "blue": { "preset": "aggressive" },
  "red": { "preset": "defensive" },
  "matches": 100,
  "seed": 1
}
```

#### نمونه پاسخ موفق (`200 OK`):
```json
{
  "matches": 100,
  "blue_wins": 52,
  "red_wins": 36,
  "draws": 12,
  "blue_goals": 184,
  "red_goals": 142,
  "blue_goals_per_match": 1.84,
  "red_goals_per_match": 1.42
}
```

---

### ۵) کامپایل استراتژی با هوش مصنوعی — `POST /api/compile-strategy/`

متن فارسی دانش‌آموز را دریافت کرده و به یک `Strategy JSON` معتبر تبدیل می‌کند.

#### نمونه بدنه درخواست (Request Body):
```json
{
  "text": "اگر توانستم شوت کنم شوت هوایی بزن. اگر توپ در نیمه ما بود برو سمت توپ. در غیر این صورت برگرد به دفاع."
}
```

#### نمونه پاسخ موفق (`200 OK`):
```json
{
  "valid": true,
  "feedback": [],
  "strategy": {
    "label": "My Bot",
    "rules": [
      {
        "priority": 1,
        "conditions": [{"left": "can_kick", "operator": "==", "rightType": "value", "right": true}],
        "action": "KICK_HIGH"
      },
      {
        "priority": 2,
        "conditions": [{"left": "ball_in_own_half", "operator": "==", "rightType": "value", "right": true}],
        "action": "MOVE_TO_BALL"
      }
    ],
    "default_action": "MOVE_TO_GOAL"
  },
  "model": "deepseek/deepseek-v4-flash-free",
  "usage": {
    "prompt_tokens": 580,
    "completion_tokens": 120,
    "total_tokens": 700
  }
}
```

---

## ناوبری مستندات

- ⬅️ **قبلی: [کامپایلر استراتژی با هوش مصنوعی (ai-compiler.md)](./ai-compiler.md)**
- 🏠 **[بازگشت به صفحه اصلی مستندات (README.md)](../README.md)**
- ➡️ **گام بعدی: [احراز هویت و پنل مدیریت (auth-and-admin.md)](./auth-and-admin.md)**
