"""Fail-closed request authorization; no public account or organization creation."""
import hashlib
import hmac
import secrets
import time
import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src import db
from src.models import User, Role
from src.models.access import Organization, AccessSession, LoginAttempt

access_api = Blueprint('access_api', __name__, url_prefix='/api/auth')
COOKIE = 'regtech_session'
SESSION_SECONDS = 3600


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def identity(user):
    org = db.session.get(Organization, user.organization_id)
    return {'id': user.id, 'name': user.name, 'email': user.email,
            'role': user.role.value, 'organization': {'id': org.id, 'name': org.name}}


def scoped(model):
    # Must never silently fall back to an unscoped query outside a request.
    return model.query.filter_by(organization_id=g.user.organization_id)


def owned(model, identifier):
    return scoped(model).filter_by(id=identifier).first_or_404()


def owner_values():
    return {'organization_id': g.user.organization_id}


def valid_credentials(body):
    if not isinstance(body, dict) or set(body) != {'email', 'password'}:
        abort(400, 'Informe e-mail e senha.')
    email, password = body.get('email'), body.get('password')
    if not isinstance(email, str) or len(email) > 120 or not isinstance(password, str) or len(password) > 256:
        abort(400, 'Credenciais inválidas.')
    return email.strip().lower(), password


def validate_new_user(body):
    if not isinstance(body, dict) or set(body) != {'name', 'email', 'password', 'role'}:
        abort(400, 'Informe nome, e-mail, senha e perfil.')
    if body['role'] not in ('analyst', 'viewer'):
        abort(400, 'Escolha analyst ou viewer.')
    for key, limit in [('name', 100), ('email', 120), ('password', 256)]:
        if not isinstance(body[key], str) or not body[key].strip() or len(body[key]) > limit:
            abort(400, 'Dados de usuário inválidos.')
    if '@' not in body['email'] or len(body['password']) < 12:
        abort(400, 'E-mail inválido ou senha com menos de 12 caracteres.')


def install_access(app):
    from flask import redirect, render_template
    app.config.setdefault('AUTH_COOKIE_SECURE', True)
    # The entrypoint reads the DB destination, without importing legacy .env files.
    app.register_blueprint(access_api)

    @app.before_request
    def authorize():
        g.user = None
        g.access_session = None
        token = request.cookies.get(COOKIE, '')
        if token and len(token) < 200:
            session = db.session.get(AccessSession, digest(token))
            if session and session.expires_at > int(time.time()):
                user = db.session.get(User, session.user_id)
                if user and user.is_active and user.organization_id and db.session.get(Organization, user.organization_id):
                    g.user, g.access_session = user, session
        private = request.path == '/api' or request.path.startswith('/api/')
        if not private:
            return
        if request.path == '/api/auth/login':
            return
        if request.path == '/api/automation/run-due':
            # This endpoint has its own exact GitHub OIDC identity check.
            return
        if g.user is None:
            return jsonify(message='Entre na sua organização.'), 401
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            csrf = request.headers.get('X-CSRF-Token', '')
            if not hmac.compare_digest(csrf.encode('utf-8'), g.access_session.csrf_token.encode('utf-8')):
                return jsonify(message='Sessão sem confirmação CSRF válida.'), 403
            if g.user.role == Role.viewer and request.path != '/api/auth/logout':
                return jsonify(message='Perfil de leitura não permite alterações ou consultas externas.'), 403

    @app.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def access_error(error):
        if request.path.startswith('/api/'):
            return jsonify(message=error.description), error.code
        return error

    @app.get('/login')
    def login_page():
        return redirect('/') if g.user else render_template('login.html')

    @app.get('/health')
    def health():
        return jsonify(status='ok')

    @app.cli.command('create-organization')
    @click.option('--organization', required=True)
    @click.option('--name', required=True)
    @click.option('--email', required=True)
    @click.password_option(confirmation_prompt=True)
    def create_organization(organization, name, email, password):
        """Explicit local provisioning; never assigns pre-existing data to the new account."""
        if not organization.strip() or len(organization) > 200:
            raise click.ClickException('Nome da organização inválido.')
        with app.test_request_context():
            validate_new_user({'name': name, 'email': email, 'password': password, 'role': 'analyst'})
        db.create_all()
        org = Organization(name=organization.strip())
        db.session.add(org)
        db.session.flush()
        user = User(name=name.strip(), email=email.strip().lower(), password=password,
                    role='admin', organization_id=org.id)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException('Conta não criada: e-mail já cadastrado.')
        click.echo('Organização e administrador criados. Dados legados não foram atribuídos.')


@access_api.post('/login')
def login():
    if not request.is_json:
        abort(400, 'Use JSON.')
    # No cross-origin login; JSON + SameSite=Strict also blocks simple form login CSRF.
    origin = request.headers.get('Origin')
    if origin and origin != (current_app.config.get('PUBLIC_ORIGIN') or request.host_url.rstrip('/')):
        abort(403, 'Origem de login inválida.')
    email, password = valid_credentials(request.get_json())
    now = int(time.time())
    address = digest(request.remote_addr or 'unknown')  # Never trust arbitrary X-Forwarded-For.
    account = digest(email)
    LoginAttempt.query.filter(LoginAttempt.created_at < now - 900).delete()
    by_ip = LoginAttempt.query.filter_by(address_hash=address).count()
    by_account = LoginAttempt.query.filter_by(account_hash=account).count()
    if by_ip >= 50 or by_account >= 5:
        db.session.commit()
        return jsonify(message='Aguarde antes de tentar novamente.'), 429, {'Retry-After': '900'}
    db.session.add(LoginAttempt(address_hash=address, account_hash=account, created_at=now))
    db.session.commit()
    user = User.query.filter_by(email=email).first()
    # Use the same expensive verification path for unknown accounts.
    check_hash = user.password_hash if user else current_app.config['AUTH_DUMMY_HASH']
    from werkzeug.security import check_password_hash
    valid = check_password_hash(check_hash, password)
    if not user or not valid or not user.is_active or not user.organization_id:
        return jsonify(message='E-mail ou senha inválidos.'), 401
    if not db.session.get(Organization, user.organization_id):
        return jsonify(message='E-mail ou senha inválidos.'), 401
    AccessSession.query.filter(AccessSession.expires_at <= now).delete()
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    # Rotate the incoming session if present; no session fixation.
    previous = request.cookies.get(COOKIE)
    if previous:
        AccessSession.query.filter_by(token_hash=digest(previous)).delete()
    db.session.add(AccessSession(token_hash=digest(token), csrf_token=csrf, user_id=user.id, expires_at=now + SESSION_SECONDS))
    db.session.commit()
    response = jsonify(user=identity(user), csrf_token=csrf)
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=current_app.config['AUTH_COOKIE_SECURE'], samesite='Strict', path='/')
    return response


@access_api.get('/me')
def me():
    return jsonify(user=identity(g.user), csrf_token=g.access_session.csrf_token)


@access_api.post('/logout')
def logout():
    db.session.delete(g.access_session)
    db.session.commit()
    response = jsonify(message='Sessão encerrada.')
    response.delete_cookie(COOKIE, path='/', secure=current_app.config['AUTH_COOKIE_SECURE'], httponly=True, samesite='Strict')
    return response


def require_admin():
    if g.user.role != Role.admin:
        abort(403, 'Somente o administrador da organização pode gerenciar usuários.')


@access_api.get('/users')
def users():
    require_admin()
    return jsonify(items=[{**identity(u), 'is_active': u.is_active} for u in scoped(User).order_by(User.id)])


@access_api.post('/users')
def add_user():
    require_admin()
    body = request.get_json()
    validate_new_user(body)
    user = User(name=body['name'].strip(), email=body['email'].strip().lower(), password=body['password'], role=body['role'], **owner_values())
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(message='Não foi possível criar a conta com os dados informados.'), 409
    return jsonify(user=identity(user)), 201


@access_api.patch('/users/<int:identifier>')
def update_user(identifier):
    require_admin()
    user = owned(User, identifier)
    if user.id == g.user.id:
        abort(400, 'Esta operação não altera o próprio administrador.')
    body = request.get_json()
    if not isinstance(body, dict) or not body or set(body) - {'role', 'is_active'}:
        abort(400, 'Informe perfil e/ou situação da conta.')
    if 'role' in body:
        if body['role'] not in ('viewer', 'analyst'):
            abort(400, 'Perfil inválido.')
        user.role = Role(body['role'])
    if 'is_active' in body:
        if type(body['is_active']) is not bool:
            abort(400, 'Situação inválida.')
        user.is_active = body['is_active']
    AccessSession.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify(user=identity(user), is_active=user.is_active)
