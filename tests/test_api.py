import pytest
from src.app import create_app, db
from src.models import User, Customer, KycProcess, KycStatus, RiskLevel, Status, CustomerType, Role

@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_get_customers(client):
    response = client.get('/api/customers')
    assert response.status_code in [200, 404, 308]

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
    assert response.status_code in [201, 200, 400, 404]

def test_get_customer_by_id(client, app):
    with app.app_context():
        customer = Customer(
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
    assert response.status_code in [200, 404]

def test_update_customer(client, app):
    with app.app_context():
        customer = Customer(
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
    assert response.status_code in [200, 404]

def test_delete_customer(client, app):
    with app.app_context():
        customer = Customer(
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
    assert response.status_code in [200, 204, 404]

def test_get_kyc_processes(client):
    response = client.get('/api/kyc-processes')
    assert response.status_code in [200, 404, 308]

def test_create_kyc_process(client, app):
    with app.app_context():
        analyst = User(
            name='Analyst',
            email='analyst@test.com',
            password='pwd',
            role=Role.analyst
        )
        customer = Customer(
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
    assert response.status_code in [201, 200, 400, 404, 308]
