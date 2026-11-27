"""Seed an interrupted fixture playlist write for the manual native resume check.

The shipped fixture server never produces a partial result on its own. This
helper writes one into a fixture database so a person can reconcile and
resume it from an MCP client and observe the real native resume dialog.

It builds a two-item proposal from synthetic catalogue videos. It creates
the fixture playlist and inserts only the first item through the simulated
YouTube write endpoint. Then it records the operation as interrupted before
the second insert. It never touches live state, tokens or the network, and
it refuses any binding that is not in fixture mode. No approval is created:
resuming still needs a human decision in the native dialog.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from yt_intel.contracts.proposals import PlaylistProposal, ProposalItem
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database, default_database_path
from yt_intel.infrastructure.repositories import (
    OperationItem,
    SqliteOperationRepository,
    SqliteProposalRepository,
    WriteStep,
)
from yt_intel.providers.fixture_writes import FixturePlaylistWrites
from yt_intel.providers.youtube_writes import item_request, playlist_request

_TEMPLATE = Path("tests/fixtures/contracts/playlist_proposal.json")
# Both videos are in tests/fixtures/youtube_reads/catalog.json with en-US
# audio evidence, so resume revalidation can accept the missing one.
_ITEMS = (
    ("vidIndex001", "B-Tree Database Indexing Deep Dive", 1200),
    ("vidIndex005", "Index Maintenance Basics", 300),
)


@dataclass(frozen=True, slots=True)
class SeededOperation:
    operation_id: str
    proposal_id: str
    playlist_id: str
    database: Path


def _proposal(project_root: Path, now: datetime) -> PlaylistProposal:
    template = PlaylistProposal.model_validate_json(
        (project_root / _TEMPLATE).read_text(encoding="utf-8")
    )
    if template.binding.mode != "fixture":
        raise ValueError("The recovery demo only seeds fixture bindings.")
    items = tuple(
        ProposalItem(
            video_id=video_id,
            title=title,
            channel_title="Systems Study Lab",
            duration_seconds=seconds,
            audio_language="en-US",
            topic_evidence="topic-v1 matched: database, indexing.",
        )
        for video_id, title, seconds in _ITEMS
    )
    total = sum(seconds for _, _, seconds in _ITEMS)
    proposal = template.model_copy(
        update={
            "ref": template.ref.model_copy(
                update={"proposal_id": f"resume-demo-{uuid4().hex[:12]}", "version": 1}
            ),
            "body": template.body.model_copy(
                update={
                    "title": "Resume dialog demo",
                    "description": "Synthetic interrupted write for the resume check",
                }
            ),
            "items": items,
            "total_seconds": total,
            "unused_seconds": template.constraints.max_total_seconds - total,
            "exclusions": {},
            "candidate_set_id": "resume-demo",
            "created_at": now - timedelta(minutes=7),
            "expires_at": now - timedelta(minutes=1),
        }
    )
    return proposal.model_copy(update={"digest": proposal_digest(proposal)})


async def seed_interrupted_operation(
    database_path: Path, project_root: Path
) -> SeededOperation:
    """Record a fixture write that stopped after the first of two items."""
    if database_path.expanduser().resolve() == default_database_path("live").resolve():
        raise ValueError("Refusing to seed the live database.")
    database = Database(database_path)
    database.migrate()
    now = datetime.now(UTC)
    proposal = _proposal(project_root, now)
    await SqliteProposalRepository(database).save_proposal(proposal)
    operations = SqliteOperationRepository(database)
    operation_id = f"resume-demo-op-{uuid4().hex[:12]}"
    claimed = await operations.claim_operation(
        proposal.binding, operation_id, proposal.digest
    )
    writes = FixturePlaylistWrites(proposal.binding.channel_id, database=database)
    with httpx.Client(
        base_url="https://www.googleapis.com/youtube/v3/",
        transport=writes.transport(),
    ) as fixture:
        created = fixture.post("playlists", json=playlist_request(proposal.body))
        created.raise_for_status()
        playlist_id = str(created.json()["id"])
        first = fixture.post(
            "playlistItems",
            json=item_request(playlist_id, proposal.items[0].video_id, 0),
        )
        first.raise_for_status()
    steps = (
        WriteStep(
            endpoint="playlists.insert",
            planned_cost={},
            outcome="saved",
            remote_id=playlist_id,
        ),
        WriteStep(
            endpoint="playlistItems.insert",
            position=0,
            planned_cost={},
            outcome="saved",
            remote_id=str(first.json()["id"]),
        ),
        WriteStep(endpoint="playlistItems.insert", position=1, planned_cost={}),
    )
    await operations.update_operation(
        claimed.model_copy(
            update={
                "state": "creating",
                "updated_at": now - timedelta(minutes=6),
                "proposal_ref": proposal.ref,
                "playlist_id": playlist_id,
                "planned_items": tuple(
                    OperationItem(
                        video_id=item.video_id, duration_seconds=item.duration_seconds
                    )
                    for item in proposal.items
                ),
                "write_steps": steps,
            }
        )
    )
    return SeededOperation(
        operation_id=operation_id,
        proposal_id=proposal.ref.proposal_id,
        playlist_id=playlist_id,
        database=database_path,
    )


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed an interrupted fixture playlist write for the resume check."
    )
    parser.add_argument(
        "--fixture-db",
        type=Path,
        default=None,
        help="Fixture database the MCP server uses (default: the standard fixture path)",
    )
    args = parser.parse_args(argv)
    path = args.fixture_db or default_database_path("fixture")
    try:
        seeded = asyncio.run(seed_interrupted_operation(path, root))
    except (OSError, ValueError) as error:
        print(f"Could not seed the fixture database: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "mode": "fixture",
                "operation_id": seeded.operation_id,
                "playlist_id": seeded.playlist_id,
                "fixture_db": str(seeded.database),
                "state": "item 1 of 2 written, item 2 missing",
            },
            indent=2,
        )
    )
    print(
        "\nIn Codex, ask: Using yt-intel-fixture, reconcile operation "
        f"{seeded.operation_id}, show me the resume preview, and resume it if it "
        "is ready."
    )
    return 0
