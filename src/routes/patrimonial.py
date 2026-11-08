"""API de inteligência patrimonial com segregação por organização."""
from flask import Blueprint, jsonify, request, g
from src import db
from src.access import scoped, owned, owner_values
from src.models.financial_analysis import FinancialAnalysis
from src.services.financial_analysis import canonical_hash
from src.services.patrimonial_intelligence import analyze_network

patrimonial_api = Blueprint("patrimonial_api", __name__, url_prefix="/api/patrimonial")

@patrimonial_api.post("/investigations")
def create_investigation():
    payload = request.get_json(silent=True)
    try:
        result = analyze_network(payload)
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    envelope = {"request": payload, "organization_id": g.user.organization_id, "created_by_user_id": g.user.id}
    item = FinancialAnalysis(**owner_values(), created_by_user_id=g.user.id,
                             module="assets", name=result["name"],
                             input_payload=envelope, result_payload=result,
                             input_sha256=canonical_hash(envelope), result_sha256=canonical_hash(result))
    db.session.add(item)
    db.session.commit()
    return jsonify(id=item.id, result=result, integrity={"input_sha256": item.input_sha256,
                   "result_sha256": item.result_sha256}), 201

@patrimonial_api.get("/investigations")
def list_investigations():
    rows = scoped(FinancialAnalysis).filter_by(module="assets").order_by(FinancialAnalysis.created_at.desc()).limit(50).all()
    return jsonify(items=[{"id": x.id, "name": x.name, "created_at": x.created_at,
                           "summary": x.result_payload["summary"]} for x in rows])

@patrimonial_api.get("/investigations/<string:identifier>")
def get_investigation(identifier):
    item = owned(FinancialAnalysis, identifier)
    if item.module != "assets":
        return jsonify(message="Investigação não encontrada"), 404
    return jsonify(id=item.id, result=item.result_payload, integrity={
        "input_matches": canonical_hash(item.input_payload) == item.input_sha256,
        "result_matches": canonical_hash(item.result_payload) == item.result_sha256})
