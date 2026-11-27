"""Repeatable evaluations for brain-ingest (SK-01), brain-refine (SK-02),
brain-query (SK-03), and scripts/validate_knowledge.py (GOV-01/02/05, SK-06).
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextResourceContents

from yt_intel.client_skills import canonical_skills

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_knowledge.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_knowledge", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_knowledge"] = module
    spec.loader.exec_module(module)
    return module


def _scaffold_vault(base: Path) -> Path:
    """Create a minimal valid PARA vault with one distilled note and one skill."""
    for sub in ("inbox", "projects/demo", "areas", "resources", "archive"):
        (base / "brain" / sub).mkdir(parents=True, exist_ok=True)
    (base / "brain" / "schema.md").write_text("# Schema\n", encoding="utf-8")
    (base / "brain" / "log.md").write_text("# Log\n\n- [[01-seed]]\n", encoding="utf-8")
    (base / "brain" / "index.md").write_text(
        "# Index\n\n- [[01-seed]]\n", encoding="utf-8"
    )
    (base / "brain" / "resources" / "01-seed.md").write_text(
        "---\n"
        'id: "RN-01"\n'
        'type: "research"\n'
        'title: "Seed finding"\n'
        'created: "2026-11-27"\n'
        'author: "Test"\n'
        'status: "distilled"\n'
        'sources: ["docs/requirements/SRS.md p. 1"]\n'
        'requirements: ["SK-01"]\n'
        "---\n\n"
        "# Seed finding\n",
        encoding="utf-8",
    )
    skill_dir = base / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: Demo skill for validation tests.\n"
        "---\n\n"
        "# Demo\n\n"
        "Distilled basis: [[01-seed]].\n",
        encoding="utf-8",
    )
    return base


def test_repository_knowledge_validator_passes_with_stage1_baseline() -> None:
    """Live repo check: >= 10 research notes, all skills/ADRs/links/traceability valid."""
    validator = _load_validator()
    report = validator.validate_knowledge(ROOT)
    assert report.ok, f"Unexpected knowledge validation issues: {report.issues}"
    assert report.research_notes >= 10
    assert report.skills_checked >= 4
    assert report.adrs_checked >= 9
    assert validator.main(["--root", str(ROOT)]) == 0

    skills = canonical_skills(ROOT)
    assert {"brain-ingest", "brain-refine", "brain-query"} <= set(skills.keys())


def test_sk01_brain_ingest_positive_negative_and_secret_hygiene(
    tmp_path: Path,
) -> None:
    """SK-01 evaluation: valid ingest passes; missing metadata, unindexed note, and secrets fail."""
    validator = _load_validator()
    vault = _scaffold_vault(tmp_path)

    # Positive: ingest a new source-linked research note and index it
    (vault / "brain" / "resources" / "02-ingested.md").write_text(
        "---\n"
        'id: "RN-02"\n'
        'type: "research"\n'
        'title: "Ingested note"\n'
        'created: "2026-11-27"\n'
        'author: "Antigravity (Gemini)"\n'
        'status: "distilled"\n'
        'sources: ["https://example.com/spec (accessed 27 November 2026)"]\n'
        'requirements: ["SK-01"]\n'
        "---\n\n"
        "Related: [[01-seed]].\n",
        encoding="utf-8",
    )
    (vault / "brain" / "index.md").write_text(
        "# Index\n\n- [[01-seed]]\n- [[02-ingested]]\n", encoding="utf-8"
    )
    ok_report = validator.validate_knowledge(
        vault, min_research_notes=2, check_traceability=False
    )
    assert ok_report.ok, ok_report.issues

    # Negative: unindexed note + missing sources + secret token pattern
    (vault / "brain" / "resources" / "03-bad.md").write_text(
        "---\n"
        'id: "RN-03"\n'
        'type: "research"\n'
        'title: "Bad note"\n'
        'created: "2026-11-27"\n'
        'author: "Antigravity (Gemini)"\n'
        'status: "distilled"\n'
        "sources: []\n"
        'requirements: ["SK-01"]\n'
        "---\n\n"
        "Leaked token ya29.a0AfH6SMB_example_secret_token_123456.\n",
        encoding="utf-8",
    )
    bad_report = validator.validate_knowledge(
        vault, min_research_notes=1, check_traceability=False
    )
    assert not bad_report.ok
    categories = {issue.category for issue in bad_report.issues}
    assert {"frontmatter", "unindexed-note", "secret-hygiene"} <= categories


def test_sk02_brain_refine_detects_and_verifies_duplicate_and_broken_link_fixes(
    tmp_path: Path,
) -> None:
    """SK-02 evaluation: duplicate stem/id and broken links are caught before refine and pass after."""
    validator = _load_validator()
    vault = _scaffold_vault(tmp_path)

    # Before refine: duplicate stem '01-seed' in projects/ with duplicate id + broken wikilink
    dup = vault / "brain" / "projects" / "demo" / "01-seed.md"
    dup.write_text(
        "---\n"
        'id: "RN-01"\n'
        'type: "research"\n'
        'title: "Duplicate seed"\n'
        'created: "2026-11-27"\n'
        'author: "Teammate"\n'
        'status: "distilled"\n'
        'sources: ["extra-source.pdf p. 4"]\n'
        'requirements: ["SK-02"]\n'
        "---\n\n"
        "Broken ref: [[nonexistent-note]].\n",
        encoding="utf-8",
    )
    before = validator.validate_knowledge(
        vault, min_research_notes=1, check_traceability=False
    )
    assert not before.ok
    before_cats = {issue.category for issue in before.issues}
    assert {"duplicate-stem", "duplicate-id", "broken-wikilink"} <= before_cats

    # After refine: merge into canonical note preserving both sources and authors, repair link
    dup.unlink()
    (vault / "brain" / "resources" / "01-seed.md").write_text(
        "---\n"
        'id: "RN-01"\n'
        'type: "research"\n'
        'title: "Seed finding"\n'
        'created: "2026-11-27"\n'
        'author: "Test; Teammate"\n'
        'status: "distilled"\n'
        'sources: ["docs/requirements/SRS.md p. 1", "extra-source.pdf p. 4"]\n'
        'requirements: ["SK-01", "SK-02"]\n'
        "---\n\n"
        "# Seed finding\n\n"
        "Merged duplicate note preserving both original sources and authors.\n",
        encoding="utf-8",
    )
    after = validator.validate_knowledge(
        vault, min_research_notes=1, check_traceability=False
    )
    assert after.ok, after.issues


def test_sk03_brain_query_traces_requirement_to_decision_and_detects_unsupported() -> (
    None
):
    """SK-03 evaluation: FR-5.5 traces to distilled note + ADR-0003; unsupported FR-99.9 returns empty."""
    trace_path = ROOT / "docs" / "requirements" / "traceability.csv"
    with trace_path.open("r", encoding="utf-8", newline="") as handle:
        rows = {row["requirement_id"]: row for row in csv.DictReader(handle)}

    # Positive requirement-to-decision trace: FR-5.5 -> 06-preview-and-human-approval -> ADR-0003
    assert "FR-5.5" in rows
    note_stems = [
        s.strip() for s in rows["FR-5.5"]["brain_note"].split(";") if s.strip()
    ]
    assert "06-preview-and-human-approval" in note_stems
    note_file = ROOT / "brain" / "resources" / "06-preview-and-human-approval.md"
    assert note_file.is_file()
    adr_file = ROOT / "docs" / "adr" / "0003-native-human-approval.md"
    assert adr_file.is_file()
    assert "06-preview-and-human-approval" in adr_file.read_text(encoding="utf-8")

    # Negative / unsupported requirement query: FR-99.9 must not exist anywhere in register
    assert "FR-99.9" not in rows


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_brain_skills_are_discoverable_as_mcp_resources() -> None:
    """All three J2-06 knowledge skills are exposed over fixture stdio MCP resources."""
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(ROOT),
        ],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            uris = {item.uri for item in (await client.list_resources()).resources}
            expected = {
                "yt-intel://skills/brain-ingest",
                "yt-intel://skills/brain-refine",
                "yt-intel://skills/brain-query",
            }
            assert expected <= uris
            for name in ("brain-ingest", "brain-refine", "brain-query"):
                res = (
                    await client.read_resource(f"yt-intel://skills/{name}")
                ).contents[0]
                assert isinstance(res, TextResourceContents)
                assert res.mime_type == "text/markdown"
                canonical = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                assert res.text == canonical
