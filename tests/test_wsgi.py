import importlib

from src import db
from src.app import create_app
from src.models.financial_analysis import FinancialAnalysis


def test_render_entrypoint_creates_tables_without_erasing_records(monkeypatch, tmp_path):
    uri = 'sqlite:///' + str(tmp_path / 'render-startup.db')
    monkeypatch.setattr('src.app.create_app', lambda: create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': uri}))
    entrypoint = importlib.import_module('wsgi')
    with entrypoint.app.app_context():
        item = FinancialAnalysis(module='fidc', name='Registro preservado', input_payload={},
                                 result_payload={}, input_sha256='0'*64, result_sha256='0'*64)
        db.session.add(item)
        db.session.commit()
        identifier = item.id
    entrypoint = importlib.reload(entrypoint)
    with entrypoint.app.app_context():
        assert db.session.get(FinancialAnalysis, identifier).name == 'Registro preservado'
