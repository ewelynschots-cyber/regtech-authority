"""Documentary and nominal-assignment checks for declared credit rights."""
from collections import defaultdict
from decimal import Decimal, localcontext
from src.services.financial_analysis import (
    InputError, object_fields, text, iso_date, number, money, flag, list_rows,
)

VERSION = '1.0.0'
REFERENCES = [
    'https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm',
    'https://atos.cnj.jus.br/atos/detalhar/3130',
    'https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm',
]
CREDIT_FIELDS = {'credit_id', 'kind', 'debtor_ref', 'original_holder_ref', 'declared_holder_ref',
                'face_amount', 'document_amount', 'paid_amount', 'reserved_amount', 'document_ref',
                'process_number', 'court', 'precatorio_number', 'nature', 'final_judgment_ref',
                'requisition_ref', 'payment_order_ref', 'claim_confirmed', 'holder_confirmed',
                'holder_check_ref', 'encumbrance_status', 'encumbrance_ref',
                'dispute_status', 'dispute_ref', 'assignments', 'economic'}


def optional_amount(raw, field, label):
    value = raw.get(field)
    return None if value in (None, '') else number(value, label + ': ' + field, minimum=Decimal(0))


def analyze_assignments(raw, credit, as_of, alerts, sources):
    ledger = defaultdict(Decimal, {credit['original_holder_ref']: Decimal(credit['face_amount'])})
    events, identifiers = [], set()
    consistent, documented = True, True
    previous_date = None
    for i, item in enumerate(list_rows(raw, 'assignments', maximum=1000, allow_empty=True), 1):
        object_fields(item, {'assignment_id', 'date', 'transferor_ref', 'transferee_ref', 'face_amount',
                            'instrument_ref', 'court_notification_ref', 'debtor_notification_ref'}, f'Cessão {i}')
        event = {key: text(item.get(key), f'Cessão {i}: {key}')
                 for key in ('assignment_id', 'transferor_ref', 'transferee_ref')}
        if event['assignment_id'] in identifiers:
            raise InputError('assignment_id repetido no mesmo crédito')
        identifiers.add(event['assignment_id'])
        event['date'] = iso_date(item.get('date'), f'Cessão {i}: date')
        if event['date'] > as_of:
            raise InputError('Cessão posterior à data-base da análise')
        amount = number(item.get('face_amount'), f'Cessão {i}: face_amount', minimum=Decimal('.01'))
        event['face_amount'] = money(amount)
        for key in ('instrument_ref', 'court_notification_ref', 'debtor_notification_ref'):
            event[key] = text(item.get(key), f'Cessão {i}: {key}', optional=True)
            if event[key]:
                sources.append(event[key])
        evidence = {'credit_id': credit['credit_id'], 'assignment_id': event['assignment_id'],
                    'transferor_ref': event['transferor_ref'], 'transferee_ref': event['transferee_ref'],
                    'face_amount': event['face_amount']}
        for key, code, message in [
            ('instrument_ref', 'ASSIGNMENT_INSTRUMENT_MISSING', 'Instrumento de cessão não referenciado'),
            ('debtor_notification_ref', 'DEBTOR_NOTIFICATION_PENDING', 'Comprovação de comunicação ao devedor pendente'),
        ]:
            if not event[key]:
                documented = False
                flag(alerts, code, message, evidence=evidence)
        if credit['kind'] == 'precatorio' and not event['court_notification_ref']:
            documented = False
            flag(alerts, 'COURT_NOTIFICATION_PENDING', 'Comprovação de comunicação da cessão ao tribunal pendente', evidence=evidence)
        if previous_date and event['date'] < previous_date:
            consistent = False
            flag(alerts, 'ASSIGNMENT_ORDER_INCONSISTENT', 'Cessões fora da ordem cronológica declarada', evidence=evidence)
        previous_date = event['date']
        if event['transferor_ref'] == event['transferee_ref']:
            consistent = False
            flag(alerts, 'ASSIGNMENT_SAME_PARTY', 'Cedente e cessionário coincidem', evidence=evidence)
        available = ledger[event['transferor_ref']]
        if amount > available:
            consistent = False
            flag(alerts, 'ASSIGNMENT_EXCEEDS_NOMINAL_HOLDING', 'Cessão excede a participação nominal reconstruída do cedente',
                 evidence={**evidence, 'available_nominal_holding': money(available)})
        # Once inconsistent, do not propagate balances or infer a final holder.
        event['applied_to_nominal_ledger'] = consistent
        if consistent:
            ledger[event['transferor_ref']] -= amount
            ledger[event['transferee_ref']] += amount
        events.append(event)
    holder_share = ledger[credit['declared_holder_ref']] if consistent else None
    if consistent and holder_share <= 0:
        flag(alerts, 'DECLARED_HOLDER_WITHOUT_NOMINAL_SHARE', 'Titular declarado não possui participação na cadeia nominal informada',
             evidence={'credit_id': credit['credit_id'], 'declared_holder_ref': credit['declared_holder_ref']})
    return {'events': events, 'arithmetic_consistent': consistent, 'document_references_complete': documented,
            'declared_holder_nominal_share': money(holder_share) if holder_share is not None else None,
            'nominal_holdings': [{'holder_ref': holder, 'face_amount': money(value)} for holder, value in sorted(ledger.items()) if value > 0],
            'holdings_status': 'declared_nominal_reconstruction' if consistent else 'partial_reconstruction_inconclusive',
            'basis': 'Cessões expressas em valores nominais da mesma base do crédito original. '
                     'Participações não são reduzidas automaticamente por pagamentos ou reservas sem alocação por titular.'}


def economic_scenarios(raw, credit, alerts):
    if raw is None:
        return None
    object_fields(raw, {'acquired_face_amount', 'purchase_price', 'upfront_costs', 'scenarios'}, 'economic')
    face = number(raw.get('acquired_face_amount'), 'acquired_face_amount', minimum=Decimal('.01'))
    price = number(raw.get('purchase_price'), 'purchase_price', minimum=Decimal('.01'))
    upfront = number(raw.get('upfront_costs'), 'upfront_costs', minimum=Decimal(0))
    if face > Decimal(credit['face_amount']):
        raise InputError('Valor nominal da parcela adquirida excede o valor nominal do crédito')
    investment = price + upfront
    discount = (1 - price / face) * 100
    scenarios = []
    names = set()
    for i, item in enumerate(list_rows(raw.get('scenarios'), 'scenarios', maximum=20), 1):
        object_fields(item, {'name', 'months_to_receipt', 'expected_gross_amount', 'receipt_costs',
                            'taxes', 'discount_rate_annual_percent'}, f'Cenário {i}')
        name = text(item.get('name'), f'Cenário {i}: name')
        if name in names:
            raise InputError('Nomes de cenário repetidos')
        names.add(name)
        months = item.get('months_to_receipt')
        if type(months) is not int or not 1 <= months <= 600:
            raise InputError('months_to_receipt deve ser inteiro entre 1 e 600')
        gross = number(item.get('expected_gross_amount'), 'expected_gross_amount', minimum=Decimal(0))
        costs = number(item.get('receipt_costs'), 'receipt_costs', minimum=Decimal(0))
        taxes = number(item.get('taxes'), 'taxes', minimum=Decimal(0))
        net = gross - costs - taxes
        profit = net - investment
        rate = optional_amount(item, 'discount_rate_annual_percent', 'Cenário')
        if rate is not None and rate > 1000:
            raise InputError('Taxa anual de desconto deve estar entre 0 e 1000')
        with localcontext() as ctx:
            ctx.prec = 40
            annualized = ((net / investment) ** (Decimal(12) / months) - 1) * 100 if net > 0 else None
            present = net / ((1 + rate / 100) ** (Decimal(months) / 12)) if rate is not None else None
        scenario = {'name': name, 'months_to_receipt': months, 'expected_gross_amount': money(gross),
                    'receipt_costs': money(costs), 'taxes': money(taxes), 'net_receipt': money(net),
                    'profit_or_loss': money(profit), 'total_return_percent': format(profit / investment * 100, '.4f'),
                    'annualized_return_percent': format(annualized, '.4f') if annualized is not None else None,
                    'discount_rate_annual_percent': money(rate) if rate is not None else None,
                    'net_present_receipt': money(present) if present is not None else None,
                    'net_present_value': money(present - investment) if present is not None else None}
        if net <= 0:
            flag(alerts, 'SCENARIO_NONPOSITIVE_RECEIPT', 'Cenário informado tem recebimento líquido não positivo; taxa anualizada não calculada',
                 evidence={'credit_id': credit['credit_id'], 'scenario': name, 'net_receipt': money(net)})
        if profit < 0:
            flag(alerts, 'SCENARIO_LOSS', 'Premissas do cenário resultam em perda econômica',
                 evidence={'credit_id': credit['credit_id'], 'scenario': name, 'profit_or_loss': money(profit)})
        scenarios.append(scenario)
    return {'acquired_face_amount': money(face), 'purchase_price': money(price), 'upfront_costs': money(upfront),
            'total_initial_investment': money(investment), 'purchase_discount_percent': format(discount, '.4f'),
            'scenarios': scenarios,
            'basis': 'Fluxo único hipotético: desembolso inicial na data-base e recebimento em meses de 1/12 de ano. '
                     'Valores, custos, tributos, prazo e taxa de desconto são premissas informadas, sem atualização judicial automática.'}


def analyze_credits(payload):
    object_fields(payload, {'name', 'as_of', 'source_ref', 'credits', 'linked_fidc_analysis_id'}, 'Direitos creditórios')
    name = text(payload.get('name'), 'name')
    as_of = iso_date(payload.get('as_of'), 'as_of')
    source = text(payload.get('source_ref'), 'source_ref')
    linked = text(payload.get('linked_fidc_analysis_id'), 'linked_fidc_analysis_id', optional=True)
    credits, alerts, sources = [], [], [source]
    ids, precatorios, documents = defaultdict(list), defaultdict(list), defaultdict(list)
    face_total = Decimal(0)
    for i, raw in enumerate(list_rows(payload.get('credits'), 'credits', maximum=1000), 1):
        object_fields(raw, CREDIT_FIELDS, f'Crédito {i}')
        credit = {'row': i}
        for key in ('credit_id', 'kind', 'debtor_ref', 'original_holder_ref', 'declared_holder_ref'):
            credit[key] = text(raw.get(key), f'Crédito {i}: {key}')
        if credit['kind'] not in ('precatorio', 'judicial', 'contractual'):
            raise InputError('kind deve ser precatorio, judicial ou contractual')
        face = number(raw.get('face_amount'), f'Crédito {i}: face_amount', minimum=Decimal('.01'))
        face_total += face
        credit['face_amount'] = money(face)
        evidence = {'credit_id': credit['credit_id'], 'source_ref': source}
        for key in ('document_ref', 'process_number', 'court', 'precatorio_number', 'nature',
                    'final_judgment_ref', 'requisition_ref', 'payment_order_ref', 'holder_check_ref',
                    'encumbrance_ref', 'dispute_ref'):
            credit[key] = text(raw.get(key), f'Crédito {i}: {key}', optional=True)
            if credit[key] and key.endswith('_ref'):
                sources.append(credit[key])
        if not credit['document_ref']:
            flag(alerts, 'CREDIT_DOCUMENT_MISSING', 'Documento de origem não referenciado', row=i, evidence=evidence)
        if credit['kind'] in ('precatorio', 'judicial'):
            for key in ('process_number', 'court'):
                if not credit[key]:
                    flag(alerts, key.upper() + '_MISSING', 'Identificação judicial incompleta: ' + key, row=i, evidence=evidence)
        if credit['kind'] == 'precatorio':
            for key, message in [('precatorio_number', 'Número do precatório pendente'),
                                 ('final_judgment_ref', 'Referência do trânsito em julgado pendente'),
                                 ('requisition_ref', 'Referência do requisitório pendente'),
                                 ('payment_order_ref', 'Referência de posição/lista de pagamento pendente')]:
                if not credit[key]:
                    flag(alerts, key.upper() + '_MISSING', message, row=i, evidence=evidence)
            if credit['court'] and credit['precatorio_number']:
                precatorios[(credit['court'], credit['precatorio_number'], credit['original_holder_ref'])].append(i)
        for key, ref in [('claim_confirmed', 'document_ref'), ('holder_confirmed', 'holder_check_ref')]:
            value = raw.get(key)
            if value is not None and type(value) is not bool:
                raise InputError(key + ' deve ser true, false ou null')
            if value is True and not credit[ref]:
                raise InputError(key + ' exige referência de evidência: ' + ref)
            credit[key] = value
            if value is not True:
                flag(alerts, key.upper() + ('_NEGATIVE' if value is False else '_PENDING'),
                     ('Existência do crédito' if key == 'claim_confirmed' else 'Titularidade') +
                     (' não confirmada' if value is False else ' pendente de confirmação'), row=i, evidence=evidence)
        for key, reference in [('encumbrance_status', 'encumbrance_ref'), ('dispute_status', 'dispute_ref')]:
            value = raw.get(key, 'unknown')
            if value not in ('unknown', 'none', 'present'):
                raise InputError(key + ' deve ser unknown, none ou present')
            credit[key] = value
            if value == 'present':
                flag(alerts, key.upper() + '_PRESENT', 'Restrição/ônus informado' if key.startswith('encumbrance') else 'Disputa informada',
                     row=i, evidence={**evidence, 'reference': credit[reference]})
            if value == 'unknown' or not credit[reference]:
                flag(alerts, key.upper() + '_CHECK_PENDING', 'Conferência de ônus/restrições pendente' if key.startswith('encumbrance') else 'Conferência de disputas pendente', row=i, evidence=evidence)
        values = {key: optional_amount(raw, key, f'Crédito {i}') for key in ('document_amount', 'paid_amount', 'reserved_amount')}
        for key, value in values.items():
            credit[key] = money(value) if value is not None else None
        if values['document_amount'] is None:
            flag(alerts, 'CREDIT_DOCUMENT_VALUE_PENDING', 'Valor documental não informado', row=i, evidence=evidence)
        elif values['document_amount'] != face:
            flag(alerts, 'CREDIT_AMOUNT_MISMATCH', 'Valor nominal diverge do suporte documental informado', row=i,
                 evidence={**evidence, 'face_amount': money(face), 'document_amount': money(values['document_amount'])})
        paid, reserved = values['paid_amount'], values['reserved_amount']
        if paid is None or reserved is None:
            credit['reference_after_deductions'] = None
            flag(alerts, 'PAYMENT_RESERVE_DATA_PENDING', 'Pagamentos ou reservas não conferidos; referência líquida não calculada', row=i, evidence=evidence)
        else:
            remainder = face - paid - reserved
            credit['reference_after_deductions'] = money(max(remainder, Decimal(0)))
            if remainder < 0:
                flag(alerts, 'DEDUCTIONS_EXCEED_FACE', 'Pagamentos e reservas excedem o valor nominal informado', row=i,
                     evidence={**evidence, 'raw_balance': money(remainder)})
        credit['assignment_chain'] = analyze_assignments(raw.get('assignments', []), credit, as_of, alerts, sources)
        credit['economic'] = economic_scenarios(raw.get('economic'), credit, alerts)
        share = credit['assignment_chain']['declared_holder_nominal_share']
        if credit['economic'] and share is not None and Decimal(credit['economic']['acquired_face_amount']) > Decimal(share):
            flag(alerts, 'ACQUISITION_EXCEEDS_DECLARED_NOMINAL_SHARE',
                 'Parcela simulada excede a participação nominal reconstruída do titular declarado', row=i,
                 evidence={**evidence, 'acquired_face_amount': credit['economic']['acquired_face_amount'],
                           'declared_holder_nominal_share': share})
        ids[credit['credit_id']].append(i)
        if credit['document_ref']:
            documents[(credit['document_ref'], credit['original_holder_ref'], credit['debtor_ref'])].append(i)
        credits.append(credit)
    for code, groups in [('REPEATED_CREDIT_ID', ids), ('POSSIBLE_REPEATED_PRECATORIO', precatorios),
                         ('POSSIBLE_REPEATED_CREDIT_DOCUMENT', documents)]:
        for key, rows in groups.items():
            if len(rows) > 1:
                flag(alerts, code, 'Possível repetição dentro da carteira; conferir parcelas e participações',
                     evidence={'rows': rows, 'key': list(key) if isinstance(key, tuple) else key, 'source_ref': source})
    return {'module': 'credits', 'engine_version': VERSION, 'name': name, 'as_of': as_of,
            'linked_fidc_analysis_id': linked, 'credits': credits, 'alerts': alerts,
            'sources': sorted(set(sources)), 'reference_sources': REFERENCES,
            'summary': {'credit_count': len(credits), 'declared_face_total': money(face_total), 'alert_count': len(alerts)},
            'method': 'Diligência sobre dados e referências documentais declarados. Sem consulta automática a tribunais, '
                      'autenticação de documentos ou certificação de titularidade/exigibilidade. '
                      'Cadeias nominais e cenários são reconstruções condicionadas aos dados fornecidos; '
                      'o prazo do cenário não é previsão de pagamento.'}
