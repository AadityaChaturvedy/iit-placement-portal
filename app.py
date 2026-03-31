import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Admin, Company, Student, JobPosition, Application, Placement
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import or_, func
from datetime import datetime
import os
from werkzeug.utils import secure_filename

# Setup basic logging to help with debugging later
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Helper function for file upload capabilities
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Initialize our main Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Bind the SQLAlchemy obj to the app
db.init_app(app)

# ==== DECORATORS ====

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('user_role') != role:
                flash('This page is not available for your account role.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not email or not password or not role:
            flash('Please enter email, password, and role.', 'danger')
            return render_template('login.html')
        
        if role == 'admin':
            user = Admin.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['user_role'] = 'admin'
                session['username'] = user.username
                flash(f'Welcome back, {user.username}.', 'success')
                return redirect(url_for('admin_dashboard'))
            flash('Admin login failed. Please check your credentials.', 'danger')

        elif role == 'company':
            user = Company.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('This account is currently blocked. Please contact the placement office.', 'danger')
                    return render_template('login.html')
                
                session.update({
                    'user_id': user.id,
                    'user_role': 'company',
                    'username': user.company_name,
                    'approval_status': user.approval_status
                })
                flash(f'Welcome back, {user.company_name}.', 'success')
                
                if user.approval_status == 'Approved':
                    return redirect(url_for('company_dashboard'))
                return redirect(url_for('company_pending'))
                
            flash('Company login failed. Please check your credentials.', 'danger')
        
        elif role == 'student':
            user = Student.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('This account is currently blocked. Please contact the placement office.', 'danger')
                    return render_template('login.html')
                
                session.update({
                    'user_id': user.student_id,
                    'user_role': 'student',
                    'username': user.name
                })
                flash(f'Welcome back, {user.name}.', 'success')
                return redirect(url_for('student_dashboard'))
                
            flash('Student login failed. Please check your credentials.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        form = request.form
        student_id = form.get('student_id')
        name = form.get('name')
        email = form.get('email')
        password = form.get('password')
        confirm_password = form.get('confirm_password')
        contact = form.get('contact')
        
        # basic validations
        required_fields = [student_id, name, email, password, confirm_password, contact]
        if not all(required_fields):
            flash('Please complete all mandatory fields.', 'danger')
            return render_template('student_register.html')
        
        if password != confirm_password:
            flash('Password and confirm password do not match.', 'danger')
            return render_template('student_register.html')
        
        if Student.query.filter((Student.email == email) | (Student.student_id == student_id)).first():
            flash('Student ID or email is already registered.', 'danger')
            return render_template('student_register.html')
        
        # Handle resume upload safely
        resume_filename = None
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename != '' and allowed_file(file.filename):
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                # Secure filename with student ID prefix to prevent overwrites
                filename = secure_filename(file.filename)
                resume_filename = f"{student_id}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
                file.save(filepath)

        # save student
        cgpa_val = float(form.get('cgpa')) if form.get('cgpa') else None
        grad_year = int(form.get('graduation_year')) if form.get('graduation_year') else None

        new_student = Student(
            student_id=student_id,
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            contact=contact,
            degree=form.get('degree'),
            branch=form.get('branch'),
            cgpa=cgpa_val,
            graduation_year=grad_year,
            skills=form.get('skills'),
            resume_path=resume_filename
        )
        
        try:
            db.session.add(new_student)
            db.session.commit()
            logger.info(f"Student registered successfully: {student_id}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            # Catching integrity errors or anything else that might blow up the DB
            logger.error(f"Error registering student {student_id}: {e}")
            db.session.rollback()
            flash('Error registering account. Please try again.', 'danger')
            return render_template('student_register.html')
    
    return render_template('student_register.html')

@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if request.method == 'POST':
        form = request.form
        
        required_fields = ['company_name', 'email', 'password', 'confirm_password', 'hr_contact']
        if not all([form.get(f) for f in required_fields]):
            flash('Please complete all mandatory fields.', 'danger')
            return render_template('company_register.html')
            
        password = form.get('password')
        if password != form.get('confirm_password'):
            flash('Password and confirm password do not match.', 'danger')
            return render_template('company_register.html')
        
        if Company.query.filter_by(email=form.get('email')).first():
            flash('This email is already registered.', 'danger')
            return render_template('company_register.html')
        
        new_company = Company(
            company_name=form.get('company_name'),
            email=form.get('email'),
            password_hash=generate_password_hash(password),
            # Important HR details
            hr_contact=form.get('hr_contact'),
            website=form.get('website'),
            industry=form.get('industry'),
            description=form.get('description'),
            # Default to Pending, admin must approve
            approval_status='Pending'
        )
        
        try:
            db.session.add(new_company)
            db.session.commit()
            logger.info(f"New company registered: {form.get('company_name')}")
            flash('Company registration submitted. Wait for approval before dashboard access.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error registering company {form.get('company_name')}: {e}")
            db.session.rollback()
            flash('Failed to register company due to an internal error.', 'danger')
            return render_template('company_register.html')
    
    return render_template('company_register.html')

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    return render_template(
        'admin/dashboard.html',
        total_students=Student.query.count(),
        total_companies=Company.query.count(),
        total_job_positions=JobPosition.query.count(),
        total_applications=Application.query.count(),
        pending_companies=Company.query.filter_by(approval_status='Pending').count(),
        pending_jobs=JobPosition.query.filter_by(status='Pending').count()
    )


@app.route('/admin/companies')
@login_required
@role_required('admin')
def admin_companies():
    search_query = request.args.get('search', '').strip()

    if search_query:
        companies = Company.query.filter(
            or_(
                Company.company_name.ilike(f'%{search_query}%'),
                Company.industry.ilike(f'%{search_query}%')
            )
        ).all()
    else:
        companies = Company.query.all()

    return render_template('admin/companies.html', companies=companies, search_query=search_query)

@app.route('/admin/company/approve/<int:company_id>')
@login_required
@role_required('admin')
def admin_approve_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.approval_status = 'Approved'
    db.session.commit()
    flash(f'Company "{company.company_name}" is now approved.', 'success')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/reject/<int:company_id>')
@login_required
@role_required('admin')
def admin_reject_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.approval_status = 'Rejected'
    db.session.commit()
    flash(f'Company "{company.company_name}" was rejected.', 'warning')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/blacklist/<int:company_id>')
@login_required
@role_required('admin')
def admin_blacklist_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.is_blacklisted = not company.is_blacklisted
    db.session.commit()

    status = 'blacklisted' if company.is_blacklisted else 'activated'
    flash(f'Company "{company.company_name}" was {status}.', 'info')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/delete/<int:company_id>')
@login_required
@role_required('admin')
def admin_delete_company(company_id):
    company = Company.query.get_or_404(company_id)
    company_name = company.company_name
    db.session.delete(company)
    db.session.commit()
    flash(f'Company "{company_name}" was deleted.', 'danger')
    return redirect(url_for('admin_companies'))


@app.route('/admin/students')
@login_required
@role_required('admin')
def admin_students():
    search_query = request.args.get('search', '').strip()

    if search_query:
        students = Student.query.filter(
            or_(
                Student.name.ilike(f'%{search_query}%'),
                Student.student_id.ilike(f'%{search_query}%'),
                Student.email.ilike(f'%{search_query}%'),
                Student.contact.ilike(f'%{search_query}%')
            )
        ).all()
    else:
        students = Student.query.all()

    return render_template('admin/students.html', students=students, search_query=search_query)

@app.route('/admin/student/blacklist/<string:student_id>')
@login_required
@role_required('admin')
def admin_blacklist_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_blacklisted = not student.is_blacklisted
    db.session.commit()

    status = 'blacklisted' if student.is_blacklisted else 'activated'
    flash(f'Student "{student.name}" has been {status}.', 'info')
    return redirect(url_for('admin_students'))

@app.route('/admin/student/delete/<string:student_id>')
@login_required
@role_required('admin')
def admin_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    student_name = student.name
    db.session.delete(student)
    db.session.commit()
    flash(f'Student "{student_name}" has been deleted.', 'danger')
    return redirect(url_for('admin_students'))

@app.route('/admin/jobs')
@login_required
@role_required('admin')
def admin_jobs():
    return render_template('admin/jobs.html', jobs=JobPosition.query.all())

@app.route('/admin/job/approve/<int:job_id>')
@login_required
@role_required('admin')
def admin_approve_job(job_id):
    job = JobPosition.query.get_or_404(job_id)
    job.status = 'Approved'
    db.session.commit()
    flash(f'Job "{job.job_title}" has been approved!', 'success')
    return redirect(url_for('admin_jobs'))

@app.route('/admin/job/reject/<int:job_id>')
@login_required
@role_required('admin')
def admin_reject_job(job_id):
    job = JobPosition.query.get_or_404(job_id)
    job.status = 'Rejected'
    db.session.commit()
    flash(f'Job "{job.job_title}" has been rejected.', 'warning')
    return redirect(url_for('admin_jobs'))

@app.route('/admin/job/delete/<int:job_id>')
@login_required
@role_required('admin')
def admin_delete_job(job_id):
    job = JobPosition.query.get_or_404(job_id)
    job_title = job.job_title
    db.session.delete(job)
    db.session.commit()
    flash(f'Job "{job_title}" has been deleted.', 'danger')
    return redirect(url_for('admin_jobs'))

@app.route('/admin/applications')
@login_required
@role_required('admin')
def admin_applications():
    return render_template('admin/applications.html', applications=Application.query.order_by(Application.application_date.desc()).all())


@app.route('/admin/reports')
@login_required
@role_required('admin')
def admin_reports():
    total_students = Student.query.count()
    total_companies = Company.query.count()
    total_jobs = JobPosition.query.count()
    total_applications = Application.query.count()

    approved_jobs = JobPosition.query.filter_by(status='Approved').count()
    pending_jobs = JobPosition.query.filter_by(status='Pending').count()
    rejected_jobs = JobPosition.query.filter_by(status='Rejected').count()
    closed_jobs = JobPosition.query.filter_by(status='Closed').count()

    applied_apps = Application.query.filter_by(status='Applied').count()
    shortlisted_apps = Application.query.filter_by(status='Shortlisted').count()
    interview_apps = Application.query.filter_by(status='Interview').count()
    selected_apps = Application.query.filter_by(status='Selected').count()
    rejected_apps = Application.query.filter_by(status='Rejected').count()

    approved_companies = Company.query.filter_by(approval_status='Approved').count()
    pending_companies = Company.query.filter_by(approval_status='Pending').count()
    rejected_companies = Company.query.filter_by(approval_status='Rejected').count()

    top_companies = db.session.query(
        Company.company_name,
        func.count(Application.id).label('app_count')
    ).join(
        JobPosition, JobPosition.company_id == Company.id
    ).join(
        Application, Application.job_position_id == JobPosition.id
    ).group_by(
        Company.id, Company.company_name
    ).order_by(
        func.count(Application.id).desc()
    ).limit(10).all()

    top_students = db.session.query(
        Student.name,
        Student.student_id,
        func.count(Application.id).label('app_count')
    ).join(
        Application, Application.student_id == Student.student_id
    ).group_by(
        Student.student_id, Student.name
    ).order_by(
        func.count(Application.id).desc()
    ).limit(10).all()

    return render_template(
        'admin/reports.html',
        total_students=total_students,
        total_companies=total_companies,
        total_jobs=total_jobs,
        total_applications=total_applications,
        approved_jobs=approved_jobs,
        pending_jobs=pending_jobs,
        rejected_jobs=rejected_jobs,
        closed_jobs=closed_jobs,
        applied_apps=applied_apps,
        shortlisted_apps=shortlisted_apps,
        interview_apps=interview_apps,
        selected_apps=selected_apps,
        rejected_apps=rejected_apps,
        approved_companies=approved_companies,
        pending_companies=pending_companies,
        rejected_companies=rejected_companies,
        top_companies=top_companies,
        top_students=top_students
    )


@app.route('/admin/placement-records')
@login_required
@role_required('admin')
def admin_placement_records():
    placements = Application.query.filter_by(status='Selected').order_by(Application.updated_at.desc()).all()
    return render_template('admin/placement_records.html', placements=placements)


@app.route('/company/dashboard')
@login_required
@role_required('company')
def company_dashboard():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    company = Company.query.get(session['user_id'])

    total_jobs = JobPosition.query.filter_by(company_id=company.id).count()
    active_jobs = JobPosition.query.filter_by(company_id=company.id, status='Approved').count()
    total_applications = Application.query.join(JobPosition).filter(JobPosition.company_id == company.id).count()

    recent_jobs = JobPosition.query.filter_by(company_id=company.id).order_by(JobPosition.id.desc()).limit(5).all()

    return render_template(
        'company/dashboard.html',
        company=company,
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        total_applications=total_applications,
        recent_jobs=recent_jobs
    )


@app.route('/company/jobs')
@login_required
@role_required('company')
def company_jobs():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    company = Company.query.get(session['user_id'])
    jobs = JobPosition.query.filter_by(company_id=company.id).order_by(JobPosition.id.desc()).all()

    return render_template('company/jobs.html', jobs=jobs)


@app.route('/company/job/create', methods=['GET', 'POST'])
@login_required
@role_required('company')
def company_create_job():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    if request.method == 'POST':
        job_title = request.form.get('job_title')
        job_description = request.form.get('job_description')
        eligibility_criteria = request.form.get('eligibility_criteria')
        required_skills = request.form.get('required_skills')
        experience_required = request.form.get('experience_required')
        salary_range = request.form.get('salary_range')
        application_deadline = request.form.get('application_deadline')

        if not all([job_title, job_description, application_deadline]):
            flash('Please complete the required fields.', 'danger')
            return render_template('company/create_job.html')

        new_job = JobPosition(
            company_id=session['user_id'],
            job_title=job_title,
            job_description=job_description,
            eligibility_criteria=eligibility_criteria,
            required_skills=required_skills,
            experience_required=experience_required,
            salary_range=salary_range,
            application_deadline=datetime.strptime(application_deadline, '%Y-%m-%d').date(),
            status='Pending'
        )

        db.session.add(new_job)
        db.session.commit()

        flash('Job posted. It is now waiting for admin approval.', 'success')
        return redirect(url_for('company_jobs'))

    return render_template('company/create_job.html')


@app.route('/company/job/edit/<int:job_id>', methods=['GET', 'POST'])
@login_required
@role_required('company')
def company_edit_job(job_id):
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    job = JobPosition.query.get_or_404(job_id)

    if job.company_id != session['user_id']:
        flash('You can edit only your own job posts.', 'danger')
        return redirect(url_for('company_jobs'))

    if request.method == 'POST':
        job.job_title = request.form.get('job_title')
        job.job_description = request.form.get('job_description')
        job.eligibility_criteria = request.form.get('eligibility_criteria')
        job.required_skills = request.form.get('required_skills')
        job.experience_required = request.form.get('experience_required')
        job.salary_range = request.form.get('salary_range')

        deadline = request.form.get('application_deadline')
        if deadline:
            job.application_deadline = datetime.strptime(deadline, '%Y-%m-%d').date()

        db.session.commit()
        flash('Job details updated.', 'success')
        return redirect(url_for('company_jobs'))

    return render_template('company/edit_job.html', job=job)


@app.route('/company/job/close/<int:job_id>')
@login_required
@role_required('company')
def company_close_job(job_id):
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    job = JobPosition.query.get_or_404(job_id)

    if job.company_id != session['user_id']:
        flash('You can close only your own job posts.', 'danger')
        return redirect(url_for('company_jobs'))

    job.status = 'Closed'
    db.session.commit()
    flash(f'Job "{job.job_title}" has been closed.', 'info')
    return redirect(url_for('company_jobs'))


@app.route('/company/job/delete/<int:job_id>')
@login_required
@role_required('company')
def company_delete_job(job_id):
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    job = JobPosition.query.get_or_404(job_id)

    if job.company_id != session['user_id']:
        flash('You can delete only your own job posts.', 'danger')
        return redirect(url_for('company_jobs'))

    job_title = job.job_title
    db.session.delete(job)
    db.session.commit()
    flash(f'Job "{job_title}" has been deleted.', 'danger')
    return redirect(url_for('company_jobs'))


@app.route('/company/applications')
@login_required
@role_required('company')
def company_applications():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    company = Company.query.get(session['user_id'])

    applications = Application.query.join(JobPosition).filter(
        JobPosition.company_id == company.id
    ).order_by(Application.application_date.desc()).all()

    return render_template('company/applications.html', applications=applications)


@app.route('/company/application/<int:app_id>')
@login_required
@role_required('company')
def company_view_application(app_id):
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    application = Application.query.get_or_404(app_id)

    if application.job_position.company_id != session['user_id']:
        flash('You can view applications only for your company jobs.', 'danger')
        return redirect(url_for('company_applications'))

    return render_template('company/view_application.html', application=application)


@app.route('/company/application/update/<int:app_id>/<status>')
@login_required
@role_required('company')
def company_update_application(app_id, status):
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    application = Application.query.get_or_404(app_id)

    if application.job_position.company_id != session['user_id']:
        flash('You can update applications only for your company jobs.', 'danger')
        return redirect(url_for('company_applications'))

    valid_statuses = ['Applied', 'Shortlisted', 'Interview', 'Selected', 'Rejected']

    if status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('company_applications'))

    application.status = status
    db.session.commit()

    flash(f'Application status updated to "{status}".', 'success')
    return redirect(url_for('company_view_application', app_id=app_id))


@app.route('/company/shortlisted')
@login_required
@role_required('company')
def company_shortlisted():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    company = Company.query.get(session['user_id'])

    applications = Application.query.join(JobPosition).filter(
        JobPosition.company_id == company.id,
        Application.status.in_(['Shortlisted', 'Interview', 'Selected'])
    ).order_by(Application.updated_at.desc()).all()

    return render_template('company/shortlisted.html', applications=applications)


@app.route('/company/analytics')
@login_required
@role_required('company')
def company_analytics():
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))

    company = Company.query.get(session['user_id'])
    all_jobs = JobPosition.query.filter_by(company_id=company.id).order_by(JobPosition.id.desc()).all()

    job_stats = []
    for job in all_jobs:
        apps = Application.query.filter_by(job_position_id=job.id)
        stats = {
            'job': job,
            'total': apps.count(),
            'applied': apps.filter_by(status='Applied').count(),
            'shortlisted': apps.filter_by(status='Shortlisted').count(),
            'interview': apps.filter_by(status='Interview').count(),
            'selected': apps.filter_by(status='Selected').count(),
            'rejected': apps.filter_by(status='Rejected').count()
        }
        job_stats.append(stats)

    return render_template('company/analytics.html', job_stats=job_stats)

@app.route('/company/pending')
@login_required
@role_required('company')
def company_pending():
    company = Company.query.get(session['user_id'])
    return render_template('company/pending_approval.html', company=company)

# ==================== STUDENT ROUTES ====================

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    student = Student.query.get(session['user_id'])
    
    # Dashboard metrics for a quick overview
    total_applications = Application.query.filter_by(student_id=student.student_id).count()
    shortlisted = Application.query.filter_by(student_id=student.student_id, status='Shortlisted').count()
    selected = Application.query.filter_by(student_id=student.student_id, status='Selected').count()
    
    # fetch recent approved jobs
    recent_jobs = JobPosition.query.filter_by(status='Approved').order_by(JobPosition.id.desc()).limit(5).all()
    
    # recent applications by this student
    recent_applications = Application.query.filter_by(student_id=student.student_id).order_by(Application.application_date.desc()).limit(5).all()
    
    # latest notifications via status changes
    notifications = Application.query.filter_by(student_id=student.student_id).filter(
        Application.status.in_(['Shortlisted', 'Interview', 'Selected', 'Rejected'])
    ).order_by(Application.updated_at.desc()).limit(5).all()
    
    return render_template('student/dashboard.html',
                         student=student,
                         total_applications=total_applications,
                         shortlisted=shortlisted,
                         selected=selected,
                         recent_jobs=recent_jobs,
                         recent_applications=recent_applications,
                         notifications=notifications)

@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_profile():
    # session['user_id'] is actually the student_id string
    student = Student.query.get(session['user_id'])
    
    if request.method == 'POST':
        student.name = request.form.get('name')
        student.contact = request.form.get('contact')
        student.degree = request.form.get('degree')
        student.branch = request.form.get('branch')
        
        cgpa = request.form.get('cgpa')
        student.cgpa = float(cgpa) if cgpa else None
        
        grad_year = request.form.get('graduation_year')
        student.graduation_year = int(grad_year) if grad_year else None
        
        student.skills = request.form.get('skills')
        
        # Handling the resume upload logically
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename != '' and allowed_file(file.filename):
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                filename = secure_filename(file.filename)
                resume_filename = f"{student.student_id}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
                
                # Cleanup the old resume to avoid junk accumulating on server
                if student.resume_path:
                    old_resume = os.path.join(app.config['UPLOAD_FOLDER'], student.resume_path)
                    if os.path.exists(old_resume):
                        os.remove(old_resume)
                
                file.save(filepath)
                student.resume_path = resume_filename
        
        try:
            db.session.commit()
            logger.info(f"Student profile updated for {student.student_id}")
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            logger.error(f"Error updating profile for {student.student_id}: {e}")
            db.session.rollback()
            flash('Could not update profile right now due to a server error.', 'danger')
            
        return redirect(url_for('student_profile'))
    
    return render_template('student/profile.html', student=student)

@app.route('/student/jobs')
@login_required
@role_required('student')
def student_jobs():
    search_query = request.args.get('search', '')
    
    # We strictly only want to display approved jobs to students
    query = JobPosition.query.filter_by(status='Approved')
    
    if search_query:
        query = query.join(Company).filter(
            or_(
                JobPosition.job_title.ilike(f'%{search_query}%'),
                Company.company_name.ilike(f'%{search_query}%'),
                JobPosition.required_skills.ilike(f'%{search_query}%')
            )
        )
    
    jobs = query.order_by(JobPosition.id.desc()).all()
    
    # Fetch which jobs the student already applied to so UI shows an 'Applied' tag
    student_applications = Application.query.filter_by(student_id=session['user_id']).all()
    applied_job_ids = [app.job_position_id for app in student_applications]
    
    return render_template('student/jobs.html', 
                         jobs=jobs, 
                         search_query=search_query,
                         applied_job_ids=applied_job_ids)

@app.route('/student/job/<int:job_id>')
@login_required
@role_required('student')
def student_view_job(job_id):
    job = JobPosition.query.get_or_404(job_id)
    
    if job.status != 'Approved':
        flash('This job is not currently available.', 'warning')
        return redirect(url_for('student_jobs'))
    
    existing_application = Application.query.filter_by(
        student_id=session['user_id'],
        job_position_id=job_id
    ).first()
    
    return render_template('student/view_job.html', 
                         job=job, 
                         has_applied=(existing_application is not None),
                         application=existing_application)

@app.route('/student/job/apply/<int:job_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_apply_job(job_id):
    job = JobPosition.query.get_or_404(job_id)
    
    if job.status != 'Approved':
        flash('This job is not available for applications.', 'warning')
        return redirect(url_for('student_jobs'))
    
    # Double-check they haven't applied already to prevent DB constraint failures!
    existing_application = Application.query.filter_by(
        student_id=session['user_id'],
        job_position_id=job_id
    ).first()
    
    if existing_application:
        flash('You have already applied for this job.', 'warning')
        return redirect(url_for('student_view_job', job_id=job_id))
    
    if request.method == 'POST':
        cover_letter = request.form.get('cover_letter')
        
        new_application = Application(
            student_id=session['user_id'],
            job_position_id=job_id,
            cover_letter=cover_letter,
            status='Applied'
        )
        
        try:
            db.session.add(new_application)
            db.session.commit()
            logger.info(f"Student {session['user_id']} successfully applied to Job {job_id}")
            flash(f'Successfully applied for {job.job_title}!', 'success')
            return redirect(url_for('student_applications'))
        except Exception as e:
            logger.error(f"Error applying to job {job_id} for {session['user_id']}: {e}")
            db.session.rollback()
            flash('There was an error processing your application.', 'danger')
    
    return render_template('student/apply_job.html', job=job)

@app.route('/student/applications')
@login_required
@role_required('student')
def student_applications():
    applications = Application.query.filter_by(student_id=session['user_id']).order_by(Application.application_date.desc()).all()
    return render_template('student/applications.html', applications=applications)


@app.route('/student/placement-history')
@login_required
@role_required('student')
def student_placement_history():
    student = Student.query.get(session['user_id'])

    all_applications = Application.query.filter_by(
        student_id=student.student_id
    ).order_by(
        Application.application_date.desc()
    ).all()

    selected_applications = [app for app in all_applications if app.status == 'Selected']
    rejected_applications = [app for app in all_applications if app.status == 'Rejected']
    pending_applications = [
        app for app in all_applications
        if app.status in ['Applied', 'Shortlisted', 'Interview']
    ]

    return render_template(
        'student/placement_history.html',
        all_applications=all_applications,
        selected_applications=selected_applications,
        rejected_applications=rejected_applications,
        pending_applications=pending_applications
    )

@app.route('/student/application/<int:app_id>')
@login_required
@role_required('student')
def student_view_application(app_id):
    application = Application.query.get_or_404(app_id)
    
    # Ensure students can only view their own applications for strict privacy
    if application.student_id != session['user_id']:
        logger.warning(f"Unauthorized application view attempt by {session['user_id']} on app {app_id}")
        flash('You do not have permission to view this application.', 'danger')
        return redirect(url_for('student_applications'))
    
    return render_template('student/view_application.html', application=application)

@app.route('/student/notifications')
@login_required
@role_required('student')
def student_notifications():
    notifications = Application.query.filter_by(student_id=session['user_id']).order_by(Application.updated_at.desc()).all()
    return render_template('student/notifications.html', notifications=notifications)

if __name__ == '__main__':
    app.run(debug=True)