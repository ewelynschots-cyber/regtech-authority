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

    identifier = saved.json["id"]
    export = f"/api/financial/analyses/{identifier}/export"
    assert other.get(export).status_code == 404
    assert other.get(f"{endpoint}/{identifier}").status_code == 404
    assert other.get(endpoint).json["items"] == []
    assert analyst.get("/api/financial/analyses?module=assets").json["total"] == 1
    exported = analyst.get(export).json
    assert exported["input"]["request"] == payload
    assert all(exported["integrity"].values())

    with app.app_context():
        row = db.session.get(FinancialAnalysis, identifier)
        row.result_payload = {**row.result_payload, "name": "alterado"}
        db.session.commit()
    assert analyst.get(export).json["integrity"]["result_matches"] is False

    payload["events"][0]["source_ids"] = ["ausente"]
    assert analyst.post(endpoint, json=payload).status_code == 400
