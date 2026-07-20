import pytest
from incidentlens.state_machine import InvalidStateTransition, InvestigationStateMachine


def test_state_machine_accepts_the_bounded_happy_path() -> None:
    machine = InvestigationStateMachine()

    for state in [
        "collecting",
        "timeline_building",
        "hypothesizing",
        "verifying",
        "ranking",
        "reporting",
        "completed",
    ]:
        machine.transition(state)  # type: ignore[arg-type]

    assert machine.state == "completed"


def test_state_machine_rejects_skipping_verification() -> None:
    machine = InvestigationStateMachine("hypothesizing")

    with pytest.raises(InvalidStateTransition):
        machine.transition("ranking")
