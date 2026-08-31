# BOT-NASEB

بوت Telegram واحد لصفحة **لقاء ونصيب**، مبني على فصل واضح بين واجهة الأدمن وواجهة العميل.

## Phase 1

المرحلة الحالية هي Bootstrap فقط، وتشمل:

- `/start` يوجّه المستخدم حسب Telegram User ID.
- لوحة أدمن بسيطة محمية بفحص صلاحية مركزي.
- واجهة عميل بسيطة.
- طبقة AI مستقلة بدون استدعاءات أو Parser فعلي.
- طبقة PostgreSQL/SQLAlchemy جاهزة للمرحلة التالية بدون schema نهائي.
- فصل أولي بين `public_data` و`private_contact_data`.
- Webhook مناسب لـ Render مع endpoint `/health`.
- fallback إلى polling عند التشغيل المحلي بدون `PUBLIC_BASE_URL`.

## الصلاحيات

الصلاحية الإدارية تعتمد حصراً على `ADMIN_USER_IDS`. لا يتم الاعتماد على الاسم أو Username.

## المتغيرات

انسخ `.env.example` إلى `.env` محلياً وأضف القيم الحقيقية خارج Git.

- `TELEGRAM_BOT_TOKEN` — مطلوب.
- `ADMIN_USER_IDS` — مطلوب، عدة IDs مفصولة بفواصل.
- `AI_API_KEY` — اختياري حالياً، وسيستخدم في مرحلة Parser.
- `DATABASE_URL` — اختياري حالياً، وسيستخدم عند إضافة قاعدة البيانات.
- `PUBLIC_BASE_URL` — اختياري محلياً؛ على Render يمكن الاعتماد على `RENDER_EXTERNAL_URL` تلقائياً.
- `WEBHOOK_SECRET` — يفضل ضبطه في بيئة الإنتاج.
- `WEBHOOK_PATH` — الافتراضي `/telegram`.
- `PORT` — الافتراضي `10000` على Render.

## التشغيل محلياً

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -m app.main
```

عند عدم وجود `PUBLIC_BASE_URL` أو `RENDER_EXTERNAL_URL`، يعمل التشغيل المحلي عبر polling.

## Render

`render.yaml` يجهز Web Service على الخطة المجانية، ويضيف `WEBHOOK_SECRET` مولداً من Render بدون كتابته في المستودع. Render يوفّر `RENDER_EXTERNAL_URL` تلقائياً للخدمة، ويستطيع التطبيق استخدامه لبناء Webhook URL.

> ملاحظة: قاعدة بيانات Render PostgreSQL ليست جزءاً من Blueprint في هذه المرحلة. يتم تجهيز `DATABASE_URL` فقط، وسيتم ربط قاعدة البيانات فعلياً مع مرحلة قاعدة البيانات.

## الاختبارات

```bash
pytest -q
python -m compileall -q app tests
```

## خارج نطاق Phase 1

لا يوجد حالياً: إدخال/تحليل إعلانات، AI parser، CRUD، بحث أو فلاتر، كشف معلومات التواصل، دفع، أو إحصائيات.
