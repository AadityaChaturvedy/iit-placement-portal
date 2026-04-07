from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Admin(db.Model):
    __tablename__ = 'admin'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return '<Admin %s>' % self.username


class Company(db.Model):
    """Represents a recruiting company that needs admin approval before posting jobs."""
    __tablename__ = 'company'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    hr_contact = db.Column(db.String(15), nullable=False)
    website = db.Column(db.String(200))
    industry = db.Column(db.String(100))
    description = db.Column(db.Text)

    approval_status = db.Column(db.String(20), default='Pending')
    is_blacklisted = db.Column(db.Boolean, default=False)

    job_positions = db.relationship('JobPosition', backref='company',
                                    lazy=True, cascade='all, delete-orphan')

    @property
    def is_active(self):
        if self.is_blacklisted:
            return False
        return self.approval_status == 'Approved'

    def __repr__(self):
        return f'<Company {self.company_name} ({self.approval_status})>'


class Student(db.Model):
    __tablename__ = 'student'

    # using roll number as primary key since that's the unique identifier at IIT
    student_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    contact = db.Column(db.String(15), nullable=False)

    degree = db.Column(db.String(100))
    branch = db.Column(db.String(100))
    cgpa = db.Column(db.Float)
    graduation_year = db.Column(db.Integer)

    skills = db.Column(db.Text)
    resume_path = db.Column(db.String(300))
    # resume_version = db.Column(db.Integer, default=1)

    is_blacklisted = db.Column(db.Boolean, default=False)

    applications = db.relationship('Application', backref='student',
                                    lazy=True, cascade='all, delete-orphan')

    @property
    def has_resume(self):
        return bool(self.resume_path)


class JobPosition(db.Model):
    __tablename__ = 'job_position'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    job_title = db.Column(db.String(200), nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    eligibility_criteria = db.Column(db.Text)

    required_skills = db.Column(db.Text)
    experience_required = db.Column(db.String(50))
    salary_range = db.Column(db.String(100))

    application_deadline = db.Column(db.Date, nullable=False)
    # Pending -> Approved/Rejected by admin, Closed by company
    status = db.Column(db.String(20), default='Pending')

    applications = db.relationship('Application', backref='job_position',
                                    lazy=True, cascade='all, delete-orphan')

    @property
    def is_expired(self):
        if self.application_deadline:
            return date.today() > self.application_deadline
        return False

    @property
    def days_left(self):
        if not self.application_deadline:
            return None
        remaining = self.application_deadline - date.today()
        if remaining.days < 0:
            return 0
        return remaining.days

    def __repr__(self):
        return '<Job #{} - {}>'.format(self.id, self.job_title)


class Application(db.Model):
    """
    Links a student to a job position.
    Status flow: Applied -> Shortlisted -> Interview -> Selected/Rejected
    """
    __tablename__ = 'application'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('student.student_id'), nullable=False)
    job_position_id = db.Column(db.Integer, db.ForeignKey('job_position.id'), nullable=False)

    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Applied')
    cover_letter = db.Column(db.Text)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'job_position_id', name='unique_application'),
    )

    placement = db.relationship('Placement', backref='application',
                                 uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return '<Application {} -> Job {}>'.format(self.student_id, self.job_position_id)


class Placement(db.Model):
    __tablename__ = 'placement'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'),
                                nullable=False, unique=True)
    placement_date = db.Column(db.DateTime, default=datetime.utcnow)
    offer_letter_path = db.Column(db.String(300))

    joining_date = db.Column(db.Date)
    package = db.Column(db.String(100))
    remarks = db.Column(db.Text)

    def __repr__(self):
        return '<Placement for app #{}>'.format(self.application_id)