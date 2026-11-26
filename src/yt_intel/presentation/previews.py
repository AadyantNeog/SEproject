from yt_intel.contracts.approval import ApprovableProposal
from yt_intel.contracts.proposals import PlaylistProposal, ProposalItem, ResumeProposal

from .text import TextSurface, display_text, format_duration, mode_label, render_lines


def render_proposal(
    proposal: ApprovableProposal, *, surface: TextSurface = "plain"
) -> str:
    """Return the complete ordered preview for a validated, account-bound proposal."""
    action = "Create playlist" if proposal.purpose == "create" else "Resume playlist"
    constraints = proposal.constraints
    lines = [
        f"{action} preview",
        mode_label(proposal.binding.mode),
        f"Proposal: {display_text(proposal.ref.proposal_id, surface)} (version {proposal.ref.version})",
        f"Proposal digest: {proposal.digest}",
        f"State: {proposal.state}",
        f"Expires: {proposal.expires_at.isoformat()}",
        f"Destination: {display_text(proposal.destination_channel_title, surface)} "
        f"({display_text(proposal.binding.channel_id, surface)})",
        f"Title: {display_text(proposal.body.title, surface)}",
        f"Description: {display_text(proposal.body.description, surface) or '(empty)'}",
        f"Privacy: {proposal.body.privacy}",
        f"Topic: {display_text(constraints.topic, surface)}",
        f"Maximum total duration: {format_duration(constraints.max_total_seconds)}",
        f"Maximum per-video duration: {format_duration(constraints.max_video_seconds)}",
        f"Requested audio language: {constraints.language}",
    ]
    if isinstance(proposal, PlaylistProposal):
        lines.extend(_creation_details(proposal, surface))
    else:
        lines.extend(_resume_details(proposal, surface))
    if proposal.warnings:
        lines.extend(
            [
                "",
                "Warnings",
                *(f"- {display_text(w, surface)}" for w in proposal.warnings),
            ]
        )
    return render_lines(lines, surface)


def _creation_details(proposal: PlaylistProposal, surface: TextSurface) -> list[str]:
    lines = [
        f"Total duration: {format_duration(proposal.total_seconds)}",
        f"Unused time: {format_duration(proposal.unused_seconds)}",
        f"Candidate set: {display_text(proposal.candidate_set_id, surface)}",
    ]
    for algorithm, version in sorted(proposal.algorithm_versions.items()):
        lines.append(
            f"Algorithm {display_text(algorithm, surface)}: {display_text(version, surface)}"
        )
    for reason, count in sorted(proposal.exclusions.items()):
        lines.append(f"Excluded for {display_text(reason, surface)}: {count}")
    lines.extend(["", f"Videos in order ({len(proposal.items)})"])
    for position, item in enumerate(proposal.items, start=1):
        lines.extend(_render_item(position, item, surface))
    return lines


def _resume_details(proposal: ResumeProposal, surface: TextSurface) -> list[str]:
    lines = [
        f"Existing playlist: https://www.youtube.com/playlist?list={proposal.remote_playlist_id}",
        f"Original operation: {display_text(proposal.original_operation_id, surface)}",
        f"Original proposal: {display_text(proposal.original_proposal.proposal_id, surface)} "
        f"(version {proposal.original_proposal.version})",
        f"Original digest: {proposal.original_digest}",
        f"Last verified: {proposal.verified_at.isoformat()}",
        "This proposal inserts only the missing videos into the existing playlist.",
        "",
        f"Already verified in order ({len(proposal.verified_prefix)})",
    ]
    for position, entry in enumerate(proposal.verified_prefix, start=1):
        lines.extend(_render_item(position, entry.item, surface))
        lines.append(
            f"   Playlist item ID: {display_text(entry.playlist_item_id, surface)}"
        )
    lines.extend(["", f"Missing videos to insert ({len(proposal.missing_suffix)})"])
    for position, item in enumerate(
        proposal.missing_suffix, start=len(proposal.verified_prefix) + 1
    ):
        lines.extend(_render_item(position, item, surface))
    return lines


def _render_item(position: int, item: ProposalItem, surface: TextSurface) -> list[str]:
    return [
        f"{position}. {display_text(item.title, surface)}",
        f"   Channel: {display_text(item.channel_title, surface)}",
        f"   URL: {item.canonical_url}",
        f"   Duration: {format_duration(item.duration_seconds)}",
        f"   Audio language (API evidence): {item.audio_language}",
        f"   Topic evidence: {display_text(item.topic_evidence, surface)}",
    ]
