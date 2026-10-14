"""Thin client for Ollama's native chat API.

Two call shapes:
- ``structured``: non-streamed, constrained to a JSON schema via Ollama's
  ``format`` field, validated with Pydantic. Used for planning/evaluation.
- ``stream``: token stream for the interviewer's spoken reply.
"""

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from enum import Enum
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    pass


def field_guide(schema: type[BaseModel], indent: str = "") -> str:
    """Describe a model's fields in plain text for the prompt.

    Ollama enforces `format` as a grammar but never shows the schema to the
    model, so field descriptions (rubrics, units, what goes where) would be
    invisible without this. Found via the eval harness: the model filled
    `missing` with the literal word "missing" and ignored scoring rubrics.
    """
    lines = []
    for name, f in schema.model_fields.items():
        ann = f.annotation
        inner = getattr(ann, "__args__", (ann,))[0] if getattr(ann, "__origin__", None) is list else ann
        if isinstance(inner, type) and issubclass(inner, Enum):
            kind = "one of " + ", ".join(m.value for m in inner)
        elif isinstance(inner, type) and issubclass(inner, BaseModel):
            kind = "list of objects" if inner is not ann else "object"
        else:
            kind = ("list of " if inner is not ann else "") + getattr(inner, "__name__", str(inner))
        bounds = {k: getattr(m, k) for m in f.metadata for k in ("ge", "le", "max_length", "min_length") if hasattr(m, k)}
        if "ge" in bounds and "le" in bounds:
            kind += f" {bounds['ge']}-{bounds['le']}"
        if "max_length" in bounds:
            kind += f", at most {bounds['max_length']}" + (" items" if inner is not ann else " characters")
        desc = f": {f.description}" if f.description else ""
        lines.append(f"{indent}- {name} ({kind}){desc}")
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            lines.append(field_guide(inner, indent + "  "))
    return "\n".join(lines)


def with_field_guide(messages: list[dict], schema: type[BaseModel]) -> list[dict]:
    guide = {"role": "system", "content": "Reply with a JSON object with these fields:\n" + field_guide(schema)}
    # Right after the main system prompt, before the content to judge.
    return messages[:1] + [guide] + messages[1:]


class LLM(Protocol):
    async def structured(self, messages: list[dict], schema: type[T], temperature: float = 0.2) -> T: ...

    def stream(self, messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]: ...


class OllamaLLM:
    def __init__(self, base_url: str = config.OLLAMA_URL, model: str = config.LLM_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5))

    def _payload(self, messages: list[dict], temperature: float, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "think": False,  # qwen3: skip the reasoning trace, we want low latency
            "options": {"temperature": temperature, "num_ctx": config.LLM_NUM_CTX},
        }

    async def structured(self, messages: list[dict], schema: type[T], temperature: float = 0.2) -> T:
        payload = self._payload(with_field_guide(messages, schema), temperature, stream=False)
        payload["format"] = schema.model_json_schema()
        last_err: Exception | None = None
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                resp = await self._client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise LLMError(f"Ollama request failed: {e}") from e
            content = _THINK_RE.sub("", resp.json()["message"]["content"]).strip()
            log.info("llm.structured %s %.2fs attempt=%d", schema.__name__, time.perf_counter() - t0, attempt)
            try:
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_err = e
                log.warning("Schema validation failed (%s): %s", schema.__name__, content[:300])
        raise LLMError(f"Invalid {schema.__name__} from LLM: {last_err}")

    async def stream(self, messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]:
        payload = self._payload(messages, temperature, stream=True)
        try:
            async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama stream failed: {e}") from e

    async def health(self) -> dict:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags", timeout=3)
            names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "model": self.model, "model_ready": self.model in names, "installed": names}
        except Exception as e:  # noqa: BLE001 - surfaced to the UI as-is
            return {"ok": False, "model": self.model, "model_ready": False, "error": str(e)}

    async def aclose(self) -> None:
        await self._client.aclose()
