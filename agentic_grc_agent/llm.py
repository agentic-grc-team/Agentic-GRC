"""LLM access with structured output, timing and a degradation path (E0-04).

Every call returns the validated object plus metadata that goes into the trace.
If the model fails, times out or returns invalid JSON after the retries,
`LLMError` is raised and the caller uses its deterministic fallback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@dataclass
class CallMeta:
    model_name: str
    prompt_id: str
    prompt_version: str
    latency_ms: int
    attempts: int


class LLM(Protocol):
    model_name: str

    def structured(
        self, *, prompt_id: str, prompt_version: str, system: str, user: str, schema: type[T]
    ) -> tuple[T, CallMeta]: ...


class OllamaLLM:
    """Local model served by Ollama. Data never leaves the machine."""

    def __init__(self, model_name: str, host: str, timeout_s: float, retries: int = 1):
        import ollama  # imported here so tests do not need the package

        self.model_name = model_name
        self.retries = retries
        self._client = ollama.Client(host=host, timeout=timeout_s)

    def structured(self, *, prompt_id, prompt_version, system, user, schema):
        start = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            try:
                resp = self._client.chat(
                    model=self.model_name,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    format=schema.model_json_schema(),  # Ollama constrains the output to this schema
                    options={"temperature": 0},
                )
                obj = schema.model_validate_json(resp["message"]["content"])
                latency = int((time.perf_counter() - start) * 1000)
                return obj, CallMeta(self.model_name, prompt_id, prompt_version, latency, attempt)
            except ValidationError as e:  # malformed JSON: retry
                last_error = e
            except Exception as e:  # timeout, connection refused, model not pulled...
                raise LLMError(f"{type(e).__name__}: {e}") from e
        raise LLMError(f"Invalid structured output after {self.retries + 1} attempts: {last_error}")


class FakeLLM:
    """Deterministic stand-in for tests: a function per prompt_id returns the object."""

    model_name = "fake"

    def __init__(self, handlers: dict[str, Callable[[str], BaseModel | Exception]]):
        self.handlers = handlers
        self.calls: list[tuple[str, str]] = []

    def structured(self, *, prompt_id, prompt_version, system, user, schema):
        self.calls.append((prompt_id, user))
        result = self.handlers[prompt_id](user)
        if isinstance(result, Exception):
            raise LLMError(str(result))
        return schema.model_validate(result.model_dump()), CallMeta("fake", prompt_id, prompt_version, 0, 1)
