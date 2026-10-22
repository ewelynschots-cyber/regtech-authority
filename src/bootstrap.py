"""Opt-in first administrator provisioning from operator-controlled environment."""
import os
import re
import secrets
from sqlalchemy.exc import IntegrityError
from src import db
from src.models import User, Role
from src.models.access import Organization

KEYS = ('INITIAL_ADMIN_EMAIL', 'INITIAL_ADMIN_PASSWORD_HASH',
        'INITIAL_ADMIN_NAME', 'INITIAL_ORGANIZATION_NAME')
ERROR = 'Configuração inicial inválida. Confira as quatro variáveis INITIAL_*. Nenhum valor secreto será exibido.'
CONFLICT = 'O acesso inicial não foi alterado: já existe uma organização ou conta incompatível. Use o procedimento administrativo.'


def validate_hash(value):
    # Bound the accepted algorithm/cost so operator mistakes cannot create a weak
    # password or an excessive-cost login. Generated hashes use one million rounds.
    if not isinstance(value, str) or len(value) > 256:
        return False
    match = re.fullmatch(r'pbkdf2:sha256:([0-9]{6,7})\$[A-Za-z0-9]{16,64}\$[a-f0-9]{64}', value)
    return bool(match and 600000 <= int(match[1]) <= 2000000)


def existing_admin(email, organization_name):
    user = User.query.filter_by(email=email).first()
    if user:
        organization = db.session.get(Organization, user.organization_id) if user.organization_id else None
        if organization and organization.name == organization_name and user.role == Role.admin and user.is_active:
            return user
        raise RuntimeError(CONFLICT)
    return None


def bootstrap_admin(environ=None):
    values = os.environ if environ is None else environ
    supplied = [values.get(key, '') for key in KEYS]
    if not any(supplied):
        return None  # No public fallback or automatic enrollment.
    if any(not isinstance(value, str) or not value.strip() for value in supplied):
        raise RuntimeError(ERROR)
    email, password_hash, name, organization_name = [value.strip() for value in supplied]
    email = email.lower()
    if (len(email) > 120 or email.count('@') != 1 or any(c.isspace() for c in email)
            or not all(email.split('@')) or len(name) > 100 or len(organization_name) > 200
            or not validate_hash(password_hash)):
        raise RuntimeError(ERROR)
    user = existing_admin(email, organization_name)
    if user:
        return user  # Never reset an existing password or reactivate/elevate a user.
    if Organization.query.first() or User.query.first():
        raise RuntimeError(CONFLICT)
    organization = Organization(name=organization_name)
    db.session.add(organization)
    try:
        db.session.flush()
        user = User(name=name, email=email, password=secrets.token_urlsafe(32),
                    role='admin', organization_id=organization.id)
        user.password_hash = password_hash
        db.session.add(user)
        db.session.commit()
        return user
    except IntegrityError:
        # A second startup process may have provisioned this exact account first.
        # The whole transaction (including its organization) is rolled back.
        db.session.rollback()
        user = existing_admin(email, organization_name)
        if user:
            return user
        raise RuntimeError(CONFLICT) from None
