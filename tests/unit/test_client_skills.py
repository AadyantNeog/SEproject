from hashlib import sha256
from pathlib import Path

import pytest

from yt_intel.client_skills import canonical_skills, project_file, sync_claude_skills


def test_sync_copies_only_canonical_skills_and_checks_exact_bytes(tmp_path: Path):
    source = tmp_path / ".agents/skills/brain-ingest/SKILL.md"
    source.parent.mkdir(parents=True)
    content = b"---\r\nname: brain-ingest\r\n---\r\n"
    source.write_bytes(content)
    other = tmp_path / ".agents/skills/unrelated/SKILL.md"
    other.parent.mkdir(parents=True)
    other.write_text("Unrelated", encoding="utf-8")
    expected = {"brain-ingest": sha256(content).hexdigest()}
    assert canonical_skills(tmp_path) == {"brain-ingest": content}
    with pytest.raises(ValueError, match="update brain-ingest"):
        sync_claude_skills(tmp_path, check=True)
    assert sync_claude_skills(tmp_path) == expected
    target = tmp_path / ".claude/skills/brain-ingest/SKILL.md"
    assert target.read_bytes() == content
    assert not (tmp_path / ".claude/skills/unrelated").exists()
    assert sync_claude_skills(tmp_path, check=True) == expected
    target.write_bytes(b"modified")
    with pytest.raises(ValueError, match="update brain-ingest"):
        sync_claude_skills(tmp_path, check=True)
    assert target.read_bytes() == b"modified"
    assert sync_claude_skills(tmp_path) == expected
    assert target.read_bytes() == content


def test_project_file_rejects_paths_outside_the_checkout(tmp_path: Path):
    with pytest.raises(ValueError, match="inside the checkout"):
        project_file(tmp_path, Path("..", "outside.txt"))
