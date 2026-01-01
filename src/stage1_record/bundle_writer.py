"""Session bundle writer (where 002 D17 + D18 are implemented).

- jsonl members are appended incrementally (redacted at write time + each record passes the schema); page_state is written as each snapshot is taken (redacted before gzip);
- the har is rescanned against the full secret set during finalization before being written; the manifest is written last (the validity criterion);
- Stage 1 invariant: at no moment does unredacted content exist on disk.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

from common.contracts import validate_artifact
from common.request_material_shape import (
    RequestMaterialShapeError,
    load_request_material_shapes,
)

from .secrets import SecretRegistry

PAGE_STATE_FORMAT = "dom_html_v1"  # the value table is frozen (002 D14)


class BundleWriter:
    def __init__(self, bundle_dir: str | Path, secrets: SecretRegistry):
        self.bundle_dir = Path(bundle_dir)
        self.bundle_dir.mkdir(parents=True, exist_ok=True)
        (self.bundle_dir / "page_state").mkdir(exist_ok=True)
        self._secrets = secrets
        self._page_state_index: list[dict] = []
        self._ps_seq = 0
        # create the jsonl members as empty files first (member names frozen by the manifest)
        (self.bundle_dir / "ui_action_log.jsonl").touch()
        (self.bundle_dir / "action_decision_log.jsonl").touch()
        self._finalized = False

    def _append_jsonl(self, filename: str, schema_name: str, record: dict) -> dict:
        record = self._secrets.redact_obj(record)  # redact at write time (D18 invariant)
        validate_artifact(schema_name, record)  # pass the schema before the artifact is written (contract rule)
        with open(self.bundle_dir / filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
        return record

    def append_ui_action(self, record: dict) -> dict:
        return self._append_jsonl(
            "ui_action_log.jsonl", "session_bundle_ui_action.schema.json", record
        )

    def append_decision(self, record: dict) -> dict:
        return self._append_jsonl(
            "action_decision_log.jsonl", "session_bundle_action_decision.schema.json", record
        )

    def write_page_state(
        self, *, url: str, title: str, dom_html: str, action_id: str, captured_at: str
    ) -> None:
        snapshot = {
            "url": url,
            "title": title,
            "captured_at": captured_at,
            "action_id": action_id,
            "dom_html": dom_html,
        }
        snapshot = self._secrets.redact_obj(snapshot)  # redact before gzip (D18)
        self._ps_seq += 1
        rel = f"page_state/{self._ps_seq:04d}.json.gz"
        with gzip.open(self.bundle_dir / rel, "wt", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        self._page_state_index.append(
            {
                "file": rel,
                "timestamp": captured_at,
                "action_id": action_id,
                "format": PAGE_STATE_FORMAT,
            }
        )

    def finalize(self, *, har: dict, metadata: dict, session: dict) -> Path:
        """Finalize a structured-redaction bundle; manifest remains the last write."""
        har = copy.deepcopy(har)
        self._secrets.register_from_obj(har)
        descriptors, terminal_json_texts = self._redact_json_request_material(har)
        har = self._secrets.redact_obj(har)
        for entry_index, text in terminal_json_texts.items():
            post = har["log"]["entries"][entry_index]["request"].get("postData")
            if not isinstance(post, dict):
                raise ValueError(
                    f"recorded JSON request lost postData during redaction "
                    f"(entry_index={entry_index})"
                )
            # Typed JSON redaction is terminal; generic string replacement must
            # not turn scalar tokens into unquoted placeholders afterward.
            post["text"] = text
        validate_artifact("session_bundle_har.schema.json", har)

        descriptor_path = self.bundle_dir / "request_material_shapes.jsonl"
        descriptor_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
                for row in descriptors
            )
        )
        (self.bundle_dir / "har.json").write_text(
            json.dumps(har, ensure_ascii=False, indent=1) + "\n"
        )

        session_metadata = self._secrets.redact_obj(session)
        auth = session.get("auth_context", {})
        safe_auth = session_metadata.get("auth_context", {})
        # These are workflow references and verified relation enums, not
        # cookie/token values. Keep the global registered-secret substitution;
        # bypass only the generic sensitive-key heuristic in this metadata.
        if isinstance(auth.get("session_ref"), str):
            safe_auth["session_ref"] = self._secrets.redact_text(auth["session_ref"])
        for source, saved in zip(
            auth.get("identity_relations", []), safe_auth.get("identity_relations", [])
        ):
            for key in ("left_session_ref", "right_session_ref"):
                if isinstance(source.get(key), str):
                    saved[key] = self._secrets.redact_text(source[key])
            if source.get("session_relation") in {"same", "different"}:
                saved["session_relation"] = source["session_relation"]
        manifest = {
            "metadata": metadata,
            "session": session_metadata,
            "members": {
                "har": "har.json",
                "ui_action_log": "ui_action_log.jsonl",
                "action_decision_log": "action_decision_log.jsonl",
                "request_material_shapes": "request_material_shapes.jsonl",
                "page_state": self._page_state_index,
            },
        }
        try:
            load_request_material_shapes(
                self.bundle_dir,
                manifest,
                har["log"]["entries"],
            )
        except RequestMaterialShapeError:
            raise ValueError("request-material descriptor closure failed") from None
        validate_artifact("session_bundle_manifest.schema.json", manifest)
        manifest_path = self.bundle_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        self._finalized = True
        return manifest_path

    def _redact_json_request_material(
        self, har: dict
    ) -> tuple[list[dict], dict[int, str]]:
        descriptors = []
        terminal_texts = {}
        for entry_index, entry in enumerate(har["log"]["entries"]):
            request = entry["request"]
            post = request.get("postData") or {}
            mime = str(post.get("mimeType") or "")
            text = post.get("text")
            if "json" not in mime.lower() or not isinstance(text, str) or not text:
                continue
            try:
                body = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                raise ValueError(
                    f"recorded JSON request is invalid before redaction (entry_index={entry_index})"
                ) from None
            redacted, nodes = self._secrets.redact_json_value(body)
            if nodes and not isinstance(redacted, (dict, list)):
                raise ValueError(
                    f"redacted JSON request root is not object/array (entry_index={entry_index})"
                )
            redacted_text = json.dumps(
                redacted,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            post["text"] = redacted_text
            terminal_texts[entry_index] = redacted_text
            if not nodes:
                continue
            descriptor = {
                "entry_index": entry_index,
                "method": request["method"],
                "mime_type": mime,
                "root_kind": "object" if isinstance(redacted, dict) else "array",
                "redacted_body_bytes": len(redacted_text.encode()),
                "redacted_body_sha256": hashlib.sha256(
                    redacted_text.encode()
                ).hexdigest(),
                "redactions": nodes,
            }
            validate_artifact(
                "session_bundle_request_material_shape.schema.json", descriptor
            )
            descriptors.append(descriptor)
        return descriptors, terminal_texts
