from tests.access_helpers import provision, signed_client
import pytest
from src.app import create_app, db
from src.models import User, Customer, KycProcess, KycStatus, RiskLevel, Status, CustomerType, Role

@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        provision(app)
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return signed_client(app)

def test_get_customers(client):
    response = client.get('/api/customers')
    assert response.status_code == 200

def test_create_customer(client):
    payload = {
        'name': 'New Customer',
        'email': 'new@test.com',
        'customer_type': 'PF',
        'cpf_cnpj': '52998224725',
        'phone': '11987654321',
        'address': 'Avenida Paulista, 1000',
        'risk_level': 'BAIXO',
        'status': 'PENDENTE'
    }
    response = client.post('/api/customers', json=payload)
    assert response.status_code == 201

def test_get_customer_by_id(client, app):
    with app.app_context():
        customer = Customer(
            organization_id=app.config["TEST_ORG_ID"],
            name='Test Customer',
            email='test@test.com',
            customer_type=CustomerType.PF,
            cpf_cnpj='52998224725',
            phone='11999999999',
            address='Rua Teste, 123',
            risk_level=RiskLevel.BAIXO,
            status=Status.PENDENTE
        )
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id
    
    response = client.get(f'/api/customers/{customer_id}')
    assert response.status_code == 200

def test_update_customer(client, app):
    with app.app_context():
        customer = Customer(
            organization_id=app.config["TEST_ORG_ID"],
            name='Test Customer',
            email='test@test.com',
            customer_type=CustomerType.PF,
            cpf_cnpj='52998224725',
            phone='11999999999',
            address='Rua Teste, 123',
            risk_level=RiskLevel.BAIXO,
            status=Status.PENDENTE
        )
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id
    
    payload = {'name': 'Updated Name'}
    response = client.put(f'/api/customers/{customer_id}', json=payload)
    assert response.status_code == 200

def test_delete_customer(client, app):
    with app.app_context():
        customer = Customer(
            organization_id=app.config["TEST_ORG_ID"],
            name='Test Customer',
            email='test@test.com',
            customer_type=CustomerType.PF,
            cpf_cnpj='52998224725',
            phone='11999999999',
            address='Rua Teste, 123',
            risk_level=RiskLevel.BAIXO,
            status=Status.PENDENTE
        )
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id
    
    response = client.delete(f'/api/customers/{customer_id}')
    assert response.status_code == 204

def test_get_kyc_processes(client):
    response = client.get('/api/kyc-processes')
    assert response.status_code == 200

def test_create_kyc_process(client, app):
    with app.app_context():
        analyst = User(
            organization_id=app.config["TEST_ORG_ID"],
            name='Analyst',
            email='analyst@test.com',
            password='pwd',
            role=Role.analyst
        )
        customer = Customer(
            organization_id=app.config["TEST_ORG_ID"],
            name='Test Customer',
            email='test@test.com',
            customer_type=CustomerType.PF,
            cpf_cnpj='52998224725',
            phone='11999999999',
            address='Rua Teste, 123',
            risk_level=RiskLevel.BAIXO,
            status=Status.PENDENTE
        )
        db.session.add_all([analyst, customer])
        db.session.commit()
        analyst_id = analyst.id
        customer_id = customer.id
    
    payload = {
        'customer_id': customer_id,
        'analyst_id': analyst_id,
        'status': 'INICIADO'
    }
    response = client.post('/api/kyc-processes', json=payload)
    assert response.status_code == 201


def payload(cpf='52998224725'):
    return {'name': 'Cliente teste', 'email': 'cliente@example.test',
            'customer_type': 'PF', 'cpf_cnpj': cpf, 'phone': '11999999999',
            'address': 'Rua de teste, 10'}


def test_customer_lifecycle(client):
    created = client.post('/api/customers', json=payload())
    assert created.status_code == 201
    identifier = created.json['id']
    assert created.json['customer_type'] == 'PF'
    assert len(client.get('/api/customers/').json) == 1
    assert client.get(f'/api/customers/{identifier}').json['customer']['name'] == 'Cliente teste'
    updated = client.put(f'/api/customers/{identifier}', json={'name': 'Nome atualizado'})
    assert updated.status_code == 200
    assert client.get(f'/api/customers/{identifier}').json['customer']['name'] == 'Nome atualizado'
    assert client.delete(f'/api/customers/{identifier}').status_code == 204
    assert client.get(f'/api/customers/{identifier}').status_code == 404


def test_customer_errors_do_not_write_partial_changes(client):
    assert client.post('/api/customers', json=payload()).status_code == 201
    assert client.post('/api/customers', json=payload()).status_code == 409
    for invalid in ({}, [], {'name': 'Incompleto'}, dict(payload(), customer_type='INVALIDO')):
        assert client.post('/api/customers', json=invalid).status_code == 400
    item = client.get('/api/customers').json[0]
    result = client.put(f"/api/customers/{item['id']}", json={'name': 'Não salvar', 'cpf_cnpj': '1'})
    assert result.status_code == 400
    assert client.get(f"/api/customers/{item['id']}").json['customer']['name'] == 'Cliente teste'
    assert len(client.get('/api/customers').json) == 1


def test_duplicate_address_returns_serializable_signal_without_writing_alerts(client, app):
    from src.services.address_alert_service import AddressAlert
    first = client.post('/api/customers', json=payload()).json['id']
    assert client.post('/api/customers', json=payload('11144477735')).status_code == 201
    for _ in range(2):
        response = client.get(f'/api/customers/{first}')
        assert response.status_code == 200
        assert len(response.json['address_alert']['duplicates']) == 2
        assert response.json['address_alert']['risk_level'] == 'LOW'
    with app.app_context():
        assert AddressAlert.query.count() == 0


def test_kyc_roundtrip_and_linked_customer_cannot_be_deleted(client):
    customer_id = client.post('/api/customers', json=payload()).json['id']
    created = client.post('/api/kyc-processes', json={'customer_id': customer_id, 'status': 'INICIADO'})
    assert created.status_code == 201
    assert created.json['status'] == 'INICIADO'
    assert client.get('/api/kyc-processes').json[0]['id'] == created.json['id']
    assert client.delete(f'/api/customers/{customer_id}').status_code == 409
    assert client.get(f'/api/customers/{customer_id}').status_code == 200
    assert client.post('/api/kyc-processes', json={'customer_id': 999}).status_code == 404
    assert client.post('/api/kyc-processes', json={'customer_id': customer_id, 'status': 'INVALIDO'}).status_code == 400
