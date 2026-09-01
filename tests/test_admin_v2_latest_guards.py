from app.keyboards.admin import admin_main_keyboard, admin_orders_keyboard


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_admin_dashboard_exposes_core_v2_sections():
    labels = _labels(admin_main_keyboard())
    assert "➕ إضافة إعلان" in labels
    assert "🔎 البحث الذكي" in labels
    assert "📋 إدارة الإعلانات" in labels
    assert "💳 طلبات التواصل" in labels
    assert "🔒 الحجوزات" in labels
    assert "🗃️ الأرشيف" in labels
    assert "⚠️ بحاجة لاستكمال" in labels
    assert "📊 التقارير" in labels
    assert "🧾 سجل العمليات" in labels
    assert "💾 النسخ الاحتياطية" in labels
    assert "⚙️ الإعدادات" in labels
    assert "🛑 منطقة الخطر" in labels


def test_legacy_order_callbacks_remain_clickable_for_old_messages():
    callbacks = _callbacks(admin_orders_keyboard([5001]))
    assert "admin:order:view:5001" in callbacks
    assert "admin:order:confirm:5001" in callbacks
    assert "admin:order:reject:5001" in callbacks
    assert "admin:order:delete:5001" in callbacks
    assert "admin:orders:delete:pending" in callbacks
