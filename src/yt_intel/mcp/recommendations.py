from pathlib import Path
from typing import Annotated
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import Label, LanguageTag, Limit, OpaqueId, Positive
from yt_intel.contracts.errors import ContractError, ErrorDetail, ResultEnvelope
from yt_intel.contracts.models import CandidateSet, LibrarySnapshot
from yt_intel.domain.language import normalize_language_tag
from yt_intel.presentation.results import render_error, render_ranked_results
from yt_intel.presentation.text import format_duration
from yt_intel.services.recommendations import (
    RecommendationFilters,
    RecommendationResult,
    RecommendationService,
)


class RecommendationInput(RecommendationFilters):
    snapshot_id: OpaqueId | None = None


def register_fixture_recommendations(
    server: MCPServer[None], project_root: Path
) -> None:
    fixture_root = Path("tests", "fixtures")
    snapshot_path = project_file(
        project_root, fixture_root / "contracts/library_snapshot.json"
    )
    candidates_path = project_file(
        project_root, fixture_root / "recommendations/candidates.json"
    )
    if not snapshot_path.is_file() or not candidates_path.is_file():
        return

    snapshot = LibrarySnapshot.model_validate_json(snapshot_path.read_bytes())
    candidates = CandidateSet.model_validate_json(candidates_path.read_bytes())
    if snapshot.binding.mode != "fixture" or candidates.binding != snapshot.binding:
        raise ValueError(
            "recommendation fixtures must share a synthetic account binding"
        )
    fixture_time = max(snapshot.fetched_at, candidates.created_at)
    service = RecommendationService(normalize_language_tag)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    def recommend_videos(
        ctx: Context[None, object],
        topic: Label | None = None,
        total_seconds: Positive | None = None,
        max_video_seconds: Positive | None = None,
        language: LanguageTag | None = None,
        limit: Limit = 10,
        snapshot_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[RecommendationResult]]:
        """Rank synthetic recommendations from the local fixture snapshot and candidates."""
        request_id = uuid4().hex
        # The signature advertises the flat MCP schema. Validate the original JSON
        # arguments before using values that the SDK might coerce.
        arguments = (ctx.request_context.params or {}).get("arguments", {})
        try:
            inputs = RecommendationInput.model_validate(arguments)
        except ValidationError:
            return _error_response(
                request_id,
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid recommendation parameters.",
                    retryable=False,
                    safe_next_action="Use the advertised filters and a limit from 1 to 50.",
                ),
            )
        if (
            inputs.snapshot_id is not None
            and inputs.snapshot_id != snapshot.snapshot_id
        ):
            return _error_response(
                request_id,
                ErrorDetail(
                    code="CONTENT_UNAVAILABLE",
                    message="The requested snapshot is unavailable in this fixture.",
                    retryable=False,
                    safe_next_action="Omit snapshot_id to use the default fixture snapshot.",
                ),
            )
        try:
            result = service.recommend(
                snapshot,
                candidates,
                binding=snapshot.binding,
                now=fixture_time,
                filters=inputs,
            )
        except ContractError as error:
            return _error_response(request_id, error.detail)
        return _recommendation_response(request_id, result)


def _error_response(request_id: str, problem: ErrorDetail) -> CallToolResult:
    envelope = ResultEnvelope[RecommendationResult](
        mode="fixture", request_id=request_id, status="error", data=None, error=problem
    )
    return CallToolResult(
        is_error=True,
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="fixture"))],
    )


def _recommendation_response(
    request_id: str, result: RecommendationResult
) -> CallToolResult:
    envelope = ResultEnvelope[RecommendationResult](
        mode="fixture",
        request_id=request_id,
        status="ok" if result.results else "empty",
        data=result,
        coverage=result.candidate_coverage,
        warnings=result.warnings,
    )
    text = render_ranked_results(
        result.results,
        mode="fixture",
        coverage=result.candidate_coverage,
        warnings=result.warnings,
    )
    sources = ", ".join(
        f"{name}: {source.state.replace('_', ' ')}"
        for name, source in result.sources.items()
    )
    lines = [text, f"Preference source states: {sources}."]
    if result.total_seconds is not None and result.unused_seconds is not None:
        lines.extend(
            [
                f"Total duration: {format_duration(result.total_seconds)}",
                f"Unused time: {format_duration(result.unused_seconds)}",
            ]
        )
    return CallToolResult(
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text="\n".join(lines))],
    )
