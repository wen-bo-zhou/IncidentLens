from typing import Literal

WorkflowState = Literal[
    "queued",
    "collecting",
    "timeline_building",
    "hypothesizing",
    "verifying",
    "ranking",
    "reporting",
    "awaiting_approval",
    "completed",
    "failed",
    "canceled",
    "inconclusive",
]

TERMINAL_STATES: set[WorkflowState] = {"completed", "failed", "canceled", "inconclusive"}

ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    "queued": {"collecting", "canceled", "failed", "inconclusive"},
    "collecting": {"timeline_building", "canceled", "failed", "inconclusive"},
    "timeline_building": {"hypothesizing", "canceled", "failed", "inconclusive"},
    "hypothesizing": {"verifying", "canceled", "failed", "inconclusive"},
    "verifying": {"ranking", "canceled", "failed", "inconclusive"},
    "ranking": {"reporting", "canceled", "failed", "inconclusive"},
    "reporting": {"awaiting_approval", "completed", "failed", "inconclusive"},
    "awaiting_approval": {"completed", "canceled", "failed"},
    "completed": set(),
    "failed": set(),
    "canceled": set(),
    "inconclusive": set(),
}


class InvalidStateTransition(ValueError):
    pass


class InvestigationStateMachine:
    def __init__(self, state: WorkflowState = "queued") -> None:
        self.state = state

    def transition(self, target: WorkflowState) -> WorkflowState:
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidStateTransition(f"Cannot transition from {self.state} to {target}")
        self.state = target
        return self.state
