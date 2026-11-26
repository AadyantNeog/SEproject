import asyncio
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_intel.approval import helper
from yt_intel.approval.grants import InMemoryGrantStore, InvalidGrant
from yt_intel.approval.native import NativeApprovalAdapter
from yt_intel.approval.service import (
    ApprovalRejected,
    ApprovalService,
    ApprovalUnavailable,
)
from yt_intel.contracts.approval import HumanDecision
from yt_intel.contracts.proposals import PlaylistProposal

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class Cancellation:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await asyncio.Future()


class FakeAdapter:
    def __init__(self, clock: FakeClock, decision: str = "approve") -> None:
        self.clock = clock
        self.decision = decision
        self.mutate = None
        self.fail = False

    async def request_decision(self, ctx, proposal, operation_id, challenge_ref):
        if self.fail:
            raise ApprovalUnavailable("helper failed")
        values = {
            "challenge_ref": challenge_ref,
            "response_ref": "response-fixture",
            "operation_id": operation_id,
            "proposal": proposal.ref,
            "proposal_digest": proposal.digest,
            "binding": proposal.binding,
            "decision": self.decision,
            "observed_at": self.clock.now(),
        }
        if self.mutate:
            self.mutate(values)
        return HumanDecision(**values)


def setup_approval(decision: str = "approve"):
    proposal = PlaylistProposal.model_validate_json(
        (FIXTURES / "playlist_proposal.json").read_bytes()
    )
    now = proposal.created_at + timedelta(minutes=1)
    clock = FakeClock(now)
    ctx = type("Context", (), {})()
    ctx.binding = proposal.binding
    ctx.deadline = proposal.expires_at
    ctx.cancellation = Cancellation()
    adapter = FakeAdapter(clock, decision)
    grants = InMemoryGrantStore()
    service = ApprovalService(adapter, grants, clock)
    return proposal, clock, ctx, adapter, grants, service


@pytest.mark.anyio
async def test_native_approval_grant_binds_exact_proposal_and_is_one_use():
    proposal, clock, ctx, _, grants, service = setup_approval()
    grant = await service.request_grant(ctx, proposal, "operation-fixture")

    consumed = service.consume(grant, proposal, "operation-fixture")
    assert consumed.consumed_at == clock.now()
    assert consumed.binding == proposal.binding
    assert consumed.proposal == proposal.ref
    assert consumed.proposal_digest == proposal.digest
    with pytest.raises(InvalidGrant):
        grants.consume(
            grant_id=grant.grant_id,
            operation_id="operation-fixture",
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=proposal.binding,
            now=clock.now(),
        )


@pytest.mark.anyio
async def test_rejection_and_dialog_close_never_issue_grant():
    proposal, _, ctx, _, grants, service = setup_approval("reject")
    with pytest.raises(ApprovalRejected):
        await service.request_grant(ctx, proposal, "operation-fixture")
    with pytest.raises(InvalidGrant):
        grants.consume(
            grant_id="missing",
            operation_id="operation-fixture",
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=proposal.binding,
            now=proposal.created_at,
        )


@pytest.mark.anyio
async def test_expired_proposal_and_expired_grant_are_rejected():
    proposal, clock, ctx, _, grants, service = setup_approval()
    grant = await service.request_grant(ctx, proposal, "operation-fixture")
    clock.value = grant.expires_at
    with pytest.raises(InvalidGrant):
        service.consume(grant, proposal, "operation-fixture")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda response: response.update(challenge_ref="forged-challenge"),
        lambda response: response.update(operation_id="other-operation"),
        lambda response: response.update(proposal_digest="0" * 64),
        lambda response: response.update(observed_at=datetime(2020, 1, 1, tzinfo=UTC)),
    ],
)
async def test_stale_or_forged_helper_responses_are_rejected(mutation):
    proposal, _, ctx, adapter, _, service = setup_approval()
    adapter.mutate = mutation
    with pytest.raises(ApprovalUnavailable):
        await service.request_grant(ctx, proposal, "operation-fixture")


@pytest.mark.anyio
async def test_helper_failure_fails_closed_without_a_grant():
    proposal, _, ctx, adapter, grants, service = setup_approval()
    adapter.fail = True
    with pytest.raises(ApprovalUnavailable):
        await service.request_grant(ctx, proposal, "operation-fixture")
    with pytest.raises(InvalidGrant):
        grants.consume(
            grant_id="missing",
            operation_id="operation-fixture",
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=proposal.binding,
            now=proposal.created_at,
        )


@pytest.mark.anyio
async def test_native_helper_launch_error_fails_closed(monkeypatch):
    async def fail_to_launch(*args, **kwargs):
        raise OSError("synthetic missing helper")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_to_launch)
    proposal, _, ctx, _, _, _ = setup_approval()
    adapter = NativeApprovalAdapter()
    with pytest.raises(ApprovalUnavailable, match="could not start"):
        await adapter.request_decision(ctx, proposal, "operation-fixture", "challenge")


def test_closing_native_dialog_returns_rejection(monkeypatch):
    class Widget:
        def __init__(self, *args, **kwargs):
            self.command = kwargs.get("command")

        def pack(self, *args, **kwargs):
            pass

        def insert(self, *args, **kwargs):
            pass

        def configure(self, *args, **kwargs):
            pass

        def yview(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    class Root(Widget):
        def title(self, *args):
            pass

        def geometry(self, *args):
            pass

        def minsize(self, *args):
            pass

        def protocol(self, _name, callback):
            self.close = callback

        def destroy(self):
            pass

        def mainloop(self):
            self.close()

    tk = types.ModuleType("tkinter")
    tk.BOTH = "both"
    tk.Button = Widget
    tk.Frame = Widget
    tk.Scrollbar = Widget
    tk.Text = Widget
    tk.Tk = Root
    ttk = types.ModuleType("tkinter.ttk")
    ttk.Label = Widget
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    proposal, *_ = setup_approval()
    request = {
        "challenge_ref": "challenge",
        "response_ref": "unused",
        "operation_id": "operation-fixture",
        "proposal": proposal.ref.model_dump(mode="json"),
        "proposal_digest": proposal.digest,
        "binding": proposal.binding.model_dump(mode="json"),
        "preview": "complete synthetic preview",
    }

    response = helper._decision_dialog(request)

    assert response["decision"] == "reject"
