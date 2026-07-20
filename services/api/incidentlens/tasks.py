from celery import Celery
from sqlalchemy.exc import OperationalError

from incidentlens.config import get_settings
from incidentlens.db import InvestigationStore, create_session_factory
from incidentlens.model_client import build_model_client
from incidentlens.observability import configure_tracer
from incidentlens.schemas import IncidentCase, WorkflowEvent
from incidentlens.workflow import InvestigationEngine

settings = get_settings()
configure_tracer("incidentlens-worker")
celery_app = Celery("incidentlens", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_time_limit=120,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="incidentlens.run_investigation",
    autoretry_for=(OperationalError,),
    retry_kwargs={"max_retries": 2},
)
def run_investigation(investigation_id: str, case_json: str, database_url: str) -> None:
    store = InvestigationStore(create_session_factory(database_url))
    if store.is_canceled(investigation_id):
        return
    case = IncidentCase.model_validate_json(case_json)
    engine = InvestigationEngine(
        model_client=build_model_client(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=settings.model_name,
            max_cost_cny=settings.max_cost_cny,
        )
    )

    class InvestigationCanceled(Exception):
        pass

    def persist(event: WorkflowEvent) -> None:
        if store.is_canceled(investigation_id):
            raise InvestigationCanceled
        store.append_event(investigation_id, event)

    try:
        result = engine.run(case, investigation_id=investigation_id, on_event=persist)
    except InvestigationCanceled:
        return
    store.save_result(investigation_id, result)
