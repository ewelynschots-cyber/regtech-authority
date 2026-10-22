"""Temporary UI-test server: all DataJud requests use an explicit test fixture."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import db
from src.app import create_app
from src.integrations.datajud import lookup_process
import src.routes.automation as automation


def fixture_lookup(number,key):
    raw=json.dumps({'hits':{'total':{'value':1,'relation':'eq'},'hits':[{'_source':{
        'numeroProcesso':number,'nivelSigilo':0,'tribunal':'TRF1','grau':'G1',
        'classe':{'nome':'Classe fictícia do teste'},'orgaoJulgador':{'nome':'Órgão fictício do teste'},
        'dataHoraUltimaAtualizacao':'2026-10-20T10:00:00Z','movimentos':[]}}]}}).encode()
    return lookup_process(number,'mock-fixture-only',transport=lambda *args:raw)


if __name__=='__main__':
    automation.lookup_process=fixture_lookup
    app=create_app({'SQLALCHEMY_DATABASE_URI':'sqlite:///'+sys.argv[1],'DATAJUD_API_KEY':'test-key-not-real'})
    with app.app_context():db.create_all()
    app.run(port=int(sys.argv[2]))
