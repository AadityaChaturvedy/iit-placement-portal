from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Admin, Company, Student, JobPosition, Application, Placement
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import or_

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('user_role') != role:
                flash('You do not have permission to access this page.', 'danger')
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
            flash('Please fill all fields.', 'danger')
            return render_template('login.html')
        
        if role == 'admin':
            user = Admin.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['user_role'] = 'admin'
                session['username'] = user.username
                flash(f'Welcome Admin {user.username}!', 'success')
                return redirect(url_for('admin_dashboard'))
            flash('Invalid admin credentials.', 'danger')

        elif role == 'company':
            user = Company.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('Your account has been blacklisted. Contact admin.', 'danger')
                    return render_template('login.html')
                
                session.update({
                    'user_id': user.id,
                    'user_role': 'company',
                    'username': user.company_name,
                    'approval_status': user.approval_status
                })
                flash(f'Welcome {user.company_name}!', 'success')
                
                if user.approval_status == 'Approved':
                    return redirect(url_for('company_dashboard'))
                return redirect(url_for('company_pending'))
                
            flash('Invalid company credentials.', 'danger')
        
        elif role == 'student':
            user = Student.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('Your account has been blacklisted. Contact admin.', 'danger')
                    return render_template('login.html')
                
                session.update({
                    'user_id': user.student_id,
                    'user_role': 'student',
                    'username': user.name
                })
                flash(f'Welcome {user.name}!', 'success')
                return redirect(url_for('student_dashboard'))
                
            flash('Invalid student credentials.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
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
            flash('Please fill all required fields.', 'danger')
            return render_template('student_register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('student_register.html')
        
        if Student.query.filter((Student.email == email) | (Student.student_id == student_id)).first():
            flash('Student ID or Email already registered.', 'danger')
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
        
        db.session.add(new_student)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('student_register.html')

@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if request.method == 'POST':
        form = request.form
        
        required_fields = ['company_name', 'email', 'password', 'confirm_password', 'hr_contact']
        if not all([form.get(f) for f in required_fields]):
            flash('Please fill all required fields.', 'danger')
            return render_template('company_register.html')
            
        password = form.get('password')
        if password != form.get('confirm_password'):
            flash('Passwords do not match.', 'danger')
            return render_template('company_register.html')
        
        if Company.query.filter_by(email=form.get('email')).first():
            flash('Email already registered.', 'danger')
            return render_template('company_register.html')
        
        new_company = Company(
            company_name=form.get('company_name'),
            email=form.get('email'),
            password_hash=generate_password_hash(password),
            hr_contact=form.get('hr_contact'),
            website=form.get('website'),
            industry=form.get('industry'),
            description=form.get('description'),
            approval_status='Pending'
        )
        
        db.session.add(new_company)
        db.session.commit()
        
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))
    
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
    flash(f'Company "{company.company_name}" has been approved!', 'success')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/reject/<int:company_id>')
@login_required
@role_required('admin')
def admin_reject_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.approval_status = 'Rejected'
    db.session.commit()
    flash(f'Company "{company.company_name}" has been rejected.', 'warning')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/blacklist/<int:company_id>')
@login_required
@role_required('admin')
def admin_blacklist_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.is_blacklisted = not company.is_blacklisted
    db.session.commit()

    status = 'blacklisted' if company.is_blacklisted else 'activated'
    flash(f'Company "{company.company_name}" has been {status}.', 'info')
    return redirect(url_for('admin_companies'))

@app.route('/admin/company/delete/<int:company_id>')
@login_required
@role_required('admin')
def admin_delete_company(company_id):
    company = Company.query.get_or_404(company_id)
    company_name = company.company_name
    db.session.delete(company)
    db.session.commit()
    flash(f'Company "{company_name}" has been deleted.', 'danger')
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
    return render_template('company/dashboard.html')

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