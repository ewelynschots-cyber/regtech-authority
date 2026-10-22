"""Bounded local extraction. Suggestions never confirm legal facts."""
import hashlib
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from pypdf import PdfReader
from src.services.financial_analysis import InputError


def extract_pdf(data):
    if not data or len(data) > 3_000_000 or not data.startswith(b'%PDF-'):
        raise InputError('Envie um PDF de até 3 MB.')
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 10:
            raise InputError('Use PDF sem senha, com até 10 páginas.')
        pages = []
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.pdf'
            source.write_bytes(data)
            for index, page in enumerate(reader.pages):
                value = (page.extract_text() or '')[:40000]
                method = 'text'
                if len(value.strip()) < 30:
                    method = 'ocr_unavailable'
                    if index < 2 and shutil.which('pdftoppm') and shutil.which('tesseract'):
                        target = str(Path(folder) / 'page')
                        try:
                            subprocess.run(['pdftoppm','-f',str(index+1),'-l',str(index+1),'-singlefile','-scale-to','1800','-png',str(source),target],check=True,timeout=8,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                            result = subprocess.run(['tesseract',target+'.png','stdout','-l','eng'],check=True,timeout=8,capture_output=True)
                            value = result.stdout.decode('utf-8',errors='replace')[:40000]
                            method = 'ocr'
                        except (subprocess.SubprocessError,OSError):
                            method = 'ocr_failed'
                pages.append({'page':index+1,'method':method,'text':value})
    except InputError:
        raise
    except Exception as exc:
        raise InputError('Não foi possível ler este PDF.') from exc
    candidates = []
    for page in pages:
        for match in re.finditer(r'\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b',page['text']):
            candidates.append({'field':'process_number','value':match.group(),'page':page['page'],'method':page['method']})
        for match in re.finditer(r'R\$\s*\d[\d.]*,\d{2}',page['text']):
            candidates.append({'field':'amount_unclassified','value':match.group(),'page':page['page'],'method':page['method']})
    return {'sha256':hashlib.sha256(data).hexdigest(),'pages':pages,'candidates':candidates[:100],
            'requires_review':True,'complete':all(p['text'].strip() and p['method'] in ('text','ocr') for p in pages),
            'notice':'Confira página e contexto. Valores não identificam saldo nem confirmam titularidade.'}
