from src.app import create_app
from src import db

app = create_app()

# Render starts this entrypoint directly. Create missing tables before serving
# requests; create_all does not drop tables or modify existing records.
with app.app_context():
    db.create_all()
    from src.bootstrap import bootstrap_admin
    bootstrap_admin()

if __name__ == '__main__':
    app.run()
