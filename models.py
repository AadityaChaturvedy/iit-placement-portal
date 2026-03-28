from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize the db here, we'll bind it in app.py
db = SQLAlchemy()

class Admin(db.Model):
    """Admin user for the placement portal."""
    __tablename__ = 'admin'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    
    # Storing hashed password for security (using werkzeug in app.py)
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<Admin {self.username}>'


class Company(db.Model):
    """Represents a company visiting for placements."""
    __tablename__ = 'company'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # HR contact info
    hr_contact = db.Column(db.String(15), nullable=False)
    website = db.Column(db.String(200))
    industry = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    # Needs admin approval to post jobs
    approval_status = db.Column(db.String(20), default='Pending') 
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    job_positions = db.relationship('JobPosition', backref='company', lazy=True, cascade='all, delete-orphan')
    
    @property
    def is_active(self):
        """Helper to check if company can use the portal"""
        return self.approval_status == 'Approved' and not self.is_blacklisted

    def __repr__(self):
        # Good for debugging
        return f'<Company {self.company_name} ({self.approval_status})>'


class Student(db.Model):
    """Student profile for placements."""
    __tablename__ = 'student'
    
    # Using their actual ID (like roll number) as primary key makes sense here
    student_id = db.Column(db.String(50), primary_key=True) 
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    contact = db.Column(db.String(15), nullable=False)
    
    # Academics
    degree = db.Column(db.String(100))
    branch = db.Column(db.String(100))
    cgpa = db.Column(db.Float)
    graduation_year = db.Column(db.Integer)
    
    # Optional stuff, might be empty initially
    skills = db.Column(db.Text)
    resume_path = db.Column(db.String(300))
    
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    applications = db.relationship('Application', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Student {self.student_id} - {self.name}>'


class JobPosition(db.Model):
    """A specific job posting by a company."""
    __tablename__ = 'job_position'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to which company posted this
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    job_title = db.Column(db.String(200), nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    eligibility_criteria = db.Column(db.Text)
    
    required_skills = db.Column(db.Text)
    experience_required = db.Column(db.String(50))
    salary_range = db.Column(db.String(100))
    
    # Deadline is super important
    application_deadline = db.Column(db.Date, nullable=False)
    
    # Needs admin approval before showing up to students
    status = db.Column(db.String(20), default='Pending') 
    
    applications = db.relationship('Application', backref='job_position', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<JobPosition {self.id}: {self.job_title}>'


class Application(db.Model):
    """Tracks a student applying to a job position."""
    __tablename__ = 'application'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('student.student_id'), nullable=False)
    job_position_id = db.Column(db.Integer, db.ForeignKey('job_position.id'), nullable=False)
    
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Status flows from Applied -> Shortlisted -> Interview -> Selected / Rejected
    status = db.Column(db.String(20), default='Applied')
    cover_letter = db.Column(db.Text)
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # A student can only apply to a job once! This constraint enforces it at DB level.
    __table_args__ = (
        db.UniqueConstraint('student_id', 'job_position_id', name='unique_application'),
    )
    
    placement = db.relationship('Placement', backref='application', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Application {self.student_id} -> Job {self.job_position_id}>'


class Placement(db.Model):
    """Final offer/placement details, attached to a successful application."""
    __tablename__ = 'placement'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 1:1 relationship with application
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False, unique=True)
    placement_date = db.Column(db.DateTime, default=datetime.utcnow)
    offer_letter_path = db.Column(db.String(300))
    
    joining_date = db.Column(db.Date)
    package = db.Column(db.String(100))
    remarks = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Placement App_ID: {self.application_id}>'