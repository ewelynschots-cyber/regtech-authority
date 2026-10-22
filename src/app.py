import logging
import os
from flask import Flask, request, Blueprint, render_template, g, redirect
from flask_restx import Api, Resource, Namespace
from sqlalchemy.exc import IntegrityError
from src import db
from src.models import Customer, KycProcess, CustomerType, RiskLevel, Status, KycStatus, User
from src.services.address_alert_service import calculate_risk_level
from src.access import scoped, owned, owner_values

logger = logging.getLogger(__name__)
CUSTOMER_FIELDS = {'name', 'email', 'customer_type', 'cpf_cnpj', 'phone', 'address', 'risk_level', 'status'}


def enum_value(enum, value):
    for member in enum:
        if value in (member.name, member.value):
            return member
    raise ValueError('Valor inválido para ' + enum.__name__)


def customer_data(data, partial=False):
    if not isinstance(data, dict) or not data or set(data) - CUSTOMER_FIELDS:
        raise ValueError('Informe um objeto com campos válidos de cliente')
    required = {'name', 'email', 'customer_type', 'cpf_cnpj', 'phone', 'address'}
    if not partial and required - set(data):
        raise ValueError('Preencha os campos obrigatórios do cliente')
    data = dict(data)
    for field, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Campo inválido: ' + field)
        data[field] = value.strip()
    for field, enum in [('customer_type', CustomerType), ('risk_level', RiskLevel), ('status', Status)]:
        if field in data:
            data[field] = enum_value(enum, data[field])
    if 'email' in data and '@' not in data['email']:
        raise ValueError('E-mail inválido')
    return data


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///kyc.db'), SQLALCHEMY_TRACK_MODIFICATIONS=False, PUBLIC_ORIGIN=os.getenv('PUBLIC_ORIGIN'))
    if config:
        app.config.update(config)
    db.init_app(app)
    from werkzeug.security import generate_password_hash
    app.config['AUTH_DUMMY_HASH'] = generate_password_hash('not-a-real-account-password', method='pbkdf2:sha256')
    from src.access import install_access
    install_access(app)
    from src.routes.financial import financial_api
    app.config.setdefault('MAX_CONTENT_LENGTH', 3_000_000)
    if app.config['MAX_CONTENT_LENGTH'] is None:
        app.config['MAX_CONTENT_LENGTH'] = 3_000_000
    app.register_blueprint(financial_api)
    from src.routes.automation import source_api
    app.register_blueprint(source_api)
    from src.models.process_monitor import ProcessMonitor

    @app.cli.command("recheck-processes")
    def recheck_processes():
        from src.services.rechecks import run_due
        print(f"Reconsultas registradas: {run_due()}")

    @app.cli.command('init-db')
    def init_db():
        """Create missing tables without dropping existing data."""
        db.create_all()
        print('Tabelas verificadas e criadas quando ausentes.')

    @app.get('/')
    def financial_portal():
        return render_template('financial.html') if g.user else redirect('/login')
    api_bp = Blueprint('api', __name__, url_prefix='/api')
    api = Api(api_bp, version='1.0', title='RegTech Authority API', doc='/docs')
    customers_ns = Namespace('customers', description='Customer operations')
    kyc_ns = Namespace('kyc-processes', description='KYC process operations')
    api.add_namespace(customers_ns)
    api.add_namespace(kyc_ns)

    @customers_ns.route('/', strict_slashes=False)
    class CustomerList(Resource):
        def get(self):
            return [c.to_dict() for c in scoped(Customer).all()]

        def post(self):
            try:
                customer = Customer(**customer_data(request.get_json()), **owner_values())
                db.session.add(customer)
                db.session.commit()
                return customer.to_dict(), 201
            except ValueError as exc:
                db.session.rollback()
                return {'message': str(exc)}, 400
            except IntegrityError:
                db.session.rollback()
                return {'message': 'Cliente em conflito com cadastro existente'}, 409

    @customers_ns.route('/<int:id>')
    class CustomerDetail(Resource):
        def get(self, id):
            customer = owned(Customer, id)
            duplicates = [c.id for c in scoped(Customer).filter_by(address=customer.address).all()]
            alert = None
            if len(duplicates) > 1:
                alert = {'risk_level': calculate_risk_level(len(duplicates)),
                         'duplicates': duplicates, 'address': customer.address}
            return {'customer': customer.to_dict(), 'address_alert': alert}

        def put(self, id):
            customer = owned(Customer, id)
            try:
                data = customer_data(request.get_json(), partial=True)
                for field, value in data.items():
                    setattr(customer, field, value)
                customer.validate_cpf_cnpj()
                db.session.commit()
                return customer.to_dict()
            except ValueError as exc:
                db.session.rollback()
                return {'message': str(exc)}, 400
            except IntegrityError:
                db.session.rollback()
                return {'message': 'Cliente em conflito com cadastro existente'}, 409

        def delete(self, id):
            customer = owned(Customer, id)
            from src.services.address_alert_service import AddressAlert
            if KycProcess.query.filter_by(customer_id=id).first() or AddressAlert.query.filter_by(customer_id=id).first():
                return {'message': 'Cliente possui processos ou alertas vinculados'}, 409
            try:
                db.session.delete(customer)
                db.session.commit()
                return '', 204
            except IntegrityError:
                db.session.rollback()
                return {'message': 'Cliente possui registros vinculados'}, 409

    @kyc_ns.route('/', strict_slashes=False)
    class KycList(Resource):
        def get(self):
            return [k.to_dict() for k in scoped(KycProcess).all()]

        def post(self):
            data = request.get_json()
            allowed = {'customer_id', 'analyst_id', 'status', 'risk_assessment', 'documents_submitted', 'notes'}
            if not isinstance(data, dict) or not data or set(data) - allowed:
                return {'message': 'Informe campos válidos do processo KYC'}, 400
            data = dict(data)
            for field in ('customer_id', 'analyst_id'):
                value = data.get(field)
                if field == 'analyst_id' and value is None:
                    continue
                if type(value) is not int or value <= 0:
                    return {'message': 'Identificador inválido: ' + field}, 400
            if scoped(Customer).filter_by(id=data['customer_id']).first() is None:
                return {'message': 'Cliente não encontrado'}, 404
            if data.get('analyst_id') is not None and scoped(User).filter_by(id=data['analyst_id']).first() is None:
                return {'message': 'Analista não encontrado'}, 404
            try:
                if 'status' in data:
                    data['status'] = enum_value(KycStatus, data['status'])
                for field in ('risk_assessment', 'notes'):
                    if field in data and data[field] is not None and not isinstance(data[field], str):
                        raise ValueError('Campo inválido: ' + field)
                process = KycProcess(**data, **owner_values())
                db.session.add(process)
                db.session.commit()
                return process.to_dict(), 201
            except ValueError as exc:
                db.session.rollback()
                return {'message': str(exc)}, 400
            except IntegrityError:
                db.session.rollback()
                return {'message': 'Dados do processo em conflito'}, 409

    app.register_blueprint(api_bp)
    return app


app = create_app()
