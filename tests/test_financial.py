import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
from src import db
from src.app import create_app
from src.models.financial_analysis import FinancialAnalysis, FinancialReview
from src.services.financial_analysis import InputError, analyze_fidc, analyze_cdb, csv_receivables, canonical_hash


@pytest.fixture
def client():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cdb():
    return json.loads(Path('src/static/examples/cdb.json').read_text())


@pytest.fixture
def fidc():
    return {'name': 'Carteira teste', 'as_of': '2026-10-20', 'source_ref': 'arquivo fictício.csv',
            'receivables': [{'title_id': 'T1', 'originator_id': 'O1', 'debtor_id': 'D1',
                             'amount': '0.10', 'document_ref': 'DOC1', 'document_amount': '0.10',
                             'assignment_ref': 'CESS1', 'installment': '1',
                             'existence_confirmed': True, 'ownership_confirmed': True}]}


def codes(result):
    return {alert['code'] for alert in result['alerts']}


def fgc_parameters(**changes):
    return dict(eligibility_confirmed=True, balances_include_interest=True,
                history_confirmed=True, prior_payments_current_window='0.00',
                source_ref='Histórico fictício conferido', **changes)


def test_fidc_decimal_totals_and_no_flags_for_documented_rows(fidc):
    second = dict(fidc['receivables'][0], title_id='T2', document_ref='DOC2', amount='0.20', document_amount='0.20')
    fidc['receivables'].append(second)
    result = analyze_fidc(fidc)
    assert result['summary']['declared_total'] == '0.30'
    assert result['summary']['alert_count'] == 0


def test_fidc_duplicates_mismatch_and_absence(fidc):
    row = dict(fidc['receivables'][0], amount='0.20', document_amount='0.15')
    fidc['receivables'].append(row)
    fidc['receivables'].append({'title_id': 'T3', 'originator_id': 'O1', 'debtor_id': 'D1', 'amount': '20.00'})
    result = analyze_fidc(fidc)
    assert {'DUPLICATE_TITLE_ID', 'POSSIBLE_DUPLICATE_RECEIVABLE', 'AMOUNT_MISMATCH',
            'DOCUMENT_MISSING', 'ASSIGNMENT_MISSING', 'DOCUMENT_VALUE_MISSING',
            'EXISTENCE_CONFIRMED_PENDING', 'OWNERSHIP_CONFIRMED_PENDING'} <= codes(result)
    assert result['receivables'][2]['existence_confirmed'] is None
    assert fidc['receivables'][2].get('existence_confirmed') is None


def test_distinct_installments_are_not_duplicate_receivables(fidc):
    fidc['receivables'].append(dict(fidc['receivables'][0], title_id='T2', installment='2'))
    assert 'POSSIBLE_DUPLICATE_RECEIVABLE' not in codes(analyze_fidc(fidc))


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '0', '1.001', True, {}, '1,50'])
def test_bad_amount_rejected_without_persisting(client, fidc, value):
    fidc['receivables'][0]['amount'] = value
    response = client.post('/api/financial/fidc', json=fidc)
    assert response.status_code == 400
    assert client.get('/api/financial/analyses').json['total'] == 0


def test_false_confirmation_is_explicit_and_strings_are_rejected(fidc):
    fidc['receivables'][0]['existence_confirmed'] = False
    assert 'EXISTENCE_CONFIRMED_NEGATIVE' in codes(analyze_fidc(fidc))
    fidc['receivables'][0]['existence_confirmed'] = 'false'
    with pytest.raises(InputError):
        analyze_fidc(fidc)


def test_cannot_confirm_without_reference(fidc):
    fidc['receivables'][0]['document_ref'] = ''
    with pytest.raises(InputError):
        analyze_fidc(fidc)


def test_csv_round_trip_and_source_hash(client):
    content = Path('src/static/examples/carteira.csv').read_bytes()
    response = client.post('/api/financial/fidc/import', data={'name': 'CSV', 'as_of': '2026-10-20',
        'source_ref': 'teste.csv', 'file': (io.BytesIO(content), 'teste.csv')})
    assert response.status_code == 201
    report = response.json
    assert report['result']['summary']['receivable_count'] == 4
    export = client.get('/api/financial/analyses/' + report['id'] + '/export')
    assert export.json['input']['import']['file_sha256'] == hashlib.sha256(content).hexdigest()
    assert 'attachment;' in export.headers['Content-Disposition']
    assert all(export.json['integrity'].values())


@pytest.mark.parametrize('content', [
    'title_id,title_id,amount\nA,B,1\n',
    'title_id,originator_id,debtor_id,amount\nA,O,D,1,extra\n',
    'title_id,originator_id,debtor_id,amount\nA,O,D\n',
    'title_id,originator_id,debtor_id,amount,existence_confirmed\nA,O,D,1,yes\n',
])
def test_csv_invalid_headers_and_rows(content):
    with pytest.raises(InputError):
        csv_receivables(content)


def test_utf8_bom_and_semicolon_csv():
    rows = csv_receivables('\ufefftitle_id;originator_id;debtor_id;amount\nA;O;D;1.20\n')
    assert rows[0]['amount'] == '1.20'


def test_cdb_compares_below_arbitrary_high_rate(cdb):
    result = analyze_cdb(cdb)
    assert result['comparison']['median_percent_cdi'] == '106.00'
    assert result['comparison']['difference_percentage_points'] == '12.00'
    assert 'RATE_ABOVE_COMPARABLE_MEDIAN' in codes(result)
    cdb['offer']['rate_percent_cdi'] = '106.00'
    assert 'RATE_ABOVE_COMPARABLE_MEDIAN' not in codes(analyze_cdb(cdb))


def test_high_absolute_rate_does_not_trigger_without_context(cdb):
    cdb['offer']['rate_percent_cdi'] = '160.00'
    for peer in cdb['comparables']:
        peer['rate_percent_cdi'] = '170.00'
    assert 'RATE_ABOVE_COMPARABLE_MEDIAN' not in codes(analyze_cdb(cdb))


@pytest.mark.parametrize('field,value', [('term_days', 360), ('liquidity', 'daily'), ('as_of', '2026-10-19'), ('conglomerate_ref', 'GRUPO-A')])
def test_mismatched_comparables_excluded(cdb, field, value):
    cdb['comparables'][0][field] = value
    result = analyze_cdb(cdb)
    assert len(result['comparison']['excluded']) == 1
    assert result['comparison']['median_percent_cdi'] is None
    assert 'INSUFFICIENT_COMPARABLES' in codes(result)


def test_duplicate_offer_identifier_rejected(cdb):
    cdb['comparables'][1]['offer_id'] = cdb['comparables'][0]['offer_id']
    with pytest.raises(InputError):
        analyze_cdb(cdb)


def test_missing_and_negative_financials_are_distinguished(cdb):
    assert 'NEGATIVE_NET_INCOME' in codes(analyze_cdb(cdb))
    cdb['financials']['equity'] = '0.00'
    result = analyze_cdb(cdb)
    assert 'NONPOSITIVE_EQUITY' in codes(result)
    assert result['financials']['deposits_to_equity'] is None
    del cdb['financials']
    assert 'FINANCIALS_MISSING' in codes(analyze_cdb(cdb))


def test_financial_snapshot_of_other_issuer_rejected(cdb):
    cdb['financials']['issuer_ref'] = 'OTHER'
    with pytest.raises(InputError):
        analyze_cdb(cdb)


def test_exposure_groups_and_user_defined_limit(cdb):
    result = analyze_cdb(cdb)
    assert result['exposure']['total_balance'] == '300000.00'
    assert result['exposure']['target_group_balance'] == '270000.00'
    assert result['exposure']['groups'][0]['share_percent'] == '90.00'
    assert 'CONCENTRATION_LIMIT_EXCEEDED' in codes(result)
    del cdb['concentration_limit_percent']
    assert 'CONCENTRATION_LIMIT_EXCEEDED' not in codes(analyze_cdb(cdb))


def test_fgc_aggregates_same_group(cdb):
    cdb['fgc'] = fgc_parameters()
    fgc = analyze_cdb(cdb)['exposure']['fgc']
    assert fgc['estimated_total'] == '280000.00'
    assert fgc['eligible_excess'] == '20000.00'


def test_fgc_global_cap_applies_to_all_groups_together(cdb):
    cdb['fgc'] = fgc_parameters()
    cdb['fgc']['prior_payments_current_window'] = '900000.00'
    result = analyze_cdb(cdb)
    assert result['exposure']['fgc']['estimated_total'] == '100000.00'
    assert result['exposure']['fgc']['eligible_excess'] == '200000.00'


def test_fgc_unknown_eligibility_does_not_give_estimate(cdb):
    cdb['fgc'] = fgc_parameters()
    cdb['positions'][0]['eligible'] = None
    assert analyze_cdb(cdb)['exposure']['fgc']['estimated_total'] is None


def test_fgc_false_confirmation_does_not_give_estimate(cdb):
    cdb['fgc'] = fgc_parameters()
    cdb['fgc']['history_confirmed'] = False
    assert analyze_cdb(cdb)['exposure']['fgc']['estimated_total'] is None


def test_ineligible_positions_are_excluded_from_fgc(cdb):
    cdb['fgc'] = fgc_parameters()
    for row in cdb['positions']:
        row['eligible'] = False
    assert analyze_cdb(cdb)['exposure']['fgc']['estimated_total'] == '0.00'


def test_reviews_preserve_original_and_check_revision(client, fidc):
    fidc['receivables'][0]['existence_confirmed'] = None
    created = client.post('/api/financial/fidc', json=fidc)
    assert created.status_code == 201
    report = created.json
    identifier = report['id']
    original_hash = report['result_sha256']
    url = '/api/financial/analyses/' + identifier + '/reviews'
    review = {'alert_id': report['result']['alerts'][0]['id'], 'status': 'resolved',
              'reviewer': 'Revisor fictício', 'reason': 'Conferência concluída',
              'evidence_ref': 'evidencia-teste', 'expected_revision': 0}
    updated = client.post(url, json=review)
    assert updated.status_code == 201
    assert updated.json['result_sha256'] == original_hash
    assert updated.json['result']['alerts'][0]['status'] == 'resolved'
    assert all(updated.json['integrity'].values())
    assert client.post(url, json=review).status_code == 409
    review.update(status='open', expected_revision=1, reason='Nova evidência exige reabertura')
    reopened = client.post(url, json=review)
    assert reopened.status_code == 201
    assert len(reopened.json['reviews']) == 2
    assert reopened.json['reviews'][1]['event']['previous_sha256'] == reopened.json['reviews'][0]['sha256']
    exported = client.get('/api/financial/analyses/' + identifier + '/export').json
    assert canonical_hash(exported['input']) == exported['input_sha256']
    with client.application.app_context():
        assert db.session.get(FinancialAnalysis, identifier).result_payload['alerts'][0]['status'] == 'open'


def test_review_rejects_foreign_alert_and_missing_evidence(client, fidc):
    fidc['receivables'][0]['existence_confirmed'] = None
    report = client.post('/api/financial/fidc', json=fidc).json
    url = '/api/financial/analyses/' + report['id'] + '/reviews'
    payload = dict(alert_id='OTHER', status='resolved', reviewer='R', reason='Teste', evidence_ref='E', expected_revision=0)
    assert client.post(url, json=payload).status_code == 400
    payload.update(alert_id=report['result']['alerts'][0]['id'], evidence_ref='')
    assert client.post(url, json=payload).status_code == 400
    assert client.get('/api/financial/analyses/' + report['id']).json['revision'] == 0


def test_detect_modified_result_and_block_review(client, fidc):
    report = client.post('/api/financial/fidc', json=fidc).json
    with client.application.app_context():
        analysis = db.session.get(FinancialAnalysis, report['id'])
        modified = copy.deepcopy(analysis.result_payload)
        modified['name'] = 'Alteração indevida'
        analysis.result_payload = modified
        db.session.commit()
    loaded = client.get('/api/financial/analyses/' + report['id']).json
    assert loaded['integrity']['result_matches'] is False


def test_history_filter_and_reload_from_database(client, fidc, cdb):
    first = client.post('/api/financial/fidc', json=fidc).json
    assert client.post('/api/financial/cdb', json=cdb).status_code == 201
    assert client.get('/api/financial/analyses').json['total'] == 2
    assert client.get('/api/financial/analyses?module=fidc').json['items'][0]['id'] == first['id']
    assert client.get('/api/financial/analyses?page=no').status_code == 400
    assert client.get('/api/financial/analyses?page=0').status_code == 400
    assert client.get('/api/financial/analyses/unknown').status_code == 404


def test_portal_static_assets_and_non_destructive_init_command(client, fidc):
    assert client.get('/').status_code == 200
    assert client.get('/static/financial.js').status_code == 200
    assert client.get('/static/examples/carteira.csv').status_code == 200
    identifier = client.post('/api/financial/fidc', json=fidc).json['id']
    assert client.application.test_cli_runner().invoke(args=['init-db']).exit_code == 0
    assert client.get('/api/financial/analyses/' + identifier).status_code == 200


def test_peer_conglomerate_cannot_be_counted_twice(cdb):
    cdb['comparables'][1]['conglomerate_ref'] = cdb['comparables'][0]['conglomerate_ref']
    result = analyze_cdb(cdb)
    assert result['summary']['comparable_count'] == 2
    assert result['comparison']['median_percent_cdi'] is None


def test_even_median_preserves_subcent_precision(cdb):
    cdb['comparables'] = [dict(cdb['comparables'][0], offer_id='P'+str(i),
                             conglomerate_ref='DISTINCT'+str(i), rate_percent_cdi=rate)
                          for i, rate in enumerate(['100.00', '100.01', '100.02', '100.03'])]
    cdb['offer']['rate_percent_cdi'] = '100.02'
    result = analyze_cdb(cdb)
    assert result['comparison']['median_percent_cdi'] == '100.015'
    assert result['comparison']['difference_percentage_points'] == '0.005'
    assert 'RATE_ABOVE_COMPARABLE_MEDIAN' in codes(result)


def test_truncated_csv_quotes_are_rejected():
    with pytest.raises(InputError):
        csv_receivables('title_id,originator_id,debtor_id,amount\n"unclosed,O,D,1.00')


def test_incomplete_fgc_still_rejects_bad_numeric_input(client, cdb):
    cdb['fgc'] = fgc_parameters()
    cdb['fgc'].update(history_confirmed=False, prior_payments_current_window='NaN')
    assert client.post('/api/financial/cdb', json=cdb).status_code == 400


def test_modified_review_chain_is_detected_and_blocks_new_event(client, fidc):
    fidc['receivables'][0]['existence_confirmed'] = None
    report = client.post('/api/financial/fidc', json=fidc).json
    path = '/api/financial/analyses/' + report['id']
    payload = dict(alert_id=report['result']['alerts'][0]['id'], status='in_review',
                   reviewer='R', reason='Teste', evidence_ref='DOC', expected_revision=0)
    assert client.post(path + '/reviews', json=payload).status_code == 201
    with client.application.app_context():
        row = FinancialReview.query.filter_by(analysis_id=report['id']).one()
        row.event = {**row.event, 'reason': 'Alteração posterior'}
        db.session.commit()
    assert client.get(path).json['integrity']['review_chain_matches'] is False
    payload.update(status='resolved', expected_revision=1)
    assert client.post(path + '/reviews', json=payload).status_code == 409


@pytest.mark.parametrize('field,value', [('as_of', '2099-01-01'), ('document_sha256', 'not-a-hash')])
def test_dates_and_document_hashes_rejected(client, fidc, field, value):
    if field == 'as_of':
        fidc[field] = value
    else:
        fidc['receivables'][0][field] = value
    assert client.post('/api/financial/fidc', json=fidc).status_code == 400


def test_body_and_portfolio_limits(client, fidc):
    assert client.post('/api/financial/fidc', data=b'x'*3_000_001, content_type='application/json').status_code == 413
    fidc['receivables'] *= 5001
    assert client.post('/api/financial/fidc', json=fidc).status_code == 400
