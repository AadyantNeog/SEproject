from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from yt_intel.contracts.approval import (
    ApprovableProposal,
    ApprovalAdapter,
    HumanDecision,
)
from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.workflow import RequestContext
from yt_intel.presentation.previews import render_proposal

from .service import ApprovalUnavailable

_DECISION = TypeAdapter(HumanDecision)
_MAX_HELPER_OUTPUT = 64_000


class NativeApprovalAdapter(ApprovalAdapter):
    """Launch the bundled Tk dialog and accept only its private pipe response."""

    async def request_decision(
        self,
        ctx: RequestContext,
        proposal: ApprovableProposal,
        operation_id: OpaqueId,
        challenge_ref: OpaqueId,
    ) -> HumanDecision:
        payload = {
            "challenge_ref": challenge_ref,
            "operation_id": operation_id,
            "proposal": proposal.ref.model_dump(mode="json"),
            "proposal_digest": proposal.digest,
            "binding": proposal.binding.model_dump(mode="json"),
            "preview": render_proposal(proposal),
        }
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "yt_intel.approval.helper",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (OSError, ValueError) as error:
            raise ApprovalUnavailable(
                "native approval helper could not start"
            ) from error

        communication = asyncio.create_task(
            process.communicate(json.dumps(payload, separators=(",", ":")).encode())
        )
        cancellation = asyncio.create_task(ctx.cancellation.wait())
        timeout = max(0.0, (ctx.deadline - datetime.now(UTC)).total_seconds())
        try:
            done, _ = await asyncio.wait(
                (communication, cancellation),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if communication not in done:
                process.kill()
                await process.wait()
                communication.cancel()
                if cancellation in done:
                    raise ApprovalUnavailable("approval dialog was cancelled")
                raise ApprovalUnavailable("approval dialog expired")
            stdout, _ = await communication
            if process.returncode != 0 or len(stdout) > _MAX_HELPER_OUTPUT:
                raise ApprovalUnavailable("native approval helper failed")
            try:
                value = json.loads(stdout)
                decision = _DECISION.validate_python(value)
            except (
                json.JSONDecodeError,
                ValidationError,
                TypeError,
                ValueError,
            ) as error:
                raise ApprovalUnavailable(
                    "native approval helper returned invalid data"
                ) from error
            return decision
        finally:
            cancellation.cancel()
            if process.returncode is None:
                process.kill()
                await process.wait()
