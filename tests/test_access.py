import copy
import json
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import text
from src import db
from src.app import create_app
from src.models import User
from src.models.access import AccessSession
from src.models.financial_analysis import FinancialAnalysis
from tests.access_helpers import provision, signed_client, PASSWORD
from tests.test_automation import PROCESS, mock_lookup


@pytest.fixture
def secured(tmp_path):
    app = create_app({'TESTING': True, 'AUTH_COOKIE_SECURE': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'access.db')})
    with app.app_context():
        db.create_all()
        admin_a, org_a = provision(app, email='a@example.test')
        admin_b, org_b = provision(app, email='b@example.test')
        yield app, org_a, org_b, admin_a, admin_b
        db.session.remove()


def fidc_payload():
    return {'name':'Fictício', 'as_of':'2026-10-20', 'source_ref':'Fonte fictícia',
            'receivables':[{'title_id':'T1','originator_id':'O1','debtor_id':'D1','amount':'100.00'}]}


def create_analysis(client, module='fidc'):
    if module == 'fidc':
        payload = fidc_payload()
    else:
        payload = json.loads(Path('src/static/examples/'+('cdb' if module=='cdb' else 'credits')+'.json').read_text())
    response = client.post('/api/financial/'+module, json=payload)
    assert response.status_code == 201, response.json
    return response.json


@pytest.mark.parametrize('method,path', [
    ('get','/api/customers'),('post','/api/customers'),('get','/api/kyc-processes'),
    ('get','/api/financial/analyses'),('get','/api/financial/analyses/missing/export'),
    ('get','/api/financial/analyses/missing/checklist.csv'),('post','/api/financial/fidc'),
    ('get','/api/automation/status'),('post','/api/automation/process'),
    ('post','/api/automation/documents/extract'),('get','/api/automation/monitors'),
    ('post','/api/automation/monitors'),('get','/api/auth/me'),('post','/api/auth/users'),
    ('options','/api/financial/analyses'),
])
def test_anonymous_requests_are_denied(secured, method, path):
    app,*_ = secured
    response = getattr(app.test_client(), method)(path)
    assert response.status_code == 401
    assert response.headers['Cache-Control'] == 'no-store'


def test_portal_requires_login_and_has_public_health(secured):
    app,*_ = secured
    c=app.test_client()
    assert c.get('/').headers['Location']=='/login'
    assert c.get('/login').status_code==200
    assert c.get('/health').json=={'status':'ok'}


def test_session_cookie_hash_logout_expiry_and_csrf(secured):
    app,*_ = secured
    c=app.test_client()
    response=c.post('/api/auth/login',json={'email':'A@EXAMPLE.TEST','password':PASSWORD})
    assert response.status_code==200
    cookie=response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    token=c.get_cookie('regtech_session').value
    with app.app_context():
        row=AccessSession.query.one()
        assert row.token_hash != token and len(row.token_hash)==64
    assert c.post('/api/financial/fidc',json=fidc_payload()).status_code==403
    assert c.post('/api/auth/logout',headers={'X-CSRF-Token':'wrong'}).status_code==403
    csrf=response.json['csrf_token']
    assert c.post('/api/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    # A copied cookie is also revoked server-side.
    c.set_cookie('regtech_session',token)
    assert c.get('/api/auth/me').status_code==401
    c=signed_client(app,'a@example.test')
    with app.app_context():
        row=AccessSession.query.one();row.expires_at=int(time.time())-1;db.session.commit()
    assert c.get('/api/auth/me').status_code==401


def test_secure_cookie_default_and_no_login_csrf(secured):
    app,*_ = secured
    app.config['AUTH_COOKIE_SECURE']=True
    c=app.test_client()
    assert c.post('/api/auth/login',data={'email':'a@example.test','password':PASSWORD}).status_code==400
    assert c.post('/api/auth/login',json={'email':'a@example.test','password':PASSWORD},headers={'Origin':'https://attacker.invalid'}).status_code==403
    r=c.post('/api/auth/login',json={'email':'a@example.test','password':PASSWORD})
    assert 'Secure' in r.headers['Set-Cookie']


def test_unknown_and_wrong_password_have_same_error_and_limit(secured):
    app,*_ = secured
    c=app.test_client()
    a=c.post('/api/auth/login',json={'email':'a@example.test','password':'wrong'})
    b=c.post('/api/auth/login',json={'email':'unknown@example.test','password':'wrong'})
    assert a.status_code==b.status_code==401 and a.json==b.json
    for _ in range(4):
        assert c.post('/api/auth/login',json={'email':'a@example.test','password':'wrong'}).status_code==401
    response=c.post('/api/auth/login',json={'email':'a@example.test','password':PASSWORD})
    assert response.status_code==429 and response.headers['Retry-After']=='900'


@pytest.mark.parametrize('module',['fidc','cdb','credits'])
def test_analysis_history_exports_reviews_are_isolated(secured,module):
    app,*_=secured
    a,b=signed_client(app,'a@example.test'),signed_client(app,'b@example.test')
    report=create_analysis(a,module);base='/api/financial/analyses/'+report['id']
    assert a.get(base).status_code==200
    assert b.get('/api/financial/analyses').json['total']==0
    for suffix in ['', '/export','/checklist.csv']:
        assert b.get(base+suffix).status_code==404
    assert b.post(base+'/reviews',json={}).status_code==404
    assert a.get('/api/financial/analyses?module='+module).json['total']==1


def test_authenticated_review_ignores_forged_name(secured):
    app,org_a,*_=secured
    a=signed_client(app,'a@example.test');report=create_analysis(a)
    response=a.post('/api/financial/analyses/'+report['id']+'/reviews',json={
        'alert_id':report['result']['alerts'][0]['id'],'status':'in_review','reviewer':'FORGED',
        'reason':'Conferência fictícia','evidence_ref':'Documento fictício','expected_revision':0})
    assert response.status_code==201
    event=response.json['reviews'][0]['event']
    assert event['reviewer_declared']=='Revisor fictício' and event['organization_id']==org_a
    assert event['reviewer_id']==a.get('/api/auth/me').json['user']['id']
    assert all(response.json['integrity'].values())


def test_foreign_fidc_and_source_cannot_be_linked(secured):
    app,*_=secured
    a,b=signed_client(app,'a@example.test'),signed_client(app,'b@example.test')
    record=create_analysis(a)
    payload=json.loads(Path('src/static/examples/credits.json').read_text())
    payload['linked_fidc_analysis_id']=record['id']
    assert b.post('/api/financial/credits',json=payload).status_code==404
    with patch('src.routes.automation.lookup_process',side_effect=mock_lookup):
        snapshot=a.post('/api/automation/process',json={'process_number':PROCESS}).json
    payload['linked_fidc_analysis_id']=None
    payload['credits'][0]['process_number']=PROCESS
    payload['process_lookup_ids']=[snapshot['id']]
    assert b.post('/api/financial/credits',json=payload).status_code==404
    assert b.get('/api/automation/process/'+snapshot['id']).status_code==404


def test_process_cache_monitor_and_runner_keep_organizations_separate(secured):
    from src.services.rechecks import run_due
    app,*_=secured
    a,b=signed_client(app,'a@example.test'),signed_client(app,'b@example.test')
    with patch('src.routes.automation.lookup_process',side_effect=mock_lookup) as lookup:
        first=a.post('/api/automation/process',json={'process_number':PROCESS})
        assert first.status_code==201
        assert a.post('/api/automation/process',json={'process_number':PROCESS}).status_code==200
        second=b.post('/api/automation/process',json={'process_number':PROCESS})
        assert second.status_code==201 and first.json['id']!=second.json['id']
        assert lookup.call_count==2
    for c in (a,b):
        assert c.post('/api/automation/monitors',json={'process_number':PROCESS}).status_code==201
        assert len(c.get('/api/automation/monitors').json['items'])==1
    assert a.post('/api/automation/monitors',json={'process_number':PROCESS,'enabled':False}).status_code==201
    assert b.get('/api/automation/monitors').json['items'][0]['enabled'] is True
    with app.app_context(),patch('src.services.rechecks.lookup_process',side_effect=mock_lookup):
        assert run_due()==1
    monitor=b.get('/api/automation/monitors').json['items'][0]
    assert b.get('/api/automation/process/'+monitor['last_lookup_id']).status_code==200
    assert a.get('/api/automation/process/'+monitor['last_lookup_id']).status_code==404


def customer_payload():
    return {'name':'Cliente fictício','email':'client@example.test','customer_type':'PF',
            'cpf_cnpj':'52998224725','phone':'11999999999','address':'Mesmo endereço fictício'}


def test_same_document_and_address_in_two_orgs_do_not_leak(secured):
    app,*_=secured
    a,b=signed_client(app,'a@example.test'),signed_client(app,'b@example.test')
    one=a.post('/api/customers',json=customer_payload());two=b.post('/api/customers',json=customer_payload())
    assert one.status_code==two.status_code==201
    assert len(a.get('/api/customers').json)==len(b.get('/api/customers').json)==1
    path='/api/customers/'+str(one.json['id'])
    assert a.get(path).json['address_alert'] is None
    for method in ('get','put','delete'):
        assert getattr(b,method)(path).status_code==404
    assert b.post('/api/kyc-processes',json={'customer_id':one.json['id']}).status_code==404
    assert b.post('/api/kyc-processes',json={'customer_id':two.json['id'],'analyst_id':a.get('/api/auth/me').json['user']['id']}).status_code==404
    assert a.post('/api/kyc-processes',json={'customer_id':one.json['id']}).status_code==201
    assert b.get('/api/kyc-processes').json==[]


def test_admin_can_create_readonly_and_analyst_accounts_but_not_foreign_users(secured):
    app,*_=secured
    a,b=signed_client(app,'a@example.test'),signed_client(app,'b@example.test')
    new=a.post('/api/auth/users',json={'name':'Leitor','email':'reader@example.test','password':PASSWORD,'role':'viewer'})
    assert new.status_code==201
    reader=signed_client(app,'reader@example.test')
    data=create_analysis(a)
    assert reader.get('/api/financial/analyses/'+data['id']+'/export').status_code==200
    for path in ('/api/financial/fidc','/api/automation/process','/api/automation/monitors','/api/automation/documents/extract','/api/auth/users'):
        assert reader.post(path,json={}).status_code==403
    assert reader.get('/api/auth/users').status_code==403
    identifier=new.json['user']['id']
    assert b.patch('/api/auth/users/'+str(identifier),json={'role':'analyst'}).status_code==404
    assert a.patch('/api/auth/users/'+str(identifier),json={'role':'analyst'}).status_code==200
    assert reader.get('/api/auth/me').status_code==401  # role change revokes old sessions
    analyst=signed_client(app,'reader@example.test')
    create_analysis(analyst)
    assert analyst.post('/api/auth/users',json={}).status_code==403
    assert a.patch('/api/auth/users/'+str(identifier),json={'is_active':False}).status_code==200
    assert analyst.get('/api/auth/me').status_code==401
    assert app.test_client().post('/api/auth/login',json={'email':'reader@example.test','password':PASSWORD}).status_code==401


def test_no_public_enrollment_or_tenant_field_override(secured):
    app,*_=secured
    a=signed_client(app,'a@example.test')
    payload=fidc_payload();payload['organization_id']='foreign'
    assert a.post('/api/financial/fidc',json=payload).status_code==400
    assert app.test_client().post('/api/auth/register',json={}).status_code==401
    assert a.post('/api/auth/users',json={'name':'X','email':'x@example.test','password':PASSWORD,'role':'admin'}).status_code==400


def test_legacy_tables_and_unowned_records_stay_inaccessible(secured):
    app,*_=secured
    with app.app_context():
        # Model the pre-auth schema; creating the protected tables must never reassign these rows.
        db.session.execute(text('CREATE TABLE financial_analyses (id TEXT PRIMARY KEY, name TEXT)'))
        db.session.execute(text("INSERT INTO financial_analyses VALUES ('legacy', 'preservado')"))
        item=FinancialAnalysis(module='fidc',name='Sem dono',input_payload={},result_payload={},input_sha256='0'*64,result_sha256='0'*64)
        db.session.add(item);db.session.commit();identifier=item.id
        db.create_all()
        assert db.session.execute(text("SELECT name FROM financial_analyses WHERE id='legacy'")).scalar()=='preservado'
    a=signed_client(app,'a@example.test')
    assert a.get('/api/financial/analyses').json['total']==0
    assert a.get('/api/financial/analyses/'+identifier).status_code==404


def test_cli_provisioning_is_explicit_and_password_hidden(tmp_path):
    app=create_app({'TESTING':True,'AUTH_COOKIE_SECURE':False,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'cli.db')})
    result=app.test_cli_runner().invoke(args=['create-organization','--organization','Org fictícia','--name','Admin','--email','cli@example.test'],input=PASSWORD+'\n'+PASSWORD+'\n')
    assert result.exit_code==0,result.output
    assert PASSWORD not in result.output
    assert app.test_client().post('/api/auth/login',json={'email':'cli@example.test','password':PASSWORD}).status_code==200
