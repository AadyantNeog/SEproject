"""The resume-demo seed produces a real resume path on the shipped fixture server.

The seeded operation is reconciled and resumed over MCP stdio. The scripted
approval seam in write_launcher.py stands in for the native dialog that a
person uses in the manual check.
"""

from pathlib import Path

import anyio
import pytest
from write_launcher import ROOT, WriteHarness, call

from yt_intel.fixture_recovery_demo import seed_interrupted_operation
from yt_intel.infrastructure.database import default_database_path


@pytest.mark.parametrize(
    ("decision", "state", "writes"),
    [("approve", "completed", ["/youtube/v3/playlistItems"]), ("reject", None, [])],
)
def test_seeded_operation_reconciles_to_a_resume_preview_and_resumes(
    tmp_path: Path, decision: str, state: str | None, writes: list[str]
) -> None:
    harness = WriteHarness(tmp_path, decisions=[decision])

    async def run() -> None:
        seeded = await seed_interrupted_operation(harness.state, ROOT)
        async with harness.client() as client:
            args = {"operation_id": seeded.operation_id}
            status = await call(client, "get_operation", args)
            pending = status.structured_content["data"]
            assert pending["playlist_id"] == seeded.playlist_id
            assert pending["confirmed_items"] == 1

            reconciled = await call(client, "reconcile_operation", args)
            assert not reconciled.is_error, reconciled.content
            data = reconciled.structured_content["data"]
            assert data["state"] == "resume_ready"
            assert [row["item"]["video_id"] for row in data["verified_items"]] == [
                "vidIndex001"
            ]
            preview = data["preview"]
            assert [item["video_id"] for item in preview["missing_suffix"]] == [
                "vidIndex005"
            ]

            result = await call(client, "resume_operation", {**args, **preview["ref"]})
            if decision == "approve":
                assert not result.is_error, result.content
                done = result.structured_content["data"]
                assert done["state"] == state
                assert done["confirmed_items"] == 2
                assert done["confirmed_duration_seconds"] == 1500
                assert done["pending_items"] == []
            else:
                assert result.is_error
                assert result.structured_content["error"]["code"] == (
                    "APPROVAL_REJECTED"
                )

    anyio.run(run)
    assert harness.writes() == writes
    assert [entry["decision"] for entry in harness.approvals()] == [decision]


def test_seed_refuses_the_live_database() -> None:
    with pytest.raises(ValueError, match="live"):
        anyio.run(seed_interrupted_operation, default_database_path("live"), ROOT)
