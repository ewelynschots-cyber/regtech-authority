"""Identity and server-side sessions for the organization-scoped portal."""
from uuid import uuid4
from src import db


class Organization(db.Model):
    __tablename__ = 'portal_organizations'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    name = db.Column(db.String(200), nullable=False)


class AccessSession(db.Model):
    __tablename__ = 'portal_sessions'
    token_hash = db.Column(db.String(64), primary_key=True)
    csrf_token = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('org_users.id'), nullable=False, index=True)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)


class LoginAttempt(db.Model):
    __tablename__ = 'portal_login_attempts'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    address_hash = db.Column(db.String(64), nullable=False, index=True)
    account_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False, index=True)
