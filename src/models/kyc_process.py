from src import db
from enum import Enum

class KycStatus(Enum):
    INICIADO = 'iniciado'
    EM_ANALISE = 'em_analise'
    APROVADO = 'aprovado'
    REJEITADO = 'rejeitado'

class KycProcess(db.Model):
    __tablename__ = 'kyc_processes'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    status = db.Column(db.Enum(KycStatus), nullable=False, default=KycStatus.INICIADO)
    risk_assessment = db.Column(db.String(50), nullable=True)
    documents_submitted = db.Column(db.JSON, nullable=True)
    analyst_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    completed_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship('Customer', backref=db.backref('kyc_processes', lazy=True))
    analyst = db.relationship('User', backref=db.backref('kyc_processes', lazy=True))

    def __repr__(self):
        return f'<KycProcess {self.id} - Customer {self.customer_id} - Status {self.status.value}>'

    def to_dict(self):
        return {
            'id': self.id, 'customer_id': self.customer_id,
            'analyst_id': self.analyst_id, 'status': self.status.name,
            'risk_assessment': self.risk_assessment,
            'documents_submitted': self.documents_submitted, 'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
