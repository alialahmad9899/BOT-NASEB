# Admin V2 Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** تحويل لوحة الأدمن إلى مركز إدارة كامل ومريح وآمن مع الحفاظ الكامل على كل الإعلانات والطلبات الحالية.

**Architecture:** نضيف طبقة حالات وبيانات إدارية فوق الجداول الحالية، مع Migration non-destructive تضيف أعمدة/جداول جديدة فقط ولا تحذف أو تعيد إنشاء البيانات. نفصل إدارة الأدمن إلى Dashboard، بحث شامل، إدارة إعلانات، حجوزات، طلبات، تقارير، نسخ احتياطية وسجل عمليات، مع إبقاء Gemini لفهم البحث وتحسين الإدخالات دون اختراع بيانات.

**Tech Stack:** Python 3.13، python-telegram-bot 22.x، SQLAlchemy 2.x، PostgreSQL/psycopg، Pydantic، Gemini.

**Spec:** اقتراحات Admin V2 الشاملة المعتمدة في المحادثة بتاريخ 2026-09-02.

## Global Constraints

- لا حذف لأي سجل قائم ولا إعادة إنشاء قاعدة البيانات.
- لا تغيير لـ `DATABASE_URL`.
- كل تغييرات schema يجب أن تكون additive وbackward-compatible.
- القيم القديمة `active/reserved/inactive` تبقى مفهومة بعد التحديث.
- `transaction_id` يبقى للتوافق الخلفي ولا يعود مطلوباً في رحلة العميل.
- بيانات التواصل تبقى خاصة بالأدمن ولا تظهر في نتائج العميل.
- Gemini لا ينفذ SQL ولا يخترع معلومات.
- كل العمليات المدمرة تحتاج تأكيداً واضحاً، والحذف النهائي يبقى اختياراً متقدماً.
- كل النصوص الموجهة للأدمن والعملاء بالعربية.
- كل ميزة جديدة لها اختبارات regression/unit مناسبة.

---

### Task 1: Safe schema migration and admin audit foundation

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/connection.py`
- Modify: `app/main.py`
- Create: `app/database/migrations.py`
- Create: `tests/test_schema_migration.py`

**Interfaces:**
- `migrate_schema(engine) -> None`
- `AdminAuditLog` model with `id`, `admin_user_id`, `action`, `entity_type`, `entity_number`, `details`, `created_at`
- New optional profile fields: `archive_status`, `publication_status`, `published_at`, `quality_score`, `duplicate_of_request_number`
- New reservation fields: `reserved_at`, `reservation_expires_at`, `reservation_reason`
- New order fields: `payment_status`, `contact_status`, `contacted_at`, `completed_at`
- New `Backups` table storing immutable JSON snapshots and creator metadata.

- [ ] Write tests proving an existing SQLite database with current `profiles`, `profile_contacts`, and `orders` can be opened after migration and existing rows remain intact.
- [ ] Add additive migration SQL for PostgreSQL using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and equivalent SQLite checks.
- [ ] Add `audit_logs` and `backups` tables without touching existing records.
- [ ] Call `migrate_schema(engine)` immediately after `Base.metadata.create_all(engine)`.
- [ ] Run migration tests and compile tests.
- [ ] Commit schema foundation.

---

### Task 2: Admin roles and centralized authorization

**Files:**
- Modify: `app/config.py`
- Modify: `app/services/permissions.py`
- Modify: `app/handlers/admin.py`
- Create: `tests/test_admin_roles.py`
- Modify: `.env.example`
- Modify: `render.yaml`

**Interfaces:**
- `AdminRole` enum: `owner`, `manager`, `viewer`
- `AdminAccess` with `role_for(user_id)` and permission helpers.
- Optional env vars `ADMIN_OWNER_IDS`, `ADMIN_MANAGER_IDS`, `ADMIN_VIEWER_IDS`; legacy `ADMIN_USER_IDS` remains valid and defaults to owner access for backward compatibility.

- [ ] Add tests for legacy admin access, owner, manager, viewer, and denial.
- [ ] Implement role parsing without invalidating `ADMIN_USER_IDS`.
- [ ] Enforce destructive operations and backups to owner/manager; viewer is read-only.
- [ ] Add admin role summary to settings screen.
- [ ] Run role tests.
- [ ] Commit roles.

---

### Task 3: Admin Dashboard and navigation

**Files:**
- Modify: `app/keyboards/admin.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/services/reports.py` (create)
- Modify: `tests/test_keyboards.py`
- Create: `tests/test_admin_dashboard.py`

**Interfaces:**
- `admin_dashboard_keyboard() -> InlineKeyboardMarkup`
- `build_dashboard_snapshot(session) -> dict`
- `render_admin_dashboard(snapshot) -> str`

- [ ] Add dashboard counters for active, reserved, inactive, archived, new today, pending orders, paid orders, completed contacts.
- [ ] Add quick navigation to profiles, search, reservations, orders, archive, reports, backups, settings.
- [ ] Keep old callbacks working as aliases where practical.
- [ ] Add tests for dashboard rendering and keyboard callbacks.
- [ ] Run tests.
- [ ] Commit dashboard.

---

### Task 4: Full profile lifecycle: active/reserved/inactive/archived

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/services/profiles.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_profile_lifecycle.py`

**Interfaces:**
- `archive(request_number, reason=None)`
- `restore_archived(request_number)`
- `reactivate(request_number)`
- `set_publication_status(request_number, status)`
- Preserve old `disable()` and `reserve()/activate()` behavior for compatibility.

- [ ] Add tests showing inactive profiles can be reactivated.
- [ ] Add archive/restore flow that never deletes a profile.
- [ ] Add archive reason and timestamps.
- [ ] Add publication states `review`, `ready`, `published`, `unpublished`.
- [ ] Update profile action buttons by status.
- [ ] Add audit logging to lifecycle changes.
- [ ] Run lifecycle tests.
- [ ] Commit lifecycle.

---

### Task 5: Profile management with pagination and category filters

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_admin_profile_pagination.py`

**Interfaces:**
- `list_profiles_page(page, page_size, status=None, gender=None, archived=False)`
- Pagination callbacks encode page and filter safely.

- [ ] Add 10-item pages for profile management.
- [ ] Add filters: all, women, men, active, reserved, inactive, archived, ready-to-publish, published.
- [ ] Add previous/next navigation.
- [ ] Add direct open by request number.
- [ ] Ensure page navigation never exposes private contact fields.
- [ ] Run pagination tests.
- [ ] Commit.

---

### Task 6: Complete admin search engine

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/services/search.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_admin_search_advanced.py`

**Interfaces:**
- Extend `ProfileFilters` with `height_min`, `height_max`, `weight_min`, `weight_max`, `status`, `archive_status`, `publication_status`, `has_photo`, `has_contact`, `created_after`, `created_before`, `text_query`, `request_number`.
- `parse_admin_search_text(text) -> AdminSearchQuery`

- [ ] Support natural language for all currently available fields.
- [ ] Support direct number lookup.
- [ ] Support exact/partial name lookup.
- [ ] Support phone/WhatsApp/Telegram lookup for admins only.
- [ ] Support searching appearance/partner requirements via text query.
- [ ] Support status and archive filters.
- [ ] Support date phrases for today/week/month.
- [ ] Show an interpreted-search confirmation before executing complex searches.
- [ ] Add pagination to search results.
- [ ] Run search regression tests.
- [ ] Commit advanced search.

---

### Task 7: Button-based profile editor

**Files:**
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Modify: `app/services/profiles.py`
- Create: `tests/test_admin_profile_editor.py`

**Interfaces:**
- Field callback family `admin:editfield:<request>:<field>`.
- `render_edit_field_prompt(profile, field) -> str`
- `apply_single_field_edit(...)`

- [ ] Add field-by-field buttons for name, age, residence, marital status, children, occupation, education, height, weight, appearance, requirements, phone, WhatsApp, Telegram, photo, publication status.
- [ ] Keep multiline `key=value` editing as an advanced fallback.
- [ ] Validate each changed field.
- [ ] Re-display full updated profile after save.
- [ ] Audit every update.
- [ ] Run editor tests.
- [ ] Commit.

---

### Task 8: Duplicate detection during addition

**Files:**
- Create: `app/services/duplicates.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/database/repositories.py`
- Create: `tests/test_duplicate_detection.py`

**Interfaces:**
- `find_profile_duplicates(candidate: ProfileDraft, session, limit=5) -> list[DuplicateMatch]`
- Duplicate signals: normalized phone/WhatsApp, same name+age+residence, close name similarity, overlapping partner metadata.

- [ ] Add tests for exact contact duplicate, strong demographic duplicate, and non-duplicate.
- [ ] Run duplicate detector before save.
- [ ] Show candidate matches with `✅ نفس الشخص / ➕ إعلان جديد` actions.
- [ ] Store `duplicate_of_request_number` only when admin explicitly marks the relationship.
- [ ] Audit duplicate decisions.
- [ ] Commit.

---

### Task 9: Ad quality scoring, missing-data checks, and ready-to-publish state

**Files:**
- Create: `app/services/profile_quality.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/services/profiles.py`
- Create: `tests/test_profile_quality.py`

**Interfaces:**
- `score_profile(draft_or_profile) -> QualityReport`
- `QualityReport.score`, `missing_fields`, `warnings`, `ready`

- [ ] Score core identity, contact, photo, description, partner requirements, and consistency.
- [ ] Mark missing/weak areas without inventing values.
- [ ] Add `🤖 تحسين الإعلان` action that uses Gemini only to rewrite existing facts, never add facts.
- [ ] Add `📋 نص المنشور`, `📷 الصورة`, and publication-status controls.
- [ ] Allow explicit `ready` transition only after required-field validation.
- [ ] Run quality tests.
- [ ] Commit.

---

### Task 10: Reservation management with duration, reason, expiry, and renewal

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `app/services/reservations.py`
- Create: `tests/test_reservations_v2.py`

**Interfaces:**
- `reserve(request_number, reason=None, expires_at=None)`
- `extend_reservation(request_number, days)`
- `release_reservation(request_number)`
- `expire_reservations(now)`

- [ ] Add duration options 7/14/30 days/no expiry.
- [ ] Add reason options and free-form reason.
- [ ] Show expiry countdown/date.
- [ ] Add reservation dashboard with per-item actions.
- [ ] Add automatic expiry during dashboard/read operations, without deleting data.
- [ ] Audit reservation changes.
- [ ] Run reservation tests.
- [ ] Commit.

---

### Task 11: Orders as a full workflow

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Modify: `app/handlers/payment.py`
- Create: `tests/test_order_workflow_v2.py`

**Interfaces:**
- `payment_status`: `pending`, `paid`, `rejected`.
- `contact_status`: `new`, `contacted`, `opened`, `completed`, `cancelled`.
- Existing order `status` remains for backward compatibility and is synchronized from legacy values.

- [ ] Split payment and contact lifecycle from the legacy single status.
- [ ] Add one-click `📱 واتساب`, `📞 تم التواصل`, `💰 تأكيد الدفع`, `🤝 فتح التواصل`, `✅ إغلاق الطلب`.
- [ ] Keep transaction ID legacy-only; customer flow never asks for it.
- [ ] Add order pagination and filters.
- [ ] Add customer WhatsApp in order details for admin only.
- [ ] Notify customer on relevant status changes without exposing internal notes.
- [ ] Audit payment/contact transitions.
- [ ] Run full order workflow tests.
- [ ] Commit.

---

### Task 12: Safe deletion and automatic pre-delete backups

**Files:**
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `app/services/backups.py`
- Create: `tests/test_safe_delete_backup.py`

**Interfaces:**
- `create_backup(session, created_by, reason) -> Backup`
- `restore_backup(session, backup_id, actor_id) -> RestoreReport`
- `archive` is the default for normal removal.

- [ ] Change normal profile removal UI from direct deletion to archive.
- [ ] Keep permanent deletion behind owner/manager permission and explicit phrase confirmation.
- [ ] Automatically create a backup immediately before permanent deletion.
- [ ] Automatically create a backup before bulk deletions.
- [ ] Prevent deletion if backup creation fails.
- [ ] Ensure existing data survives all archive operations.
- [ ] Run destructive-operation tests.
- [ ] Commit.

---

### Task 13: Backup history and restore

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_backup_restore.py`

**Interfaces:**
- Backup list pagination.
- Restore dry-run summary before destructive replacement.

- [ ] Store JSON snapshots including profiles, contacts, orders, audit metadata required for restoration.
- [ ] Add `💾 إنشاء نسخة الآن`.
- [ ] Add `📚 النسخ السابقة`.
- [ ] Add `♻️ استعادة نسخة` with two-step confirmation.
- [ ] Restore transactionally; on failure roll back.
- [ ] Never delete the backup record being restored.
- [ ] Create a pre-restore safety backup.
- [ ] Run restore tests with existing rows.
- [ ] Commit.

---

### Task 14: Audit log and admin activity history

**Files:**
- Create: `app/services/audit.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Modify: `app/database/repositories.py`
- Create: `tests/test_audit_log.py`

**Interfaces:**
- `log_admin_action(session, admin_user_id, action, entity_type=None, entity_number=None, details=None)`
- `list_audit_logs(session, limit, action=None, admin_user_id=None)`

- [ ] Log additions, edits, archiving, deletion, restore, reservations, payment actions, contact workflow, backup, restore, publication actions.
- [ ] Never store raw secrets or bot token/API keys in audit details.
- [ ] Add filter by admin and action.
- [ ] Show timestamp, actor, action, target.
- [ ] Run audit tests.
- [ ] Commit.

---

### Task 15: Reports and analytics dashboard

**Files:**
- Create: `app/services/reports.py`
- Modify: `app/database/repositories.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_reports.py`

**Interfaces:**
- `daily_weekly_monthly_metrics(session) -> dict`
- `top_residences(session, limit=5) -> list`
- `contact_conversion(session) -> dict`

- [ ] Add today/week/month new profiles.
- [ ] Add orders, paid, completed, rejected.
- [ ] Add active/reserved/inactive/archived counts.
- [ ] Add men/women counts.
- [ ] Add top residences.
- [ ] Add contact conversion rate.
- [ ] Add report pagination where applicable.
- [ ] Run reports tests.
- [ ] Commit.

---

### Task 16: Admin settings and operational controls

**Files:**
- Modify: `app/config.py`
- Modify: `app/handlers/admin.py`
- Modify: `app/keyboards/admin.py`
- Create: `tests/test_admin_settings.py`

**Interfaces:**
- Read-only runtime settings view.
- Safe editable settings only when persisted in a dedicated DB settings table; secrets remain environment-only.

- [ ] Show payment amount/method/account status without displaying secrets unnecessarily.
- [ ] Show active admin roles.
- [ ] Show database connectivity status.
- [ ] Show Gemini configured/not configured.
- [ ] Add safe maintenance controls for backup creation and health checks.
- [ ] Run settings tests.
- [ ] Commit.

---

### Task 17: Client-facing publication and privacy regression checks

**Files:**
- Modify: `app/services/profiles.py`
- Modify: `app/handlers/client.py`
- Create/Modify: `tests/test_client_privacy_admin_v2.py`

- [ ] Ensure archived/inactive/unpublished profiles are excluded from public/client search.
- [ ] Ensure admin-only phone/WhatsApp/Telegram fields remain hidden from clients.
- [ ] Ensure ready-to-publish text contains only public fields.
- [ ] Ensure reserved profiles remain visible as reserved but cannot receive new contact requests.
- [ ] Run privacy regression tests.
- [ ] Commit.

---

### Task 18: Documentation, full regression, CI, and production safety review

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `render.yaml`
- Create/Modify: `tests/test_admin_v2_integration.py`

- [ ] Document all admin V2 operations and new optional environment variables.
- [ ] Verify Render settings remain backward-compatible; no existing environment variable is renamed or removed.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q app tests`.
- [ ] Review schema migration for zero destructive SQL.
- [ ] Review all destructive callbacks for permissions and confirmations.
- [ ] Create PR from `admin-v2-complete` to `main`.
- [ ] Require CI success.
- [ ] Merge only after all checks pass.
- [ ] Verify merged `main` commit and CI status.
