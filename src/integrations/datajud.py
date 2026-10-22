"""Bounded, read-only access to public DataJud metadata."""
import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from src.services.financial_analysis import InputError

HOST = 'https://api-publica.datajud.cnj.jus.br/'
STATE_ALIASES = ['tjac','tjal','tjap','tjam','tjba','tjce','tjdft','tjes','tjgo','tjma',
                 'tjmt','tjms','tjmg','tjpa','tjpb','tjpr','tjpe','tjpi','tjrj','tjrn',
                 'tjrs','tjro','tjrr','tjsc','tjse','tjsp','tjto']
SOURCE_FIELDS = ['id','numeroProcesso','tribunal','grau','classe','assuntos','orgaoJulgador',
                 'dataAjuizamento','dataHoraUltimaAtualizacao','movimentos','nivelSigilo']


def identify_process(value):
    if not isinstance(value,str) or len(value)>50:
        raise InputError('Informe o número CNJ do processo')
    digits=re.sub(r'[.\-\s]','',value)
    if not re.fullmatch(r'[0-9]{20}',digits):
        raise InputError('Número CNJ deve conter 20 dígitos')
    if int(digits[:7]+digits[9:]+digits[7:9])%97!=1:
        raise InputError('Dígito verificador do processo inválido')
    branch,region=int(digits[13]),int(digits[14:16])
    alias=None
    if branch==8 and 1<=region<=27: alias=STATE_ALIASES[region-1]
    elif branch==4 and 1<=region<=6: alias='trf'+str(region)
    elif branch==5 and 1<=region<=24: alias='trt'+str(region)
    return {'number':digits,'formatted':f'{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}',
            'court':alias.upper() if alias else None,'alias':alias}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def post_public_metadata(url,body,key):
    request=urllib.request.Request(url,data=json.dumps(body).encode(),
        headers={'Authorization':'APIKey '+key,'Content-Type':'application/json','Accept':'application/json'})
    opener=urllib.request.build_opener(NoRedirect())
    with opener.open(request,timeout=8) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('response_limit')
        return raw


def lookup_process(number,key,transport=None):
    process=identify_process(number)
    result={'provider':'datajud','process':process,'checked_at':datetime.now(timezone.utc).isoformat(),
            'status':'unavailable','source_url':None,'records':[],'complete':False,
            'error_code':None,'response_sha256':None}
    if not process['alias']:
        result['error_code']='unsupported_court'
        return result
    url=HOST+'api_publica_'+process['alias']+'/_search'
    result['source_url']=url
    if not key:
        result['error_code']='not_configured'
        return result
    body={'size':100,'query':{'bool':{'must':[{'match':{'numeroProcesso':process['number']}}],
                                    'filter':[{'term':{'nivelSigilo':0}}]}},'_source':SOURCE_FIELDS}
    try:
        raw=(transport or post_public_metadata)(url,body,key)
        result['response_sha256']=hashlib.sha256(raw).hexdigest()
        def invalid_constant(value):
            raise ValueError('invalid_response')
        data=json.loads(raw,parse_constant=invalid_constant)
        hits=data['hits']['hits']
        if not isinstance(hits,list) or len(hits)>100: raise ValueError('invalid_response')
        total=data['hits'].get('total',len(hits))
        total_value=total.get('value') if isinstance(total,dict) else total
        exact_total=not isinstance(total,dict) or total.get('relation','eq')=='eq'
        if type(total_value) is not int or total_value<0 or total_value<len(hits): raise ValueError('invalid_response')
        records=[]
        for hit in hits:
            source=hit['_source']
            if not isinstance(source,dict) or source.get('numeroProcesso')!=process['number'] or source.get('nivelSigilo') not in (0,'0'):
                raise ValueError('invalid_response')
            # Retain only documented public fields even if the upstream ignores _source.
            record={k:source[k] for k in SOURCE_FIELDS if k in source}
            if not isinstance(record.get('movimentos',[]),list): raise ValueError('invalid_response')
            records.append(record)
        complete=exact_total and total_value==len(hits) and data.get('timed_out',False) is False
        result.update(status='found' if records else ('not_found' if complete else 'unavailable'),
                      records=records,complete=complete,total_matches=total_value,
                      error_code=None if complete else 'partial_response')
    except urllib.error.HTTPError as exc:
        result['error_code']='access_rejected' if exc.code in (401,403) else 'rate_limited' if exc.code==429 else 'upstream_http_error'
    except (TimeoutError,socket.timeout): result['error_code']='timeout'
    except urllib.error.URLError: result['error_code']='connection_error'
    except OSError: result['error_code']='connection_error'
    except (ValueError,KeyError,TypeError,UnicodeError,RecursionError): result['error_code']='invalid_response'
    return result
