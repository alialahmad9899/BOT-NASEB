# BOT-NASEB Phase 1 Bootstrap Design

## Goal
إنشاء أساس نظيف وقابل للتوسع لبوت Telegram واحد باسم BOT-NASEB مع فصل Admin/Client على مستوى الصلاحيات والواجهة، دون تنفيذ نظام الإعلانات أو البحث أو Parser الذكاء الاصطناعي في هذه المرحلة.

## Architecture
- Telegram layer: `python-telegram-bot` مع handlers منفصلة عن الخدمات.
- Authorization: خدمة مركزية تعتمد حصراً على Telegram User ID الموجود في `ADMIN_USER_IDS`.
- Runtime: Webhook على Render عبر Starlette/Uvicorn مع fallback إلى polling محلياً عندما لا يتوفر عنوان Webhook عام.
- Future AI: طبقة `services/ai.py` مستقلة، بلا أي اتصال API فعلي في Phase 1.
- Future DB: طبقة SQLAlchemy/PostgreSQL مستقلة، مع Base/session factory فقط، بلا schema نهائي للإعلانات.
- Public/private separation: نموذج أولي واضح في `ProfileDraft` يميز البيانات العامة عن بيانات التواصل الخاصة.

## Security
- لا يتم وضع أي Secret في Git.
- Telegram token وAI key وadmin IDs وdatabase URL كلها Environment Variables.
- فحص الصلاحية يتم داخل كل handler إداري، وليس عبر إخفاء أزرار الواجهة فقط.
- لا يتم تسجيل محتوى رسائل المستخدم أو بيانات التواصل الحساسة في logs.

## Phase 1 Scope
1. Project structure.
2. Configuration and environment loading.
3. `/start` routing to Admin or Client UI.
4. Basic admin/client keyboards.
5. Direct protection for admin callbacks.
6. AI service scaffold.
7. PostgreSQL/SQLAlchemy connection scaffold.
8. Render Blueprint and health endpoint.
9. `.env.example`, `.gitignore`, README.
10. Unit tests for permissions and `/start` routing.

## Explicitly Out of Scope
- Final profile schema.
- AI parsing.
- Database CRUD.
- Search and filters.
- Contact disclosure workflow.
- Payments.
- Backup/statistics.
