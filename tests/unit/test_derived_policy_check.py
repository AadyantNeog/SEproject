"""The injected D-02 check: fixture always, live only with a reviewed record."""

import json
from pathlib import Path

import pytest

from yt_intel.contracts.common import AccountBinding
from yt_intel.domain.derived import fixture_only
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.policy import recorded_policy_check
from yt_intel.services.fixture_candidates import FixtureCandidateSets

LIVE = AccountBinding(
    installation_id="local-cli",
    credential_binding_id="live-test-binding",
    channel_id="UClivetest00000000000001",
    mode="live",
)
FIXTURE = LIVE.model_copy(update={"mode": "fixture"})


def _record(path: Path, **fields: object) -> Path:
    path.write_text(json.dumps(fields), "utf-8")
    return path


def test_default_check_allows_only_fixture_bindings() -> None:
    assert fixture_only(FIXTURE) is True
    assert fixture_only(LIVE) is False


@pytest.mark.parametrize(
    ("fields", "allowed"),
    [
        ({"state": "unresolved", "evidence_url": None, "recorded_by": None}, False),
        ({"state": "resolved", "evidence_url": None, "recorded_by": "A"}, False),
        (
            {"state": "resolved", "evidence_url": "http://x.edu", "recorded_by": "A"},
            False,
        ),
        (
            {"state": "resolved", "evidence_url": "https://x.edu", "recorded_by": " "},
            False,
        ),
        (
            {"state": "resolved", "evidence_url": "https://x.edu", "recorded_by": "A"},
            True,
        ),
    ],
)
def test_recorded_check_needs_a_complete_human_record(
    tmp_path: Path, fields: dict[str, object], allowed: bool
) -> None:
    permits = recorded_policy_check(_record(tmp_path / "d02.json", **fields))
    assert permits(LIVE) is allowed
    assert permits(FIXTURE) is True


def test_recorded_check_rereads_the_record_and_fails_closed(tmp_path: Path) -> None:
    path = _record(
        tmp_path / "d02.json",
        state="resolved",
        evidence_url="https://x.edu",
        recorded_by="A",
    )
    permits = recorded_policy_check(path)
    assert permits(LIVE) is True
    path.write_text("not json", "utf-8")
    assert permits(LIVE) is False
    path.unlink()
    assert permits(LIVE) is False


def test_services_keep_fixture_only_as_their_default() -> None:
    planner = PlaylistPlanner(normalize_language_tag)
    assert planner._permits is fixture_only
    sets = FixtureCandidateSets(lambda: None)  # type: ignore[arg-type, return-value]
    assert sets._permits is fixture_only
