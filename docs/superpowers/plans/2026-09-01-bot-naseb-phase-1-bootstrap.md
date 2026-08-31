# BOT-NASEB Phase 1 Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** إنشاء Bootstrap فعلي ومستقر لبوت BOT-NASEB مع `/start` وفصل Admin/Client وتجهيز طبقات AI وPostgreSQL وRender.

**Architecture:** Handlers رفيعة، صلاحيات مركزية، إعدادات typed، Keyboard builders منفصلة، Webhook HTTP layer مستقلة عن Telegram handlers، وطبقات AI/Database غير متداخلة مع واجهة البوت.

**Tech Stack:** Python 3.13+, python-telegram-bot 22.8، Starlette، Uvicorn، SQLAlchemy 2.0.x، psycopg 3.x، python-dotenv، pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-bot-naseb-phase-1-bootstrap.md`

## Global Constraints

- Telegram bot واحد فقط.
- الصلاحيات تعتمد حصراً على Telegram User ID.
- كل رسائل البوت للمستخدمين بالعربية العامية السورية الواضحة.
- لا توجد Secrets في GitHub.
- لا AI parsing فعلي في Phase 1.
- لا CRUD أو بحث إعلانات في Phase 1.
- لا نظام دفع في Phase 1.
- لا تخزين صور Binary في قاعدة البيانات.
- لا خدمة Worker إضافية.
- لا Redis إلا عند الحاجة المستقبلية.
- المشروع يستهدف Render Free.

---

### Task 1: Authorization and `/start` behavior

**Files:**
- Create: `app/services/permissions.py`
- Create: `app/handlers/start.py`
- Test: `tests/test_permissions.py`
- Test: `tests/test_start.py`

**Interfaces:**
- `parse_admin_user_ids(raw: str) -> set[int]`
- `is_admin(user_id: int, admin_user_ids: set[int]) -> bool`
- `start_content_for_user(user_id: int, admin_user_ids: set[int]) -> StartContent`

- [x] **Step 1: Write the failing tests**

```python
def test_admin_id_is_recognized_from_configured_ids():
    assert is_admin(123, {123, 456}) is True

def test_non_admin_id_is_denied():
    assert is_admin(999, {123, 456}) is False

def test_start_returns_admin_menu_for_admin_user():
    result = start_content_for_user(123, {123})
    assert result.role == "admin"
    assert "لوحة الأدمن" in result.text
```

- [x] **Step 2: Run the tests and verify they fail because the implementation is absent**

Run: `pytest -q tests/test_permissions.py tests/test_start.py`

Expected: collection failure because `app.services.permissions` and `app.handlers.start` do not exist yet.

- [x] **Step 3: Implement minimal permission and start-routing logic**

```python
@dataclass(frozen=True)
class StartContent:
    role: Literal["admin", "client"]
    text: str


def parse_admin_user_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for value in raw.split(","):
        value = value.strip()
        if value and value.lstrip("-").isdigit():
            ids.add(int(value))
    return ids


def is_admin(user_id: int, admin_user_ids: set[int]) -> bool:
    return user_id in admin_user_ids
```

- [x] **Step 4: Run the tests and verify they pass**

Run: `pytest -q tests/test_permissions.py tests/test_start.py`

Expected: all tests PASS.

---

### Task 2: Configuration and environment safety

**Files:**
- Create: `app/config.py`
- Create: `.env.example`
- Create: `.gitignore`
- Test: `tests/test_config.py`

**Interfaces:**
- `Settings.from_env()` reads environment variables and never stores secrets in source code.

- [x] **Step 1: Write the failing tests**

```python
def test_settings_requires_token_and_at_least_one_admin(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("ADMIN_USER_IDS", "123")
    settings = Settings.from_env()
    assert settings.telegram_bot_token == "token"
    assert settings.admin_user_ids == frozenset({123})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `pytest -q tests/test_config.py`

Expected: import failure because `app.config` is missing.

- [x] **Step 3: Implement `Settings` with required and optional variables**

Required: `TELEGRAM_BOT_TOKEN`, `ADMIN_USER_IDS`.

Optional: `AI_API_KEY`, `DATABASE_URL`, `PUBLIC_BASE_URL`, `WEBHOOK_SECRET`, `WEBHOOK_PATH`, `PORT`.

- [x] **Step 4: Add secret-safe examples and ignore rules**

`.env.example` contains variable names only. `.gitignore` includes `.env`, virtualenvs, bytecode, pytest cache, and local database files.

- [x] **Step 5: Run all current tests**

Run: `pytest -q`

Expected: all tests PASS.

---

### Task 3: Telegram UI handlers and permission enforcement

**Files:**
- Create: `app/handlers/admin.py`
- Create: `app/handlers/client.py`
- Create: `app/keyboards/admin.py`
- Create: `app/keyboards/client.py`
- Modify: `app/handlers/start.py`
- Test: `tests/test_admin_guard.py`

**Interfaces:**
- Admin callbacks check `is_admin()` from the handler itself.
- Client callbacks never receive private contact data and only acknowledge placeholder actions in Phase 1.

- [x] **Step 1: Write the failing admin-guard test**

```python
def test_admin_callback_policy_denies_non_admins():
    assert admin_action_allowed(999, {123}) is False
    assert admin_action_allowed(123, {123}) is True
```

- [x] **Step 2: Run focused test and verify failure**

Run: `pytest -q tests/test_admin_guard.py`

Expected: import failure because `app.handlers.admin` is missing.

- [x] **Step 3: Implement guard plus keyboard builders**

Use callback prefixes `admin:` and `client:`. Every admin callback checks the user ID before doing any action.

- [x] **Step 4: Run all unit tests**

Run: `pytest -q`

Expected: all tests PASS.

---

### Task 4: AI and database scaffolds

**Files:**
- Create: `app/services/ai.py`
- Create: `app/services/profiles.py`
- Create: `app/database/connection.py`
- Create: `app/database/models.py`
- Create: package `__init__.py` files

**Interfaces:**
- `AIService.is_configured -> bool`
- `AIService.extract_profile(...)` is explicitly unavailable until Phase 3 and makes no external API call.
- `build_engine(database_url)` returns a SQLAlchemy Engine or `None` when no URL is configured.
- `ProfileDraft` separates `public_data` and `private_contact_data`.

- [x] **Step 1: Implement only the interfaces needed by Phase 1**
- [x] **Step 2: Compile every Python file**

Run: `python -m compileall -q app tests`

Expected: exit code 0.

---

### Task 5: Application runtime and Render

**Files:**
- Create: `app/main.py`
- Create: `render.yaml`
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `README.md`

**Interfaces:**
- `build_application(settings)` constructs one Telegram application and registers handlers.
- `/health` returns HTTP 200.
- On Render, `RENDER_EXTERNAL_URL` can provide the webhook base automatically.
- Locally, when no public webhook base is configured, the app falls back to polling.

- [x] **Step 1: Implement the application factory**
- [x] **Step 2: Implement the Starlette webhook/health app**
- [x] **Step 3: Add Render Free service configuration**
- [x] **Step 4: Document environment variables and Phase 1 scope**
- [x] **Step 5: Run unit tests and compileall**

Run: `pytest -q && python -m compileall -q app tests`

Expected: all tests PASS and compilation succeeds.

---

### Task 6: Final verification and phase commit

**Files:**
- All files created/modified above.
- Preserve existing repository history and do not force push.

- [x] **Step 1: Verify no secrets are present**

Run:

```bash
grep -RInE '([0-9]{7,}:AA|sk-[A-Za-z0-9_-]{20,}|TELEGRAM_BOT_TOKEN\s*=\s*[^[:space:]]+|AI_API_KEY\s*=\s*[^[:space:]]+)' . --exclude-dir=.git --exclude='.env.example' || true
```

Expected: no real credential values.

- [x] **Step 2: Run final tests**

Run: `pytest -q && python -m compileall -q app tests`

Expected: all tests PASS.

- [x] **Step 3: Create one phase commit**

```text
feat: bootstrap telegram bot
```

- [x] **Step 4: Push fast-forward to `main` only**

Use the GitHub API to create the commit from the current `main` parent and advance `main` with `force=false`.
