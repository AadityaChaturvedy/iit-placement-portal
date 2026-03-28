"""
One-off script to initialize the database.
WARNING: This drops all tables! Don't run this in production without thinking twice.
"""
from app import app, db
from models import Admin, Company, Student, JobPosition, Application, Placement
from werkzeug.security import generate_password_hash
import sys

if __name__ == '__main__':
    print("Initializing Database...")
    
    # Just a little safety check
    user_input = input("This will destroy all existing data. Are you sure? (y/n): ")
    if user_input.lower() != 'y':
        print("Aborting database initialization.")
        sys.exit(0)

    with app.app_context():
        # drop everything and recreate schema from scratch
        db.drop_all()
        db.create_all()
        
        # We need a default admin to start using the app.
        try:
            admin = Admin(
                username='admin',
                email='admin@admin.com',
                password_hash=generate_password_hash('admin123') # TODO: Read this from .env later
            )

            db.session.add(admin)
            db.session.commit()
            print("Successfully created the default admin user.")
        except Exception as e:
            # Catching generic exceptions just in case we hit some weird constraint
            print(f"Failed to create admin user: {e}")
            db.session.rollback()
            sys.exit(1)
        
        print("Done. Ready to run 'app.py'!")