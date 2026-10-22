import logging
import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from src import db
from src.access import scoped, owned, owner_values
from src.models import Customer

logger = logging.getLogger(__name__)

class AddressAlert(db.Model):
    __tablename__ = 'org_address_alerts'
    organization_id = db.Column(db.String(36), db.ForeignKey('portal_organizations.id'), nullable=True, index=True)
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('org_customers.id'), nullable=False)
    address = Column(String(255), nullable=False)
    customer_count = Column(Integer, default=0)
    risk_level = Column(String(20), nullable=False)
    duplicate_customer_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

MAX_CUSTOMERS_PER_ADDRESS = int(os.getenv('MAX_CUSTOMERS_PER_ADDRESS', 5))

def check_address_duplicates(address, exclude_customer_id=None):
    """Verifica se existem múltiplos clientes no mesmo endereço."""
    try:
        query = scoped(Customer).filter(Customer.address == address)
        if exclude_customer_id:
            query = query.filter(Customer.id != exclude_customer_id)
        return query.count() > 0
    except Exception as e:
        logger.error(f"Erro ao verificar duplicatas de endereço {address}: {e}")
        return False

def get_duplicate_customers(address, exclude_customer_id=None):
    """Retorna lista de IDs de clientes associados ao mesmo endereço."""
    try:
        query = scoped(Customer).with_entities(Customer.id).filter(Customer.address == address)
        if exclude_customer_id:
            query = query.filter(Customer.id != exclude_customer_id)
        return [c.id for c in query.all()]
    except Exception as e:
        logger.error(f"Erro ao buscar IDs duplicados para {address}: {e}")
        return []

def calculate_risk_level(customer_count):
    """Calcula o nível de risco baseado na contagem de clientes."""
    if customer_count >= MAX_CUSTOMERS_PER_ADDRESS * 2:
        return "HIGH"
    elif customer_count >= MAX_CUSTOMERS_PER_ADDRESS:
        return "MEDIUM"
    return "LOW"

def create_alert(customer_id, risk_level, address=None):
    """Cria um novo registro de alerta de endereço."""
    try:
        owned(Customer, customer_id)
        alert = AddressAlert(**owner_values(),
            customer_id=customer_id,
            address=address,
            risk_level=risk_level,
            created_at=datetime.utcnow()
        )
        db.session.add(alert)
        db.session.commit()
        logger.info(f"Alerta criado para o cliente {customer_id} com risco {risk_level}")
        return alert
    except Exception as e:
        db.session.rollback()
        logger.error(f"Falha ao criar alerta para cliente {customer_id}: {e}")
        raise
