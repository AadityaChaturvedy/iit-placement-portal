import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Admin, Company, Student, JobPosition, Application, Placement
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import or_
from datetime import datetime

# Setup basic logging to help with debugging later
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
            skills=form.get('skills')
        )
        
        try:
            db.session.add(new_student)
            db.session.commit()
            logger.info(f"Student registered successfully: {student_id}")
            flash('Student registration completed. Please sign in.', 'success')
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

@app.route('/company/pending')
@login_required
@role_required('company')
def company_pending():
    company = Company.query.get(session['user_id'])
    return render_template('company/pending_approval.html', company=company)

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    return render_template('student/dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)