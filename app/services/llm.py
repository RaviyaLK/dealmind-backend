"""Shared LLM client — uses OpenRouter (OpenAI-compatible) with free models."""
import re
import time
import logging
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# OpenRouter client (OpenAI-compatible API)
client = OpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# Default model
DEFAULT_MODEL = settings.LLM_MODEL

# Regex to strip <think>…</think> blocks from reasoning models (DeepSeek R1, etc.)
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def _strip_think_tags(text: str) -> str:
    """Remove <think>…</think> reasoning blocks that R1 models prepend."""
    return _THINK_RE.sub("", text).strip()


def call_llm(prompt: str, max_tokens: int = 2048, model: str = None) -> str:
    """Call the LLM with a single user prompt and return the text response."""
    used_model = model or DEFAULT_MODEL
    prompt_preview = prompt[:120].replace("\n", " ")
    logger.info("LLM call → model=%s  max_tokens=%d  prompt='%s…'", used_model, max_tokens, prompt_preview)

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=used_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content or ""
        elapsed = time.perf_counter() - t0

        # Token usage (if provided by OpenRouter)
        usage = response.usage
        tokens_info = ""
        if usage:
            tokens_info = f"  tokens(in={usage.prompt_tokens}, out={usage.completion_tokens})"

        logger.info(
            "LLM done ← %.1fs  raw_len=%d  clean_len=%d%s",
            elapsed, len(raw), len(_strip_think_tags(raw)), tokens_info,
        )
        logger.debug("LLM raw response (first 300 chars): %s", raw[:300])

        return _strip_think_tags(raw)

    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error("LLM error after %.1fs: %s: %s", elapsed, type(e).__name__, e)
        raise
