# ⚽ AI Football Arena

A Django/Python platform for 1‑vs‑1 AI head‑ball matches, built for student workshops and AI competitions.

Each player designs the "brain" of a football‑playing bot — either visually with a **rule builder** or by **writing plain‑language strategy that an AI compiles into rules** — and then watches that bot compete in a live 2D simulation, or runs hundreds of matches at once to see which strategy actually wins.

The important design choice: **the server is the game.** All physics, sensors, and rule evaluation run in Python on the server. The browser only draws the frames the server already computed. Editing the client‑side JavaScript can't change the outcome of a match, so tournaments stay fair and every result is reproducible from its seed.

---

## Features

- **Server‑authoritative physics** — ball motion, collisions, jumps, kicks, and headers are simulated in Python at 60 Hz. The client is a pure replay/renderer.
- **Two ways to build a bot** — a visual rule builder (with multi‑condition `AND` rules and adjustable numeric thresholds), or natural‑language strategy text that an LLM translates into the exact same rule format.
- **Fast batch testing** — run up to 250 sixty‑second matches to compare two strategies; sides are swapped on alternating matches to cancel out any home‑side advantage.
- **Anti‑stall engine** — a watchdog keeps the ball in play if it ever gets wedged or goes to sleep, so a match never freezes.
- **Polished arena** — a floodlit stadium, a broadcast‑style scoreboard, a live "what is each bot doing right now" panel, goal celebrations, and an end‑of‑match winner screen.
- **Authentication** — every page and API is gated behind login; accounts are created by an admin, there is no public sign‑up.

---

## Quick start

Requires **Python 3.12+**. Written for Django 5.2–6.x.

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py test
python manage.py runserver
```

### macOS / Linux (bash / zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py test
python manage.py runserver
```

Then open:

```text
http://127.0.0.1:8000/
```

You'll be redirected to the login page. Sign in with the superuser you just created.

> **Static files note:** the project serves static assets through WhiteNoise's manifest storage. After you edit anything under `game/static/`, re‑run `python manage.py collectstatic` **and restart the server** — the file manifest is loaded into memory at startup.

---

## Accounts & login

There is no public registration. Access is intentionally invite‑only:

- All views use `@login_required`; visiting `/` while logged out redirects to `/login/`.
- Create players from the Django admin at `http://127.0.0.1:8000/admin/` (or with `python manage.py createsuperuser` for the first admin).
- Staff users see an extra "پنل مدیریت" (admin panel) link in the header.

See [`doc/auth-and-admin.md`](doc/auth-and-admin.md) for details.

---

## How a match works

1. A player builds a bot in the **Build Bot** tab — from a preset, the visual rule builder, or natural‑language text sent to the AI compiler.
2. The strategy is validated on the server (`/api/validate/` or `/api/compile-strategy/`).
3. In the **Arena** tab, the server simulates a 60‑second match (`/api/simulate/`) and returns the recorded frames.
4. The browser replays those frames on a `<canvas>`, with a live status panel, goal celebrations, and a winner screen.

**How a bot "thinks":** every frame the engine builds a snapshot of ~26 sensors (ball position and speed, distances, remaining time, score, `can_kick`, `ball_above_me`, …). It walks the bot's rules in priority order and fires the first rule whose conditions are all true; if none match, it uses the default action. Actions include `MOVE_TO_BALL`, `MOVE_TO_GOAL`, `JUMP`, `KICK_LOW`, `KICK_HIGH`, `KICK_CLEAR`, and more.

Full details: [`doc/strategy-system.md`](doc/strategy-system.md) and [`doc/game-engine.md`](doc/game-engine.md).

---

## API reference

All endpoints require an authenticated session and a CSRF token. `POST` bodies are JSON.

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/vocabulary/` | Available sensors, operators, actions, and preset names. |
| `POST` | `/api/validate/` | Validate a custom strategy before it runs. |
| `POST` | `/api/compile-strategy/` | Compile Persian strategy text into a validated strategy (LLM). |
| `POST` | `/api/simulate/` | Run one match and return the result plus recorded frames. |
| `POST` | `/api/batch/` | Run many matches and return aggregate win/goal stats. |

Example simulate request:

```json
{
  "blue": { "preset": "aggressive" },
  "red":  { "preset": "adaptive" },
  "seed": 1
}
```

A strategy side can be either `{"preset": "<name>"}` or `{"strategy": { ...strategy JSON... }}`. Full request/response shapes are in [`doc/api-reference.md`](doc/api-reference.md).

---

## Configuration

Copy `.env.example` to `.env` and set values as needed.

| Variable | Purpose |
| :--- | :--- |
| `ORCAROUTER_API_KEY` | API key for the AI strategy compiler. **Required only for the AI/natural‑language feature** — everything else works without it. Keep it server‑side only. |
| `ORCAROUTER_MODEL` | Model id (default: `deepseek/deepseek-v4-flash-free`). |
| `ORCAROUTER_BASE_URL` | OpenAI‑compatible base URL (default: OrcaRouter). |
| `DJANGO_SECRET_KEY` | Django secret key. Set a real value in production. |
| `DJANGO_DEBUG` | `True` for local development, `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma‑separated hostnames. |

If `ORCAROUTER_API_KEY` is not set, the visual rule builder and all match/batch features still work; only the "compile from Persian text" button reports that the AI is unavailable. See [`doc/ai-compiler.md`](doc/ai-compiler.md).

---

## Tuning the game

Match feel is controlled by one dataclass, `GameConfig`, at the top of [`game/engine.py`](game/engine.py). A few useful knobs:

| Setting | Effect |
| :--- | :--- |
| `player_speed`, `player_jump_speed` | How fast bots run and how high they jump. |
| `player_collision_inset` | How close two players stand before they bump (smaller box = closer). |
| `stall_pop_after`, `stall_kickoff_after` | How long a dead ball waits before it's nudged back into play / re‑kicked off. |
| `match_time`, `record_fps` | Match length and replay frame rate. |

The rendering (stadium, pitch, ball, goals) lives in the `draw*` functions in [`game/static/game/game.js`](game/static/game/game.js); the theme colors are CSS variables at the top of [`game/static/game/styles.css`](game/static/game/styles.css).

---

## Project structure

```text
headballKarsoogh/
├── doc/                          # Detailed guides (architecture, engine, API, auth, …)
├── config/                       # Django project
│   ├── settings.py               # apps, auth, static (WhiteNoise), database
│   └── urls.py                   # /admin/, /login/, /logout/, /accounts/, /
├── game/                         # The game app (self‑contained, portable)
│   ├── engine.py                 # physics + match simulation
│   ├── strategy.py               # vocabulary: sensors, operators, actions, presets
│   ├── validators.py             # strict Strategy‑JSON validation
│   ├── views.py                  # login‑gated views + JSON APIs
│   ├── urls.py                   # game + API routes
│   ├── tests.py                  # engine, API, and auth tests
│   ├── prompts/strategy_compiler.py  # system prompt for the AI compiler
│   ├── services/llm.py           # LLM client (OrcaRouter / OpenAI‑compatible)
│   ├── templates/game/           # index.html, login.html
│   └── static/game/              # game.js (UI + canvas replay), styles.css, fonts/
├── Dockerfile / docker-compose.yml
├── manage.py
├── requirements.txt
└── README.md
```

The `game/` app is intended to be portable — to drop it into an existing Django site, you don't need this project's `config/` folder or `manage.py`.

---

## Running with Docker

```bash
docker compose up --build
```

`docker-compose.yml` reads the same environment variables described above. Run migrations and create an admin user inside the container the first time.

---

## Tests

```bash
python manage.py test
```

The suite covers strategy validation, the engine (matches finish, batch counts add up), the JSON APIs, and authentication.

---

## Documentation

| Topic | Guide |
| :--- | :--- |
| System architecture & data flow | [`doc/architecture.md`](doc/architecture.md) |
| Physics engine & mechanics | [`doc/game-engine.md`](doc/game-engine.md) |
| Strategy format, sensors & actions | [`doc/strategy-system.md`](doc/strategy-system.md) |
| AI (Persian → rules) compiler | [`doc/ai-compiler.md`](doc/ai-compiler.md) |
| REST API reference | [`doc/api-reference.md`](doc/api-reference.md) |
| Authentication & admin | [`doc/auth-and-admin.md`](doc/auth-and-admin.md) |
| Setup & deployment | [`doc/deployment-and-setup.md`](doc/deployment-and-setup.md) |
