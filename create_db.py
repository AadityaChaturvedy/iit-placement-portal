"""Run this once to set up the database tables and default admin account.
Use --force to skip the confirmation prompt.
"""
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import sys

def main():
    print("=== DB Init Script ===")

    if len(sys.argv) > 1 and sys.argv[1] == '--force':
        print("Force mode, skipping confirmation")
    else:
        confirmation = input("This DROPS all tables. sure? (y/n): ")
        if confirmation.strip().lower() != 'y':
            print("Aborted.")
            return

    with app.app_context():
        db.drop_all()
        db.create_all()
        print("tables created.")

        default_admin = Admin(
            username='admin',
            email='admin@admin.com',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(default_admin)

        try:
            db.session.commit()
            print("default admin account ready (admin@admin.com / admin123)")
        except Exception as db_error:
            print("couldn't create admin: {}".format(db_error))
            db.session.rollback()
            sys.exit(1)

    print("all done, run app.py now")

if __name__ == '__main__':
    main()