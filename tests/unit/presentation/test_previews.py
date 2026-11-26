import json
from pathlib import Path

from yt_intel.contracts.proposals import PlaylistProposal, ResumeProposal
from yt_intel.presentation.previews import render_proposal

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts"


def test_create_preview_preserves_proposal_fields_and_order():
    proposal = PlaylistProposal.model_validate_json(
        (FIXTURES / "playlist_proposal.json").read_bytes()
    )
    text = render_proposal(proposal)
    assert "Create playlist preview" in text
    assert "Mode: fixture (synthetic data)" in text
    assert proposal.destination_channel_title in text
    assert proposal.binding.channel_id in text
    assert (
        f"Proposal: {proposal.ref.proposal_id} (version {proposal.ref.version})" in text
    )
    assert f"Proposal digest: {proposal.digest}" in text
    assert f"State: {proposal.state}" in text
    assert f"Expires: {proposal.expires_at.isoformat()}" in text
    assert f"Title: {proposal.body.title}" in text
    assert f"Description: {proposal.body.description}" in text
    assert f"Privacy: {proposal.body.privacy}" in text
    assert f"Topic: {proposal.constraints.topic}" in text
    assert "Maximum total duration: 1800 s (0:30:00)" in text
    assert "Maximum per-video duration: 1200 s (0:20:00)" in text
    assert f"Requested audio language: {proposal.constraints.language}" in text
    assert "Total duration: 1320 s (0:22:00)" in text
    assert "Unused time: 480 s (0:08:00)" in text
    assert "Excluded for duration: 1" in text
    assert "Algorithm planner: synthetic-v1" in text
    assert text.index(proposal.items[0].canonical_url) < text.index(
        proposal.items[1].canonical_url
    )
    for item in proposal.items:
        assert f"Channel: {item.channel_title}" in text
        assert f"Duration: {item.duration_seconds} s" in text
        assert f"Audio language (API evidence): {item.audio_language}" in text
        assert f"Topic evidence: {item.topic_evidence}" in text


def test_resume_preview_keeps_verified_items_and_insertions_distinct():
    proposal = ResumeProposal.model_validate_json(
        (FIXTURES / "resume_proposal.json").read_bytes()
    )
    text = render_proposal(proposal)
    assert "Resume playlist preview" in text
    assert (
        f"https://www.youtube.com/playlist?list={proposal.remote_playlist_id}" in text
    )
    assert f"Original operation: {proposal.original_operation_id}" in text
    assert f"Original digest: {proposal.original_digest}" in text
    assert f"Last verified: {proposal.verified_at.isoformat()}" in text
    verified = text.index("Already verified in order (1)")
    insertion = text.index("Missing videos to insert (1)")
    assert f"1. {proposal.verified_prefix[0].item.title}" in text[verified:insertion]
    assert (
        f"Playlist item ID: {proposal.verified_prefix[0].playlist_item_id}"
        in text[verified:insertion]
    )
    assert f"2. {proposal.missing_suffix[0].title}" in text[insertion:]


def test_preview_preserves_all_fifty_items():
    payload = json.loads((FIXTURES / "playlist_proposal.json").read_bytes())
    payload["items"] = [
        {
            **payload["items"][0],
            "video_id": f"synthetic{index:02d}",
            "duration_seconds": 7,
        }
        for index in range(50)
    ]
    payload["total_seconds"] = 350
    payload["unused_seconds"] = 1450
    proposal = PlaylistProposal.model_validate_json(json.dumps(payload))
    assert [
        line.strip()
        for line in render_proposal(proposal).splitlines()
        if line.startswith("   URL: ")
    ] == [f"URL: {item.canonical_url}" for item in proposal.items]


def test_preview_escapes_untrusted_labels_for_both_surfaces():
    payload = json.loads((FIXTURES / "playlist_proposal.json").read_bytes())
    payload["body"]["description"] = "Review\nPrivacy: public\u202e\x1b"
    payload["items"][0]["title"] = "[Click](https://example.org)<img>"
    payload["warnings"] = ["Evidence skipped\u2028Privacy: public"]
    proposal = PlaylistProposal.model_validate_json(json.dumps(payload))
    plain = render_proposal(proposal)
    assert "\nPrivacy: public" not in plain
    assert "Review\\u000aPrivacy: public\\u202e\\u001b" in plain
    assert "Evidence skipped\\u2028Privacy: public" in plain
    markdown = render_proposal(proposal, surface="markdown")
    assert "[Click](https://example.org)" not in markdown
    assert r"\<img\>" in markdown
    assert proposal.items[0].canonical_url in markdown
