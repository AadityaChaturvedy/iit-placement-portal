from app import app, db
from models import Admin, Company, Student, JobPosition, Application, Placement
from werkzeug.security import generate_password_hash

if __name__ == '__main__':
    with app.app_context():
        # sync db schema
        db.drop_all()
        db.create_all()
        
        # create default admin
        admin = Admin(
            username='admin',
            email='admin@admin.com',
            password_hash=generate_password_hash('admin123')
        )

        db.session.add(admin)
        db.session.commit()
        print("init complete")