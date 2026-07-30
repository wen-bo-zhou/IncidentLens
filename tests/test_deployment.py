from pathlib import Path


def test_api_container_leaves_forwarded_client_parsing_to_the_application() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "services" / "api" / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "--no-proxy-headers" in dockerfile
