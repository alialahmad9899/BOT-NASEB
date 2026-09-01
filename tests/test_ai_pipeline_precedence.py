import asyncio

import pytest

from app.services.ai import AIExtractionError, AIService, ProfileExtraction, basic_profile_extraction


class FakeAI(AIService):
    def __init__(self, result=None, error=None):
        super().__init__(api_key="configured")
        self.result = result
        self.error = error
        self.called = False

    async def extract_profile(self, raw_text: str):
        self.called = True
        if self.error:
            raise self.error
        return self.result


def test_configured_ai_is_called_before_local_fallback():
    async def run():
        expected = ProfileExtraction(gender="female", name="آية", age=25, residence="دمشق")
        ai = FakeAI(result=expected)
        deterministic = basic_profile_extraction("آية\nعمري 25\nدمشق\n09xxxxxxxx")

        result = await AIService.resolve_profile_extraction(ai, "raw", deterministic)

        assert ai.called is True
        assert result.name == "آية"
        assert result.age == 25
        assert result.residence == "دمشق"

    asyncio.run(run())


def test_configured_ai_failure_is_not_silently_replaced_by_fallback():
    async def run():
        ai = FakeAI(error=RuntimeError("provider failed"))
        deterministic = basic_profile_extraction("آية\nعمري 25\nدمشق\n09xxxxxxxx")

        with pytest.raises(AIExtractionError):
            await AIService.resolve_profile_extraction(ai, "raw", deterministic)

    asyncio.run(run())


def test_local_fallback_understands_common_syrian_age_phrase():
    parsed = basic_profile_extraction("اسمي آية\nعمري 25 من دمشق\nبدي شب محترم وطويل\n09xxxxxxxx")
    assert parsed.name == "آية"
    assert parsed.age == 25
    assert parsed.residence == "دمشق"
    assert parsed.phone == "09xxxxxxxx"
