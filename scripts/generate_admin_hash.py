"""Local interactive helper. Never put a real password in command arguments."""
import getpass
from werkzeug.security import generate_password_hash


def main():
    password = getpass.getpass('Defina a senha do administrador (12 a 256 caracteres): ')
    confirmation = getpass.getpass('Confirme a senha: ')
    if not 12 <= len(password) <= 256 or not password.strip():
        raise SystemExit('A senha deve conter de 12 a 256 caracteres.')
    if password != confirmation:
        raise SystemExit('As senhas não coincidem.')
    encoded = generate_password_hash(password, method='pbkdf2:sha256:1000000', salt_length=16)
    print('\nCopie o valor abaixo para INITIAL_ADMIN_PASSWORD_HASH no Render.')
    print('Trate o hash como segredo; não o envie no chat nem o publique no GitHub.\n')
    print(encoded)


if __name__ == '__main__':
    main()
