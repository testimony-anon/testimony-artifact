"""Historical proposal-provider compatibility surface."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Protocol

from .current_providers import (
    OpenAICompatibleRenderedTransport as _OpenAICompatibleRenderedTransport,
    RenderedProposalResponse as _RenderedProposalResponse,
)


@dataclass(frozen=True)
class ProposalResponse:
    content: dict[str, Any]
    response_sha256: str
    model: str
    endpoint_shape: str
    endpoint_host: str
    temperature: float
    retry_count: int
    response_received_at: str | None = None


class ProposalProvider(Protocol):
    def propose(self, *, prompt: str, evidence: dict[str, Any]) -> ProposalResponse:
        """Return one typed JSON proposal without making an admission decision."""


class OpenAICompatibleProvider(_OpenAICompatibleRenderedTransport):
    """Historical prompt-plus-evidence OpenAI-compatible provider."""

    def propose(self, *, prompt: str, evidence: dict[str, Any]) -> ProposalResponse:
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(evidence, sort_keys=True, separators=(",", ":"))},
            ],
        }
        raw, retries, received_at = self._call(payload)
        content = raw["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("proposal response must be a JSON object")
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
        return ProposalResponse(
            content=parsed,
            response_sha256=hashlib.sha256(canonical).hexdigest(),
            model=self._model,
            endpoint_shape="openai_compatible",
            endpoint_host=urllib.parse.urlparse(self._endpoint).netloc,
            temperature=self._temperature,
            retry_count=retries,
            response_received_at=received_at,
        )

    def propose_rendered(self, *, rendered_prompt: str) -> _RenderedProposalResponse:
        """Historical convenience method; current code uses current_providers."""

        return self(rendered_prompt=rendered_prompt)


__all__ = ["OpenAICompatibleProvider", "ProposalProvider", "ProposalResponse"]
