"""Whether derived processing (FR-1 to FR-5) may run for an account binding.

Derived processing is similarity, recommendations, analysis and planning. It
is always allowed on synthetic fixture bindings. For live bindings it depends
on D-02, which only a reviewed, human-recorded policy record can resolve
(see `yt_intel.policy`). Services take the check as a dependency so that the
domain stays pure and fixture-only remains the default.
"""

from collections.abc import Callable

from yt_intel.contracts.common import AccountBinding

type DerivedProcessingCheck = Callable[[AccountBinding], bool]


def fixture_only(binding: AccountBinding) -> bool:
    """The default: derived processing runs only on synthetic fixture bindings."""
    return binding.mode == "fixture"
