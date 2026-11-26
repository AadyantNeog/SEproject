"""Private stdin/stdout protocol and native Tk confirmation dialog."""

from __future__ import annotations

import json
import secrets
import sys
from datetime import UTC, datetime
from typing import Any


def _decision_dialog(request: dict[str, Any]) -> dict[str, Any]:
    from tkinter import BOTH, Button, Frame, Scrollbar, Text, Tk
    from tkinter.ttk import Label

    root = Tk()
    root.title("YouTube playlist approval")
    root.geometry("760x680")
    root.minsize(560, 420)
    Label(
        root,
        text="Review the complete proposal and account before choosing.",
        wraplength=720,
    ).pack(fill="x", padx=12, pady=10)
    account = request["binding"]
    Label(
        root,
        text=(
            f"Installation: {account['installation_id']}  |  "
            f"Account binding: {account['credential_binding_id']}  |  "
            f"Channel: {account['channel_id']}"
        ),
        wraplength=720,
    ).pack(fill="x", padx=12, pady=(0, 10))
    frame = Frame(root)
    frame.pack(fill=BOTH, expand=True, padx=12)
    scrollbar = Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    preview = Text(frame, wrap="word", yscrollcommand=scrollbar.set)
    preview.insert("1.0", request["preview"])
    preview.configure(state="disabled")
    preview.pack(side="left", fill=BOTH, expand=True)
    scrollbar.configure(command=preview.yview)
    result: list[str] = []

    def choose(value: str) -> None:
        result[:] = [value]
        root.destroy()

    controls = Frame(root)
    controls.pack(fill="x", padx=12, pady=12)
    Button(controls, text="Reject", command=lambda: choose("reject")).pack(
        side="right", padx=(8, 0)
    )
    Button(
        controls, text="Approve this exact proposal", command=lambda: choose("approve")
    ).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", lambda: choose("reject"))
    root.mainloop()
    return {
        "challenge_ref": request["challenge_ref"],
        "response_ref": secrets.token_urlsafe(32),
        "operation_id": request["operation_id"],
        "proposal": request["proposal"],
        "proposal_digest": request["proposal_digest"],
        "binding": request["binding"],
        "decision": result[0] if result else "reject",
        "observed_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("preview"), str):
            return 2
        response = _decision_dialog(request)
        sys.stdout.write(json.dumps(response, separators=(",", ":")))
        sys.stdout.flush()
        return 0
    except (EOFError, OSError, RuntimeError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
