import logging
from flask import Flask, request, jsonify, Blueprint
from flask_restx import Api, Resource, fields, Namespace
from src import db
from src.models import Customer, KycProcess
from src.services.address_alert_service import check_address_duplicates, calculate_risk_level, get_duplicate_customers, create_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config=None):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kyc.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    if config:
        app.config.update(config)
    
    db.init_app(app)
    
    api_bp = Blueprint('api', __name__, url_prefix='/api')
    api = Api(api_bp, version='1.0', title='RegTech Authority API', doc='/docs')
    
    customers_ns = Namespace('customers', description='Customer operations')
    kyc_ns = Namespace('kyc-processes', description='KYC process operations')
    
    api.add_namespace(customers_ns)
    api.add_namespace(kyc_ns)

    customer_model = api.model('Customer', {'id': fields.Integer, 'name': fields.String, 'address': fields.String})
    kyc_model = api.model('KycProcess', {'id': fields.Integer, 'customer_id': fields.Integer, 'status': fields.String})
    alert_model = api.model('Alert', {'risk_level': fields.String, 'duplicates': fields.List(fields.Integer)})

    @customers_ns.route('/')
    class CustomerList(Resource):
        def get(self):
            return [c.to_dict() for c in Customer.query.all()]
        @customers_ns.expect(customer_model)
        def post(self):
            data = request.json
            new_c = Customer(**data)
            db.session.add(new_c)
            db.session.commit()
            return new_c.to_dict(), 201

    @customers_ns.route('/<int:id>')
    class CustomerDetail(Resource):
        def get(self, id):
            customer = Customer.query.get_or_404(id)
            try:
                duplicates = get_duplicate_customers(customer.address)
                if len(duplicates) > 1:
                    risk = calculate_risk_level(duplicates)
                    alert = create_alert(customer.id, risk, duplicates)
                    return {'customer': customer.to_dict(), 'address_alert': alert}
                return {'customer': customer.to_dict(), 'address_alert': None}
            except Exception as e:
                logger.error(f'Error processing alerts: {e}')
                return {'customer': customer.to_dict(), 'address_alert': None}

    @kyc_ns.route('/')
    class KycList(Resource):
        def get(self):
            return [k.to_dict() for k in KycProcess.query.all()]
        def post(self):
            data = request.json
            new_k = KycProcess(**data)
            db.session.add(new_k)
            db.session.commit()
            return new_k.to_dict(), 201

    app.register_blueprint(api_bp)
    return app

app = create_app()
