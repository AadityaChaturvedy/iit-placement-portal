from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Admin(db.Model):
    """Stores system administrators."""
    __tablename__ = 'admin'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    
    # Needs to be long enough for pbkdf2 or bcrypt hashes
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<Admin {self.username}>'


class Company(db.Model):
    """Registered companies that can post job openings."""
    __tablename__ = 'company'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # basic contact info
    hr_contact = db.Column(db.String(15), nullable=False)
    website = db.Column(db.String(200))
    industry = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    # internal tracking statuses
    approval_status = db.Column(db.String(20), default='Pending')  # Options: Pending, Approved, Rejected
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    # cascade delete orphan will wipe out all job postings if the company gets removed
    job_positions = db.relationship('JobPosition', backref='company', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Company {self.company_name} ({self.approval_status})>'


class Student(db.Model):
    """Students applying for placements."""
    __tablename__ = 'student'
    
    student_id = db.Column(db.String(50), primary_key=True)  # Using roll number/enrollment id as primary key
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    contact = db.Column(db.String(15), nullable=False)
    
    # Academic details
    degree = db.Column(db.String(100))
    branch = db.Column(db.String(100))
    cgpa = db.Column(db.Float)
    graduation_year = db.Column(db.Integer)
    
    # Store skills as a JSON string for now
    skills = db.Column(db.Text)
    resume_path = db.Column(db.String(300))
    
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    applications = db.relationship('Application', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Student {self.student_id} - {self.name}>'


class JobPosition(db.Model):
    """Job openings posted by companies."""
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
    
    # Pending initially so admin can approve it before it goes live
    status = db.Column(db.String(20), default='Pending')  # Pending, Approved, Active, Closed
    
    applications = db.relationship('Application', backref='job_position', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<JobPosition {self.id}: {self.job_title}>'


class Application(db.Model):
    """Tracks a student's application to a specific job position."""
    __tablename__ = 'application'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('student.student_id'), nullable=False)
    job_position_id = db.Column(db.Integer, db.ForeignKey('job_position.id'), nullable=False)
    
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Applied')  # statuses: Applied, Shortlisted, Interview, Selected, Rejected
    cover_letter = db.Column(db.Text)
    
    # keep track of when status changes
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # make sure a student can't apply to the same job twice
    __table_args__ = (
        db.UniqueConstraint('student_id', 'job_position_id', name='unique_application'),
    )
    
    placement = db.relationship('Placement', backref='application', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Application {self.student_id} -> Job {self.job_position_id}>'


class Placement(db.Model):
    """Final placement records for selected students."""
    __tablename__ = 'placement'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 1-to-1 mapping with an accepted application
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False, unique=True)
    placement_date = db.Column(db.DateTime, default=datetime.utcnow)
    offer_letter_path = db.Column(db.String(300))
    
    joining_date = db.Column(db.Date)
    package = db.Column(db.String(100))
    remarks = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Placement App_ID: {self.application_id}>'