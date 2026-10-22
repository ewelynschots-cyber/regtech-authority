import pytest
from src.app import create_app, db
from src.models import User, Customer, KycProcess, KycStatus, RiskLevel, Status, CustomerType, Role

@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def session(app):
    return db.session

def test_create_user(session):
    user = User(name='Analyst', email='analyst@test.com', password='password123', role=Role.analyst)
    session.add(user)
    session.commit()
    assert user.id is not None
    assert user.role == Role.analyst

def test_user_password_hash(session):
    user = User(name='Test', email='test@test.com', password='password123', role=Role.analyst)
    session.add(user)
    session.commit()
    assert user.password_hash is not None
    assert user.password_hash != 'password123'

def test_create_customer(session):
    customer = Customer(
        name='John Doe',
        email='john@test.com',
        customer_type=CustomerType.PF,
        cpf_cnpj='52998224725',
        phone='11999999999',
        address='Rua Teste, 123',
        risk_level=RiskLevel.BAIXO,
        status=Status.PENDENTE
    )
    session.add(customer)
    session.commit()
    assert customer.id is not None
    assert customer.cpf_cnpj == '52998224725'

def test_create_kyc_process(session):
    user = User(name='Analyst', email='a@test.com', password='pwd', role=Role.analyst)
    customer = Customer(
        name='Client', 
        email='c@test.com', 
        customer_type=CustomerType.PF, 
        cpf_cnpj='52998224725', 
        phone='11999999999', 
        address='Rua Teste, 123',
        risk_level=RiskLevel.BAIXO, 
        status=Status.PENDENTE
    )
    session.add_all([user, customer])
    session.commit()
    
    kyc = KycProcess(customer_id=customer.id, analyst_id=user.id, status=KycStatus.INICIADO)
    session.add(kyc)
    session.commit()
    
    assert kyc.id is not None
    assert kyc.customer_id == customer.id
    assert kyc.analyst_id == user.id

def test_kyc_process_status(session):
    user = User(name='A', email='a@t.com', password='p', role=Role.analyst)
    customer = Customer(
        name='C', email='c@t.com', customer_type=CustomerType.PF, 
        cpf_cnpj='52998224725', phone='11999999999', address='Rua Teste, 123',
        risk_level=RiskLevel.BAIXO, status=Status.PENDENTE
    )
    session.add_all([user, customer])
    session.commit()
    
    kyc = KycProcess(customer_id=customer.id, analyst_id=user.id, status=KycStatus.INICIADO)
    session.add(kyc)
    session.commit()
    
    assert kyc.status == KycStatus.INICIADO
