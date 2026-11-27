"""P2-08 AT-06, AT-09 and AT-15 write and quota outcomes over MCP stdio.

Successful, rejected and partial creation with replay is already covered in
test_playlist_execution_stdio.py. Restart recovery is covered in
test_operation_replay.py. This module adds the ambiguous-timeout case and
the write-stage accounting checks.
"""

from collections import Counter
from pathlib import Path

import anyio
from write_launcher import WriteHarness, call, prepared

from yt_intel.infrastructure.database import Database


def test_ambiguous_timeout_is_unknown_never_retried_then_reconciled(
    tmp_path: Path,
) -> None:
    harness = WriteHarness(
        tmp_path, fail_at=0, fault="timeout_after_insert", decisions=["approve"]
    )

    async def run() -> None:
        async with harness.client() as client:
            flow = await prepared(client)
            args = flow["creation_args"]
            first = await call(client, "create_playlist", args)
            assert first.is_error
            assert first.structured_content["error"]["code"] == "OPERATION_UNKNOWN"
            data = first.structured_content["data"]
            assert data["state"] == "unknown"
            assert data["playlist_id"] is not None and data["confirmed_items"] == 0
            assert [item["outcome"] for item in data["pending_items"]] == ["unknown"]
            assert harness.writes() == [
                "/youtube/v3/playlists",
                "/youtube/v3/playlistItems",
            ]

            replay = await call(client, "create_playlist", args)
            assert replay.structured_content["data"] == data
            assert len(harness.writes()) == 2

            reconciled = await call(
                client, "reconcile_operation", {"operation_id": args["operation_id"]}
            )
            assert not reconciled.is_error, reconciled.content
            verified = reconciled.structured_content["data"]
            assert verified["state"] == "complete"
            assert verified["playlist_id"] == data["playlist_id"]
            assert [row["item"]["video_id"] for row in verified["verified_items"]] == [
                item["video_id"] for item in flow["proposal"]["items"]
            ]
            status = await call(
                client, "get_operation", {"operation_id": args["operation_id"]}
            )
            final = status.structured_content["data"]
            assert final["state"] == "completed"
            assert final["confirmed_items"] == 1
            assert final["confirmed_duration_seconds"] == sum(
                item["duration_seconds"] for item in flow["proposal"]["items"]
            )

    anyio.run(run)
    # Reconciliation reads; it never repeats the ambiguous write.
    assert len(harness.writes()) == 2
    assert [entry["decision"] for entry in harness.approvals()] == ["approve"]


def test_write_stage_uses_the_composed_reservation_and_one_attempt_per_write(
    tmp_path: Path,
) -> None:
    harness = WriteHarness(tmp_path, extra_candidates=2, decisions=["approve"])

    async def run() -> None:
        async with harness.client() as client:
            flow = await prepared(client, limit=3)
            result = await call(client, "create_playlist", flow["creation_args"])
            assert not result.is_error, result.content
            data = result.structured_content["data"]
            assert data["state"] == "completed"
            assert data["confirmed_items"] == len(flow["proposal"]["items"]) == 3

    anyio.run(run)
    endpoints = Counter(harness.attempts())
    assert endpoints["playlists.insert"] == 1
    assert endpoints["playlistItems.insert"] == 3
    assert len(harness.writes()) == 4
    with Database(harness.state).transaction(immediate=False) as connection:
        reservations = connection.execute(
            "SELECT reservation_id, released FROM quota_reservations"
        ).fetchall()
        assert len(reservations) == 1 and reservations[0]["released"] == 1
        ceilings = {
            row["endpoint"]: row["attempts_per_call"]
            for row in connection.execute(
                "SELECT endpoint, attempts_per_call FROM quota_endpoint_ceilings"
            )
        }
    assert ceilings["playlists.insert"] == ceilings["playlistItems.insert"] == 1
