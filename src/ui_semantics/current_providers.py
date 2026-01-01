"""Current rendered-input provider boundary and live transports."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol


_MAX_SSE_EVENT_BYTES = 4 * 1024 * 1024
_MAX_SSE_STREAM_BYTES = 64 * 1024 * 1024
_MAX_SSE_EVENTS = 100_000


@dataclass(frozen=True)
class RenderedProposalResponse:
    """Raw response metadata for the current single-rendered-input boundary."""

    content: str
    model: str
    endpoint_shape: str
    endpoint_host: str
    temperature: float
    retry_count: int
    response_received_at: str
    raw_envelope: dict[str, Any] | None = None
    reasoning_effort: str | None = None


class RenderedProposalProvider(Protocol):
    def propose_rendered(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        """Receive exactly one already-rendered scientific input."""


class RenderedProposalTransport(Protocol):
    def __call__(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        """Transport hook whose only scientific payload is the rendered string."""


@dataclass(frozen=True)
class RenderedProposalProviderAdapter:
    """Current provider boundary around an explicitly injected transport."""

    transport: RenderedProposalTransport

    def propose_rendered(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        if not isinstance(rendered_prompt, str) or not rendered_prompt:
            raise ValueError("rendered proposal prompt must be a nonempty string")
        return self.transport(rendered_prompt=rendered_prompt)


class OpenAICompatibleRenderedTransport:
    """Rendered-only OpenAI-compatible transport for one bounded attempt.

    ``max_retries`` remains the frozen, cross-invocation budget.  One transport
    instance consumes at most one attempt so a concurrent M10 stage cannot
    amplify a gateway failure through immediate per-call retries.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        reasoning_effort: str | None = None,
        temperature: float = 0.1,
        max_retries: int = 2,
        timeout_seconds: float = 180,
        max_output_tokens: int | None = None,
        on_transport_attempt: Callable[[], None] | None = None,
        prior_attempt_count: int = 0,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._temperature = temperature
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._on_transport_attempt = on_transport_attempt
        if not 0 <= prior_attempt_count <= max_retries:
            raise ValueError("prior provider attempts exceed the frozen retry limit")
        self._prior_attempt_count = prior_attempt_count

    def __call__(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        if not isinstance(rendered_prompt, str) or not rendered_prompt:
            raise ValueError("rendered proposal prompt must be a nonempty string")
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": rendered_prompt}],
            # Stream the completion so long generations are not cut by idle
            # connection limits; the response is aggregated back into one
            # chat.completion envelope before any scientific processing.
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self._max_output_tokens is not None:
            payload["max_tokens"] = self._max_output_tokens
        if self._reasoning_effort is not None:
            # OpenAI-format thinking control; DeepSeek accepts low/high/max here.
            payload["reasoning_effort"] = self._reasoning_effort
        raw, retries, received_at = self._call(payload)
        content = raw["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content:
            raise ValueError("proposal response must contain nonempty message content")
        response_model = raw.get("model")
        if not isinstance(response_model, str) or not response_model.strip():
            raise ValueError("proposal response must report its actual model")
        return RenderedProposalResponse(
            content=content,
            raw_envelope=raw,
            model=response_model,
            endpoint_shape="openai_compatible",
            endpoint_host=urllib.parse.urlparse(self._endpoint).netloc,
            temperature=self._temperature,
            retry_count=retries,
            response_received_at=received_at,
            reasoning_effort=self._reasoning_effort,
        )

    def _call(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int, str]:
        body = json.dumps(payload).encode()
        if self._on_transport_attempt is not None:
            self._on_transport_attempt()
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        attempt_started_at = time.monotonic()
        with urllib.request.urlopen(
            request, timeout=self._timeout_seconds
        ) as response:
            headers = getattr(response, "headers", None)
            content_type = str(headers.get("Content-Type") or "") if headers is not None else ""
            if content_type.split(";")[0].strip().lower() == "text/event-stream":
                raw = _read_openai_sse_response(
                    response, attempt_started_at=attempt_started_at
                )
            else:
                raw = json.loads(response.read())
            received_at = (
                datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            return raw, self._prior_attempt_count, received_at



def _read_openai_sse_response(
    response: Any, *, attempt_started_at: float
) -> dict[str, Any]:
    """Aggregate one OpenAI-compatible SSE stream into a chat.completion envelope."""

    event_data_lines: list[str] = []
    events: list[dict[str, Any]] = []
    stream_bytes = 0
    first_event_elapsed_seconds: float | None = None
    done = False

    def dispatch_event() -> None:
        nonlocal done, first_event_elapsed_seconds
        if not event_data_lines:
            return
        data = "\n".join(event_data_lines)
        event_data_lines.clear()
        if done:
            raise ValueError("provider stream contains data after [DONE]")
        if data == "[DONE]":
            done = True
            return
        if len(data.encode("utf-8")) > _MAX_SSE_EVENT_BYTES:
            raise ValueError("provider SSE event exceeds the bounded size")
        event = json.loads(data)
        if not isinstance(event, dict):
            raise ValueError("provider SSE event must be a JSON object")
        if len(events) >= _MAX_SSE_EVENTS:
            raise ValueError("provider SSE event count exceeds the bounded limit")
        if first_event_elapsed_seconds is None:
            first_event_elapsed_seconds = time.monotonic() - attempt_started_at
        events.append(event)

    for raw_line in response:
        if not isinstance(raw_line, bytes):
            raise ValueError("provider SSE stream must yield bytes")
        stream_bytes += len(raw_line)
        if stream_bytes > _MAX_SSE_STREAM_BYTES:
            raise ValueError("provider SSE stream exceeds the bounded size")
        try:
            line = raw_line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError as exc:
            raise ValueError("provider SSE stream is not valid UTF-8") from exc
        if not line:
            dispatch_event()
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field == "data" and separator:
            event_data_lines.append(value[1:] if value.startswith(" ") else value)
            continue
        if field in {"event", "id", "retry"} and separator:
            continue
        raise ValueError("provider response is not valid SSE")
    dispatch_event()
    if not done:
        raise ValueError("provider SSE stream ended without [DONE]")
    if not events:
        raise ValueError("provider SSE stream contains no response events")
    return _aggregate_openai_sse_events(
        events,
        stream_bytes=stream_bytes,
        first_event_elapsed_seconds=first_event_elapsed_seconds,
        total_elapsed_seconds=time.monotonic() - attempt_started_at,
    )


def _aggregate_openai_sse_events(
    events: list[dict[str, Any]],
    *,
    stream_bytes: int,
    first_event_elapsed_seconds: float | None,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    models: set[str] = set()
    fingerprints: set[str] = set()
    response_ids: set[str] = set()
    finish_reasons: list[str] = []
    usage: dict[str, Any] | None = None

    for event in events:
        model = event.get("model")
        if model is not None:
            if not isinstance(model, str) or not model.strip():
                raise ValueError("provider stream reports an invalid model")
            models.add(model)
        fingerprint = event.get("system_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            fingerprints.add(fingerprint)
        response_id = event.get("id")
        if isinstance(response_id, str) and response_id:
            response_ids.add(response_id)
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            # OpenAI sends a trailing usage-only event; DeepSeek attaches usage
            # to the final content chunk. Accept both; the last one wins.
            usage = event_usage
        choices = event.get("choices")
        if choices is None or choices == []:
            continue
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("provider stream must contain exactly one choice")
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
            raise ValueError("provider stream choice must have index zero")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise ValueError("provider stream choice must contain a delta object")
        content = delta.get("content")
        if content is not None:
            if not isinstance(content, str):
                raise ValueError("provider stream content chunk must be a string")
            content_parts.append(content)
        reasoning = delta.get("reasoning_content")
        if reasoning is not None:
            if not isinstance(reasoning, str):
                raise ValueError("provider stream reasoning chunk must be a string")
            reasoning_parts.append(reasoning)
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None:
            if not isinstance(finish_reason, str):
                raise ValueError("provider stream finish reason must be a string")
            finish_reasons.append(finish_reason)

    if len(models) != 1:
        raise ValueError("provider stream actual model is missing or changed between chunks")
    if len(fingerprints) > 1:
        raise ValueError("provider stream system fingerprint changed between chunks")
    if len(response_ids) > 1:
        raise ValueError("provider stream response id changed between chunks")
    if finish_reasons != ["stop"]:
        raise ValueError(
            f"provider stream must finish exactly once with reason stop, got {finish_reasons}"
        )
    if usage is None:
        raise ValueError("provider stream is missing usage")
    content = "".join(content_parts)
    if not content:
        raise ValueError("proposal response must contain nonempty message content")
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    return {
        "id": next(iter(response_ids), None),
        "object": "chat.completion",
        "model": next(iter(models)),
        "system_fingerprint": next(iter(fingerprints), None),
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": usage,
        "_uisemtest_stream": {
            "delivery": "sse",
            "event_count": len(events),
            "stream_bytes": stream_bytes,
            "first_event_elapsed_seconds": first_event_elapsed_seconds,
            "total_elapsed_seconds": total_elapsed_seconds,
        },
    }


class CodexCLIRenderedTransport:
    """Rendered-only ChatGPT-authenticated Codex CLI transport.

    The CLI does not expose an actual dated model snapshot.  The response uses
    the frozen requested alias for the existing call-spec identity check and
    records that provenance explicitly in the raw envelope.
    """

    _ALLOWED_EVENT_TYPES = {
        "thread.started",
        "turn.started",
        "item.started",
        "item.updated",
        "item.completed",
        "turn.completed",
    }
    _ALLOWED_ITEM_TYPES = {"agent_message", "reasoning"}
    _STRIPPED_ENVIRONMENT = {
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_BASE_URL",
        "AZURE_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }

    def __init__(
        self,
        *,
        executable: Path,
        cli_version: str,
        model: str,
        reasoning_effort: str,
        endpoint_host: str,
        temperature: float = 0.1,
        max_retries: int = 1,
        timeout_seconds: float = 300,
        on_transport_attempt: Callable[[], None] | None = None,
        prior_attempt_count: int = 0,
    ) -> None:
        if not executable.is_absolute():
            raise ValueError("Codex CLI executable must be an absolute path")
        if not cli_version.strip():
            raise ValueError("Codex CLI version must be nonempty")
        if not 0 <= prior_attempt_count <= max_retries:
            raise ValueError("prior provider attempts exceed the frozen retry limit")
        self._executable = executable
        self._cli_version = cli_version.strip()
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._endpoint_host = endpoint_host
        self._temperature = temperature
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._on_transport_attempt = on_transport_attempt
        self._prior_attempt_count = prior_attempt_count

    def __call__(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        if not isinstance(rendered_prompt, str) or not rendered_prompt:
            raise ValueError("rendered proposal prompt must be a nonempty string")
        if self._on_transport_attempt is not None:
            self._on_transport_attempt()
        with tempfile.TemporaryDirectory(prefix="uisemtest-codex-cli-") as raw_root:
            workdir = Path(raw_root)
            final_path = workdir / "last_message.txt"
            command = [
                str(self._executable),
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "-C",
                str(workdir),
                "-s",
                "read-only",
                "-m",
                self._model,
                "-c",
                f"model_reasoning_effort={json.dumps(self._reasoning_effort)}",
                "--json",
                "--output-last-message",
                str(final_path),
                "-",
            ]
            completed = subprocess.run(
                command,
                input=rendered_prompt.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env=_codex_cli_environment(),
                timeout=self._timeout_seconds,
                check=False,
            )
            received_at = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            stdout = completed.stdout.decode("utf-8", errors="strict")
            stderr = completed.stderr.decode("utf-8", errors="replace")
            if completed.returncode != 0:
                detail = stderr.strip().splitlines()[-1] if stderr.strip() else "no stderr"
                raise RuntimeError(
                    f"Codex CLI exited with status {completed.returncode}: {detail}"
                )
            if not final_path.is_file():
                raise ValueError("Codex CLI did not write its final message")
            content = final_path.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError("Codex CLI final message is empty")
            events, usage, final_event_text = _parse_codex_cli_events(stdout)
            if final_event_text.strip() != content.strip():
                raise ValueError("Codex CLI final message differs from its JSONL event")
            return RenderedProposalResponse(
                content=content,
                raw_envelope={
                    "schema_version": "uisemtest-codex-cli-response-v1",
                    "transport": "codex_cli",
                    "requested_model": self._model,
                    "reasoning_effort": self._reasoning_effort,
                    "response_model_identity": self._model,
                    "response_model_identity_source": "requested_model_alias",
                    "actual_model_snapshot_not_exposed": True,
                    "cli_executable": str(self._executable),
                    "cli_version": self._cli_version,
                    "jsonl_stdout": stdout,
                    "events": events,
                    "usage": usage,
                    "final_message": content,
                    "stderr": stderr,
                    "exit_code": completed.returncode,
                    "sandbox": "read-only",
                    "ephemeral": True,
                    "user_config_ignored": True,
                    "rules_ignored": True,
                    "output_schema_used": False,
                    "temperature_not_exposed_by_cli": self._temperature,
                },
                model=self._model,
                reasoning_effort=self._reasoning_effort,
                endpoint_shape="codex_cli",
                endpoint_host=self._endpoint_host,
                temperature=self._temperature,
                retry_count=self._prior_attempt_count,
                response_received_at=received_at,
            )


def _codex_cli_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in CodexCLIRenderedTransport._STRIPPED_ENVIRONMENT:
        environment.pop(name, None)
    return environment


def _parse_codex_cli_events(
    stdout: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    events: list[dict[str, Any]] = []
    completed_messages: list[str] = []
    completed_usages: list[dict[str, Any]] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Codex CLI emitted invalid JSONL at line {line_number}"
            ) from exc
        if not isinstance(event, dict):
            raise ValueError("Codex CLI JSONL event must be an object")
        event_type = event.get("type")
        if event_type not in CodexCLIRenderedTransport._ALLOWED_EVENT_TYPES:
            raise ValueError(f"Codex CLI emitted a forbidden event: {event_type!r}")
        if event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict):
                raise ValueError("Codex CLI item event lacks its item object")
            item_type = item.get("type")
            if item_type not in CodexCLIRenderedTransport._ALLOWED_ITEM_TYPES:
                raise ValueError(
                    f"Codex CLI emitted a forbidden tool/item: {item_type!r}"
                )
            if event_type == "item.completed" and item_type == "agent_message":
                text = item.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Codex CLI completed agent message is empty")
                completed_messages.append(text)
        if event_type == "turn.completed":
            usage = event.get("usage")
            if not isinstance(usage, dict):
                raise ValueError("Codex CLI completed turn lacks usage")
            completed_usages.append(usage)
        events.append(event)
    if len(completed_messages) != 1:
        raise ValueError("Codex CLI must emit exactly one completed agent message")
    if len(completed_usages) != 1:
        raise ValueError("Codex CLI must emit exactly one completed turn usage")
    return events, completed_usages[0], completed_messages[0]


__all__ = [
    "CodexCLIRenderedTransport",
    "OpenAICompatibleRenderedTransport",
    "RenderedProposalProvider",
    "RenderedProposalProviderAdapter",
    "RenderedProposalResponse",
    "RenderedProposalTransport",
]
