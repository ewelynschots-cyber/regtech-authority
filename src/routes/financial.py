import hashlib
import json
import csv
import io
import re
from flask import Blueprint, jsonify, request, Response, g
from sqlalchemy.exc import IntegrityError
from src import db
from src.access import scoped, owned, owner_values
from src.models.financial_analysis import FinancialAnalysis, FinancialReview, now_iso
from src.services.credit_analysis import analyze_credits
from src.models.source_lookup import SourceLookup
from src.integrations.datajud import identify_process
from src.services.financial_analysis import (
    InputError, analyze_fidc, analyze_cdb, canonical_hash, csv_receivables, object_fields, text, flag,
)

financial_api = Blueprint('financial_api', __name__, url_prefix='/api/financial')


@financial_api.errorhandler(InputError)
def input_error(exc):
    return jsonify(message=str(exc)), 400


def events_for(analysis):
    return FinancialReview.query.filter_by(analysis_id=analysis.id, organization_id=analysis.organization_id).order_by(FinancialReview.revision).all()


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
    checklist = [{'alert_id': a['id'], 'status': a['status'], 'task': a['message'],
                  'row': a.get('row'), 'evidence': a.get('evidence', {})}
                 for a in result['alerts'] if a['status'] in ('open', 'in_review')]
    return {'id': analysis.id, 'created_at': analysis.created_at, 'created_by_user_id': analysis.created_by_user_id, 'result': result, 'diligence_checklist': checklist,
            'revision': len(events), 'input_sha256': analysis.input_sha256,
            'result_sha256': analysis.result_sha256,
            'integrity': {'input_matches': canonical_hash(analysis.input_payload) == analysis.input_sha256,
                          'result_matches': canonical_hash(analysis.result_payload) == analysis.result_sha256,
                          'review_chain_matches': chain_ok},
            'reviews': [{'event': row.event, 'sha256': row.event_sha256} for row in events]}


def save_analysis(module, payload, result, artifact=None):
    envelope = {'request': payload, 'import': artifact, 'created_by_user_id': g.user.id, 'organization_id': g.user.organization_id}
    item = FinancialAnalysis(**owner_values(), created_by_user_id=g.user.id, module=module, name=result['name'], input_payload=envelope,
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


def save_credit_analysis(payload, artifact=None):
    result = analyze_credits(payload)
    linked = result['linked_fidc_analysis_id']
    if linked:
        portfolio = owned(FinancialAnalysis, linked)
        if portfolio.module != 'fidc':
            raise InputError('A análise vinculada deve pertencer ao módulo FIDC')
    result['process_queries'] = []
    for identifier in result['process_lookup_ids']:
        snapshot = owned(SourceLookup, identifier)
        if canonical_hash(snapshot.payload) != snapshot.payload_sha256:
            raise InputError('Consulta com divergência de integridade')
        lookup = snapshot.payload
        matching = []
        for credit in result['credits']:
            try:
                number = identify_process(credit.get('process_number'))['number']
            except InputError:
                continue
            if number == lookup['process']['number']:
                matching.append(credit)
        if not matching:
            raise InputError('Consulta vinculada não corresponde aos processos da carteira')
        result['process_queries'].append({'id': snapshot.id, 'payload': lookup, 'payload_sha256': snapshot.payload_sha256})
        if lookup.get('source_url'):
            result['sources'].append(lookup['source_url'])
        for credit in matching:
            evidence = {'lookup_id': snapshot.id, 'process_number': lookup['process']['number'], 'checked_at': lookup['checked_at']}
            if lookup['status'] != 'found' or not lookup['complete']:
                flag(result['alerts'], 'PUBLIC_PROCESS_CHECK_PENDING',
                     'Consulta pública indisponível, incompleta ou sem correspondência; conferir a fonte', row=credit['row'],
                     evidence={**evidence, 'status': lookup['status'], 'error_code': lookup.get('error_code')})
            court = (credit.get('court') or '').upper().strip()
            if re.fullmatch(r'(TJ[A-Z]{2,3}|TRF[1-6]|TRT[0-9]{1,2})', court) and court != lookup['process']['court']:
                flag(result['alerts'], 'PROCESS_COURT_MISMATCH', 'Tribunal declarado diverge da numeração CNJ',
                     row=credit['row'], evidence={**evidence, 'declared_court': court, 'inferred_court': lookup['process']['court']})
    result['sources'] = sorted(set(result['sources']))
    result['summary']['alert_count'] = len(result['alerts'])
    return save_analysis('credits', payload, result, artifact)


@financial_api.post('/credits')
def credit_rights():
    return save_credit_analysis(request.get_json())


@financial_api.post('/credits/import')
def credit_import():
    uploaded = request.files.get('file')
    if uploaded is None:
        raise InputError('Envie o arquivo JSON no campo file')
    raw = uploaded.read(2_000_001)
    if len(raw) > 2_000_000:
        raise InputError('Arquivo excede 2 MB')
    try:
        payload = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise InputError('Arquivo JSON inválido; utilize UTF-8')
    return save_credit_analysis(payload, {'filename': uploaded.filename,
                                         'file_sha256': hashlib.sha256(raw).hexdigest()})


@financial_api.get('/analyses')
def history():
    # Pagination avoids loading all portfolios and results into the history page.
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        raise InputError('page deve ser inteiro positivo')
    if page < 1:
        raise InputError('page deve ser inteiro positivo')
    query = scoped(FinancialAnalysis)
    module = request.args.get('module')
    if module:
        if module not in ('fidc', 'cdb', 'credits'):
            raise InputError('module deve ser fidc, cdb ou credits')
        query = query.filter_by(module=module)
    result = query.order_by(FinancialAnalysis.created_at.desc(), FinancialAnalysis.id).paginate(page=page, per_page=20, error_out=False)
    return jsonify(items=[{'id': row.id, 'module': row.module, 'name': row.name, 'created_at': row.created_at,
                           'summary': row.result_payload['summary']} for row in result.items],
                   page=page, pages=result.pages, total=result.total)


@financial_api.get('/analyses/<string:identifier>')
def analysis_detail(identifier):
    return jsonify(report(owned(FinancialAnalysis, identifier)))


@financial_api.get('/analyses/<string:identifier>/export')
def export(identifier):
    analysis = owned(FinancialAnalysis, identifier)
    return Response(json.dumps({**report(analysis), 'input': analysis.input_payload}, ensure_ascii=False, indent=2),
                    mimetype='application/json', headers={'Content-Disposition': f'attachment; filename="regtech-{analysis.id}.json"'})


@financial_api.get('/analyses/<string:identifier>/checklist.csv')
def checklist_export(identifier):
    data = report(owned(FinancialAnalysis, identifier))
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=';')
    writer.writerow(['Alerta', 'Status', 'Tarefa de diligência', 'Linha', 'Evidência'])
    def safe_cell(value):
        value = str(value if value is not None else '')
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    for task in data['diligence_checklist']:
        writer.writerow([safe_cell(task['alert_id']), safe_cell(task['status']), safe_cell(task['task']),
                         safe_cell(task['row']), safe_cell(json.dumps(task['evidence'], ensure_ascii=False))])
    return Response('\ufeff' + stream.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="pendencias-{identifier}.csv"'})


@financial_api.post('/analyses/<string:identifier>/reviews')
def review(identifier):
    analysis = owned(FinancialAnalysis, identifier)
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
             'reviewer_declared': g.user.name, 'reviewer_id': g.user.id,
             'organization_id': g.user.organization_id,
             'reason': text(payload.get('reason'), 'reason'),
             'evidence_ref': text(payload.get('evidence_ref'), 'evidence_ref'),
             'created_at': now_iso(), 'previous_sha256': previous}
    db.session.add(FinancialReview(**owner_values(), analysis_id=analysis.id, revision=expected + 1,
                                  event=event, event_sha256=canonical_hash(event)))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(message='Conflito de revisão; recarregue a análise'), 409
    return jsonify(report(analysis)), 201
