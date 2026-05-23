"""LLM client wrapper for OpenAI / Azure OpenAI."""
import json
import logging
import os

from openai import AzureOpenAI, OpenAI

logger = logging.getLogger("graphmind")

USE_AZURE = os.environ.get("GRAPHMIND_USE_AZURE", "1") not in ("0", "false", "False")
LLM_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

_cached_client = None


def _get_client():
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    if USE_AZURE:
        _cached_client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        )
    else:
        _cached_client = OpenAI()
    return _cached_client


def _get_model():
    if USE_AZURE:
        return os.environ["AZURE_OPENAI_DEPLOYMENT"]
    return LLM_MODEL


EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-large")


def _get_embed_model():
    if USE_AZURE:
        return os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-large")
    return EMBED_MODEL


def embed(texts, batch_size: int = 128):
    """Embed a list of strings via OpenAI / Azure OpenAI. Returns np.ndarray [n, d]."""
    import numpy as np
    client = _get_client()
    model = _get_embed_model()
    out = []
    for i in range(0, len(texts), batch_size):
        chunk = [t if t else " " for t in texts[i:i + batch_size]]
        resp = client.embeddings.create(model=model, input=chunk)
        out.extend(d.embedding for d in resp.data)
    return np.asarray(out, dtype=np.float32)


class AzureEmbedder:
    """``embedder(list[str]) -> np.ndarray`` adapter for ``cluster_graph``."""
    def __call__(self, texts):
        return embed(list(texts))


def _ensure_json_in_messages(messages):
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str) and "json" in content.lower():
            return
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "json" in part.get("text", "").lower():
                    return
    last = messages[-1]
    if isinstance(last.get("content"), str):
        last["content"] += "\n\nRespond with valid JSON."
    elif isinstance(last.get("content"), list):
        last["content"].append({"type": "text", "text": "\n\nRespond with valid JSON."})


def call_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 2000,
             response_in_json: bool = False, agent_name: str = "unknown") -> str:
    client = _get_client()
    kwargs = dict(
        model=_get_model(),
        messages=[{"role": "system", "content": prompt}],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    if response_in_json:
        kwargs["response_format"] = {"type": "json_object"}
        _ensure_json_in_messages(kwargs["messages"])
    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    logger.debug("[%s] tokens: %s/%s", agent_name, resp.usage.prompt_tokens, resp.usage.completion_tokens)
    return text


def call_llm_with_memory(messages: list, response_format=None,
                         temperature: float = 0.0, max_tokens: int = 10000,
                         agent_name: str = "unknown") -> str:
    client = _get_client()
    messages = [m for m in messages if isinstance(m.get("content"), str) and m["content"].strip()]
    kwargs = dict(
        model=_get_model(),
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = {"type": "json_object"}
        _ensure_json_in_messages(kwargs["messages"])

    for attempt in range(3):
        resp = client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        if response_format:
            try:
                json.loads(text)
                return text
            except (json.JSONDecodeError, TypeError):
                if attempt < 2:
                    logger.warning("[%s] Attempt %d: Invalid JSON, retrying...", agent_name, attempt + 1)
                else:
                    logger.error("[%s] JSON validation failed after 3 attempts.", agent_name)
                    return text
        else:
            return text
    return text


def call_llm_with_memory_for_image(messages: list, image: str = None,
                                    response_format=None, temperature: float = 0.0,
                                    max_tokens: int = 800, agent_name: str = "unknown") -> str:
    client = _get_client()
    if image:
        messages = [dict(messages[0]), *messages[1:]]
        messages[0]["content"] = [
            {"type": "text", "text": messages[0]["content"]},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
        ]
    kwargs = dict(
        model=_get_model(),
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = {"type": "json_object"}
        _ensure_json_in_messages(kwargs["messages"])
    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    logger.debug("[%s/image] tokens: %s/%s", agent_name, resp.usage.prompt_tokens, resp.usage.completion_tokens)
    return text
