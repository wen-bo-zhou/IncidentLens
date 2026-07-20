import pytest
from incidentlens.scenarios import ScenarioRepository
from incidentlens.schemas import IncidentCase
from pydantic import ValidationError


def test_repository_contains_three_showcase_and_twelve_hidden_cases() -> None:
    repository = ScenarioRepository.seeded()

    cases = repository.list_cases(include_hidden=True)

    assert len(cases) == 15
    assert sum(case.visibility == "showcase" for case in cases) == 3
    assert sum(case.visibility == "hidden" for case in cases) == 12
    assert {case.scenario_family for case in cases} == {
        "deployment_config",
        "db_pool_exhaustion",
        "poison_message",
    }
    assert [case.id for case in repository.list_cases()] == [
        "deploy-timeout-showcase",
        "db-pool-showcase",
        "poison-message-showcase",
    ]


def test_public_case_does_not_expose_ground_truth() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")

    public_case = case.to_public()

    assert "ground_truth" not in public_case.model_dump()
    assert public_case.evidence_count >= 4


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["evidence"][0].update(content_hash="0" * 64), "hash mismatch"),
        (lambda value: value.update(ends_at=value["starts_at"]), "earlier than"),
        (
            lambda value: value["ground_truth"]["required_evidence_ids"].append("missing:id"),
            "unknown evidence",
        ),
    ],
)
def test_incident_contract_rejects_tampered_packages(mutation: object, message: str) -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    payload = case.model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(ValidationError, match=message):
        IncidentCase.model_validate(payload)
