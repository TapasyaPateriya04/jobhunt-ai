"""LLM access: local Ollama first, Google Gemini free tier as fallback."""
from __future__ import annotations

import json
import time
from typing import Optional

import requests
from loguru import logger

from config import get_settings
from security.url_guard import validate_llm_endpoint

# Replies are streamed, so the read timeout is the longest wait for the *next* piece of text.
# The first piece only comes once the model has read the whole prompt, which on a laptop CPU
# can take minutes, hence the generous value. OLLAMA_MAX_SECONDS caps the whole answer.
OLLAMA_TIMEOUT = (5, 300)  # connect, longest silence
OLLAMA_MAX_SECONDS = 900
MAX_PROMPT_CHARS = 24_000
GEMINI = "gemini"  # pass as ``model`` to skip Ollama and use Gemini


class LLMUnavailable(RuntimeError):
    """No LLM backend could produce a response; the message says how to fix it."""


def _call_ollama(prompt: str, settings, model: Optional[str] = None) -> str:
    """Stream the answer from Ollama, so a slow model is only cut off if it stops producing text."""
    base = validate_llm_endpoint(settings.ollama_base_url)
    model = model or settings.ollama_model
    resp = requests.post(
        f"{base}/api/generate",
        json={"model": model, "prompt": prompt, "stream": True, "options": {"temperature": 0.4}},
        timeout=OLLAMA_TIMEOUT,
        stream=True,
    )
    try:
        if resp.status_code == 404:
            raise LLMUnavailable(f"Ollama is running but model '{model}' is not available. "
                                 f"Run: ollama pull {model}")
        resp.raise_for_status()
        parts: list[str] = []
        started = time.monotonic()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise LLMUnavailable(f"Ollama reported an error: {str(chunk['error'])[:200]}")
            parts.append(str(chunk.get("response") or ""))
            if chunk.get("done"):
                break
            if time.monotonic() - started > OLLAMA_MAX_SECONDS:
                raise requests.Timeout(f"no complete answer after {OLLAMA_MAX_SECONDS} s")
    finally:
        resp.close()
    text = "".join(parts).strip()
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


def call_llm(prompt: str, model: Optional[str] = None) -> str:
    """Generate text for ``prompt`` with Ollama, falling back to Gemini.

    ``model`` picks an installed Ollama model instead of OLLAMA_MODEL, or ``GEMINI`` to go
    straight to Gemini. Raises ``LLMUnavailable`` with setup instructions when nothing works.
    """
    settings = get_settings()
    prompt = (prompt or "")[:MAX_PROMPT_CHARS]
    problems: list[str] = []
    ollama_model = None if model == GEMINI else (model or settings.ollama_model)

    if settings.use_ollama and model != GEMINI:
        try:
            return _call_ollama(prompt, settings, ollama_model)
        except LLMUnavailable as exc:
            problems.append(str(exc))
        except ValueError as exc:  # endpoint rejected by url_guard
            problems.append(f"Ollama endpoint rejected: {exc}. Keep OLLAMA_BASE_URL on localhost "
                            f"or set ALLOW_REMOTE_LLM=true.")
        except requests.ConnectionError:
            problems.append(f"Ollama is not reachable at {settings.ollama_base_url}. Install it from "
                            f"ollama.com, then run `ollama serve` and `ollama pull {ollama_model}`.")
        except requests.Timeout:
            problems.append(f"Ollama ({ollama_model}) took too long. On a laptop without a GPU use a "
                            "smaller model: `ollama pull llama3.2:3b`, then pick it in the sidebar or set "
                            "OLLAMA_MODEL=llama3.2:3b in .env.")
        except (requests.RequestException, KeyError) as exc:
            problems.append(f"Ollama request failed ({type(exc).__name__}).")
        logger.warning("Ollama unavailable: {}", problems[-1])
    elif model != GEMINI:
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
