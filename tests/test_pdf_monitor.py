import io
from unittest.mock import patch
from pypdf import PdfWriter
from tests.test_automation import client,PROCESS
from src.services.pdf_extraction import extract_pdf
from src.services.financial_analysis import InputError
from src.services.rechecks import run_due
from src.models.source_lookup import SourceLookup
from src import db
import pytest


def test_invalid_pdf(client):
    response=client.post('/api/automation/documents/extract',data={'file':(io.BytesIO(b'not pdf'),'x.pdf')})
    assert response.status_code==400


def test_blank_pdf_is_partial():
    writer=PdfWriter();writer.add_blank_page(width=100,height=100);output=io.BytesIO();writer.write(output)
    with patch('src.services.pdf_extraction.shutil.which',return_value=None):
        result=extract_pdf(output.getvalue())
    assert not result['complete']
    assert result['pages'][0]['method']=='ocr_unavailable'


def test_zero_page_pdf_is_rejected(client):
    output = io.BytesIO()
    PdfWriter().write(output)
    response = client.post('/api/automation/documents/extract',
                           data={'file': (io.BytesIO(output.getvalue()), 'empty.pdf')})
    assert response.status_code == 400
    assert '1 a 10' in response.json['message']


def test_truncated_page_is_not_complete():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    with patch('pypdf._page.PageObject.extract_text', return_value='A' * 40001):
        result = extract_pdf(output.getvalue())
    assert result['complete'] is False
    assert result['pages'][0]['truncated'] is True
    assert len(result['pages'][0]['text']) == 40000


def test_monitor_recheck_once_and_disable(client):
    assert client.post('/api/automation/monitors',json={'process_number':PROCESS}).status_code==201
    payload={'checked_at':'2026-10-22T00:00:00+00:00','status':'unavailable','error_code':'timeout'}
    with client.application.app_context(),patch('src.services.rechecks.lookup_process',return_value=payload) as lookup:
        assert run_due()==1
        assert run_due()==0
        assert lookup.call_count==1
        assert SourceLookup.query.count()==1
    assert client.post('/api/automation/monitors',json={'process_number':PROCESS,'enabled':False}).json['enabled'] is False


def test_reject_non_boolean_monitor(client):
    assert client.post('/api/automation/monitors',json={'process_number':PROCESS,'enabled':'false'}).status_code==400


def test_scheduler_requires_identity(client):
    assert client.post('/api/automation/run-due').status_code == 401


def test_scheduler_rejects_wrong_workflow(client):
    with patch('jwt.PyJWKClient') as keys,patch('jwt.decode',return_value={'sub':'repo:other:ref:refs/heads/main','workflow_ref':'other'}):
        assert client.post('/api/automation/run-due',headers={'Authorization':'Bearer fake'}).status_code==403


def test_scheduler_accepts_exact_identity(client):
    claims={'sub':'repo:ewelynschots-cyber/regtech-authority:ref:refs/heads/main','workflow_ref':'ewelynschots-cyber/regtech-authority/.github/workflows/rechecks.yml@refs/heads/main'}
    with patch('jwt.PyJWKClient'),patch('jwt.decode',return_value=claims),patch('src.services.rechecks.run_due',return_value=0):
        assert client.post('/api/automation/run-due',headers={'Authorization':'Bearer fake'}).json=={'processed':0}


def test_text_pdf_candidates():
    from reportlab.pdfgen import canvas
    output=io.BytesIO();pdf=canvas.Canvas(output)
    pdf.drawString(40,750,'Processo 0000832-35.2018.4.01.3202 valor R$ 1.234,56')
    pdf.save()
    result=extract_pdf(output.getvalue())
    assert result['complete']
    assert {c['field'] for c in result['candidates']}=={'process_number','amount_unclassified'}


def test_scanned_pdf_ocr():
    import shutil
    if not shutil.which('tesseract') or not shutil.which('pdftoppm'):
        pytest.skip('OCR binaries unavailable')
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGB',(1600,400),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',38)
    draw.text((40,80),'Processo 0000832-35.2018.4.01.3202',fill='black',font=font)
    output=io.BytesIO();image.save(output,format='PDF')
    result=extract_pdf(output.getvalue())
    assert result['pages'][0]['method']=='ocr'
    assert result['complete']
    assert any(c['field']=='process_number' for c in result['candidates'])
