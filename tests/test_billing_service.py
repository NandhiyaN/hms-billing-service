from fastapi.testclient import TestClient
from billing_service import app

client = TestClient(app)


def auth(role: str):
    # Creates a simple bearer token matching the mock RBAC format.
    return {"Authorization": f"Bearer {role}_test"}


def test_health():
    # Verifies service health endpoint.
    response = client.get("/health")
    assert response.status_code == 200


def test_get_bills():
    # Verifies bill listing endpoint.
    response = client.get("/v1/bills", headers=auth("billing"))
    assert response.status_code == 200


def test_get_missing_bill():
    # Verifies unknown bill returns not found.
    response = client.get("/v1/bills/99999", headers=auth("billing"))
    assert response.status_code == 404


def test_forbidden_role():
    # Ensures doctor role cannot access billing list endpoint.
    response = client.get("/v1/bills", headers=auth("doctor"))
    assert response.status_code == 403