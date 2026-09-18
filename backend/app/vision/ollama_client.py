from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class OllamaClientError(RuntimeError):
    """Raised when the configured local Ollama service cannot answer."""


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen3-vl:4b"
    timeout_seconds: float = 90.0

    @classmethod
    def from_environment(cls) -> "OllamaConfig":
        timeout = os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")
        try:
            timeout_seconds = max(1.0, float(timeout))
        except ValueError:
            timeout_seconds = 90.0
        return cls(
            base_url=os.getenv("OLLAMA_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("OLLAMA_MODEL", cls.model),
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class OllamaResult:
    model: str
    raw_text: str
    raw_response: dict[str, Any]
    duration_ms: int


class OllamaClient:
    def __init__(self, config: OllamaConfig | None = None, opener: Callable[..., Any] = urlopen) -> None:
        self.config = config or OllamaConfig.from_environment()
        self._opener = opener

    def analyze_image(self, image: bytes, prompt: str) -> OllamaResult:
        started = time.perf_counter()
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "images": [base64.b64encode(image).decode("ascii")],
            "stream": False,
            "format": "json",
        }
        request = Request(
            f"{self.config.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read()
            raw_response = json.loads(response_body.decode("utf-8"))
            if not isinstance(raw_response, dict):
                raise OllamaClientError("Ollama returned a non-object response.")
            raw_text = str(raw_response.get("response", ""))
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("Ollama request succeeded model=%s duration_ms=%s", self.config.model, duration_ms)
            return OllamaResult(self.config.model, raw_text, raw_response, duration_ms)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("Ollama request failed model=%s duration_ms=%s error=%s", self.config.model, duration_ms, error)
            raise OllamaClientError(f"Could not reach Ollama at {self.config.base_url}: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError, OllamaClientError) as error:
            logger.warning("Ollama returned an invalid response model=%s error=%s", self.config.model, error)
            if isinstance(error, OllamaClientError):
                raise
            raise OllamaClientError("Ollama returned invalid JSON.") from error


__all__ = ["OllamaClient", "OllamaClientError", "OllamaConfig", "OllamaResult"]