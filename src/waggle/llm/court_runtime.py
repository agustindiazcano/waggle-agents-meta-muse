"""Wire the production client to the existing three-member unanimous court.

The caller must supply a round store; there is no silent in-memory default. Real
provider configuration and caps remain enforced by the shared client. This service
does not execute tools and does not claim a cross-family model composition: actual
model ids and any fallback labels remain in the recorded members and call log.
"""

import math
from collections.abc import Mapping, Sequence

from waggle.governance.court_contract import ReviewRequest
from waggle.governance.court_round import PreCheck, RoundResult, RoundStore, run_round
from waggle.llm.call_log import CallLog
from waggle.llm.client import LlmClient
from waggle.llm.client_factory import build_client
from waggle.llm.court_adapter import COURT_ROLES, CourtReviewer
from waggle.llm.providers import Provider


class CourtRuntime:
    """Three routed reviewers with unchanged deterministic checks and unanimity."""

    def __init__(self, client: LlmClient, log: CallLog, store: RoundStore) -> None:
        self._reviewer = CourtReviewer(client)
        self._log = log
        self._store = store

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        log: CallLog,
        store: RoundStore,
        *,
        fallbacks_enabled: bool,
        providers: Mapping[str, Provider] | None = None,
    ) -> "CourtRuntime":
        """Build the shared client without spending; mock overrides stay mock-only."""
        client = build_client(
            environ, log, fallbacks_enabled=fallbacks_enabled, providers=providers
        )
        return cls(client, log, store)

    def review(
        self,
        review: ReviewRequest,
        *,
        task_id: str,
        deadline_s: float,
        pre_checks: Sequence[PreCheck] = (),
    ) -> RoundResult:
        """Return a recorded proposal, denial or escalation, never a tool effect."""
        if not math.isfinite(deadline_s) or deadline_s <= 0:
            raise ValueError("deadline_s must be finite and positive")
        if not task_id or len(task_id) > 128:
            raise ValueError("invalid task id")
        return run_round(
            review,
            self._reviewer,
            COURT_ROLES,
            store=self._store,
            call_log=self._log,
            task_id=task_id,
            held_out=False,
            deadline_s=deadline_s,
            pre_checks=pre_checks,
        )
