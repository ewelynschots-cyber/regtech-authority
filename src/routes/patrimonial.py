"""API de inteligência patrimonial com segregação por organização."""
from flask import Blueprint, jsonify, request, abort
from src.access import scoped
from src.models.financial_analysis import FinancialAnalysis
from src.routes.financial import report, save_analysis
from src.services.patrimonial_intelligence import analyze_network

patrimonial_api = Blueprint("patrimonial_api", __name__, url_prefix="/api/patrimonial")

@patrimonial_api.post("/investigations")
def create_investigation():
    payload = request.get_json(silent=True)
    try:
        result = analyze_network(payload)
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    return save_analysis("assets", payload, result)


@patrimonial_api.get("/investigations")
def list_investigations():
    rows = scoped(FinancialAnalysis).filter_by(module="assets").order_by(FinancialAnalysis.created_at.desc()).limit(50).all()
    return jsonify(items=[{"id": x.id, "name": x.name, "created_at": x.created_at,
                           "summary": x.result_payload["summary"]} for x in rows])

@patrimonial_api.get("/investigations/<string:identifier>")
def get_investigation(identifier):
    item = scoped(FinancialAnalysis).filter_by(id=identifier, module="assets").first()
    if item is None:
        abort(404, "Investigação não encontrada")
    return jsonify(report(item))
