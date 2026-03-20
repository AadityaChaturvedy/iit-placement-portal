from app import app, db
from models import Admin, Company, Student, JobPosition, Application, Placement
from werkzeug.security import generate_password_hash

def create_DataBase():
    """This function creates the database tables"""

    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database tables created successfully.")

        admin = Admin(
            username='admin',
            email='admin@admin.com',
            password_hash=generate_password_hash('admin123')
        )

        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    create_DataBase()