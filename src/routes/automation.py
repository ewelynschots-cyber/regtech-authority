import os
from datetime import datetime,timezone,timedelta
from flask import Blueprint,current_app,jsonify,request
from src import db
from src.integrations.datajud import identify_process,lookup_process
from src.models.source_lookup import SourceLookup
from src.services.financial_analysis import InputError,object_fields,canonical_hash

source_api=Blueprint('source_api',__name__,url_prefix='/api/automation')


@source_api.errorhandler(InputError)
def bad_input(exc):
    return jsonify(message=str(exc)),400


def lookup_report(row,cached=False):
    return {'id':row.id,'payload':row.payload,'payload_sha256':row.payload_sha256,
            'integrity_matches':canonical_hash(row.payload)==row.payload_sha256,'cache_used':cached}


@source_api.get('/status')
def status():
    return jsonify(datajud={'configured':bool(current_app.config.get('DATAJUD_API_KEY') or os.getenv('DATAJUD_API_KEY')),
                            'scope':'Metadados públicos; TJ estaduais, TRFs e TRTs',
                            'documentation':'https://datajud-wiki.cnj.jus.br/api-publica/'})


@source_api.post('/process')
def process_lookup():
    body=object_fields(request.get_json(),{'process_number'},'Consulta')
    process=identify_process(body.get('process_number'))
    latest=SourceLookup.query.filter_by(provider='datajud',process_number=process['number']).order_by(SourceLookup.checked_at.desc()).first()
    if latest:
        age=datetime.now(timezone.utc)-datetime.fromisoformat(latest.checked_at)
        ttl=timedelta(minutes=15) if latest.status in ('found','not_found') else timedelta(seconds=60)
        if age<ttl and canonical_hash(latest.payload)==latest.payload_sha256:
            return jsonify(lookup_report(latest,True))
    key=current_app.config.get('DATAJUD_API_KEY') or os.getenv('DATAJUD_API_KEY')
    payload=lookup_process(process['number'],key)
    row=SourceLookup(provider='datajud',process_number=process['number'],checked_at=payload['checked_at'],
                     status=payload['status'],payload=payload,payload_sha256=canonical_hash(payload))
    db.session.add(row)
    db.session.commit()
    return jsonify(lookup_report(row)),201


@source_api.get('/process/<string:identifier>')
def snapshot(identifier):
    return jsonify(lookup_report(db.get_or_404(SourceLookup,identifier)))


@source_api.post('/documents/extract')
def document_extract():
    from src.services.pdf_extraction import extract_pdf
    uploaded = request.files.get('file')
    if not uploaded:
        raise InputError('Selecione um PDF.')
    return jsonify(extract_pdf(uploaded.read(3_000_001)))


@source_api.post('/monitors')
def monitor_process():
    from src.models.process_monitor import ProcessMonitor
    body = object_fields(request.get_json(), {'process_number','enabled'}, 'Monitoramento')
    process = identify_process(body.get('process_number'))
    enabled = body.get('enabled', True)
    if type(enabled) is not bool:
        raise InputError('enabled deve ser booleano.')
    row = ProcessMonitor.query.filter_by(process_number=process['number']).first()
    if row is None:
        row = ProcessMonitor(process_number=process['number'], next_check=datetime.now(timezone.utc).isoformat())
        db.session.add(row)
    row.enabled = enabled
    db.session.commit()
    return jsonify(id=row.id, enabled=row.enabled, next_check=row.next_check),201


@source_api.get('/monitors')
def monitors():
    from src.models.process_monitor import ProcessMonitor
    return jsonify(items=[{'id':r.id,'process_number':r.process_number,'enabled':r.enabled,
                           'next_check':r.next_check,'last_lookup_id':r.last_lookup_id}
                          for r in ProcessMonitor.query.order_by(ProcessMonitor.next_check).limit(100)])


@source_api.post('/run-due')
def scheduled_rechecks():
    import jwt
    from src.services.rechecks import run_due
    authorization = request.headers.get('Authorization','')
    if not authorization.startswith('Bearer '):
        return jsonify(message='Credencial do agendador necessária.'),401
    token = authorization[7:]
    try:
        client = jwt.PyJWKClient('https://token.actions.githubusercontent.com/.well-known/jwks',timeout=5)
        claims = jwt.decode(token,client.get_signing_key_from_jwt(token).key,algorithms=['RS256'],
                            audience='https://plataforma-kyc1.onrender.com',issuer='https://token.actions.githubusercontent.com',
                            options={'require':['exp','iat','sub','workflow_ref']})
        if claims['sub'] != 'repo:ewelynschots-cyber/regtech-authority:ref:refs/heads/main' or claims['workflow_ref'] != 'ewelynschots-cyber/regtech-authority/.github/workflows/rechecks.yml@refs/heads/main':
            return jsonify(message='Agendador não autorizado.'),403
    except (jwt.PyJWTError, ValueError, OSError):
        return jsonify(message='Credencial do agendador inválida.'),401
    return jsonify(processed=run_due())
