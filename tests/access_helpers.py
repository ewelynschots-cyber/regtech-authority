from src import db
from src.models import User
from src.models.access import Organization

PASSWORD = 'fictitious-password-2026'


def provision(app, email='admin@example.test', name='Revisor fictício', role='admin', organization=None):
    with app.app_context():
        org = organization or Organization(name='Organização fictícia '+email)
        db.session.add(org)
        db.session.flush()
        user = User(name=name, email=email, password=PASSWORD, role=role, organization_id=org.id)
        db.session.add(user)
        db.session.commit()
        app.config.setdefault('TEST_ORG_ID', org.id)
        return user.id, org.id


def signed_client(app, email='admin@example.test'):
    app.config['AUTH_COOKIE_SECURE'] = False
    client = app.test_client()
    result = client.post('/api/auth/login', json={'email':email, 'password':PASSWORD})
    assert result.status_code == 200, result.json
    client.environ_base['HTTP_X_CSRF_TOKEN'] = result.json['csrf_token']
    return client


def authenticated_client(app):
    provision(app)
    return signed_client(app)
