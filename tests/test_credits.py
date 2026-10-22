import copy
import io
import json
from pathlib import Path
import pytest
from src import db
from src.app import create_app
from src.services.credit_analysis import analyze_credits
from src.services.financial_analysis import InputError, canonical_hash


@pytest.fixture
def payload():
    return json.loads(Path('src/static/examples/credits.json').read_text())


@pytest.fixture
def client():
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def codes(result):
    return {a['code'] for a in result['alerts']}


def test_partial_assignments_preserve_all_interests(payload):
    result=analyze_credits(payload)
    credit=result['credits'][0]
    chain=credit['assignment_chain']
    assert chain['arithmetic_consistent'] is True
    assert chain['declared_holder_nominal_share']=='40000.00'
    assert {r['holder_ref']:r['face_amount'] for r in chain['nominal_holdings']}=={
        'CREDOR-ORIGINAL-FICTICIO':'40000.00','CESSIONARIO-B-FICTICIO':'20000.00','CESSIONARIO-C-FICTICIO':'40000.00'}
    assert credit['reference_after_deductions']=='85000.00'
    assert chain['document_references_complete'] is False
    assert 'COURT_NOTIFICATION_PENDING' in codes(result)
    assert payload['credits'][0]['assignments'][0].get('applied_to_nominal_ledger') is None


def test_oversale_does_not_infer_final_holder(payload):
    credit=payload['credits'][0]
    credit['assignments'][1]['face_amount']='70000.00'
    chain=analyze_credits(payload)['credits'][0]['assignment_chain']
    assert chain['arithmetic_consistent'] is False
    assert chain['declared_holder_nominal_share'] is None
    assert chain['events'][1]['applied_to_nominal_ledger'] is False
    assert 'ASSIGNMENT_EXCEEDS_NOMINAL_HOLDING' in codes(analyze_credits(payload))


def test_unknown_transferor_and_out_of_order_chain(payload):
    credit=payload['credits'][0]
    credit['assignments'].reverse()
    result=analyze_credits(payload)
    assert {'ASSIGNMENT_ORDER_INCONSISTENT','ASSIGNMENT_EXCEEDS_NOMINAL_HOLDING'}<=codes(result)
    assert result['credits'][0]['assignment_chain']['declared_holder_nominal_share'] is None


def test_legitimate_retransfer_back_to_original_holder(payload):
    credit=payload['credits'][0]
    credit['assignments'].append(dict(credit['assignments'][1],assignment_id='A3',date='2026-06-01',
        transferor_ref='CESSIONARIO-C-FICTICIO',transferee_ref='CREDOR-ORIGINAL-FICTICIO',face_amount='10000.00'))
    assert analyze_credits(payload)['credits'][0]['assignment_chain']['declared_holder_nominal_share']=='30000.00'


def test_duplicate_assignment_ids_rejected(payload):
    payload['credits'][0]['assignments'][1]['assignment_id']='CESSAO-01'
    with pytest.raises(InputError): analyze_credits(payload)


def test_same_party_assignment_is_not_applied(payload):
    assignment=payload['credits'][0]['assignments'][0]
    assignment['transferee_ref']=assignment['transferor_ref']
    result=analyze_credits(payload)
    assert 'ASSIGNMENT_SAME_PARTY' in codes(result)
    assert result['credits'][0]['assignment_chain']['arithmetic_consistent'] is False


def test_missing_credit_values_do_not_become_zero(payload):
    del payload['credits'][0]['paid_amount']
    result=analyze_credits(payload)
    assert result['credits'][0]['reference_after_deductions'] is None
    assert 'PAYMENT_RESERVE_DATA_PENDING' in codes(result)


def test_deductions_exceeding_face_are_flagged(payload):
    payload['credits'][0]['paid_amount']='100001.00'
    result=analyze_credits(payload)
    assert result['credits'][0]['reference_after_deductions']=='0.00'
    assert 'DEDUCTIONS_EXCEED_FACE' in codes(result)


def test_reference_value_difference_and_duplicates(payload):
    credit=payload['credits'][0]
    credit['document_amount']='99999.00'
    payload['credits'].append(copy.deepcopy(credit))
    assert {'CREDIT_AMOUNT_MISMATCH','REPEATED_CREDIT_ID','POSSIBLE_REPEATED_PRECATORIO','POSSIBLE_REPEATED_CREDIT_DOCUMENT'}<=codes(analyze_credits(payload))


def test_scenarios_use_partial_acquisition_not_full_credit(payload):
    economic=analyze_credits(payload)['credits'][0]['economic']
    assert economic['purchase_discount_percent']=='25.0000'
    assert economic['total_initial_investment']=='30500.00'
    first,second=economic['scenarios']
    assert first['net_receipt']=='44200.00'
    assert first['profit_or_loss']=='13700.00'
    assert first['annualized_return_percent']==first['total_return_percent']
    assert first['net_present_value']=='8964.29'
    assert float(second['annualized_return_percent'])<float(first['annualized_return_percent'])
    assert float(second['net_present_value'])<float(first['net_present_value'])


def test_nonpositive_receipt_has_no_annualized_rate(payload):
    scenario=payload['credits'][0]['economic']['scenarios'][0]
    scenario.update(expected_gross_amount='0.00',receipt_costs='300.00',taxes='500.00')
    result=analyze_credits(payload)
    assert result['credits'][0]['economic']['scenarios'][0]['annualized_return_percent'] is None
    assert {'SCENARIO_LOSS','SCENARIO_NONPOSITIVE_RECEIPT'}<=codes(result)


def test_no_discount_rate_means_no_present_value(payload):
    del payload['credits'][0]['economic']['scenarios'][0]['discount_rate_annual_percent']
    assert analyze_credits(payload)['credits'][0]['economic']['scenarios'][0]['net_present_value'] is None


@pytest.mark.parametrize('months',[0,-1,1.5,True,601,'12'])
def test_invalid_scenario_duration(payload,months):
    payload['credits'][0]['economic']['scenarios'][0]['months_to_receipt']=months
    with pytest.raises(InputError): analyze_credits(payload)


@pytest.mark.parametrize('value',['NaN','Infinity','-1','0','1.001',True,{}])
def test_invalid_face_rejected_without_write(client,payload,value):
    payload['credits'][0]['face_amount']=value
    assert client.post('/api/financial/credits',json=payload).status_code==400
    assert client.get('/api/financial/analyses').json['total']==0


def test_contradictory_confirmation_rejected(payload):
    payload['credits'][0]['document_ref']=''
    with pytest.raises(InputError): analyze_credits(payload)


def test_absent_confirmation_is_pending_and_negative_is_distinct(payload):
    payload['credits'][0]['claim_confirmed']=False
    result=analyze_credits(payload)
    assert 'CLAIM_CONFIRMED_NEGATIVE' in codes(result)
    assert 'HOLDER_CONFIRMED_PENDING' in codes(result)


def test_no_court_notice_requirement_for_contractual_credit(payload):
    payload['credits'][0]['kind']='contractual'
    assert 'COURT_NOTIFICATION_PENDING' not in codes(analyze_credits(payload))
    payload['credits'][0]['assignments'][0]['debtor_notification_ref']=''
    assert 'DEBTOR_NOTIFICATION_PENDING' in codes(analyze_credits(payload))


def test_undocumented_no_encumbrance_does_not_clear_check(payload):
    payload['credits'][0].update(encumbrance_status='none',encumbrance_ref='')
    assert 'ENCUMBRANCE_STATUS_CHECK_PENDING' in codes(analyze_credits(payload))


def test_assignments_after_analysis_date_rejected(payload):
    payload['credits'][0]['assignments'][0]['date']='2026-10-21'
    with pytest.raises(InputError): analyze_credits(payload)


def test_credit_roundtrip_history_export_and_review(client,payload):
    created=client.post('/api/financial/credits',json=payload)
    assert created.status_code==201
    report=created.json
    identifier=report['id']
    path='/api/financial/analyses/'+identifier
    assert client.get('/api/financial/analyses?module=credits').json['total']==1
    assert client.get(path).json['result']['credits'][0]['kind']=='precatorio'
    reviewed=client.post(path+'/reviews',json=dict(alert_id=report['result']['alerts'][0]['id'],status='in_review',
        reviewer='Revisora fictícia',reason='Examinar documentos',evidence_ref='Documento fictício',expected_revision=0))
    assert reviewed.status_code==201
    export=client.get(path+'/export').json
    assert export['result']['alerts'][0]['status']=='in_review'
    assert len(export['reviews'])==1
    assert all(export['integrity'].values())
    assert canonical_hash(export['input'])==export['input_sha256']


def test_credit_import_hash_and_invalid_file(client,payload):
    content=json.dumps(payload).encode()
    result=client.post('/api/financial/credits/import',data={'file':(io.BytesIO(content),'carteira.json')})
    assert result.status_code==201
    import hashlib
    exported=client.get('/api/financial/analyses/'+result.json['id']+'/export').json
    assert exported['input']['import']['file_sha256']==hashlib.sha256(content).hexdigest()
    assert client.post('/api/financial/credits/import',data={'file':(io.BytesIO(b'{bad'),'bad.json')}).status_code==400
    assert client.post('/api/financial/credits/import',data={}).status_code==400
    assert client.post('/api/financial/credits/import',data={'file':(io.BytesIO(b'x'*2_000_001),'large.json')}).status_code==400


def test_link_to_fidc_analysis(client,payload):
    fidc={'name':'Carteira vinculada','as_of':'2026-10-20','source_ref':'Fictício',
          'receivables':[dict(title_id='T1',originator_id='O',debtor_id='D',amount='100.00')]}
    linked=client.post('/api/financial/fidc',json=fidc).json['id']
    payload['linked_fidc_analysis_id']=linked
    created=client.post('/api/financial/credits',json=payload)
    assert created.status_code==201
    assert created.json['result']['linked_fidc_analysis_id']==linked
    payload['linked_fidc_analysis_id']=created.json['id']
    assert client.post('/api/financial/credits',json=payload).status_code==400
    payload['linked_fidc_analysis_id']='unknown'
    assert client.post('/api/financial/credits',json=payload).status_code==404


def test_credit_module_assets(client):
    assert 'Precatórios e créditos' in client.get('/').text
    assert client.get('/static/credits.js').status_code==200
    assert client.get('/static/examples/credits.json').status_code==200


def test_acquisition_larger_than_current_holders_share_is_flagged(payload):
    payload['credits'][0]['economic']['acquired_face_amount']='50000.00'
    assert 'ACQUISITION_EXCEEDS_DECLARED_NOMINAL_SHARE' in codes(analyze_credits(payload))
