from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from stock_state.config import DEFAULTS, Defaults


class NarratorUnavailable(RuntimeError):
    pass


class NarratorClient(Protocol):
    provider: str
    model: str

    def generate(self, *, prompt: str, digest: dict[str, object]) -> str:
        ...


@dataclass
class AnthropicNarratorClient:
    model: str = DEFAULTS.NARRATOR_MODEL
    config: Defaults = DEFAULTS
    provider: str = "anthropic"

    def generate(self, *, prompt: str, digest: dict[str, object]) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise NarratorUnavailable("missing ANTHROPIC_API_KEY")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise NarratorUnavailable("anthropic package is not installed") from exc
        client = Anthropic(api_key=api_key)
        kwargs = {
            "model": self.model,
            "max_tokens": self.config.NARRATOR_MAX_TOKENS,
            "system": prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(digest, ensure_ascii=False, sort_keys=True),
                }
            ],
        }
        if _anthropic_supports_temperature(self.model):
            kwargs["temperature"] = self.config.NARRATOR_TEMPERATURE
        response = client.messages.create(**kwargs)
        return "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", "") == "text"
        ).strip()


@dataclass
class OpenAINarratorClient:
    model: str = DEFAULTS.NARRATOR_OPENAI_MODEL
    config: Defaults = DEFAULTS
    provider: str = "openai"

    def generate(self, *, prompt: str, digest: dict[str, object]) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise NarratorUnavailable("missing OPENAI_API_KEY")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise NarratorUnavailable("openai package is not installed") from exc
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(digest, ensure_ascii=False, sort_keys=True),
                },
            ],
            max_output_tokens=self.config.NARRATOR_MAX_TOKENS,
            temperature=self.config.NARRATOR_TEMPERATURE,
        )
        text = getattr(response, "output_text", "")
        return str(text).strip()


def make_client(
    *,
    provider: str | None = None,
    model: str | None = None,
    config: Defaults = DEFAULTS,
) -> NarratorClient:
    selected = (provider or os.getenv("STOCK_STATE_NARRATOR_PROVIDER") or config.NARRATOR_PROVIDER).lower()
    if selected == "openai":
        return OpenAINarratorClient(
            model=model or os.getenv("STOCK_STATE_NARRATOR_MODEL") or config.NARRATOR_OPENAI_MODEL,
            config=config,
        )
    if selected == "anthropic":
        return AnthropicNarratorClient(
            model=model or os.getenv("STOCK_STATE_NARRATOR_MODEL") or config.NARRATOR_MODEL,
            config=config,
        )
    raise NarratorUnavailable(f"unsupported narrator provider: {selected}")


def _anthropic_supports_temperature(model: str) -> bool:
    current_fixed_sampling_prefixes = (
        "claude-sonnet-5",
        "claude-opus-4-8",
    )
    return not model.startswith(current_fixed_sampling_prefixes)
