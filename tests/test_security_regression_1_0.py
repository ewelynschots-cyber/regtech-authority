"""Security regression tests for existing RegTech 1.0 endpoints.

All tests use isolated local data and mocked external integrations.
"""
import pytest
from unittest.mock import patch
from src import db
from src.app import create_app
from src.models.financial_analysis import FinancialAnalysis
from tests.access_helpers import provision, signed_client
from tests.test_access import fidc_payload


@pytest.fixture
def environment(tmp_path):
    app = create_app({
        "TESTING": True,
        "AUTH_COOKIE_SECURE": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "security.db"),
    })
    with app.app_context():
        db.create_all()
        provision(app, email="security-a@example.test")
        provision(app, email="security-b@example.test")
        yield app
        db.session.remove()


def test_scheduler_rejects_unauthenticated_request(environment):
    response = environment.test_client().post("/api/automation/run-due")
    assert response.status_code == 401


def test_scheduler_rejects_invalid_bearer(environment):
    response = environment.test_client().post(
        "/api/automation/run-due", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401


def test_scheduler_rejects_wrong_workflow_claim(environment):
    claims = {
        "sub": "repo:another-owner/another-repo:ref:refs/heads/main",
        "workflow_ref": "another-owner/another-repo/.github/workflows/rechecks.yml@refs/heads/main",
    }
    with patch("jwt.PyJWKClient") as jwks, patch("jwt.decode", return_value=claims):
        jwks.return_value.get_signing_key_from_jwt.return_value.key = "unused"
        response = environment.test_client().post(
            "/api/automation/run-due", headers={"Authorization": "Bearer synthetic"}
        )
    assert response.status_code == 403


def test_foreign_organization_cannot_export_analysis(environment):
    a = signed_client(environment, "security-a@example.test")
    b = signed_client(environment, "security-b@example.test")
    created = a.post("/api/financial/fidc", json=fidc_payload())
    assert created.status_code == 201
    identifier = created.json["id"]
    assert b.get(f"/api/financial/analyses/{identifier}/export").status_code == 404
    assert b.get(f"/api/financial/analyses/{identifier}/checklist.csv").status_code == 404


def test_tampered_analysis_is_detected_and_review_blocked(environment):
    a = signed_client(environment, "security-a@example.test")
    created = a.post("/api/financial/fidc", json=fidc_payload())
    assert created.status_code == 201
    identifier = created.json["id"]
    with environment.app_context():
        row = db.session.get(FinancialAnalysis, identifier)
        changed = dict(row.result_payload)
        changed["name"] = "ALTERADO SEM REHASH"
        row.result_payload = changed
        db.session.commit()
    detail = a.get(f"/api/financial/analyses/{identifier}")
    assert detail.status_code == 200
    assert detail.json["integrity"]["result_matches"] is False
    review = a.post(
        f"/api/financial/analyses/{identifier}/reviews",
        json={
            "alert_id": created.json["result"]["alerts"][0]["id"],
            "status": "in_review",
            "reason": "Revisao de integridade",
            "evidence_ref": "Registro ficticio",
            "expected_revision": 0,
        },
    )
    assert review.status_code == 409
