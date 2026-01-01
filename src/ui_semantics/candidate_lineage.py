"""Artifact-aware lineage validation for pre-proposal-evidence-v2 candidates.

All lineage SHA-256 values in ``CandidateSet`` are hashes of each strict
contract's canonical JSON bytes.  They are deliberately not hashes of pretty
printed files, and ``rendered_input_sha256`` is not the rendered-text hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .contracts import (
    CandidateSet,
    PreProposalEvidencePackage,
    ProposalEvidenceView,
    RenderedCandidateInput,
)


@dataclass(frozen=True)
class V2RenderedInputLineage:
    package: PreProposalEvidencePackage
    view: ProposalEvidenceView
    rendered_input: RenderedCandidateInput


@dataclass(frozen=True)
class V2CandidateLineage:
    candidate_set: CandidateSet
    package: PreProposalEvidencePackage
    view: ProposalEvidenceView
    rendered_input: RenderedCandidateInput


def load_v2_rendered_input_lineage(
    *,
    package_path: str | Path,
    view_path: str | Path,
    rendered_input_path: str | Path,
) -> V2RenderedInputLineage:
    """Load three actual input artifacts and close their canonical v2 lineage."""

    package_file = _regular_file(package_path, "pre-proposal package")
    view_file = _regular_file(view_path, "proposal evidence view")
    rendered_file = _regular_file(rendered_input_path, "rendered candidate input")
    package = PreProposalEvidencePackage.model_validate_json(
        package_file.read_bytes(), strict=True
    )
    view = ProposalEvidenceView.model_validate_json(view_file.read_bytes(), strict=True)
    rendered = RenderedCandidateInput.model_validate_json(
        rendered_file.read_bytes(), strict=True
    )
    _validate_rendered_input_lineage(package, view, rendered)
    return V2RenderedInputLineage(
        package=package,
        view=view,
        rendered_input=rendered,
    )


def load_v2_candidate_lineage(
    *,
    candidate_set_path: str | Path,
    package_path: str | Path,
    view_path: str | Path,
    rendered_input_path: str | Path,
) -> V2CandidateLineage:
    """Load four actual JSON artifacts and close their canonical v2 lineage."""

    candidate_path = _regular_file(candidate_set_path, "candidate set")
    rendered_file = _regular_file(rendered_input_path, "rendered candidate input")

    candidate_set = CandidateSet.model_validate_json(candidate_path.read_bytes(), strict=True)
    input_lineage = load_v2_rendered_input_lineage(
        package_path=package_path,
        view_path=view_path,
        rendered_input_path=rendered_input_path,
    )
    package = input_lineage.package
    view = input_lineage.view
    rendered = input_lineage.rendered_input

    if candidate_set.scientific_input_version != "preproposal-evidence-v2":
        raise ValueError("artifact-aware lineage loader accepts only preproposal-evidence-v2 CandidateSet")
    if any(
        item.scientific_input_version != "preproposal-evidence-v2"
        for item in candidate_set.candidates
    ):
        raise ValueError("all candidate records must use preproposal-evidence-v2")
    referenced_rendered = _resolve_rendered_ref(
        candidate_path.parent,
        candidate_set.rendered_input_ref,
    )
    if referenced_rendered != rendered_file:
        raise ValueError("CandidateSet rendered_input_ref does not identify the supplied rendered artifact")

    package_sha = package.canonical_sha256()
    view_sha = view.canonical_sha256()
    rendered_sha = rendered.canonical_sha256()
    if candidate_set.preproposal_evidence_package_sha256 != package_sha:
        raise ValueError("CandidateSet package canonical SHA-256 mismatch")
    if candidate_set.proposal_evidence_view_sha256 != view_sha:
        raise ValueError("CandidateSet view canonical SHA-256 mismatch")
    if candidate_set.rendered_input_sha256 != rendered_sha:
        raise ValueError("CandidateSet rendered-input canonical SHA-256 mismatch")

    return V2CandidateLineage(
        candidate_set=candidate_set,
        package=package,
        view=view,
        rendered_input=rendered,
    )


def _validate_rendered_input_lineage(
    package: PreProposalEvidencePackage,
    view: ProposalEvidenceView,
    rendered: RenderedCandidateInput,
) -> None:
    if package.scientific_input_version != "preproposal-evidence-v2":
        raise ValueError("pre-proposal package scientific input version mismatch")
    if view.scientific_input_version != "preproposal-evidence-v2":
        raise ValueError("proposal evidence view scientific input version mismatch")
    if rendered.scientific_input_version != "preproposal-evidence-v2":
        raise ValueError("rendered candidate input scientific input version mismatch")

    package_sha = package.canonical_sha256()
    view_sha = view.canonical_sha256()
    if view.package_sha256 != package_sha:
        raise ValueError("proposal evidence view does not reference the supplied package")
    if rendered.package_sha256 != package_sha or rendered.view_sha256 != view_sha:
        raise ValueError("rendered candidate input package/view lineage does not close")
    component_fields = {
        "observed_api_catalog_sha256": "observed_api_catalog",
        "observed_value_flow_set_sha256": "observed_value_flow_set",
        "dependency_graph_sha256": "dependency_graph",
        "binding_opportunity_set_sha256": "binding_opportunity_set",
    }
    for view_field, artifact_name in component_fields.items():
        expected = package.artifact_sha256[artifact_name]
        if getattr(view, view_field) != expected:
            raise ValueError(
                f"proposal evidence view component lineage mismatch: {artifact_name}"
            )
        declared = view.source_sha256.get(artifact_name)
        if declared is not None and declared != expected:
            raise ValueError(
                f"view source SHA-256 conflicts with component lineage: {artifact_name}"
            )
    for artifact_name, expected in package.artifact_sha256.items():
        declared = package.source_sha256.get(artifact_name)
        if declared is not None and declared != expected:
            raise ValueError(
                f"package source SHA-256 conflicts with component lineage: {artifact_name}"
            )
    if view.channel_availability != package.channel_availability:
        raise ValueError("proposal evidence view/package channel availability mismatch")
    if view.source_sha256.get("preproposal_evidence_package", package_sha) != package_sha:
        raise ValueError("view package source SHA-256 conflicts with canonical package")
    rendered_sources = {
        "preproposal_evidence_package": package_sha,
        "proposal_evidence_view": view_sha,
        "candidate_input_template": rendered.template_sha256,
    }
    for source_name, expected in rendered_sources.items():
        declared = rendered.source_sha256.get(source_name)
        if declared is not None and declared != expected:
            raise ValueError(
                f"rendered input source SHA-256 conflicts with lineage: {source_name}"
            )


def _regular_file(path: str | Path, label: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"{label} artifact does not exist") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} artifact is not a regular file")
    return resolved


def _resolve_rendered_ref(root: Path, raw_ref: str | None) -> Path:
    if not raw_ref:
        raise ValueError("v2 CandidateSet requires rendered_input_ref")
    ref = PurePosixPath(raw_ref)
    if (
        "\\" in raw_ref
        or ref.is_absolute()
        or PureWindowsPath(raw_ref).is_absolute()
        or bool(PureWindowsPath(raw_ref).drive)
        or ref.as_posix() != raw_ref
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError("rendered_input_ref must be a normalized relative POSIX path")
    try:
        resolved = (root / Path(*ref.parts)).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError("rendered_input_ref does not exist") from exc
    if not resolved.is_relative_to(root):
        raise ValueError("rendered_input_ref escapes the CandidateSet artifact root")
    if not resolved.is_file():
        raise ValueError("rendered_input_ref is not a regular file")
    return resolved
