from src.database import db
from werkzeug.security import generate_password_hash, check_password_hash
import enum
from datetime import datetime

class Role(enum.Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'

class User(db.Model):
    __tablename__ = 'org_users'
    organization_id = db.Column(db.String(36), db.ForeignKey('portal_organizations.id'), nullable=True, index=True)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(Role), nullable=False, default=Role.viewer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, name, email, password, role='viewer', is_active=True, organization_id=None):
        if not name:
            raise ValueError("Name cannot be empty")
        if not email or '@' not in email:
            raise ValueError("Invalid email")
        if not password:
            raise ValueError("Password cannot be empty")
        self.organization_id = organization_id
        self.name = name
        self.email = email
        self.set_password(password)
        self.role = Role(role) if isinstance(role, str) else role
        self.is_active = is_active
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def set_password(self, password):
        """Gera hash da senha usando pbkdf2 (compatível com Python 3.9)"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def verify_password(self, password):
        """Verifica se a senha está correta"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.id}: {self.name} ({self.role.value})>'
