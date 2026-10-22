"""Deterministic diligence checks on supplied data; no external source is fetched."""
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median

ENGINE_VERSION = '1.0.0'
CVM_SOURCE = 'https://conteudo.cvm.gov.br/legislacao/resolucoes/resol175.html'
FGC_SOURCE = 'https://www.bcb.gov.br/estabilidadefinanceira/Fundosgarantidores'


class InputError(ValueError):
    pass


def object_fields(value, allowed, label):
    if not isinstance(value, dict):
        raise InputError(f'{label}: informe um objeto')
    unknown = set(value) - set(allowed)
    if unknown:
        raise InputError(f'{label}: campos desconhecidos: {", ".join(sorted(unknown))}')
    return value


def text(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise InputError(f'{label}: informe texto entre 1 e 1000 caracteres')
    return value.strip()


def iso_date(value, label):
    value = text(value, label)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InputError(f'{label}: use AAAA-MM-DD')
    if parsed.isoformat() != value:
        raise InputError(f'{label}: use AAAA-MM-DD')
    if parsed > date.today():
        raise InputError(f'{label}: data futura não permitida')
    return value


def number(value, label, *, minimum=None, places=2):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InputError(f'{label}: informe um número decimal')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise InputError(f'{label}: número inválido')
    if not result.is_finite() or abs(result) > Decimal('1000000000000000'):
        raise InputError(f'{label}: número fora do intervalo')
    if minimum is not None and result < minimum:
        raise InputError(f'{label}: valor inferior ao mínimo {minimum}')
    if result != result.quantize(Decimal(10) ** -places):
        raise InputError(f'{label}: use no máximo {places} casas decimais')
    return result


def money(value):
    return format(value.quantize(Decimal('.01')), 'f')


def flag(alerts, code, message, *, row=None, evidence=None):
    alerts.append({'id': f'A{len(alerts)+1:04d}', 'code': code,
                   'message': message, 'row': row, 'evidence': evidence or {}, 'status': 'open'})


def canonical_hash(payload):
    try:
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError):
        raise InputError('A entrada deve conter somente valores JSON finitos')
    return hashlib.sha256(content.encode()).hexdigest()


def list_rows(value, label, maximum=5000, allow_empty=False):
    if not isinstance(value, list) or len(value) > maximum or (not value and not allow_empty):
        raise InputError(f'{label}: informe uma lista com {0 if allow_empty else 1} a {maximum} itens')
    return value


FIDC_FIELDS = {'title_id', 'originator_id', 'debtor_id', 'amount', 'document_ref',
               'document_amount', 'document_sha256', 'assignment_ref', 'installment',
               'existence_confirmed', 'ownership_confirmed'}


def analyze_fidc(payload):
    object_fields(payload, {'name', 'as_of', 'source_ref', 'receivables'}, 'Carteira')
    name = text(payload.get('name'), 'name')
    as_of = iso_date(payload.get('as_of'), 'as_of')
    source = text(payload.get('source_ref'), 'source_ref')
    rows = list_rows(payload.get('receivables'), 'receivables')
    alerts, normalized = [], []
    ids, documents = defaultdict(list), defaultdict(list)
    total = Decimal(0)
    for i, raw in enumerate(rows, 1):
        object_fields(raw, FIDC_FIELDS, f'Linha {i}')
        row = {'row': i}
        for field in ('title_id', 'originator_id', 'debtor_id'):
            row[field] = text(raw.get(field), f'Linha {i}: {field}')
        value = number(raw.get('amount'), f'Linha {i}: amount', minimum=Decimal('.01'))
        row['amount'] = money(value)
        total += value
        for field in ('document_ref', 'assignment_ref', 'installment', 'document_sha256'):
            row[field] = text(raw.get(field), f'Linha {i}: {field}', optional=True)
        if row['document_sha256'] and not re.fullmatch(r'[a-fA-F0-9]{64}', row['document_sha256']):
            raise InputError(f'Linha {i}: document_sha256 inválido')
        doc_amount = raw.get('document_amount')
        row['document_amount'] = None
        if doc_amount not in (None, ''):
            doc_amount = number(doc_amount, f'Linha {i}: document_amount', minimum=Decimal(0))
            row['document_amount'] = money(doc_amount)
        evidence = {'source_ref': source, 'title_id': row['title_id'], 'document_ref': row['document_ref']}
        if not row['document_ref']:
            flag(alerts, 'DOCUMENT_MISSING', 'Referência documental ausente', row=i, evidence=evidence)
        if not row['assignment_ref']:
            flag(alerts, 'ASSIGNMENT_MISSING', 'Referência de cessão ausente', row=i, evidence=evidence)
        if doc_amount in (None, ''):
            flag(alerts, 'DOCUMENT_VALUE_MISSING', 'Valor do suporte documental não informado', row=i, evidence=evidence)
        elif doc_amount != value:
            flag(alerts, 'AMOUNT_MISMATCH', 'Valor do título difere do valor documental informado', row=i,
                 evidence={**evidence, 'title_amount': money(value), 'document_amount': money(doc_amount)})
        for field in ('existence_confirmed', 'ownership_confirmed'):
            confirmation = raw.get(field)
            if confirmation is not None and type(confirmation) is not bool:
                raise InputError(f'Linha {i}: {field} deve ser true, false ou null')
            if confirmation is True and not row['document_ref']:
                raise InputError(f'Linha {i}: confirmação exige referência documental')
            if field == 'ownership_confirmed' and confirmation is True and not row['assignment_ref']:
                raise InputError(f'Linha {i}: titularidade confirmada exige referência de cessão')
            row[field] = confirmation
            if confirmation is not True:
                flag(alerts, field.upper() + ('_NEGATIVE' if confirmation is False else '_PENDING'),
                     'Existência' + (' não confirmada' if confirmation is False else ' pendente de confirmação')
                     if field == 'existence_confirmed' else
                     'Titularidade' + (' não confirmada' if confirmation is False else ' pendente de confirmação'),
                     row=i, evidence=evidence)
        ids[row['title_id']].append(i)
        if row['document_ref'] and row['installment']:
            documents[(row['originator_id'], row['debtor_id'], row['document_ref'], row['installment'])].append(i)
        normalized.append(row)
    for code, groups in [('DUPLICATE_TITLE_ID', ids), ('POSSIBLE_DUPLICATE_RECEIVABLE', documents)]:
        for key, indexes in groups.items():
            if len(indexes) > 1:
                flag(alerts, code, 'Possível duplicidade dentro da carteira importada',
                     evidence={'rows': indexes, 'key': list(key) if isinstance(key, tuple) else key, 'source_ref': source})
    return {'module': 'fidc', 'engine_version': ENGINE_VERSION, 'name': name, 'as_of': as_of,
            'sources': [source], 'reference_sources': [CVM_SOURCE],
            'summary': {'receivable_count': len(rows), 'declared_total': money(total),
                        'alert_count': len(alerts)}, 'receivables': normalized, 'alerts': alerts,
            'method': 'Conferência dos dados declarados, por linha. Duplicidades restritas à carteira; '
                      'referências e hashes informados não equivalem à leitura ou autenticação dos documentos.'}


def csv_receivables(content):
    try:
        return _csv_receivables(content)
    except csv.Error:
        raise InputError('CSV inválido: confira aspas e separadores')


def _csv_receivables(content):
    if not isinstance(content, str) or len(content.encode('utf-8')) > 2_000_000:
        raise InputError('CSV excede 2 MB')
    # Explicit decimal convention: dot; delimiters comma or semicolon.
    first_line = content.lstrip('\ufeff').splitlines()[0] if content.strip() else ''
    delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), delimiter=delimiter, strict=True)
    headers = reader.fieldnames
    if not headers or len(headers) != len(set(headers)) or set(headers) - FIDC_FIELDS:
        raise InputError('Cabeçalhos CSV inválidos ou repetidos')
    if {'title_id', 'originator_id', 'debtor_id', 'amount'} - set(headers):
        raise InputError('CSV exige title_id, originator_id, debtor_id e amount')
    rows = []
    for raw in reader:
        if None in raw or any(value is None for value in raw.values()):
            raise InputError('Linha CSV com quantidade incorreta de colunas')
        row = {k: v.strip() for k, v in raw.items()}
        for field in ('existence_confirmed', 'ownership_confirmed'):
            if field in row:
                values = {'true': True, 'false': False, '': None}
                if row[field].lower() not in values:
                    raise InputError(f'CSV: {field} aceita true, false ou vazio')
                row[field] = values[row[field].lower()]
        rows.append(row)
        if len(rows) > 5000:
            raise InputError('CSV excede 5000 linhas')
    return rows


OFFER_FIELDS = {'offer_id', 'issuer_ref', 'conglomerate_ref', 'rate_percent_cdi',
                'term_days', 'liquidity', 'as_of', 'source_ref', 'indexer', 'currency'}


def offer_data(raw, label):
    object_fields(raw, OFFER_FIELDS, label)
    row = {key: text(raw.get(key), f'{label}: {key}') for key in
           ('offer_id', 'issuer_ref', 'conglomerate_ref', 'liquidity', 'source_ref', 'indexer', 'currency')}
    row['as_of'] = iso_date(raw.get('as_of'), f'{label}: as_of')
    row['rate_percent_cdi'] = money(number(raw.get('rate_percent_cdi'), f'{label}: rate_percent_cdi', minimum=Decimal(0)))
    if type(raw.get('term_days')) is not int or not 1 <= raw['term_days'] <= 36500:
        raise InputError(f'{label}: term_days deve ser inteiro entre 1 e 36500')
    if row['indexer'] != 'CDI' or row['currency'] != 'BRL':
        raise InputError(f'{label}: esta versão aceita indexer CDI e currency BRL')
    if row['liquidity'] not in ('daily', 'at_maturity'):
        raise InputError(f'{label}: liquidity aceita daily ou at_maturity')
    row['term_days'] = raw['term_days']
    return row


def exposure_analysis(payload, candidate, alerts, sources):
    raw_positions = list_rows(payload.get('positions', []), 'positions', allow_empty=True)
    groups, positions = defaultdict(Decimal), []
    for i, raw in enumerate(raw_positions, 1):
        object_fields(raw, {'position_id', 'conglomerate_ref', 'balance', 'source_ref', 'as_of', 'eligible'}, f'Posição {i}')
        row = {k: text(raw.get(k), f'Posição {i}: {k}') for k in ('position_id', 'conglomerate_ref', 'source_ref')}
        row['as_of'] = iso_date(raw.get('as_of'), f'Posição {i}: as_of')
        if row['as_of'] != candidate['as_of']:
            raise InputError('Posições e oferta devem usar a mesma data-base')
        row['balance'] = money(number(raw.get('balance'), f'Posição {i}: balance', minimum=Decimal(0)))
        if raw.get('eligible') is not None and type(raw['eligible']) is not bool:
            raise InputError('eligible deve ser true, false ou null')
        row['eligible'] = raw.get('eligible')
        positions.append(row)
        groups[row['conglomerate_ref']] += Decimal(row['balance'])
        sources.append(row['source_ref'])
    if len({p['position_id'] for p in positions}) != len(positions):
        raise InputError('position_id repetido; corrija a exposição antes de analisar')
    total = sum(groups.values(), Decimal(0))
    exposure = [{'conglomerate_ref': group, 'balance': money(value),
                 'share_percent': money(value / total * 100) if total else '0.00'}
                for group, value in sorted(groups.items())]
    if not positions:
        flag(alerts, 'EXPOSURE_NOT_SUPPLIED', 'Exposição por conglomerado não informada')
    target_balance = groups.get(candidate['conglomerate_ref'], Decimal(0))
    # An optional, explicit client mandate; no universal risk threshold.
    limit = payload.get('concentration_limit_percent')
    if limit is not None:
        limit = number(limit, 'concentration_limit_percent', minimum=Decimal(0))
        if limit > 100:
            raise InputError('concentration_limit_percent deve ser de 0 a 100')
        for group in exposure:
            if total and groups[group['conglomerate_ref']] / total * 100 > limit:
                flag(alerts, 'CONCENTRATION_LIMIT_EXCEEDED', 'Concentração excede o limite informado pelo usuário',
                     evidence={**group, 'configured_limit_percent': money(limit)})
    fgc = {'status': 'not_requested'}
    if 'fgc' in payload:
        raw = object_fields(payload['fgc'], {'eligibility_confirmed', 'balances_include_interest',
                            'history_confirmed', 'prior_payments_current_window', 'source_ref'}, 'fgc')
        for key in ('eligibility_confirmed', 'balances_include_interest', 'history_confirmed'):
            if type(raw.get(key)) is not bool:
                raise InputError(f'fgc.{key}: informe true ou false')
        # Validate supplied values even if confirmations are incomplete.
        if raw.get('prior_payments_current_window') not in (None, ''):
            prior = number(raw['prior_payments_current_window'], 'prior_payments_current_window', minimum=Decimal(0))
            if prior > 1_000_000:
                raise InputError('Pagamentos anteriores excedem o teto da janela informada')
        if not all(raw[k] for k in ('eligibility_confirmed', 'balances_include_interest', 'history_confirmed')) or not positions or any(p['eligible'] is None for p in positions):
            fgc = {'status': 'insufficient_data', 'estimated_total': None}
            flag(alerts, 'FGC_DATA_INCOMPLETE', 'Estimativa FGC exige elegibilidade, saldos com juros e histórico conferidos')
        else:
            prior = number(raw.get('prior_payments_current_window'), 'prior_payments_current_window', minimum=Decimal(0))
            if prior > 1_000_000:
                raise InputError('Pagamentos anteriores excedem o teto da janela informada')
            sources.append(text(raw.get('source_ref'), 'fgc.source_ref'))
            eligible_groups = defaultdict(Decimal)
            for row in positions:
                if row['eligible']:
                    eligible_groups[row['conglomerate_ref']] += Decimal(row['balance'])
            before_global = sum((min(v, Decimal(250000)) for v in eligible_groups.values()), Decimal(0))
            remaining = Decimal(1000000) - prior
            estimated = min(before_global, remaining)
            fgc = {'status': 'conditional_estimate', 'estimated_total': money(estimated),
                   'group_limit': '250000.00', 'global_remaining': money(remaining),
                   'eligible_balance': money(sum(eligible_groups.values(), Decimal(0))),
                   'eligible_excess': money(sum(eligible_groups.values(), Decimal(0)) - estimated),
                   'reference_source': FGC_SOURCE,
                   'basis': 'Uma única titularidade declarada. Saldos incluem principal e juros; '
                            'pagamentos prévios pertencem à janela vigente de quatro anos, conferida pelo usuário. '
                            'Teto global aplicado ao conjunto, sem atribuição de prioridade entre conglomerados.'}
            if Decimal(fgc['eligible_excess']) > 0:
                flag(alerts, 'FGC_LIMIT_EXCEEDED', 'Saldo elegível informado excede a estimativa condicionada aos limites', evidence=fgc)
    return {'positions': positions, 'groups': exposure, 'total_balance': money(total),
            'target_group_balance': money(target_balance),
            'concentration_limit_percent': money(limit) if limit is not None else None, 'fgc': fgc}


def analyze_cdb(payload):
    object_fields(payload, {'name', 'offer', 'comparables', 'financials', 'positions',
                          'concentration_limit_percent', 'fgc'}, 'CDB')
    name = text(payload.get('name'), 'name')
    offer = offer_data(payload.get('offer'), 'Oferta')
    alerts, accepted, excluded = [], [], []
    sources = [offer['source_ref']]
    seen = {offer['offer_id']}
    peer_groups = set()
    for i, raw in enumerate(list_rows(payload.get('comparables', []), 'comparables', allow_empty=True), 1):
        other = offer_data(raw, f'Comparável {i}')
        if other['offer_id'] in seen:
            raise InputError('offer_id repetido entre a oferta e os comparáveis')
        seen.add(other['offer_id'])
        reasons = [key for key in ('term_days', 'liquidity', 'as_of', 'indexer', 'currency') if other[key] != offer[key]]
        if other['conglomerate_ref'] == offer['conglomerate_ref']:
            reasons.append('same_conglomerate')
        if other['conglomerate_ref'] in peer_groups:
            reasons.append('duplicate_peer_conglomerate')
        sources.append(other['source_ref'])
        if reasons:
            excluded.append({'offer': other, 'reasons': reasons})
        else:
            accepted.append(other)
            peer_groups.add(other['conglomerate_ref'])
    comparison = {'criteria': {'term_days': offer['term_days'], 'liquidity': offer['liquidity'],
                              'as_of': offer['as_of'], 'indexer': 'CDI', 'currency': 'BRL',
                              'exclude_target_conglomerate': True, 'one_offer_per_conglomerate': True,
                              'minimum_comparables': 3},
                  'accepted': accepted, 'excluded': excluded, 'median_percent_cdi': None,
                  'difference_percentage_points': None}
    if len(accepted) < 3:
        flag(alerts, 'INSUFFICIENT_COMPARABLES', 'Menos de três ofertas equivalentes informadas; comparação inconclusiva')
    else:
        center = median([Decimal(row['rate_percent_cdi']) for row in accepted])
        difference = Decimal(offer['rate_percent_cdi']) - center
        comparison.update(median_percent_cdi=format(center, 'f'), difference_percentage_points=format(difference, 'f'))
        if difference > 0:
            flag(alerts, 'RATE_ABOVE_COMPARABLE_MEDIAN', 'Taxa acima da mediana das ofertas equivalentes informadas',
                 evidence={'rate_percent_cdi': offer['rate_percent_cdi'], 'median_percent_cdi': format(center, 'f'),
                           'difference_percentage_points': format(difference, 'f'), 'source_refs': [r['source_ref'] for r in accepted]})
    financials = None
    raw = payload.get('financials')
    if raw is None:
        flag(alerts, 'FINANCIALS_MISSING', 'Dados financeiros do emissor não informados')
    else:
        object_fields(raw, {'issuer_ref', 'as_of', 'source_ref', 'equity', 'net_income', 'deposits'}, 'financials')
        issuer = text(raw.get('issuer_ref'), 'financials.issuer_ref')
        if issuer != offer['issuer_ref']:
            raise InputError('Dados financeiros pertencem a outro emissor')
        financials = {'issuer_ref': issuer, 'as_of': iso_date(raw.get('as_of'), 'financials.as_of'),
                      'source_ref': text(raw.get('source_ref'), 'financials.source_ref')}
        if financials['as_of'] > offer['as_of']:
            raise InputError('Dados financeiros posteriores à data-base da oferta')
        sources.append(financials['source_ref'])
        for key in ('equity', 'net_income', 'deposits'):
            financials[key] = money(number(raw.get(key), 'financials.' + key,
                                          minimum=Decimal(0) if key == 'deposits' else None))
        for key, code, message in [('equity', 'NONPOSITIVE_EQUITY', 'Patrimônio líquido não positivo no período informado'),
                                   ('net_income', 'NEGATIVE_NET_INCOME', 'Resultado negativo no período informado')]:
            value = Decimal(financials[key])
            if value < 0 or (key == 'equity' and value == 0):
                flag(alerts, code, message, evidence=dict(financials))
        equity = Decimal(financials['equity'])
        financials['deposits_to_equity'] = money(Decimal(financials['deposits']) / equity) if equity > 0 else None
    exposure = exposure_analysis(payload, offer, alerts, sources)
    return {'module': 'cdb', 'engine_version': ENGINE_VERSION, 'name': name, 'as_of': offer['as_of'],
            'offer': offer, 'comparison': comparison, 'financials': financials, 'exposure': exposure,
            'sources': sorted(set(sources)), 'reference_sources': [FGC_SOURCE], 'alerts': alerts,
            'summary': {'alert_count': len(alerts), 'comparable_count': len(accepted)},
            'method': 'Comparação descritiva de taxas fornecidas, com prazo, liquidez e data-base iguais. '
                      'Sem percentual fixo para definir risco e sem classificação de solvência. '
                      'Fontes são referências declaradas; esta versão não consulta bases externas.'}
