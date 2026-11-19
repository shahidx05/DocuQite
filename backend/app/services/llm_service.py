"""
services/llm_service.py — LLM generation interface, Gemini implementation, and Mock provider.

Interface:
    generate(system_prompt: str, user_prompt: str) -> dict
        returns:
            {
                "text": str,
                "input_tokens": int,
                "output_tokens": int,
                "latency_ms": int,
                "provider": str,
                "mock": bool,
            }

Providers:
    - "mock": Deterministic local generator that extracts sentences from context block [1].
              Requires no API key, makes zero network calls, runs instantly.
    - "gemini": Google Gen AI SDK client. Fails fast without retry loops on 429.
"""

import logging
import re
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM generation errors."""
    pass


class LLMKeyMissingError(LLMError):
    """Raised when the LLM API key is not configured."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limits (HTTP 429) are encountered."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM request exceeds the configured timeout."""
    pass


class MockLLM:
    """
    Deterministic mock provider for offline testing and quota-free evaluation.
    Builds answers strictly from context block [1] in the user prompt.
    """

    def generate(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        t0 = time.perf_counter()

        # Extract text from Context Block [1]
        pattern = r"--- Context Block \[1\].*?---\n([\s\S]*?)(?:--- Context Block|\n*</context>|$)"
        match = re.search(pattern, user_prompt)

        if match:
            block_text = match.group(1).strip()
            # Split into sentences
            raw_sentences = re.split(r"(?<=[.!?])\s+", block_text)
            sentences = [s.strip() for s in raw_sentences if s.strip()]
            if sentences:
                selected = sentences[:2]
                text = " ".join(selected)
                if not text.endswith((".", "!", "?")):
                    text += "."
                text += " [1]"
            else:
                text = f"{block_text[:120].strip()} [1]"
        else:
            from app.rag.prompts import ABSTENTION_MESSAGE
            text = ABSTENTION_MESSAGE

        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
        input_tokens = len(user_prompt.split())
        output_tokens = len(text.split())

        logger.info("MockLLM generated answer (tokens in=%d, out=%d, ms=%d)", input_tokens, output_tokens, latency_ms)

        return {
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "provider": "mock",
            "mock": True,
        }


class GeminiLLM:
    """
    Production Gemini provider using official google-genai SDK.
    Fails fast without retry loops on 429 rate limit errors.
    """

    def generate(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            raise LLMKeyMissingError(
                "GEMINI_API_KEY is not configured. Set it in .env or switch LLM_PROVIDER=mock."
            )

        from google import genai
        from google.genai import errors, types

        # Disable automatic retry loops on client so 429 fails fast once
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=settings.LLM_TIMEOUT_SECONDS * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

        model_name = settings.GEMINI_MODEL
        if model_name in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash", ""):
            model_name = "gemini-3.8-flash"
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]

        t0 = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                ),
            )
        except errors.APIError as exc:
            if getattr(exc, "code", None) == 429 or "rate" in str(getattr(exc, "message", "")).lower():
                logger.warning("Gemini rate limit exceeded (429).")
                raise LLMRateLimitError(
                    "Rate limit hit, switch LLM_PROVIDER=mock or wait."
                ) from exc
            logger.error(
                "Gemini API error (code %s): %s",
                getattr(exc, "code", "unknown"),
                getattr(exc, "message", str(exc)),
            )
            raise LLMError(f"Gemini API error: {getattr(exc, 'message', str(exc))}") from exc
        except TimeoutError as exc:
            logger.warning("Gemini API request timed out after %ds", settings.LLM_TIMEOUT_SECONDS)
            raise LLMTimeoutError(
                f"Gemini API request timed out after {settings.LLM_TIMEOUT_SECONDS}s."
            ) from exc
        except Exception as exc:
            exc_str = str(exc)
            if "timed out" in exc_str.lower() or "timeout" in exc_str.lower():
                logger.warning("Gemini API request timed out.")
                raise LLMTimeoutError(
                    f"Gemini API request timed out after {settings.LLM_TIMEOUT_SECONDS}s."
                ) from exc
            logger.error("Unexpected error during Gemini generation: %s", exc)
            raise LLMError(f"LLM generation failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)

        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        text = response.text or ""
        logger.info(
            "Gemini generation completed in %d ms (in_tokens=%d, out_tokens=%d)",
            latency_ms,
            input_tokens,
            output_tokens,
        )

        return {
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "provider": "gemini",
            "mock": False,
        }


def get_llm():
    """Factory returning the configured LLM provider instance."""
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "mock":
        return MockLLM()
    elif provider == "gemini":
        return GeminiLLM()
    else:
        raise LLMError(f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Must be 'gemini' or 'mock'.")


def generate(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Dispatch generation to the configured LLM provider."""
    llm = get_llm()
    return llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
