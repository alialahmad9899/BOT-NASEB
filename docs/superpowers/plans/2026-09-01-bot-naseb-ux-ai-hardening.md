# BOT-NASEB UX + AI Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** توحيد تجربة الأدمن والعميل، التحقق من كل مسارات الأزرار والـcallbacks، وتقوية فهم Gemini للنص السوري مع إبقاء PostgreSQL مصدر النتائج النهائي.

**Architecture:** تبقى طبقات Telegram handlers وkeyboards وservices وdatabase منفصلة. يمر الإدخال النصي عبر Gemini عند الحاجة إلى فهم دلالي، ثم يخضع الناتج للتحقق قبل أن تستخدمه repository/SQL؛ الواجهة تعرض حالات واضحة وتوفر رجوعاً دائماً.

**Tech Stack:** Python 3.13, python-telegram-bot 22.x, SQLAlchemy 2.x, psycopg, Pydantic, Google GenAI SDK, PostgreSQL/Supabase, Starlette/Uvicorn, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-01-bot-naseb-ux-ai-hardening.md`

## Global Constraints
- كل رسائل Telegram للمستخدمين بالعربية العامية السورية الواضحة.
- لا Secrets داخل GitHub.
- الاعتماد على Telegram User ID للأدمن فقط.
- Gemini لا يختار النتائج ولا ينفذ SQL.
- PostgreSQL هي مصدر النتائج النهائي.
- بيانات التواصل الخاصة لا تظهر للعميل.
- لا حذف نهائي بدون تأكيد.
- لا تغيير على `main` قبل نجاح الفحوصات.

---

### Task 1: Audit callbacks, states, and keyboard reachability

**Files:**
- Modify: `app/keyboards/admin.py`
- Modify: `app/keyboards/client.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/handlers/client.py`
- Modify: `app/main.py`
- Test: `tests/test_keyboards.py`
- Test: `tests/test_callback_reachability.py`

**Interfaces:**
- Consumes existing callback prefixes `admin:*` and `client:*`.
- Produces a testable mapping of every visible callback to a registered handler and conversation state.

- [ ] Step 1: Write failing tests that enumerate every callback emitted by admin/client keyboards and assert a corresponding handler branch exists.
- [ ] Step 2: Run `pytest tests/test_callback_reachability.py tests/test_keyboards.py -q` and capture the failing callbacks.
- [ ] Step 3: Fix missing or unreachable callback handlers; remove any visible button whose feature is not implemented.
- [ ] Step 4: Ensure callbacks that require conversation state are registered in the correct `ConversationHandler.states` and that `admin:menu`/`client:menu` always clears the active flow.
- [ ] Step 5: Run the focused tests again and then `pytest -q`.
- [ ] Step 6: Commit `fix: audit telegram callback reachability`.

---

### Task 2: Build consistent navigation and onboarding UX

**Files:**
- Modify: `app/keyboards/admin.py`
- Modify: `app/keyboards/client.py`
- Modify: `app/handlers/start.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/handlers/client.py`
- Test: `tests/test_navigation_ux.py`

**Interfaces:**
- `start_command()` remains the clean reset entrypoint.
- New navigation helpers return `InlineKeyboardMarkup` and use only registered callbacks.

- [ ] Step 1: Write failing tests for main-menu/back buttons on add, search, edit, delete, reservation, payment, result, and profile screens.
- [ ] Step 2: Run `pytest tests/test_navigation_ux.py -q` and verify failures identify missing navigation.
- [ ] Step 3: Implement a consistent button hierarchy: `⬅️ رجوع` where a previous logical screen exists and `🏠 الرئيسية` for top-level exits; preserve a main-menu fallback on every long-running flow.
- [ ] Step 4: Update onboarding text so a new client is told they can write naturally without command syntax; update admin onboarding to explain the raw-text flow in one message.
- [ ] Step 5: Run focused tests and `pytest -q`.
- [ ] Step 6: Commit `feat: improve bot navigation and onboarding`.

---

### Task 3: Harden Gemini profile extraction and publishable preview

**Files:**
- Modify: `app/services/ai.py`
- Modify: `app/services/gemini_runtime.py`
- Modify: `app/services/profiles.py`
- Modify: `app/handlers/admin.py`
- Test: `tests/test_profile_ai_contract.py`
- Test: `tests/test_profile_formatting.py`

**Interfaces:**
- `AIService.extract_profile(raw_text: str) -> ProfileExtraction` remains the AI contract.
- `format_draft_preview(draft, request_number)` remains the preview entrypoint.

- [ ] Step 1: Add failing tests for raw Syrian sentences covering name, age, residence phrases (`من`, `ساكن/ساكنة`, `مقيم/مقيمة`, `عايش/عايشة`), marital status, child count, education, work/study, height, weight, appearance, and partner requirements.
- [ ] Step 2: Run the focused AI/profile tests and verify the missing extraction cases.
- [ ] Step 3: Expand the Gemini instructions so it extracts semantic meaning rather than requiring exact keywords, keeps `residence` as one field, and places partner nationality/religion inside `partner_requirements` instead of top-level fields.
- [ ] Step 4: Normalize extracted data with explicit anti-hallucination rules and deterministic private-contact reconciliation from the raw text.
- [ ] Step 5: Ensure the preview contains a complete publishable marriage post while private contact details are appended in a clearly separated admin-only section.
- [ ] Step 6: Run focused tests plus `pytest -q`.
- [ ] Step 7: Commit `feat: harden gemini profile extraction and preview`.

---

### Task 4: Harden natural-language search and clarification flow

**Files:**
- Modify: `app/services/search.py`
- Modify: `app/services/ai.py`
- Modify: `app/handlers/client.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/client.py`
- Test: `tests/test_search.py`
- Test: `tests/test_search_clarification.py`

**Interfaces:**
- `AIService.parse_search_filters(raw_text) -> SearchFilterExtraction` remains the AI parser.
- `filters_from_ai(extraction, raw_text) -> ProfileFilters` remains the DB-safe adapter.
- `ProfileRepository.search(filters)` remains the only result source.

- [ ] Step 1: Add failing tests for natural requests such as `بنت من الشام عمرها 25`, `بدي عريس ساكن بريف حماة بين 28 و35`, `مطلقه بدون ولاد`, and mixed natural wording with irrelevant text.
- [ ] Step 2: Run focused search tests and identify gaps in semantic validation.
- [ ] Step 3: Expand search prompt with Syrian morphology and contextual phrases while forbidding invented filters.
- [ ] Step 4: Add clarification behavior when the AI output has no reliable searchable filter or has an ambiguity that materially changes the result set: show interpreted filters and offer `✅ ابحث` / `✏️ عدّل` / `⬅️ رجوع`.
- [ ] Step 5: Ensure target-gender selection from `عريس/عروس` is merged with AI filters without permitting AI to overwrite the selected gender.
- [ ] Step 6: Run focused tests plus `pytest -q`.
- [ ] Step 7: Commit `feat: improve natural language search handling`.

---

### Task 5: Make profile cards and reserved states clearer

**Files:**
- Modify: `app/services/profiles.py`
- Modify: `app/handlers/client.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/client.py`
- Modify: `app/keyboards/admin.py`
- Test: `tests/test_booking_flow.py`
- Test: `tests/test_privacy.py`

**Interfaces:**
- `format_client_profile`, `format_admin_profile`, and booking repository methods remain the public service layer.

- [ ] Step 1: Add failing tests that active profiles have a contact CTA, reserved profiles show a clear reserved message, and clients cannot create a contact order for reserved profiles.
- [ ] Step 2: Run focused booking/privacy tests and verify the failure cases.
- [ ] Step 3: Make reserved status prominent in client cards and details; add clear admin actions for reserve/unreserve.
- [ ] Step 4: Ensure phone masking is presentation-only and no private fields enter public serializers or logs.
- [ ] Step 5: Run focused tests plus `pytest -q`.
- [ ] Step 6: Commit `fix: clarify reserved profile and privacy UX`.

---

### Task 6: Improve payment request UX and admin notification

**Files:**
- Modify: `app/handlers/client.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/client.py`
- Modify: `app/keyboards/admin.py`
- Modify: `app/services/profiles.py` if presentation helper changes are needed
- Test: `tests/test_payment_flow.py`

**Interfaces:**
- `OrderRepository.create_contact_request`, `set_transaction_id`, `confirm_payment`, `reject_payment` remain the order lifecycle API.
- Admin notification includes Telegram User ID, username when present, display name, profile request number, payment order number, and status.

- [ ] Step 1: Add failing tests for pending payment, transaction submission, admin notification content, confirmation, rejection, and main-menu return.
- [ ] Step 2: Run focused payment tests and verify failures.
- [ ] Step 3: Ensure the client sees the Sham Cash payment instructions from `CHAM_CASH_ACCOUNT` when configured, and receives clear next-step messaging.
- [ ] Step 4: Ensure admins get a concise notification with the customer's Telegram identifier and action buttons for review.
- [ ] Step 5: Ensure payment status transitions are idempotent and cannot be confirmed without a transaction ID.
- [ ] Step 6: Run focused tests plus `pytest -q`.
- [ ] Step 7: Commit `fix: improve payment request workflow`.

---

### Task 7: Clean documentation, CI, and deployment consistency

**Files:**
- Modify: `README.md`
- Modify: `render.yaml`
- Modify: `.env.example`
- Modify: `.github/workflows/tests.yml`
- Test: `tests/test_config.py`
- Test: `tests/test_render_config.py`

**Interfaces:**
- `Settings.from_env()` remains the configuration API.
- CI runs `pytest -q` and `python -m compileall -q app tests`.

- [ ] Step 1: Add failing tests for the current Render config, Gemini model default, required environment variables, and absence of stale province/city documentation.
- [ ] Step 2: Run focused config/deployment tests and verify failures.
- [ ] Step 3: Update README to describe the actual current architecture: Supabase/PostgreSQL, `residence`, Gemini 3.5 Flash Lite, privacy split, payment flow, booking state, and navigation.
- [ ] Step 4: Update `.env.example` and Render defaults to match the current deployment.
- [ ] Step 5: Make CI run the complete test suite and compileall on every push/PR.
- [ ] Step 6: Run all tests locally where possible; document any environment-only limitation rather than claiming success.
- [ ] Step 7: Commit `docs: align project docs and CI with current architecture`.

---

### Task 8: Integration verification and merge

**Files:**
- No new source files.
- Test: entire `tests/` suite plus CI checks.

**Interfaces:**
- The feature branch must contain all tasks above and preserve the original `main` commit ancestry.

- [ ] Step 1: Run `pytest -q` and `python -m compileall -q app tests`.
- [ ] Step 2: Inspect GitHub Actions for the exact feature-branch commit; do not treat queued/running checks as passing.
- [ ] Step 3: Verify no secrets, phone numbers, or private contact values appear in tracked files or test fixtures.
- [ ] Step 4: Verify every keyboard callback has a reachable handler branch and every conversation state is registered.
- [ ] Step 5: Verify Render configuration contains a single `DATABASE_URL` environment key and uses `gemini-3.5-flash-lite`.
- [ ] Step 6: If all checks pass, merge the feature branch into `main` with a normal merge commit or fast-forward; do not force-push.
- [ ] Step 7: Verify `main` points to the merged commit and report exact SHA and verification evidence.
