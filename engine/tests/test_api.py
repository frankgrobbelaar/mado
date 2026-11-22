"""The API's door: the health check, the token, this PC only, and the app's window alone."""

from fastapi.testclient import TestClient

from mado import __version__
from mado.api import create_app
from mado.config import DataPaths
from mado.migrations import MIGRATIONS
from tests.conftest import TOKEN


def test_health_reports_version_data_folder_and_schema(client: TestClient, paths: DataPaths):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "dataDir": str(paths.root),
        "schemaVersion": len(MIGRATIONS),
    }


def test_starting_makes_the_records_on_the_first_day(paths: DataPaths):
    assert not paths.database.exists()

    with TestClient(create_app(TOKEN, paths), base_url="http://127.0.0.1"):
        pass

    assert paths.database.is_file()


def test_requests_without_the_token_are_refused(client: TestClient):
    response = client.get("/health", headers={"Authorization": ""})

    assert response.status_code == 401


def test_requests_with_a_wrong_token_are_refused(client: TestClient):
    response = client.get("/health", headers={"Authorization": "Bearer guess"})

    assert response.status_code == 401


def test_requests_addressed_to_another_host_are_refused(paths: DataPaths):
    app = create_app(TOKEN, paths)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://mado.example", headers=headers) as client:
        response = client.get("/health")

    assert response.status_code == 400


def test_the_app_window_may_call_the_api(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_other_web_pages_may_not(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": "https://somewhere.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_the_app_window_may_read_how_long_a_preview_took(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://tauri.localhost"})

    assert "x-made-in" in response.headers["access-control-expose-headers"].lower()
