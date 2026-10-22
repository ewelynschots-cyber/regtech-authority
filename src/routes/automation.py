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
