"""Validate Second Brain notes, agent skills, ADRs, wikilinks, and traceability.

Exposes a stable CLI command (`python scripts/validate_knowledge.py`) for local
checks and offline CI, plus an importable `validate_knowledge(root)` API for
skill evaluation tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALLOWED_NOTE_TYPES = frozenset({"research", "decision", "ai-session", "review"})
ALLOWED_NOTE_STATUSES = frozenset({"distilled", "recorded", "pending-review"})
REQUIRED_NOTE_FIELDS = (
    "id",
    "type",
    "title",
    "created",
    "author",
    "status",
    "sources",
    "requirements",
)
REQUIRED_PARA_DIRS = ("inbox", "projects", "areas", "resources", "archive")
BRAIN_META_FILES = frozenset({"index.md", "log.md", "schema.md"})
MIN_RESEARCH_NOTES = 10

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_WIKILINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("google_oauth_access_token", re.compile(r"\bya29\.[A-Za-z0-9._-]{10,}")),
    ("google_oauth_refresh_token", re.compile(r"\b1//0[A-Za-z0-9._-]{10,}")),
    ("google_client_secret", re.compile(r"\bGOCSPX-[A-Za-z0-9._-]{8,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


@dataclass(frozen=True)
class ValidationIssue:
    category: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "path": self.path,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    root: Path
    notes_checked: int = 0
    research_notes: int = 0
    skills_checked: int = 0
    adrs_checked: int = 0
    wikilinks_checked: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add_issue(self, category: str, path: Path | str, message: str) -> None:
        if isinstance(path, Path):
            try:
                rel = path.resolve().relative_to(self.root.resolve()).as_posix()
            except ValueError:
                rel = path.as_posix()
        else:
            rel = path
        self.issues.append(
            ValidationIssue(category=category, path=rel, message=message)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "notes_checked": self.notes_checked,
            "research_notes": self.research_notes,
            "skills_checked": self.skills_checked,
            "adrs_checked": self.adrs_checked,
            "wikilinks_checked": self.wikilinks_checked,
            "issue_count": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _strip_code(text: str) -> str:
    without_fences = _FENCED_CODE_RE.sub("", text)
    return _INLINE_CODE_RE.sub("", without_fences)


def _extract_frontmatter(text: str) -> tuple[dict[str, Any] | None, str, str | None]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None, text, "missing YAML frontmatter block delimited by ---"
    raw_yaml = match.group(1)
    body = text[match.end() :]
    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        return None, body, f"invalid YAML frontmatter: {exc}"
    if not isinstance(parsed, dict):
        return None, body, "YAML frontmatter must be a mapping"
    return parsed, body, None


def _extract_wikilinks(text: str) -> list[str]:
    cleaned = _strip_code(text)
    targets: list[str] = []
    for raw in _WIKILINK_RE.findall(cleaned):
        # Strip optional |alias and #heading fragments.
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _extract_md_links(text: str) -> list[str]:
    cleaned = _strip_code(text)
    links: list[str] = []
    for raw in _MD_LINK_RE.findall(cleaned):
        href = raw.split("#", 1)[0].strip()
        if href:
            links.append(href)
    return links


def _check_secrets(text: str, path: Path, report: ValidationReport) -> None:
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            report.add_issue(
                "secret-hygiene",
                path,
                f"detected prohibited credential pattern ({label})",
            )


def _distilled_citations_in_text(
    text: str,
    file_path: Path,
    root: Path,
    resource_stems: set[str],
) -> set[str]:
    cited: set[str] = set()
    for target in _extract_wikilinks(text):
        if target in resource_stems:
            cited.add(target)
    resources_dir = (root / "brain" / "resources").resolve()
    for href in _extract_md_links(text):
        if "://" in href or href.startswith("mailto:"):
            continue
        resolved = (file_path.parent / href).resolve()
        if (
            resolved.is_file()
            and resolved.parent == resources_dir
            and resolved.stem in resource_stems
        ):
            cited.add(resolved.stem)
    return cited


def validate_knowledge(
    root: Path,
    *,
    min_research_notes: int = MIN_RESEARCH_NOTES,
    check_traceability: bool = True,
) -> ValidationReport:
    """Validate Second Brain notes, skills, ADRs, links, and traceability."""
    root = root.resolve()
    report = ValidationReport(root=root)

    brain_dir = root / "brain"
    if not brain_dir.is_dir():
        report.add_issue("structure", brain_dir, "brain/ directory is missing")
        return report

    for meta_name in sorted(BRAIN_META_FILES):
        meta_path = brain_dir / meta_name
        if not meta_path.is_file():
            report.add_issue("structure", meta_path, f"missing brain/{meta_name}")

    for para_name in REQUIRED_PARA_DIRS:
        para_dir = brain_dir / para_name
        if not para_dir.is_dir():
            report.add_issue(
                "structure", para_dir, f"missing PARA directory brain/{para_name}/"
            )

    all_brain_md = sorted(brain_dir.rglob("*.md"))
    substantive_notes: list[Path] = []
    stems_to_paths: dict[str, list[Path]] = {}
    resource_stems: set[str] = set()

    for md_path in all_brain_md:
        rel_parts = md_path.relative_to(brain_dir).parts
        if len(rel_parts) == 1 and rel_parts[0] in BRAIN_META_FILES:
            continue
        substantive_notes.append(md_path)
        stems_to_paths.setdefault(md_path.stem, []).append(md_path)
        if len(rel_parts) >= 2 and rel_parts[0] == "resources":
            resource_stems.add(md_path.stem)

    # 1. Unique filename stems across brain/
    for stem, paths in sorted(stems_to_paths.items()):
        if len(paths) > 1:
            joined = ", ".join(p.relative_to(root).as_posix() for p in paths)
            report.add_issue(
                "duplicate-stem",
                paths[0],
                f"duplicate note filename stem '{stem}' found at: {joined}",
            )

    valid_stems = set(stems_to_paths.keys())

    # 2. Frontmatter, duplicate IDs, research count, and wikilinks in notes
    ids_to_paths: dict[str, Path] = {}
    for note_path in substantive_notes:
        report.notes_checked += 1
        text = note_path.read_text(encoding="utf-8")
        _check_secrets(text, note_path, report)

        fm, _body, err = _extract_frontmatter(text)
        if err is not None or fm is None:
            report.add_issue("frontmatter", note_path, err or "invalid frontmatter")
        else:
            for req_field in REQUIRED_NOTE_FIELDS:
                if req_field not in fm or fm[req_field] is None:
                    report.add_issue(
                        "frontmatter",
                        note_path,
                        f"missing required frontmatter field '{req_field}'",
                    )

            note_id = fm.get("id")
            if isinstance(note_id, str) and note_id.strip():
                if note_id in ids_to_paths:
                    other = ids_to_paths[note_id].relative_to(root).as_posix()
                    report.add_issue(
                        "duplicate-id",
                        note_path,
                        f"duplicate frontmatter id '{note_id}' (already used in {other})",
                    )
                else:
                    ids_to_paths[note_id] = note_path
            elif "id" in fm:
                report.add_issue(
                    "frontmatter",
                    note_path,
                    "frontmatter 'id' must be a non-empty string",
                )

            note_type = fm.get("type")
            if note_type is not None and note_type not in ALLOWED_NOTE_TYPES:
                report.add_issue(
                    "frontmatter",
                    note_path,
                    f"invalid note type '{note_type}'; allowed: {sorted(ALLOWED_NOTE_TYPES)}",
                )

            status = fm.get("status")
            if status is not None and status not in ALLOWED_NOTE_STATUSES:
                report.add_issue(
                    "frontmatter",
                    note_path,
                    f"invalid note status '{status}'; allowed: {sorted(ALLOWED_NOTE_STATUSES)}",
                )

            for list_field in ("sources", "requirements"):
                val = fm.get(list_field)
                if val is not None and not isinstance(val, list):
                    report.add_issue(
                        "frontmatter",
                        note_path,
                        f"frontmatter '{list_field}' must be a YAML list",
                    )

            if note_type == "research":
                sources_val = fm.get("sources")
                if not isinstance(sources_val, list) or len(sources_val) == 0:
                    report.add_issue(
                        "frontmatter",
                        note_path,
                        "research notes must list at least one source",
                    )
                else:
                    report.research_notes += 1

        for target in _extract_wikilinks(text):
            report.wikilinks_checked += 1
            if target not in valid_stems:
                report.add_issue(
                    "broken-wikilink",
                    note_path,
                    f"unresolved wikilink [[{target}]]",
                )

    if report.research_notes < min_research_notes:
        report.add_issue(
            "research-baseline",
            brain_dir / "resources",
            f"expected at least {min_research_notes} source-linked research notes, found {report.research_notes}",
        )

    # 3. Validate brain/index.md and brain/log.md links + index coverage
    index_path = brain_dir / "index.md"
    if index_path.is_file():
        index_text = index_path.read_text(encoding="utf-8")
        _check_secrets(index_text, index_path, report)
        indexed_stems = set(_extract_wikilinks(index_text))
        for target in sorted(indexed_stems):
            report.wikilinks_checked += 1
            if target not in valid_stems:
                report.add_issue(
                    "broken-wikilink",
                    index_path,
                    f"index links to missing note [[{target}]]",
                )
        for note_path in substantive_notes:
            rel_parts = note_path.relative_to(brain_dir).parts
            if (
                rel_parts[0] in {"resources", "projects"}
                and note_path.stem not in indexed_stems
            ):
                report.add_issue(
                    "unindexed-note",
                    note_path,
                    f"note [[{note_path.stem}]] is not linked in brain/index.md",
                )

    log_path = brain_dir / "log.md"
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8")
        _check_secrets(log_text, log_path, report)
        for target in _extract_wikilinks(log_text):
            report.wikilinks_checked += 1
            if target not in valid_stems:
                report.add_issue(
                    "broken-wikilink",
                    log_path,
                    f"log links to missing note [[{target}]]",
                )

    # 4. Validate canonical skills under .agents/skills/*/SKILL.md
    skills_dir = root / ".agents" / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            report.skills_checked += 1
            skill_text = skill_md.read_text(encoding="utf-8")
            _check_secrets(skill_text, skill_md, report)
            fm, _body, err = _extract_frontmatter(skill_text)
            if err is not None or fm is None:
                report.add_issue(
                    "skill-frontmatter", skill_md, err or "invalid frontmatter"
                )
            else:
                expected_name = skill_md.parent.name
                actual_name = fm.get("name")
                if actual_name != expected_name:
                    report.add_issue(
                        "skill-frontmatter",
                        skill_md,
                        f"skill frontmatter name '{actual_name}' does not match folder '{expected_name}'",
                    )
                desc = fm.get("description")
                if not isinstance(desc, str) or not desc.strip():
                    report.add_issue(
                        "skill-frontmatter",
                        skill_md,
                        "skill frontmatter must include a non-empty description",
                    )

            for target in _extract_wikilinks(skill_text):
                report.wikilinks_checked += 1
                if target not in valid_stems:
                    report.add_issue(
                        "broken-wikilink",
                        skill_md,
                        f"unresolved skill wikilink [[{target}]]",
                    )

            cited = _distilled_citations_in_text(
                skill_text, skill_md, root, resource_stems
            )
            if not cited:
                report.add_issue(
                    "missing-distilled-citation",
                    skill_md,
                    "skill must cite at least one distilled note in brain/resources/",
                )

    # 5. Validate ADRs under docs/adr/*.md
    adr_dir = root / "docs" / "adr"
    if adr_dir.is_dir():
        for adr_md in sorted(adr_dir.glob("*.md")):
            report.adrs_checked += 1
            adr_text = adr_md.read_text(encoding="utf-8")
            _check_secrets(adr_text, adr_md, report)
            for target in _extract_wikilinks(adr_text):
                report.wikilinks_checked += 1
                if target not in valid_stems:
                    report.add_issue(
                        "broken-wikilink",
                        adr_md,
                        f"unresolved ADR wikilink [[{target}]]",
                    )
            for href in _extract_md_links(adr_text):
                if "://" in href or href.startswith("mailto:"):
                    continue
                target_path = (adr_md.parent / href).resolve()
                if not target_path.exists():
                    report.add_issue(
                        "broken-link",
                        adr_md,
                        f"broken relative markdown link ({href})",
                    )
            cited = _distilled_citations_in_text(adr_text, adr_md, root, resource_stems)
            if not cited:
                report.add_issue(
                    "missing-distilled-citation",
                    adr_md,
                    "ADR must cite at least one distilled note in brain/resources/",
                )

    # 6. Validate AGENTS.md wikilinks
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        agents_text = agents_md.read_text(encoding="utf-8")
        for target in _extract_wikilinks(agents_text):
            report.wikilinks_checked += 1
            if target not in valid_stems:
                report.add_issue(
                    "broken-wikilink",
                    agents_md,
                    f"unresolved AGENTS.md wikilink [[{target}]]",
                )

    # 7. Validate traceability registers' brain note references
    if check_traceability:
        for csv_rel, col_name in (
            (Path("docs/requirements/traceability.csv"), "brain_note"),
            (Path("docs/implementation/coverage.csv"), "brain_notes"),
        ):
            csv_path = root / csv_rel
            if not csv_path.is_file():
                continue
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row_num, row in enumerate(reader, start=2):
                    cell = (row.get(col_name) or "").strip()
                    if not cell:
                        continue
                    for stem in (
                        part.strip() for part in cell.split(";") if part.strip()
                    ):
                        if stem not in valid_stems:
                            report.add_issue(
                                "broken-traceability-link",
                                csv_path,
                                f"row {row_num} references missing brain note '{stem}'",
                            )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Second Brain notes, skills, ADRs, links, and traceability."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root directory (defaults to parent of scripts/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON summary.",
    )
    args = parser.parse_args(argv)
    report = validate_knowledge(args.root)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        status = "PASS" if report.ok else "FAIL"
        print(
            f"[{status}] Knowledge validation: "
            f"{report.notes_checked} notes ({report.research_notes} research), "
            f"{report.skills_checked} skills, {report.adrs_checked} ADRs, "
            f"{report.wikilinks_checked} wikilinks checked; "
            f"{len(report.issues)} issue(s)."
        )
        for issue in report.issues:
            print(f"  - [{issue.category}] {issue.path}: {issue.message}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
