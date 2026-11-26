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
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteProposalRepository

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


class FixtureProposalSource:
    def __init__(self, proposal):
        self.proposal = proposal

    async def get_current_proposal(self, binding, proposal_id, *, now):
        return self.proposal


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
    service = ApprovalService(adapter, grants, FixtureProposalSource(proposal), clock)
    return proposal, clock, ctx, adapter, grants, service


@pytest.mark.anyio
async def test_native_approval_grant_binds_exact_proposal_and_is_one_use():
    proposal, clock, ctx, _, grants, service = setup_approval()
    grant = await service.request_grant(ctx, proposal, "operation-fixture")

    consumed = await service.consume(grant, proposal, "operation-fixture")
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
async def test_revision_while_dialog_is_open_prevents_grant(tmp_path):
    proposal, clock, ctx, adapter, grants, _ = setup_approval()
    repository = SqliteProposalRepository(
        Database(tmp_path / "approval.sqlite3"), clock
    )
    await repository.save_proposal(proposal)
    dialog_open = asyncio.Event()
    dialog_closed = asyncio.Event()
    original_decision = adapter.request_decision

    async def delayed_decision(*args):
        dialog_open.set()
        await dialog_closed.wait()
        return await original_decision(*args)

    adapter.request_decision = delayed_decision
    service = ApprovalService(adapter, grants, repository, clock)
    request = asyncio.create_task(
        service.request_grant(ctx, proposal, "operation-fixture")
    )
    try:
        await asyncio.wait_for(dialog_open.wait(), timeout=5)
        revised = proposal.model_copy(
            update={
                "ref": proposal.ref.model_copy(
                    update={"version": proposal.ref.version + 1}
                ),
                "body": proposal.body.model_copy(
                    update={"title": "Revised fixture title"}
                ),
            }
        )
        await repository.save_proposal(
            revised.model_copy(update={"digest": proposal_digest(revised)})
        )
    finally:
        dialog_closed.set()
        with pytest.raises(ApprovalUnavailable, match="proposal changed"):
            await request


@pytest.mark.anyio
async def test_revision_after_grant_issuance_prevents_consumption(tmp_path):
    proposal, clock, ctx, adapter, grants, _ = setup_approval()
    repository = SqliteProposalRepository(
        Database(tmp_path / "approval.sqlite3"), clock
    )
    await repository.save_proposal(proposal)
    service = ApprovalService(adapter, grants, repository, clock)
    operation_id = "operation-fixture"
    grant = await service.request_grant(ctx, proposal, operation_id)

    revised = proposal.model_copy(
        update={
            "ref": proposal.ref.model_copy(
                update={"version": proposal.ref.version + 1}
            ),
            "body": proposal.body.model_copy(update={"title": "Revised fixture title"}),
        }
    )
    await repository.save_proposal(
        revised.model_copy(update={"digest": proposal_digest(revised)})
    )

    with pytest.raises(InvalidGrant, match="proposal changed"):
        await service.consume(grant, proposal, operation_id)


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
        await service.consume(grant, proposal, "operation-fixture")


@pytest.mark.anyio
async def test_grant_rejects_wrong_account_proposal_version_digest_or_operation():
    proposal, clock, ctx, _, grants, service = setup_approval()
    grant = await service.request_grant(ctx, proposal, "operation-fixture")
    other_binding = proposal.binding.model_copy(
        update={"credential_binding_id": "other-account"}
    )
    wrong_authorities = [
        ("other-operation", proposal.ref, proposal.digest, proposal.binding),
        (
            "operation-fixture",
            proposal.ref.model_copy(update={"version": proposal.ref.version + 1}),
            proposal.digest,
            proposal.binding,
        ),
        ("operation-fixture", proposal.ref, "0" * 64, proposal.binding),
        ("operation-fixture", proposal.ref, proposal.digest, other_binding),
    ]
    for operation, ref, digest, binding in wrong_authorities:
        with pytest.raises(InvalidGrant):
            grants.consume(
                grant_id=grant.grant_id,
                operation_id=operation,
                proposal=ref,
                proposal_digest=digest,
                binding=binding,
                now=clock.now(),
            )

    consumed = await service.consume(grant, proposal, "operation-fixture")
    assert consumed.consumed_at == clock.now()


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


@pytest.mark.parametrize("action", ["close", "reject"])
def test_dismissing_native_dialog_returns_rejection(monkeypatch, action):
    buttons = {}

    class Widget:
        def __init__(self, *args, **kwargs):
            self.command = kwargs.get("command")
            if self.command is not None:
                buttons[kwargs["text"]] = self.command

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
            if action == "close":
                self.close()
            else:
                buttons["Reject"]()

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
