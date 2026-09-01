# BOT-NASEB

بوت Telegram واحد لصفحة **لقاء ونصيب**، بواجهة أدمن وواجهة عميل، مع فصل واضح بين البيانات العامة وبيانات التواصل الخاصة.

## الفكرة

البوت مخصص لإدارة عروض الزواج والبحث عنها. الأدمن يضيف الإعلان بلصق النص الخام كما وصله؛ Gemini يفهم النص ويحوّله إلى بيانات منظمة، ثم يراجع الأدمن المعاينة قبل الحفظ.

العميل لا يحتاج حفظ أوامر خاصة. يكتب طلب البحث بطريقته الطبيعية، والبوت يعرض له كيف فهم الطلب قبل تنفيذ البحث. Gemini ينظم الفلاتر فقط، ثم PostgreSQL تنفذ الاستعلام وتعيد النتائج.

## تجربة الأدمن

- ➕ إضافة إعلان بنص خام.
- 🤖 تنظيم الإعلان عبر Gemini.
- 📋 معاينة جاهزة للنسخ والنشر على Facebook قبل الحفظ.
- ✏️ تعديل الإعلان.
- 🔎 بحث طبيعي داخل الإعلانات.
- 🔒 حجز/فك حجز الإعلان.
- ⛔ تعطيل الإعلان.
- 🧹 حذف طلبات محددة أو حذف الكل مع تأكيد.
- 💳 مراجعة طلبات التواصل والمدفوعات اليدوية.
- 📊 إحصائيات.
- 💾 نسخة احتياطية JSON.

## تجربة العميل

- 🔎 بحث عن عرض زواج.
- 🤵 «دورولي على عريس مناسب».
- 👰 «دورولي على عروس مناسبة».
- 📋 تصفح أحدث العروض.
- 💳 عرض طلبات التواصل الخاصة به.
- ℹ️ شرح طريقة العمل.
- 🔄 بحث جديد و⬅️ رجوع للقائمة الرئيسية من المسارات المهمة.

## الذكاء الاصطناعي

المشروع يستخدم Google Gemini عبر طبقة مستقلة داخل `app/services/ai.py`.

عند إضافة إعلان:

```text
النص الخام
  ↓
Gemini Structured Output
  ↓
Validation + Privacy checks
  ↓
معاينة منشور زواج
  ↓
موافقة الأدمن
  ↓
PostgreSQL
```

وعند البحث:

```text
طلب المستخدم الطبيعي
  ↓
Gemini / parser
  ↓
ProfileFilters
  ↓
PostgreSQL
  ↓
النتائج
```

Gemini لا يختار النتائج ولا ينفذ SQL ولا يخترع قيماً غير موجودة بوضوح.

## بيانات الإعلان

البيانات العامة الأساسية:

- gender
- name
- age
- residence
- marital_status
- children_count
- occupation
- education
- height
- weight
- appearance
- partner_requirements
- photo_file_id
- status

مكان السكن محفوظ كحقل واحد `residence`، مثل: `دمشق`، `ريف حمص`، `حلب`، `ريف حماة`، أو صيغة أكثر تحديداً عند الحاجة.

لا توجد حقول مستقلة للجنسية أو الديانة أو «المواصفات الشخصية». إذا كانت الجنسية أو الديانة شرطاً للشريك المطلوب، تُحفظ ضمن `partner_requirements`.

## الخصوصية

رقم الهاتف وTelegram وWhatsApp مخزنة في `profile_contacts` منفصل عن البيانات العامة.

- العميل لا يرى بيانات التواصل مكشوفة.
- يمكن عرض الهاتف للعميل بشكل مقنّع عند عرض الإعلان، مثل `09••••••92`.
- الأدمن يرى بيانات التواصل الخاصة.
- لا يتم تسجيل أرقام التواصل في logs.

## الحالات

- `active` — العرض متاح.
- `reserved` — العرض محجوز ويظهر بهذه الحالة للعميل ولا يمكن إنشاء طلب تواصل جديد عليه.
- `inactive` — العرض معطّل وغير متاح للعملاء.

## الدفع

طلب التواصل الحالي بقيمة **5 USD** عبر **شام كاش**.

الدفع يدوي، وليس هناك ربط بنكي آلي. عند إنشاء طلب تواصل:

1. يُنشأ Order بحالة `pending_payment`.
2. يصل إشعار للأدمن مع Telegram User ID واسم الحساب وUsername إن وجد ورقم الإعلان ورقم طلب الدفع.
3. العميل يرى تعليمات الدفع من إعداد `CHAM_CASH_ACCOUNT` عند توفره.
4. يرسل العميل رقم العملية.
5. تتحول الحالة إلى `pending_review`.
6. الأدمن يؤكد أو يرفض العملية.

## قاعدة البيانات

PostgreSQL هي قاعدة التشغيل الأساسية، وSupabase مستخدمة كبنية PostgreSQL خارجية.

الجداول الأساسية:

- `profiles`
- `profile_contacts`
- `orders`

الصور لا تُخزن كـBinary داخل قاعدة البيانات؛ يتم الاحتفاظ بـTelegram `file_id` فقط عند توفر صورة.

## Environment Variables

راجع `.env.example` ولا تضع أي Secret داخل GitHub.

```env
TELEGRAM_BOT_TOKEN=
ADMIN_USER_IDS=
AI_API_KEY=
AI_MODEL=gemini-3.5-flash-lite
DATABASE_URL=
WEBHOOK_SECRET=
WEBHOOK_PATH=/telegram
CHAM_CASH_ACCOUNT=
```

## Render

المشروع يعمل كـWeb Service واحد على Render Free، ويستخدم Webhook عندما يكون `RENDER_EXTERNAL_URL` أو `PUBLIC_BASE_URL` متاحاً.

`render.yaml` يجهز الخدمة مع:

- Python runtime.
- `python -m app.main`.
- `/health`.
- `gemini-3.5-flash-lite` كافتراضي.
- `DATABASE_URL` كـEnvironment Variable خارجية لـSupabase.

لا توجد Worker أو Redis أو قاعدة PostgreSQL على Render ضمن التصميم الحالي.

## التشغيل المحلي

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest -q
python -m compileall -q app tests
python -m app.main
```

## الاختبارات وCI

GitHub Actions يشغل:

```bash
python -m pytest -q
python -m compileall -q app tests
```

الاختبارات تغطي الصلاحيات، `/start`، التنقل والـcallbacks، parsing والـAI contracts، البحث، الخصوصية، الإعلانات، الحجز، الدفع، وأرقام الطلبات.

## بنية المشروع

```text
app/
├── main.py
├── config.py
├── handlers/
│   ├── start.py
│   ├── admin.py
│   └── client.py
├── services/
│   ├── ai.py
│   ├── gemini_runtime.py
│   ├── profiles.py
│   ├── permissions.py
│   └── search.py
├── database/
│   ├── connection.py
│   ├── models.py
│   └── repositories.py
└── keyboards/
    ├── admin.py
    └── client.py
```
