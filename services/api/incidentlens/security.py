from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
]


def sanitize_untrusted_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1) if match.lastindex else ''}[REDACTED]",
            redacted,
        )
    return f"[UNTRUSTED_EVIDENCE]\n{redacted[:2000]}"


class ApprovalError(RuntimeError):
    pass


@dataclass
class RemediationProposal:
    id: str
    investigation_id: str
    action_type: str
    parameters: dict[str, Any]
    approved_by: str | None = None
    token: str | None = None
    executed: bool = False


@dataclass
class RemediationResult:
    proposal_id: str
    status: str
    simulated_change: dict[str, Any]


class SandboxRemediator:
    allowed_actions = {
        "rollback_virtual_version",
        "adjust_virtual_pool",
        "isolate_poison_message",
    }

    def __init__(self) -> None:
        self._proposals: dict[str, RemediationProposal] = {}

    def propose(
        self, investigation_id: str, action_type: str, parameters: dict[str, Any]
    ) -> RemediationProposal:
        if action_type not in self.allowed_actions:
            raise ValueError(f"Action {action_type!r} is not allowed")
        proposal = RemediationProposal(
            id=str(uuid4()),
            investigation_id=investigation_id,
            action_type=action_type,
            parameters=parameters,
        )
        self._proposals[proposal.id] = proposal
        return proposal

    def approve(self, proposal_id: str, *, actor: str) -> str:
        proposal = self._proposals[proposal_id]
        proposal.approved_by = actor
        proposal.token = secrets.token_urlsafe(24)
        return proposal.token

    def execute(self, proposal_id: str, *, approval_token: str) -> RemediationResult:
        proposal = self._proposals.get(proposal_id)
        if not proposal or not proposal.token or not secrets.compare_digest(
            proposal.token, approval_token
        ):
            raise ApprovalError("A valid approval token is required")
        if proposal.executed:
            raise ApprovalError("Approval token has already been used")
        proposal.executed = True
        return RemediationResult(
            proposal_id=proposal.id,
            status="simulated",
            simulated_change={"action": proposal.action_type, **proposal.parameters},
        )
