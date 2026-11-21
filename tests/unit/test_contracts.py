import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.models import LibrarySnapshot, Page, Video
from yt_intel.contracts.proposals import PlaylistProposal, ResumeProposal
from yt_intel.contracts.workflow import WorkflowPlan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def example(name):
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (Video, "video"),
        (LibrarySnapshot, "library_snapshot"),
        (PlaylistProposal, "playlist_proposal"),
        (ResumeProposal, "resume_proposal"),
        (ResultEnvelope[None], "error"),
    ],
)
def test_examples_survive_json_round_trip(model, name):
    parsed = model.model_validate_json(example(name))
    assert model.model_validate_json(parsed.model_dump_json()) == parsed
    assert model.model_json_schema()["type"] == "object"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("duration_seconds", True),
        ("duration_seconds", "720"),
        ("duration_seconds", 0),
        ("fetched_at", "2026-11-21T09:00:00"),
        ("external_url", "https://example.com/"),
        ("canonical_url", "https://example.com/"),
        ("default_audio_language", None),
    ],
)
def test_video_rejects_invalid_foreign_or_unsubstantiated_values(field, bad_value):
    payload = json.loads(example("video"))
    payload[field] = bad_value
    with pytest.raises(ValidationError):
        Video.model_validate_json(json.dumps(payload))


def test_snapshot_has_immutable_mappings_and_timezone_aware_fields():
    payload = json.loads(example("library_snapshot"))
    payload["fetched_at"] = "2026-11-21T14:30:00+05:30"
    snapshot = LibrarySnapshot.model_validate_json(json.dumps(payload))
    assert snapshot.fetched_at == datetime(2026, 11, 21, 9, tzinfo=UTC)
    assert snapshot.fetched_at.tzinfo is UTC
    assert snapshot.likes["fixture0001"] is None
    with pytest.raises(TypeError):
        snapshot.likes["fixture0001"] = datetime.now(UTC)
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.videos["fixture0001"].title = "Changed"


def test_page_tokens_are_internal():
    page = Page[str](
        items=("result",),
        next_page_token="private-token",
        api_reported_total=None,
        omitted=0,
        inaccessible=0,
    )
    assert page.next_page_token == "private-token"
    assert "private-token" not in repr(page)
    assert "next_page_token" not in page.model_dump()


def test_proposal_rejects_exact_fill_and_approval_arguments():
    payload = json.loads(example("playlist_proposal"))
    payload["constraints"]["duration_mode"] = "exact"
    payload["confirmed"] = True
    with pytest.raises(ValidationError) as failure:
        PlaylistProposal.model_validate_json(json.dumps(payload))
    assert {error["loc"] for error in failure.value.errors()} == {
        ("constraints", "duration_mode"),
        ("confirmed",),
    }


def test_proposal_checks_exact_seconds():
    payload = json.loads(example("playlist_proposal"))
    payload["items"][0]["duration_seconds"] = 1201
    with pytest.raises(ValidationError, match="individual duration limit"):
        PlaylistProposal.model_validate_json(json.dumps(payload))


def test_resume_rejects_duplicate_video_across_prefix_and_suffix():
    payload = json.loads(example("resume_proposal"))
    payload["missing_suffix"][0] = payload["verified_prefix"][0]["item"]
    with pytest.raises(ValidationError, match="unique video IDs"):
        ResumeProposal.model_validate_json(json.dumps(payload))


def test_workflow_rejects_repeated_write_attempts():
    plan = {
        "plan_id": "fixture-plan",
        "project_id": "fixture-project",
        "quota_profile_id": "profile",
        "binding": json.loads(example("library_snapshot"))["binding"],
        "endpoint_ceilings": {"playlists.insert": {"calls": 1, "attempts_per_call": 2}},
        "buckets": {"general": 100},
        "candidate_cap": 0,
        "page_cap": 0,
        "sample_cap": 0,
        "deadline": "2026-11-21T09:00:00Z",
        "cancellation_policy": "cooperative",
        "reconciliation_allowance": {},
    }
    with pytest.raises(ValidationError, match="exactly one attempt"):
        WorkflowPlan.model_validate_json(json.dumps(plan))
