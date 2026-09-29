"""LLM access: local Ollama first, Google Gemini free tier as fallback."""
from __future__ import annotations

import requests
from loguru import logger

from config import get_settings
from security.url_guard import validate_llm_endpoint

OLLAMA_TIMEOUT = (5, 180)  # connect, read (local models can be slow on first load)
MAX_PROMPT_CHARS = 24_000


class LLMUnavailable(RuntimeError):
    """No LLM backend could produce a response; the message says how to fix it."""


def _call_ollama(prompt: str, settings) -> str:
    base = validate_llm_endpoint(settings.ollama_base_url)
    resp = requests.post(
        f"{base}/api/generate",
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.4}},
        timeout=OLLAMA_TIMEOUT,
    )
    if resp.status_code == 404:
        raise LLMUnavailable(
            f"Ollama is running but model '{settings.ollama_model}' is not available. "
            f"Run: ollama pull {settings.ollama_model}")
    resp.raise_for_status()
    text = str((resp.json() or {}).get("response") or "").strip()
    if not text:
        raise LLMUnavailable("Ollama returned an empty response.")
    return text


def _call_gemini(prompt: str, settings) -> str:
    try:
        from google import genai  # lazy optional import (google-genai SDK)
    except ImportError as exc:
        raise LLMUnavailable("Gemini fallback needs the 'google-genai' package "
                             "(pip install google-genai).") from exc
    client = genai.Client(api_key=settings.gemini_api_key)
    result = client.models.generate_content(
        model=settings.gemini_model, contents=prompt, config={"temperature": 0.4})
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        raise LLMUnavailable("Gemini returned an empty response (possibly blocked by safety filters).")
    return text


def call_llm(prompt: str) -> str:
    """Generate text for ``prompt`` with Ollama, falling back to Gemini.

    Raises ``LLMUnavailable`` with actionable setup instructions when neither works.
    """
    settings = get_settings()
    prompt = (prompt or "")[:MAX_PROMPT_CHARS]
    problems: list[str] = []

    if settings.use_ollama:
        try:
            return _call_ollama(prompt, settings)
        except LLMUnavailable as exc:
            problems.append(str(exc))
        except ValueError as exc:  # endpoint rejected by url_guard
            problems.append(f"Ollama endpoint rejected: {exc}. Keep OLLAMA_BASE_URL on localhost "
                            f"or set ALLOW_REMOTE_LLM=true.")
        except requests.ConnectionError:
            problems.append(f"Ollama is not reachable at {settings.ollama_base_url}. Install it from "
                            f"ollama.com, then run `ollama serve` and `ollama pull {settings.ollama_model}`.")
        except requests.Timeout:
            problems.append("Ollama timed out. Try a smaller model (e.g. `ollama pull mistral`) or retry.")
        except (requests.RequestException, KeyError) as exc:
            problems.append(f"Ollama request failed ({type(exc).__name__}).")
        logger.warning("Ollama unavailable: {}", problems[-1])
    else:
        problems.append("Ollama disabled (USE_OLLAMA=false).")

    if settings.gemini_api_key:
        try:
            return _call_gemini(prompt, settings)
        except LLMUnavailable as exc:
            problems.append(str(exc))
        except Exception as exc:  # SDK raises many types; never echo details that may hold the key
            problems.append(f"Gemini request failed ({type(exc).__name__}). Check GEMINI_API_KEY "
                            f"and your free-tier quota.")
        logger.warning("Gemini unavailable: {}", problems[-1])
    else:
        problems.append("No Gemini fallback: set GEMINI_API_KEY in .env "
                        "(free key at aistudio.google.com).")

    raise LLMUnavailable("No LLM available. " + " ".join(problems))
