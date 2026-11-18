import json
from pathlib import Path

from src import db
from src.app import create_app
from src.models.financial_analysis import FinancialAnalysis
from tests.access_helpers import provision, signed_client


def test_fiscal_dossier_workflow(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'dossier.db'}",
    })
    with app.app_context():
        db.create_all()
    provision(app)
    provision(app, email="other@example.test")
    analyst = signed_client(app)
    other = signed_client(app, email="other@example.test")
    example = Path(app.static_folder) / "examples" / "dossie-fiscal.json"
    payload = json.loads(example.read_text(encoding="utf-8"))
    endpoint = "/api/patrimonial/investigations"

    assert app.test_client().post(endpoint, json=payload).status_code == 401
    saved = analyst.post(endpoint, json=payload)
    assert saved.status_code == 201, saved.json
    result = saved.json["result"]
    assert [event["kind"] for event in result["events"]] == ["tax_assessment", "asset_transfer"]
    assert result["summary"]["alert_count"] == 1
    assert result["alerts"][0]["evidence"]["transfer"]["source_ids"] == ["F2"]

    assert {source["status"] for source in result["sources"]} == {"declared"}

    identifier = saved.json["id"]
    export = f"/api/financial/analyses/{identifier}/export"
    assert other.get(export).status_code == 404
    assert other.get(f"{endpoint}/{identifier}").status_code == 404
    assert other.get(endpoint).json["items"] == []
    assert analyst.get("/api/financial/analyses?module=assets").json["total"] == 1
    review_route = f"/api/financial/analyses/{identifier}/reviews"
    review = {
        "alert_id": result["alerts"][0]["id"],
        "status": "in_review",
        "reason": "Conferir matrícula e data do registro.",
        "evidence_ref": "F2",
        "expected_revision": 0,
    }
    assert other.post(review_route, json=review).status_code == 404
    assert analyst.post(review_route, json=review).status_code == 201
    assert analyst.post(review_route, json=review).status_code == 409
    exported = analyst.get(export).json
    assert exported["revision"] == 1
    assert exported["result"]["alerts"][0]["status"] == "in_review"
    assert exported["reviews"][0]["event"]["previous_sha256"] == exported["result_sha256"]
    assert exported["input"]["request"] == payload
    assert all(exported["integrity"].values())

    with app.app_context():
        row = db.session.get(FinancialAnalysis, identifier)
        row.result_payload = {**row.result_payload, "name": "alterado"}
        db.session.commit()
    assert analyst.get(export).json["integrity"]["result_matches"] is False

    assert analyst.post(review_route, json={**review, "expected_revision": 1}).status_code == 409

    payload["events"][0]["date"] = payload["events"][1]["date"]
    same_day = analyst.post(endpoint, json=payload)
    assert same_day.status_code == 201
    assert same_day.json["result"]["alerts"] == []

    payload["events"][0]["source_ids"] = ["ausente"]
    assert analyst.post(endpoint, json=payload).status_code == 400
