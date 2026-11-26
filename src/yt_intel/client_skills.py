from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

SKILL_NAMES = (
    "brain-ingest",
    "brain-refine",
    "brain-query",
    "local-check",
    "video-to-playlist",
)


def project_file(root: Path, relative: Path) -> Path:
    root = root.resolve()
    path = root / relative
    if not path.is_relative_to(root) or path.resolve() != path:
        raise ValueError(
            f"project path must stay inside the checkout without links: {relative}"
        )
    return path


def canonical_skills(root: Path) -> dict[str, bytes]:
    skills = {}
    for name in SKILL_NAMES:
        path = project_file(root, Path(".agents", "skills", name, "SKILL.md"))
        if path.is_file():
            skills[name] = path.read_bytes()
    return skills


def sync_claude_skills(root: Path, *, check: bool = False) -> dict[str, str]:
    """Copy the available canonical skills and verify their exact byte hashes."""
    expected = canonical_skills(root)
    targets = {
        name: project_file(root, Path(".claude", "skills", name, "SKILL.md"))
        for name in SKILL_NAMES
    }
    stale = [
        name for name in SKILL_NAMES if name not in expected and targets[name].exists()
    ]
    if stale:
        raise ValueError(
            f"generated skill exists without a canonical source: {', '.join(stale)}"
        )
    if not expected:
        raise ValueError("no canonical skills found in the selected checkout")
    hashes = {}
    for name, content in expected.items():
        target = targets[name]
        digest = sha256(content).hexdigest()
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != digest:
            if check:
                raise ValueError(f"run sync-claude-skills to update {name}")
            _replace_file(target, content)
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"generated skill failed byte verification: {name}")
        hashes[name] = digest
    return hashes


def _replace_file(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
