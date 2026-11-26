# A2-06 Presentation handoff

[Issue #6](https://github.com/AadyantNeog/SEproject/issues/6) tracks this work. The renderers consume the common contracts and return display text. A2-04 constructs proposals, A2-05 routes tool output, and P2-03 owns the native approval control.

## Playlist previews for the native dialog

Pass the complete, validated `PlaylistProposal` or `ResumeProposal` from the service to `render_proposal`. Use the returned plain text in a read-only, scrollable control. Keep the full text available to the reviewer, including all 50 items for a full proposal. The native approval flow binds its decision to the original proposal digest and version.

The renderer keeps the creation proposal's stored total and unused time. Recovery shows the verified prefix and insert-only suffix with their final positions and exact item times. `ResumeProposal` carries per-item durations and full limits. The approval flow uses the source proposal and recovery checks for its authoritative total.

Run this example from the repository root to see both fixture previews:

```python
from pathlib import Path

from yt_intel.contracts.proposals import PlaylistProposal, ResumeProposal
from yt_intel.presentation.previews import render_proposal

fixtures = Path("tests/fixtures/contracts")
creation = PlaylistProposal.model_validate_json((fixtures / "playlist_proposal.json").read_bytes())
recovery = ResumeProposal.model_validate_json((fixtures / "resume_proposal.json").read_bytes())
print(render_proposal(creation))
print()
print(render_proposal(recovery))
```

Use `surface="markdown"` when a client renders text as Markdown. Use default plain text in a literal text control. Both renderings preserve the item order, identify fixture data and make control characters in display fields visible. Markdown rendering escapes formatting punctuation in those fields. The structured response should carry the original DTO.

## Ranked results, analytics, and errors

`render_ranked_results` presents the ranking in its supplied order, with project scores, versions, reasons, evidence gaps and coverage. `render_error` presents the stable code, retryability and safe next action.

`render_report` accepts ordered `ReportSection` values as a presentation adapter. J2-05 supplies the report's source populations, counts and denominators, deduplication rules, timestamp basis and explanations for unknown or undefined values. The renderer displays those supplied fields and optional coverage. The current evidence uses synthetic sections. The real J2-05 report adapter and A2-05 handler wiring are follow-up integration.

See [previews tests](../../tests/unit/presentation/test_previews.py) and [results and reports tests](../../tests/unit/presentation/test_results_and_reports.py) for the A2-06 fixture evidence. Full live acceptance and trusted native approval are separate workplan gates.
