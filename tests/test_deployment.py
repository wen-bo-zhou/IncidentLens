import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_container_leaves_forwarded_client_parsing_to_the_application() -> None:
    dockerfile = (ROOT / "services" / "api" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "--no-proxy-headers" in dockerfile


def test_runtime_containers_use_non_root_users() -> None:
    api_dockerfile = (ROOT / "services" / "api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    web_dockerfile = (ROOT / "apps" / "web" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "USER incidentlens" in api_dockerfile
    assert "USER node" in web_dockerfile


def test_compose_requires_database_secrets_and_protects_core_services() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD: incidentlens" not in compose
    assert "${POSTGRES_PASSWORD:?" in compose
    assert "restart: unless-stopped" in compose
    assert "resources:" in compose
    for service in ("worker", "web", "caddy"):
        match = re.search(
            rf"(?ms)^  {service}:\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", compose
        )
        assert match is not None
        service_block = match.group(1)
        assert "healthcheck:" in service_block


def test_backup_and_restore_automation_is_versioned() -> None:
    backup = ROOT / "scripts" / "backup-postgres.sh"
    restore = ROOT / "scripts" / "restore-postgres.sh"
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert backup.is_file()
    assert restore.is_file()
    backup_script = backup.read_text(encoding="utf-8")
    assert 'pg_restore --list "$temporary"' in backup_script
    assert 'rm -f "${temporary:-}"' in backup_script
    assert "postgres-backup:" in compose
    assert "BACKUP_RETENTION_DAYS" in compose
    assert "postgres-backups:" in compose
    backup_block = re.search(
        r"(?ms)^  postgres-backup:\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)",
        compose,
    )
    assert backup_block is not None
    assert "profiles:" not in backup_block.group(1)
