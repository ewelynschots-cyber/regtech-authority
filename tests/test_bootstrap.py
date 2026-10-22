import importlib
import io
from unittest.mock import patch
import pytest
from werkzeug.security import generate_password_hash
from sqlalchemy import text
from src import db
from src.app import create_app
from src.bootstrap import bootstrap_admin, validate_hash, KEYS
from src.models import User, Role
from src.models.access import Organization
from src.models.financial_analysis import FinancialAnalysis

PASSWORD = 'senha-inteiramente-ficticia-2026'


@pytest.fixture(scope='module')
def hash_value():
    return generate_password_hash(PASSWORD, method='pbkdf2:sha256:1000000', salt_length=16)


@pytest.fixture
def settings(hash_value):
    return dict(zip(KEYS, ['admin@example.test', hash_value, 'Administrador fictício', 'Organização fictícia']))


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'AUTH_COOKIE_SECURE': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'bootstrap.db')})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_disabled_without_environment(app):
    assert bootstrap_admin({}) is None
    assert User.query.count() == Organization.query.count() == 0
    assert app.test_client().post('/api/auth/login', json={'email':'admin@example.test','password':PASSWORD}).status_code == 401


def test_creates_admin_with_supplied_hash_and_allows_real_login(app, settings):
    user = bootstrap_admin(settings)
    assert user.role == Role.admin and user.is_active
    assert user.password_hash == settings['INITIAL_ADMIN_PASSWORD_HASH']
    client = app.test_client()
    response = client.post('/api/auth/login', json={'email':'admin@example.test','password':PASSWORD})
    assert response.status_code == 200
    assert client.get('/api/auth/me').json['user']['organization']['name'] == 'Organização fictícia'
    assert 'password_hash' not in response.json['user']


def test_restart_does_not_reset_password_or_replace_user(app, settings):
    original = bootstrap_admin(settings)
    identifier, organization_id = original.id, original.organization_id
    new_hash = generate_password_hash('outra-senha-ficticia-2026', method='pbkdf2:sha256:1000000')
    again = bootstrap_admin({**settings, 'INITIAL_ADMIN_PASSWORD_HASH': new_hash})
    assert again.id == identifier and again.organization_id == organization_id
    assert again.verify_password(PASSWORD)
    assert not again.verify_password('outra-senha-ficticia-2026')
    assert User.query.count() == Organization.query.count() == 1


@pytest.mark.parametrize('field', KEYS)
def test_partial_settings_fail_closed_without_secret_in_error(app, settings, field):
    settings[field] = ''
    with pytest.raises(RuntimeError) as error:
        bootstrap_admin(settings)
    assert settings['INITIAL_ADMIN_PASSWORD_HASH'] not in str(error.value) if settings['INITIAL_ADMIN_PASSWORD_HASH'] else True
    assert User.query.count() == Organization.query.count() == 0


@pytest.mark.parametrize('value', ['password', 'pbkdf2:sha256:1$abcdefghijklmnop$'+'0'*64,
    'pbkdf2:sha256:9999999$abcdefghijklmnop$'+'0'*64, 'scrypt:32768:8:1$abcd$'+'0'*128, 'x'*1000])
def test_weak_unknown_and_excessive_hashes_are_rejected(app, settings, value):
    settings['INITIAL_ADMIN_PASSWORD_HASH'] = value
    with pytest.raises(RuntimeError):
        bootstrap_admin(settings)
    assert User.query.count() == 0


@pytest.mark.parametrize('role,active', [('viewer',True),('analyst',True),('admin',False)])
def test_never_elevates_or_reactivates_existing_account(app, settings, role, active):
    original = bootstrap_admin(settings)
    original.role, original.is_active = Role(role), active
    db.session.commit()
    with pytest.raises(RuntimeError):
        bootstrap_admin(settings)
    db.session.refresh(original)
    assert original.role == Role(role) and original.is_active == active


def test_different_organization_or_email_is_not_adopted(app, settings):
    bootstrap_admin(settings)
    for changes in [{'INITIAL_ORGANIZATION_NAME':'Outra organização'}, {'INITIAL_ADMIN_EMAIL':'other@example.test'}]:
        with pytest.raises(RuntimeError):
            bootstrap_admin({**settings, **changes})
    assert Organization.query.count() == User.query.count() == 1


def test_preserves_legacy_and_unassigned_records(app, settings):
    db.session.execute(text('CREATE TABLE financial_analyses (id TEXT PRIMARY KEY, name TEXT)'))
    db.session.execute(text("INSERT INTO financial_analyses VALUES ('legacy','preservado')"))
    record = FinancialAnalysis(module='fidc',name='Não atribuído',input_payload={},result_payload={},input_sha256='0'*64,result_sha256='0'*64)
    db.session.add(record);db.session.commit()
    bootstrap_admin(settings)
    assert db.session.execute(text("SELECT name FROM financial_analyses WHERE id='legacy'")).scalar() == 'preservado'
    assert record.organization_id is None


def test_wsgi_initializes_from_environment_and_survives_restart(app, settings, monkeypatch):
    monkeypatch.setattr('src.app.create_app', lambda: app)
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    entrypoint = importlib.import_module('wsgi')
    importlib.reload(entrypoint)
    assert User.query.count() == Organization.query.count() == 1
    assert User.query.one().verify_password(PASSWORD)


def test_empty_replacement_database_recreates_access_only(tmp_path, settings):
    # Models the ephemeral disk being replaced: access can return, old business data cannot.
    identifiers = []
    for name in ('before.db','after.db'):
        app = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/name)})
        with app.app_context():
            db.create_all()
            user = bootstrap_admin(settings)
            identifiers.append(user.organization_id)
            assert user.verify_password(PASSWORD)
            assert FinancialAnalysis.query.count() == 0
    assert identifiers[0] != identifiers[1]


def test_local_hash_helper_never_echoes_plain_password(hash_value):
    from scripts.generate_admin_hash import main
    output = io.StringIO()
    with patch('scripts.generate_admin_hash.getpass.getpass', side_effect=[PASSWORD,PASSWORD]), patch('sys.stdout',output):
        main()
    result = output.getvalue()
    assert PASSWORD not in result
    encoded = result.strip().splitlines()[-1]
    assert validate_hash(encoded)
    from werkzeug.security import check_password_hash
    assert check_password_hash(encoded, PASSWORD)


def test_local_hash_helper_rejects_mismatch():
    from scripts.generate_admin_hash import main
    with patch('scripts.generate_admin_hash.getpass.getpass', side_effect=[PASSWORD,'diferente']):
        with pytest.raises(SystemExit):
            main()
