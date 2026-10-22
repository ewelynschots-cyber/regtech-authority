from src import db
from enum import Enum
import re
from datetime import datetime

class CustomerType(Enum):
    PF = "PF"
    PJ = "PJ"

class RiskLevel(Enum):
    BAIXO = "baixo"
    MEDIO = "médio"
    ALTO = "alto"

class Status(Enum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"

def validate_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11:
        return False
    # Validação real de CPF omitida para brevidade
    return True

def validate_cnpj(cnpj):
    cnpj = re.sub(r'\D', '', cnpj)
    if len(cnpj) != 14:
        return False
    # Validação real de CNPJ omitida para brevidade
    return True

class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    customer_type = db.Column(db.Enum(CustomerType), nullable=False)
    cpf_cnpj = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    risk_level = db.Column(db.Enum(RiskLevel), default=RiskLevel.BAIXO, nullable=False)
    status = db.Column(db.Enum(Status), default=Status.PENDENTE, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Customer, self).__init__(**kwargs)
        self.validate_cpf_cnpj()

    def validate_cpf_cnpj(self):
        if self.customer_type == CustomerType.PF:
            if not validate_cpf(self.cpf_cnpj):
                raise ValueError("CPF inválido")
        elif self.customer_type == CustomerType.PJ:
            if not validate_cnpj(self.cpf_cnpj):
                raise ValueError("CNPJ inválido")

    def __repr__(self):
        return f'<Customer {self.id}: {self.name} ({self.customer_type.value})>'
