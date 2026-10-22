from src import db
from src.app import create_app
from src.database import db as database_db
from src.models import Customer, KycProcess, User


def test_models_share_database_and_create_tables():
    assert database_db is db
    for model in (Customer, KycProcess, User):
        assert model.metadata is db.metadata
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        assert Customer.query.count() == 0
        assert User.query.count() == 0
        assert KycProcess.query.count() == 0


def test_database_configuration_is_applied_before_engine_creation():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        assert db.engine.url.database == ':memory:'
