import io
import json
import urllib.error
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
from src import db
from src.app import create_app
from src.integrations.datajud import identify_process,lookup_process
from src.models.source_lookup import SourceLookup
from src.services.financial_analysis import InputError,canonical_hash

PROCESS='00008323520184013202'  # Number from the official CNJ documentation; tests mock all network calls.


def number_for(branch,region):
    rest=f'00000012024{branch}{region:02d}0001'
    checksum=98-int(rest+'00')%97
    return rest[:7]+str(checksum).zfill(2)+rest[7:]


def response_for(process=PROCESS,total=1,private=False):
    return json.dumps({'timed_out':False,'hits':{'total':{'value':total,'relation':'eq'},'hits':[
        {'_source':{'numeroProcesso':process,'tribunal':'TRF1','grau':'G1','nivelSigilo':1 if private else 0,
          'classe':{'codigo':1,'nome':'Classe de teste'},'orgaoJulgador':{'nome':'Órgão de teste'},
          'dataHoraUltimaAtualizacao':'2026-10-20T10:00:00Z','movimentos':[{'nome':'Movimento de teste','dataHora':'2026-10-20T09:00:00Z'}],
          'unexpected_personal_field':'must not be retained'}}]}}).encode()


@pytest.fixture
def client():
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','DATAJUD_API_KEY':'test-key-not-real'})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove();db.drop_all()


def mock_lookup(number,key):
    return lookup_process(number,key,transport=lambda *args:response_for(number))


def test_identify_official_example():
    process=identify_process(PROCESS)
    assert process['court']=='TRF1'
    assert identify_process(process['formatted'])['number']==PROCESS


@pytest.mark.parametrize('branch,region,court',[(8,13,'TJMG'),(8,26,'TJSP'),(8,7,'TJDFT'),(8,3,'TJAP'),(8,4,'TJAM'),(4,6,'TRF6'),(5,24,'TRT24')])
def test_inferred_courts(branch,region,court):
    assert identify_process(number_for(branch,region))['court']==court


@pytest.mark.parametrize('value',['1','0'*20,'A'+PROCESS[1:],None,123,'０'*20])
def test_bad_numbers(value):
    with pytest.raises(InputError):identify_process(value)


def test_lookup_uses_only_official_endpoint_and_public_fields():
    def transport(url,body,key):
        assert url=='https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search'
        assert body['query']['bool']['filter']==[{'term':{'nivelSigilo':0}}]
        assert 'partes' not in body['_source']
        return response_for()
    result=lookup_process(PROCESS,'test',transport)
    assert result['status']=='found'
    assert result['complete'] is True
    assert len(result['response_sha256'])==64
    assert 'unexpected_personal_field' not in result['records'][0]


def test_not_found_is_not_a_negative_certificate():
    raw=json.dumps({'hits':{'total':{'value':0,'relation':'eq'},'hits':[]}}).encode()
    assert lookup_process(PROCESS,'test',lambda *args:raw)['status']=='not_found'


def test_partial_response_is_explicit():
    result=lookup_process(PROCESS,'test',lambda *args:response_for(total=2))
    assert result['status']=='found'
    assert result['complete'] is False
    assert result['error_code']=='partial_response'


@pytest.mark.parametrize('error,code',[(urllib.error.HTTPError('x',403,'',{},None),'access_rejected'),
    (urllib.error.HTTPError('x',429,'',{},None),'rate_limited'),(TimeoutError(),'timeout'),
    (urllib.error.URLError('no route'),'connection_error')])
def test_external_failures_are_not_not_found(error,code):
    def transport(*args):raise error
    result=lookup_process(PROCESS,'test',transport)
    assert result['status']=='unavailable'
    assert result['error_code']==code


def test_private_or_mismatched_records_rejected():
    assert lookup_process(PROCESS,'test',lambda *args:response_for(private=True))['error_code']=='invalid_response'
    assert lookup_process(PROCESS,'test',lambda *args:response_for(process='0'*20))['error_code']=='invalid_response'


def test_not_configured_and_unsupported_courts_do_not_query():
    def transport(*args):raise AssertionError('Must not query')
    assert lookup_process(PROCESS,None,transport)['error_code']=='not_configured'
    assert lookup_process(number_for(1,0),'test',transport)['error_code']=='unsupported_court'


def test_lookup_persisted_cached_and_retrieved(client,monkeypatch):
    calls=[]
    def mocked(number,key):calls.append(number);return mock_lookup(number,key)
    monkeypatch.setattr('src.routes.automation.lookup_process',mocked)
    first=client.post('/api/automation/process',json={'process_number':PROCESS})
    assert first.status_code==201
    second=client.post('/api/automation/process',json={'process_number':PROCESS})
    assert second.status_code==200 and second.json['cache_used'] is True
    assert len(calls)==1
    assert client.get('/api/automation/process/'+first.json['id']).json['integrity_matches'] is True
    assert client.get('/api/automation/status').json['datajud']['configured'] is True
    assert 'test-key' not in client.get('/api/automation/status').text


def test_expired_snapshot_is_not_reused(client,monkeypatch):
    monkeypatch.setattr('src.routes.automation.lookup_process',mock_lookup)
    client.post('/api/automation/process',json={'process_number':PROCESS})
    with client.application.app_context():
        row=SourceLookup.query.one();row.checked_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat();db.session.commit()
    assert client.post('/api/automation/process',json={'process_number':PROCESS}).status_code==201


def test_lookup_linked_to_credit_with_divergence_and_no_confirmation_changes(client,monkeypatch):
    monkeypatch.setattr('src.routes.automation.lookup_process',mock_lookup)
    snapshot=client.post('/api/automation/process',json={'process_number':PROCESS}).json
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    payload['credits'][0].update(process_number=PROCESS,court='TJMG')
    payload['process_lookup_ids']=[snapshot['id']]
    created=client.post('/api/financial/credits',json=payload)
    assert created.status_code==201
    result=created.json['result']
    assert result['credits'][0]['holder_confirmed'] is None
    assert result['credits'][0]['paid_amount']=='10000.00'
    assert 'PROCESS_COURT_MISMATCH' in {a['code'] for a in result['alerts']}
    exported=client.get('/api/financial/analyses/'+created.json['id']+'/export').json
    query=exported['result']['process_queries'][0]
    assert canonical_hash(query['payload'])==query['payload_sha256']


def test_unrelated_lookup_not_accepted(client,monkeypatch):
    monkeypatch.setattr('src.routes.automation.lookup_process',mock_lookup)
    snapshot=client.post('/api/automation/process',json={'process_number':PROCESS}).json
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    payload['process_lookup_ids']=[snapshot['id']]
    assert client.post('/api/financial/credits',json=payload).status_code==400


def test_checklist_is_automatic_and_updates_with_review(client):
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    created=client.post('/api/financial/credits',json=payload).json
    assert created['diligence_checklist']
    identifier=created['id'];first=created['diligence_checklist'][0]['alert_id']
    before=len(created['diligence_checklist'])
    client.post('/api/financial/analyses/'+identifier+'/reviews',json={'alert_id':first,'status':'resolved',
        'reviewer':'Teste','reason':'Conferido','evidence_ref':'Doc','expected_revision':0})
    updated=client.get('/api/financial/analyses/'+identifier).json
    assert len(updated['diligence_checklist'])==before-1
    exported=client.get('/api/financial/analyses/'+identifier+'/checklist.csv')
    assert exported.status_code==200 and exported.data.startswith(b'\xef\xbb\xbf')
    assert first not in exported.text


def test_unavailable_lookup_keeps_diligence_pending(client,monkeypatch):
    monkeypatch.setattr('src.routes.automation.lookup_process',lambda number,key:lookup_process(number,None))
    snapshot=client.post('/api/automation/process',json={'process_number':PROCESS}).json
    assert snapshot['payload']['status']=='unavailable'
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    payload['credits'][0]['process_number']=PROCESS
    payload['process_lookup_ids']=[snapshot['id']]
    result=client.post('/api/financial/credits',json=payload).json['result']
    assert 'PUBLIC_PROCESS_CHECK_PENDING' in {a['code'] for a in result['alerts']}
    assert result['credits'][0]['holder_confirmed'] is None


def test_forged_snapshot_cannot_be_attached(client,monkeypatch):
    monkeypatch.setattr('src.routes.automation.lookup_process',mock_lookup)
    snapshot=client.post('/api/automation/process',json={'process_number':PROCESS}).json
    with client.application.app_context():
        row=db.session.get(SourceLookup,snapshot['id'])
        row.payload={**row.payload,'status':'not_found'};db.session.commit()
    assert client.get('/api/automation/process/'+snapshot['id']).json['integrity_matches'] is False
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    payload['credits'][0]['process_number']=PROCESS
    payload['process_lookup_ids']=[snapshot['id']]
    assert client.post('/api/financial/credits',json=payload).status_code==400
