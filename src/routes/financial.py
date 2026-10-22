import hashlib
import json
from flask import Blueprint, jsonify, request, Response
from sqlalchemy.exc import IntegrityError
from src import db
from src.models.financial_analysis import FinancialAnalysis, FinancialReview, now_iso
from src.services.financial_analysis import (
    InputError, analyze_fidc, analyze_cdb, canonical_hash, csv_receivables, object_fields, text,
)

financial_api = Blueprint('financial_api', __name__, url_prefix='/api/financial')


@financial_api.errorhandler(InputError)
def input_error(exc):
    return jsonify(message=str(exc)), 400


def events_for(analysis):
    return FinancialReview.query.filter_by(analysis_id=analysis.id).order_by(FinancialReview.revision).all()


def report(analysis):
    result = json.loads(json.dumps(analysis.result_payload))
    events = events_for(analysis)
    alerts = {alert['id']: alert for alert in result['alerts']}
    chain_ok, previous = True, analysis.result_sha256
    for position, row in enumerate(events, 1):
        event = row.event
        chain_ok = chain_ok and (row.event_sha256 == canonical_hash(event)) and event['previous_sha256'] == previous and row.revision == position
        previous = row.event_sha256
        if event['alert_id'] in alerts:
            alerts[event['alert_id']]['status'] = event['status']
        else:
            chain_ok = False
    return {'id': analysis.id, 'created_at': analysis.created_at, 'result': result,
            'revision': len(events), 'input_sha256': analysis.input_sha256,
            'result_sha256': analysis.result_sha256,
            'integrity': {'input_matches': canonical_hash(analysis.input_payload) == analysis.input_sha256,
                          'result_matches': canonical_hash(analysis.result_payload) == analysis.result_sha256,
                          'review_chain_matches': chain_ok},
            'reviews': [{'event': row.event, 'sha256': row.event_sha256} for row in events]}


def save_analysis(module, payload, result, artifact=None):
    envelope = {'request': payload, 'import': artifact}
    item = FinancialAnalysis(module=module, name=result['name'], input_payload=envelope,
                             result_payload=result, input_sha256=canonical_hash(envelope),
                             result_sha256=canonical_hash(result))
    db.session.add(item)
    db.session.commit()
    return jsonify(report(item)), 201


@financial_api.post('/fidc')
def fidc():
    payload = request.get_json()
    return save_analysis('fidc', payload, analyze_fidc(payload))


@financial_api.post('/fidc/import')
def fidc_import():
    uploaded = request.files.get('file')
    if uploaded is None:
        raise InputError('Envie o arquivo CSV no campo file')
    raw = uploaded.read(2_000_001)
    if len(raw) > 2_000_000:
        raise InputError('CSV excede 2 MB')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise InputError('CSV deve usar codificação UTF-8')
    payload = {'name': request.form.get('name'), 'as_of': request.form.get('as_of'),
               'source_ref': request.form.get('source_ref'), 'receivables': csv_receivables(content)}
    result = analyze_fidc(payload)
    return save_analysis('fidc', payload, result,
                         {'filename': uploaded.filename, 'file_sha256': hashlib.sha256(raw).hexdigest()})


@financial_api.post('/cdb')
def cdb():
    payload = request.get_json()
    return save_analysis('cdb', payload, analyze_cdb(payload))


@financial_api.get('/analyses')
def history():
    # Pagination avoids loading all portfolios and results into the history page.
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        raise InputError('page deve ser inteiro positivo')
    if page < 1:
        raise InputError('page deve ser inteiro positivo')
    query = FinancialAnalysis.query
    module = request.args.get('module')
    if module:
        if module not in ('fidc', 'cdb'):
            raise InputError('module deve ser fidc ou cdb')
        query = query.filter_by(module=module)
    result = query.order_by(FinancialAnalysis.created_at.desc(), FinancialAnalysis.id).paginate(page=page, per_page=20, error_out=False)
    return jsonify(items=[{'id': row.id, 'module': row.module, 'name': row.name, 'created_at': row.created_at,
                           'summary': row.result_payload['summary']} for row in result.items],
                   page=page, pages=result.pages, total=result.total)


@financial_api.get('/analyses/<string:identifier>')
def analysis_detail(identifier):
    return jsonify(report(db.get_or_404(FinancialAnalysis, identifier)))


@financial_api.get('/analyses/<string:identifier>/export')
def export(identifier):
    analysis = db.get_or_404(FinancialAnalysis, identifier)
    return Response(json.dumps({**report(analysis), 'input': analysis.input_payload}, ensure_ascii=False, indent=2),
                    mimetype='application/json', headers={'Content-Disposition': f'attachment; filename="regtech-{analysis.id}.json"'})


@financial_api.post('/analyses/<string:identifier>/reviews')
def review(identifier):
    analysis = db.get_or_404(FinancialAnalysis, identifier)
    payload = object_fields(request.get_json(), {'alert_id', 'status', 'reviewer', 'reason', 'evidence_ref', 'expected_revision'}, 'Revisão')
    alerts = {alert['id']: alert for alert in analysis.result_payload['alerts']}
    alert_id = text(payload.get('alert_id'), 'alert_id')
    if alert_id not in alerts:
        raise InputError('Alerta inexistente nesta análise')
    status = payload.get('status')
    if status not in ('open', 'in_review', 'resolved', 'dismissed'):
        raise InputError('status inválido')
    current = report(analysis)
    if not all(current['integrity'].values()):
        return jsonify(message='Falha na conferência de integridade; revisão bloqueada'), 409
    expected = payload.get('expected_revision')
    if type(expected) is not int or expected != current['revision']:
        return jsonify(message='Análise revisada por outra sessão. Recarregue antes de continuar'), 409
    old_status = next(a['status'] for a in current['result']['alerts'] if a['id'] == alert_id)
    if old_status == status:
        raise InputError('O alerta já está nesse status')
    previous = current['reviews'][-1]['sha256'] if current['reviews'] else analysis.result_sha256
    event = {'analysis_id': analysis.id, 'revision': expected + 1, 'alert_id': alert_id,
             'previous_status': old_status, 'status': status,
             'reviewer_declared': text(payload.get('reviewer'), 'reviewer'),
             'reason': text(payload.get('reason'), 'reason'),
             'evidence_ref': text(payload.get('evidence_ref'), 'evidence_ref'),
             'created_at': now_iso(), 'previous_sha256': previous}
    db.session.add(FinancialReview(analysis_id=analysis.id, revision=expected + 1,
                                  event=event, event_sha256=canonical_hash(event)))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(message='Conflito de revisão; recarregue a análise'), 409
    return jsonify(report(analysis)), 201
