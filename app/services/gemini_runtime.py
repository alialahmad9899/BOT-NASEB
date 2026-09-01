"""Gemini runtime adapter with safe diagnostics for structured extraction."""

from __future__ import annotations

import logging

from app.services.ai import AIService, PROFILE_SCHEMA_INSTRUCTIONS, ProfileExtraction

logger = logging.getLogger("bot-naseb.gemini")


class GeminiAIService(AIService):
    """Use Gemini structured output while disabling unrelated AFC behavior."""

    def extract_profile_sync(self, raw_text: str) -> ProfileExtraction:
        client = self._get_client()
        from google.genai import types

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=f"{PROFILE_SCHEMA_INSTRUCTIONS}\n\nالنص الخام:\n{raw_text}",
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=ProfileExtraction,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty text response")
            return ProfileExtraction.model_validate_json(response.text)
        except Exception as exc:
            logger.exception(
                "Gemini profile extraction failed: %s: %s",
                type(exc).__name__,
                str(exc),
            )
            raise
