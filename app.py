import logging
import os
import csv
import io
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, make_response, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func

from models import db, Admin, Company, Student, JobPosition, Application, Placement
from config import Config
from helpers import allowed_file, grab_user, bail, validate_password

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def role_required(role):
    def outer(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if session.get('user_role') != role:
                return bail('This page is not available for your account role.')
            return f(*args, **kwargs)
        return inner
    return outer


def api_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'ok': False, 'error': 'authentication required'}), 401
        return f(*args, **kwargs)
    return wrapper


def _json_error(message, code=400):
    return jsonify({'ok': False, 'error': message}), code


def _serialize_company(company):
    return {
        'id': company.id,
        'company_name': company.company_name,
        'email': company.email,
        'hr_contact': company.hr_contact,
        'website': company.website,
        'industry': company.industry,
        'description': company.description,
        'approval_status': company.approval_status,
        'is_blacklisted': company.is_blacklisted,
    }


def _serialize_student(student):
    return {
        'student_id': student.student_id,
        'name': student.name,
        'email': student.email,
        'contact': student.contact,
        'degree': student.degree,
        'branch': student.branch,
        'cgpa': student.cgpa,
        'graduation_year': student.graduation_year,
        'skills': student.skills,
        'resume_path': student.resume_path,
        'is_blacklisted': student.is_blacklisted,
    }


def _serialize_job(job):
    return {
        'id': job.id,
        'company_id': job.company_id,
        'company_name': job.company.company_name if job.company else None,
        'job_title': job.job_title,
        'job_description': job.job_description,
        'eligibility_criteria': job.eligibility_criteria,
        'required_skills': job.required_skills,
        'experience_required': job.experience_required,
        'salary_range': job.salary_range,
        'application_deadline': job.application_deadline.isoformat() if job.application_deadline else None,
        'status': job.status,
    }


def _serialize_application(application):
    return {
        'id': application.id,
        'student_id': application.student_id,
        'student_name': application.student.name if application.student else None,
        'job_position_id': application.job_position_id,
        'job_title': application.job_position.job_title if application.job_position else None,
        'company_name': application.job_position.company.company_name if application.job_position and application.job_position.company else None,
        'application_date': application.application_date.isoformat() if application.application_date else None,
        'status': application.status,
        'cover_letter': application.cover_letter,
        'updated_at': application.updated_at.isoformat() if application.updated_at else None,
    }


def _check_company_approved():
    # redirects unapproved companies away from dashboard pages
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))
    return None


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method != 'POST':
        return render_template('login.html')

    submitted_email = request.form.get('email', '').strip()
    submitted_password = request.form.get('password', '')
    selected_role = request.form.get('role', '')

    if not submitted_email or not submitted_password or not selected_role:
        flash('Please enter email, password, and role.', 'danger')
        return render_template('login.html')

    if selected_role == 'admin':
        admin_account = Admin.query.filter_by(email=submitted_email).first()
        if admin_account and check_password_hash(admin_account.password_hash, submitted_password):
            session['user_id'] = admin_account.id
            session['user_role'] = 'admin'
            session['username'] = admin_account.username
            flash(f'Welcome back, {admin_account.username}.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Admin login failed. Check credentials.', 'danger')

    elif selected_role == 'company':
        company_account = Company.query.filter_by(email=submitted_email).first()
        if company_account and check_password_hash(company_account.password_hash, submitted_password):
            if company_account.is_blacklisted:
                flash('This account is currently blocked. Contact the placement office.', 'danger')
                return render_template('login.html')

            session['user_id'] = company_account.id
            session['user_role'] = 'company'
            session['username'] = company_account.company_name
            session['approval_status'] = company_account.approval_status
            flash('Welcome back, {}.'.format(company_account.company_name), 'success')

            if company_account.approval_status == 'Approved':
                return redirect(url_for('company_dashboard'))
            return redirect(url_for('company_pending'))

        flash('Company login failed. Check credentials.', 'danger')

    elif selected_role == 'student':
        student_account = Student.query.filter_by(email=submitted_email).first()
        if not student_account or not check_password_hash(student_account.password_hash, submitted_password):
            flash('Student login failed.', 'danger')
            return render_template('login.html')

        if student_account.is_blacklisted:
            flash('Account blocked — please contact placement office.', 'danger')
            return render_template('login.html')

        session['user_id'] = student_account.student_id
        session['user_role'] = 'student'
        session['username'] = student_account.name
        flash(f'Hey {student_account.name}, welcome back!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logged_out_user = session.get('username', 'unknown')
    session.clear()
    log.info("%s logged out", logged_out_user)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method != 'POST':
        return render_template('student_register.html')

    form_data = request.form
    roll_number   = form_data.get('student_id', '').strip()
    full_name     = form_data.get('name', '').strip()
    raw_password  = form_data.get('password')
    confirm_pwd   = form_data.get('confirm_password')
    country_code  = form_data.get('country_code', '').strip()
    phone_raw     = form_data.get('contact', '').strip()

    email_address = f"{roll_number}@iit.edu.in" if roll_number else ""

    if not all([roll_number, full_name, raw_password, confirm_pwd, phone_raw, country_code]):
        flash('Please complete all mandatory fields.', 'danger')
        return render_template('student_register.html')

    phone_number = f"{country_code}{phone_raw}".strip()

    if len(country_code.replace('+', '')) > 3:
        flash('Country code can have a maximum of 3 digits.', 'danger')
        return render_template('student_register.html')

    if len(phone_number) > 15:
        flash('Country code and phone number combined must not exceed 15 characters.', 'danger')
        return render_template('student_register.html')

    pwd_error = validate_password(raw_password)
    if pwd_error:
        flash(pwd_error, 'danger')
        return render_template('student_register.html')

    if raw_password != confirm_pwd:
        flash('Passwords don\'t match.', 'danger')
        return render_template('student_register.html')

    duplicate_check = Student.query.filter(
        (Student.email == email_address) | (Student.student_id == roll_number)
    ).first()
    if duplicate_check:
        flash('Student ID or email already registered.', 'danger')
        return render_template('student_register.html')

    resume_filename = None
    if 'resume' in request.files:
        uploaded_resume = request.files['resume']
        if uploaded_resume and uploaded_resume.filename and allowed_file(uploaded_resume.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            safe_name = secure_filename(uploaded_resume.filename)
            resume_filename = f"{roll_number}_{safe_name}"
            uploaded_resume.save(os.path.join(app.config['UPLOAD_FOLDER'], resume_filename))

    cgpa_value = None
    if form_data.get('cgpa'):
        try:
            cgpa_value = float(form_data['cgpa'])
        except ValueError:
            pass

    graduation_year_value = None
    if form_data.get('graduation_year'):
        try:
            graduation_year_value = int(form_data['graduation_year'])
        except ValueError:
            pass

    new_student = Student(
        student_id=roll_number, name=full_name, email=email_address,
        password_hash=generate_password_hash(raw_password),
        contact=phone_number,
        degree=form_data.get('degree'), branch=form_data.get('branch'),
        cgpa=cgpa_value, graduation_year=graduation_year_value,
        skills=form_data.get('skills'),
        resume_path=resume_filename
    )

    try:
        db.session.add(new_student)
        db.session.commit()
        log.info("student registered: %s", roll_number)
        flash('Registration done! Please login.', 'success')
        return redirect(url_for('login'))
    except Exception as registration_error:
        log.error("registration failed for %s: %s", roll_number, registration_error)
        db.session.rollback()
        flash('Error during registration, try again.', 'danger')
        return render_template('student_register.html')


@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if request.method != 'POST':
        return render_template('company_register.html')

    reg_form = request.form
    company_name  = reg_form.get('company_name', '').strip()
    company_email = reg_form.get('email', '').strip()
    raw_password  = reg_form.get('password')
    country_code  = reg_form.get('country_code', '').strip()
    hr_phone_base = reg_form.get('hr_contact', '').strip()

    if not company_name or not company_email or not raw_password or not hr_phone_base:
        flash('Fill in all required fields.', 'danger')
        return render_template('company_register.html')

    hr_phone = f"{country_code}{hr_phone_base}".strip()

    if len(country_code.replace('+', '')) > 3:
        flash('Country code can have a maximum of 3 digits.', 'danger')
        return render_template('company_register.html')

    if len(hr_phone) > 15:
        flash('Country code and phone number combined must not exceed 15 characters.', 'danger')
        return render_template('company_register.html')

    pwd_error = validate_password(raw_password)
    if pwd_error:
        flash(pwd_error, 'danger')
        return render_template('company_register.html')

    if raw_password != reg_form.get('confirm_password'):
        flash('Passwords don\'t match.', 'danger')
        return render_template('company_register.html')

    if Company.query.filter_by(email=company_email).first():
        flash('Email already registered.', 'danger')
        return render_template('company_register.html')

    new_company = Company(
        company_name=company_name, email=company_email,
        password_hash=generate_password_hash(raw_password),
        hr_contact=hr_phone,
        website=reg_form.get('website'),
        industry=reg_form.get('industry'),
        description=reg_form.get('description'),
        approval_status='Pending'
    )

    db.session.add(new_company)
    try:
        db.session.commit()
        log.info("company registered: %s", company_name)
        flash('Registration submitted. You\'ll get access after admin approval.', 'success')
        return redirect(url_for('login'))
    except Exception:
        db.session.rollback()
        flash('Something went wrong, please try again.', 'danger')
        return render_template('company_register.html')


@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    overview_stats = {
        'total_students': Student.query.count(),
        'total_companies': Company.query.count(),
        'total_jobs': JobPosition.query.count(),
        'total_applications': Application.query.count(),
        'pending_companies': Company.query.filter_by(approval_status='Pending').count(),
        'pending_jobs': JobPosition.query.filter_by(status='Pending').count(),
    }
    return render_template('admin/dashboard.html', **overview_stats)


@app.route('/admin/companies')
@login_required
@role_required('admin')
def admin_companies():
    search_input = request.args.get('search', '').strip()

    if search_input:
        company_list = Company.query.filter(
            or_(Company.company_name.ilike('%{}%'.format(search_input)),
                Company.industry.ilike('%{}%'.format(search_input)))
        ).all()
    else:
        company_list = Company.query.all()

    return render_template('admin/companies.html', companies=company_list, search_query=search_input)


# merged approve/reject/blacklist/delete into one route to cut down on repetition
@app.route('/admin/company/<int:cid>/<action>')
@login_required
@role_required('admin')
def admin_company_action(cid, action):
    target_company = Company.query.get_or_404(cid)

    if action == 'approve':
        target_company.approval_status = 'Approved'
        db.session.commit()
        flash(f'{target_company.company_name} approved.', 'success')
    elif action == 'reject':
        target_company.approval_status = 'Rejected'
        db.session.commit()
        flash(f'{target_company.company_name} rejected.', 'warning')
    elif action == 'toggle-blacklist':
        target_company.is_blacklisted = not target_company.is_blacklisted
        db.session.commit()
        blacklist_label = 'blacklisted' if target_company.is_blacklisted else 'un-blacklisted'
        flash('{} {}.'.format(target_company.company_name, blacklist_label), 'info')
    elif action == 'delete':
        deleted_name = target_company.company_name
        db.session.delete(target_company)
        db.session.commit()
        flash(f'{deleted_name} deleted.', 'danger')
    else:
        flash('Invalid action.', 'danger')

    return redirect(url_for('admin_companies'))


@app.route('/admin/students')
@login_required
@role_required('admin')
def admin_students():
    search_input = request.args.get('search', '').strip()

    if search_input:
        student_list = Student.query.filter(
            or_(
                Student.name.ilike(f'%{search_input}%'),
                Student.student_id.ilike(f'%{search_input}%'),
                Student.email.ilike(f'%{search_input}%'),
            )
        ).all()
    else:
        student_list = Student.query.all()

    return render_template('admin/students.html', students=student_list, search_query=search_input)


@app.route('/admin/student/blacklist/<string:sid>')
@login_required
@role_required('admin')
def admin_blacklist_student(sid):
    target_student = Student.query.get_or_404(sid)
    target_student.is_blacklisted = not target_student.is_blacklisted
    db.session.commit()
    toggle_label = 'blacklisted' if target_student.is_blacklisted else 'activated'
    flash(f'{target_student.name} has been {toggle_label}.', 'info')
    return redirect(url_for('admin_students'))


@app.route('/admin/student/delete/<string:sid>')
@login_required
@role_required('admin')
def admin_delete_student(sid):
    target_student = Student.query.get_or_404(sid)
    student_name = target_student.name
    db.session.delete(target_student)
    db.session.commit()
    flash('Deleted student {}.'.format(student_name), 'danger')
    return redirect(url_for('admin_students'))


@app.route('/admin/student/edit/<string:sid>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_student(sid):
    target_student = Student.query.get_or_404(sid)

    if request.method != 'POST':
        return render_template('admin/edit_student.html', student=target_student)

    target_student.name = request.form.get('name', target_student.name).strip()
    target_student.contact = request.form.get('contact', target_student.contact).strip()
    target_student.degree = request.form.get('degree')
    target_student.branch = request.form.get('branch')
    target_student.skills = request.form.get('skills')

    email_value = request.form.get('email', target_student.email).strip()
    existing_email = Student.query.filter(
        Student.email == email_value,
        Student.student_id != target_student.student_id
    ).first()
    if existing_email:
        flash('Another student already uses that email.', 'danger')
        return render_template('admin/edit_student.html', student=target_student)
    target_student.email = email_value

    cgpa_value = request.form.get('cgpa', '').strip()
    if cgpa_value:
        try:
            target_student.cgpa = float(cgpa_value)
        except ValueError:
            flash('Invalid CGPA value.', 'danger')
            return render_template('admin/edit_student.html', student=target_student)
    else:
        target_student.cgpa = None

    graduation_year_value = request.form.get('graduation_year', '').strip()
    if graduation_year_value:
        try:
            target_student.graduation_year = int(graduation_year_value)
        except ValueError:
            flash('Invalid graduation year.', 'danger')
            return render_template('admin/edit_student.html', student=target_student)
    else:
        target_student.graduation_year = None

    target_student.is_blacklisted = request.form.get('is_blacklisted') == 'on'

    db.session.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/company/edit/<int:cid>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_company(cid):
    target_company = Company.query.get_or_404(cid)

    if request.method != 'POST':
        return render_template('admin/edit_company.html', company=target_company)

    target_company.company_name = request.form.get('company_name', target_company.company_name).strip()
    target_company.hr_contact = request.form.get('hr_contact', target_company.hr_contact).strip()
    target_company.website = request.form.get('website')
    target_company.industry = request.form.get('industry')
    target_company.description = request.form.get('description')

    email_value = request.form.get('email', target_company.email).strip()
    existing_email = Company.query.filter(Company.email == email_value, Company.id != target_company.id).first()
    if existing_email:
        flash('Another company already uses that email.', 'danger')
        return render_template('admin/edit_company.html', company=target_company)
    target_company.email = email_value

    status_value = request.form.get('approval_status', target_company.approval_status)
    if status_value not in ['Pending', 'Approved', 'Rejected']:
        flash('Invalid approval status.', 'danger')
        return render_template('admin/edit_company.html', company=target_company)
    target_company.approval_status = status_value
    target_company.is_blacklisted = request.form.get('is_blacklisted') == 'on'

    db.session.commit()
    flash('Company updated successfully.', 'success')
    return redirect(url_for('admin_companies'))


@app.route('/admin/jobs')
@login_required
@role_required('admin')
def admin_jobs():
    all_jobs = JobPosition.query.order_by(JobPosition.id.desc()).all()
    return render_template('admin/jobs.html', jobs=all_jobs)


@app.route('/admin/job/<int:jid>/<action>')
@login_required
@role_required('admin')
def admin_job_action(jid, action):
    target_job = JobPosition.query.get_or_404(jid)

    if action == 'approve':
        target_job.status = 'Approved'
        db.session.commit()
        flash(f'"{target_job.job_title}" approved!', 'success')
    elif action == 'reject':
        target_job.status = 'Rejected'
        db.session.commit()
        flash(f'"{target_job.job_title}" rejected.', 'warning')
    elif action == 'delete':
        deleted_title = target_job.job_title
        db.session.delete(target_job)
        db.session.commit()
        flash('"{}" deleted.'.format(deleted_title), 'danger')
    else:
        flash('Invalid action.', 'danger')

    return redirect(url_for('admin_jobs'))


@app.route('/admin/applications')
@login_required
@role_required('admin')
def admin_applications():
    application_list = Application.query.order_by(Application.application_date.desc()).all()
    return render_template('admin/applications.html', applications=application_list)


@app.route('/admin/reports')
@login_required
@role_required('admin')
def admin_reports():
    total_students = Student.query.count()
    total_companies = Company.query.count()
    total_jobs = JobPosition.query.count()
    total_applications = Application.query.count()

    job_status_counts = {}
    for status_label in ['Approved', 'Pending', 'Rejected', 'Closed']:
        job_status_counts[status_label.lower()] = JobPosition.query.filter_by(status=status_label).count()

    application_status_counts = {}
    for status_label in ['Applied', 'Shortlisted', 'Interview', 'Selected', 'Rejected']:
        application_status_counts[status_label.lower()] = Application.query.filter_by(status=status_label).count()

    company_approval_counts = {}
    for status_label in ['Approved', 'Pending', 'Rejected']:
        company_approval_counts[status_label.lower()] = Company.query.filter_by(approval_status=status_label).count()

    # print("DEBUG job_status_counts:", job_status_counts)

    top_companies_by_applications = db.session.query(
        Company.company_name,
        func.count(Application.id).label('cnt')
    ).join(
        JobPosition, JobPosition.company_id == Company.id
    ).join(
        Application, Application.job_position_id == JobPosition.id
    ).group_by(Company.id, Company.company_name
    ).order_by(func.count(Application.id).desc()
    ).limit(10).all()

    most_active_students = db.session.query(
        Student.name, Student.student_id,
        func.count(Application.id).label('cnt')
    ).join(Application, Application.student_id == Student.student_id
    ).group_by(Student.student_id, Student.name
    ).order_by(func.count(Application.id).desc()
    ).limit(10).all()

    return render_template('admin/reports.html',
        total_students=total_students, total_companies=total_companies,
        total_jobs=total_jobs, total_apps=total_applications,
        job_counts=job_status_counts, app_counts=application_status_counts,
        company_counts=company_approval_counts,
        top_companies=top_companies_by_applications, top_students=most_active_students
    )


@app.route('/admin/placement-records')
@login_required
@role_required('admin')
def admin_placement_records():
    placed_applications = Application.query.filter_by(
        status='Selected'
    ).order_by(Application.updated_at.desc()).all()
    return render_template('admin/placement_records.html', placements=placed_applications)


@app.route('/admin/export-placements')
@login_required
@role_required('admin')
def admin_export_placements():
    # csv columns match what the placement office spreadsheet expects
    placed_students = Application.query.filter_by(status='Selected').all()

    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    csv_writer.writerow(['Student ID', 'Student Name', 'Company', 'Job Title', 'Date'])

    for placed_record in placed_students:
        student_name = placed_record.student.name if placed_record.student else 'N/A'
        company_name = placed_record.job_position.company.company_name if placed_record.job_position else 'N/A'
        position_title = placed_record.job_position.job_title if placed_record.job_position else 'N/A'
        placement_date = placed_record.updated_at.strftime('%Y-%m-%d') if placed_record.updated_at else ''

        csv_writer.writerow([
            placed_record.student_id,
            student_name,
            company_name,
            position_title,
            placement_date
        ])

    response = make_response(csv_buffer.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=placements.csv'
    return response


@app.route('/company/dashboard')
@login_required
@role_required('company')
def company_dashboard():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    current_company = Company.query.get(session['user_id'])
    company_jobs = JobPosition.query.filter_by(company_id=current_company.id)

    return render_template('company/dashboard.html',
        company=current_company,
        total_jobs=company_jobs.count(),
        active_jobs=company_jobs.filter_by(status='Approved').count(),
        total_applications=Application.query.join(JobPosition).filter(
            JobPosition.company_id == current_company.id).count(),
        recent_jobs=company_jobs.order_by(JobPosition.id.desc()).limit(5).all()
    )


@app.route('/company/jobs')
@login_required
@role_required('company')
def company_jobs():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    current_company = Company.query.get(session['user_id'])
    job_listings = JobPosition.query.filter_by(
        company_id=current_company.id
    ).order_by(JobPosition.id.desc()).all()
    return render_template('company/jobs.html', jobs=job_listings)


@app.route('/company/job/create', methods=['GET', 'POST'])
@login_required
@role_required('company')
def company_create_job():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    if request.method != 'POST':
        return render_template('company/create_job.html')

    position_title = request.form.get('job_title', '').strip()
    position_description = request.form.get('job_description', '').strip()
    deadline_string = request.form.get('application_deadline', '')

    if not position_title or not position_description or not deadline_string:
        flash('Title, description and deadline are required.', 'danger')
        return render_template('company/create_job.html')

    try:
        parsed_deadline = datetime.strptime(deadline_string, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return render_template('company/create_job.html')

    new_position = JobPosition(
        company_id=session['user_id'],
        job_title=position_title,
        job_description=position_description,
        eligibility_criteria=request.form.get('eligibility_criteria'),
        required_skills=request.form.get('required_skills'),
        experience_required=request.form.get('experience_required'),
        salary_range=request.form.get('salary_range'),
        application_deadline=parsed_deadline,
        status='Pending'
    )
    db.session.add(new_position)
    db.session.commit()
    flash('Job posted! Waiting for admin approval.', 'success')
    return redirect(url_for('company_jobs'))


@app.route('/company/job/edit/<int:job_id>', methods=['GET', 'POST'])
@login_required
@role_required('company')
def company_edit_job(job_id):
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    existing_job = JobPosition.query.get_or_404(job_id)

    if existing_job.company_id != session['user_id']:
        return bail('You can only edit your own jobs.', dest='company_jobs')

    if request.method == 'POST':
        existing_job.job_title = request.form.get('job_title')
        existing_job.job_description = request.form.get('job_description')
        existing_job.eligibility_criteria = request.form.get('eligibility_criteria')
        existing_job.required_skills = request.form.get('required_skills')
        existing_job.experience_required = request.form.get('experience_required')
        existing_job.salary_range = request.form.get('salary_range')

        deadline_raw = request.form.get('application_deadline')
        if deadline_raw:
            try:
                existing_job.application_deadline = datetime.strptime(deadline_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('Bad date format, skipping deadline update.', 'warning')

        db.session.commit()
        flash('Job updated.', 'success')
        return redirect(url_for('company_jobs'))

    return render_template('company/edit_job.html', job=existing_job)


@app.route('/company/job/close/<int:job_id>')
@login_required
@role_required('company')
def company_close_job(job_id):
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    target_job = JobPosition.query.get_or_404(job_id)
    if target_job.company_id != session['user_id']:
        return bail('Not your job listing.', dest='company_jobs')

    target_job.status = 'Closed'
    db.session.commit()
    flash('Closed "{}".'.format(target_job.job_title), 'info')
    return redirect(url_for('company_jobs'))


@app.route('/company/job/delete/<int:job_id>')
@login_required
@role_required('company')
def company_delete_job(job_id):
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    target_job = JobPosition.query.get_or_404(job_id)
    if target_job.company_id != session['user_id']:
        return bail('Not your job listing.', dest='company_jobs')

    deleted_title = target_job.job_title
    db.session.delete(target_job)
    db.session.commit()
    flash(f'Deleted "{deleted_title}".', 'danger')
    return redirect(url_for('company_jobs'))


@app.route('/company/applications')
@login_required
@role_required('company')
def company_applications():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    current_company_id = session['user_id']
    received_applications = Application.query.join(JobPosition).filter(
        JobPosition.company_id == current_company_id
    ).order_by(Application.application_date.desc()).all()
    return render_template('company/applications.html', applications=received_applications)


@app.route('/company/application/<int:app_id>')
@login_required
@role_required('company')
def company_view_application(app_id):
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    selected_application = Application.query.get_or_404(app_id)
    if selected_application.job_position.company_id != session['user_id']:
        return bail('Not your application to view.', dest='company_applications')

    return render_template('company/view_application.html', application=selected_application)


@app.route('/company/application/update/<int:app_id>/<status>')
@login_required
@role_required('company')
def company_update_application(app_id, status):
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    selected_application = Application.query.get_or_404(app_id)
    if selected_application.job_position.company_id != session['user_id']:
        return bail('Not your application.', dest='company_applications')

    allowed_statuses = ['Applied', 'Shortlisted', 'Interview', 'Selected', 'Rejected']
    if status not in allowed_statuses:
        flash('Invalid status value.', 'danger')
        return redirect(url_for('company_applications'))

    selected_application.status = status
    db.session.commit()
    # print(f"DEBUG: updated app {app_id} to {status}")
    flash(f'Status changed to {status}.', 'success')
    return redirect(url_for('company_view_application', app_id=app_id))


@app.route('/company/shortlisted')
@login_required
@role_required('company')
def company_shortlisted():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    current_company_id = session['user_id']
    shortlisted_applications = Application.query.join(JobPosition).filter(
        JobPosition.company_id == current_company_id,
        Application.status.in_(['Shortlisted', 'Interview', 'Selected'])
    ).order_by(Application.updated_at.desc()).all()
    return render_template('company/shortlisted.html', applications=shortlisted_applications)


@app.route('/company/analytics')
@login_required
@role_required('company')
def company_analytics():
    approval_redirect = _check_company_approved()
    if approval_redirect:
        return approval_redirect

    current_company = Company.query.get(session['user_id'])
    all_company_jobs = JobPosition.query.filter_by(
        company_id=current_company.id
    ).order_by(JobPosition.id.desc()).all()

    # TODO: this is N+1 queries per job, should probably optimize if it gets slow
    per_job_stats = []
    for single_job in all_company_jobs:
        job_applications = Application.query.filter_by(job_position_id=single_job.id)
        per_job_stats.append({
            'job': single_job,
            'total': job_applications.count(),
            'applied': job_applications.filter_by(status='Applied').count(),
            'shortlisted': job_applications.filter_by(status='Shortlisted').count(),
            'interview': job_applications.filter_by(status='Interview').count(),
            'selected': job_applications.filter_by(status='Selected').count(),
            'rejected': job_applications.filter_by(status='Rejected').count(),
        })

    return render_template('company/analytics.html', job_stats=per_job_stats)


@app.route('/company/pending')
@login_required
@role_required('company')
def company_pending():
    pending_company = Company.query.get(session['user_id'])
    return render_template('company/pending_approval.html', company=pending_company)


@app.route('/company/profile', methods=['GET', 'POST'])
@login_required
@role_required('company')
def company_profile():
    current_company = Company.query.get_or_404(session['user_id'])

    if request.method != 'POST':
        return render_template('company/profile.html', company=current_company)

    current_company.company_name = request.form.get('company_name', current_company.company_name).strip()
    current_company.hr_contact = request.form.get('hr_contact', current_company.hr_contact).strip()
    current_company.website = request.form.get('website')
    current_company.industry = request.form.get('industry')
    current_company.description = request.form.get('description')

    email_value = request.form.get('email', current_company.email).strip()
    duplicate_email = Company.query.filter(Company.email == email_value, Company.id != current_company.id).first()
    if duplicate_email:
        flash('Email already in use by another company.', 'danger')
        return render_template('company/profile.html', company=current_company)
    current_company.email = email_value

    db.session.commit()
    session['username'] = current_company.company_name
    flash('Company profile updated.', 'success')
    return redirect(url_for('company_profile'))


@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    current_student = Student.query.get(session['user_id'])
    student_applications = Application.query.filter_by(student_id=current_student.student_id)

    return render_template('student/dashboard.html',
        student=current_student,
        total_applications=student_applications.count(),
        shortlisted=student_applications.filter_by(status='Shortlisted').count(),
        selected=student_applications.filter_by(status='Selected').count(),
        recent_jobs=JobPosition.query.filter_by(status='Approved').order_by(
            JobPosition.id.desc()).limit(5).all(),
        recent_applications=student_applications.order_by(
            Application.application_date.desc()).limit(5).all(),
        notifications=student_applications.filter(
            Application.status.in_(['Shortlisted', 'Interview', 'Selected', 'Rejected'])
        ).order_by(Application.updated_at.desc()).limit(5).all()
    )


@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_profile():
    current_student = Student.query.get(session['user_id'])

    if request.method != 'POST':
        return render_template('student/profile.html', student=current_student)

    current_student.name = request.form.get('name', current_student.name)
    current_student.contact = request.form.get('contact', current_student.contact)
    current_student.degree = request.form.get('degree')
    current_student.branch = request.form.get('branch')
    current_student.skills = request.form.get('skills')

    cgpa_input = request.form.get('cgpa')
    if cgpa_input:
        current_student.cgpa = float(cgpa_input)
    else:
        current_student.cgpa = None

    grad_year_input = request.form.get('graduation_year')
    if grad_year_input:
        current_student.graduation_year = int(grad_year_input)
    else:
        current_student.graduation_year = None

    if 'resume' in request.files:
        uploaded_file = request.files['resume']
        if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

            sanitized_name = secure_filename(uploaded_file.filename)
            new_resume_name = "{}_{}".format(current_student.student_id, sanitized_name)
            new_resume_path = os.path.join(app.config['UPLOAD_FOLDER'], new_resume_name)

            if current_student.resume_path:
                old_resume_path = os.path.join(app.config['UPLOAD_FOLDER'], current_student.resume_path)
                if os.path.exists(old_resume_path):
                    os.remove(old_resume_path)

            uploaded_file.save(new_resume_path)
            current_student.resume_path = new_resume_name

    try:
        db.session.commit()
        flash('Profile saved!', 'success')
    except Exception as profile_error:
        log.error("profile update failed: %s", profile_error)
        db.session.rollback()
        flash('Could not save profile right now.', 'danger')

    return redirect(url_for('student_profile'))


@app.route('/student/jobs')
@login_required
@role_required('student')
def student_jobs():
    search_input = request.args.get('search', '').strip()

    approved_jobs_query = JobPosition.query.filter_by(status='Approved')

    if search_input:
        approved_jobs_query = approved_jobs_query.join(Company).filter(
            or_(
                JobPosition.job_title.ilike(f'%{search_input}%'),
                Company.company_name.ilike(f'%{search_input}%'),
                JobPosition.required_skills.ilike(f'%{search_input}%'),
            )
        )

    available_jobs = approved_jobs_query.order_by(JobPosition.id.desc()).all()

    # figure out which jobs this student already applied to so we can grey out those buttons
    my_applications = Application.query.filter_by(student_id=session['user_id']).all()
    already_applied_job_ids = set()
    for app_record in my_applications:
        already_applied_job_ids.add(app_record.job_position_id)

    return render_template('student/jobs.html',
        jobs=available_jobs, search_query=search_input, applied_job_ids=already_applied_job_ids)


@app.route('/student/job/<int:job_id>')
@login_required
@role_required('student')
def student_view_job(job_id):
    requested_job = JobPosition.query.get_or_404(job_id)

    if requested_job.status != 'Approved':
        flash('This job is not available.', 'warning')
        return redirect(url_for('student_jobs'))

    existing_application = Application.query.filter_by(
        student_id=session['user_id'], job_position_id=job_id
    ).first()

    return render_template('student/view_job.html',
        job=requested_job, has_applied=existing_application is not None, application=existing_application)


@app.route('/student/job/apply/<int:job_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_apply_job(job_id):
    target_job = JobPosition.query.get_or_404(job_id)

    if target_job.status != 'Approved':
        flash('Job not open for applications.', 'warning')
        return redirect(url_for('student_jobs'))

    if Application.query.filter_by(
        student_id=session['user_id'], job_position_id=job_id
    ).first():
        flash('Already applied for this one.', 'warning')
        return redirect(url_for('student_view_job', job_id=job_id))

    if request.method != 'POST':
        return render_template('student/apply_job.html', job=target_job)

    new_application = Application(
        student_id=session['user_id'],
        job_position_id=job_id,
        cover_letter=request.form.get('cover_letter'),
        status='Applied'
    )

    try:
        db.session.add(new_application)
        db.session.commit()
        log.info("student %s applied to job %d", session['user_id'], job_id)
        flash(f'Applied for {target_job.job_title}!', 'success')
        return redirect(url_for('student_applications'))
    except Exception as apply_error:
        log.error("application error: %s", apply_error)
        db.session.rollback()
        flash('Error submitting application.', 'danger')

    return render_template('student/apply_job.html', job=target_job)


@app.route('/student/applications')
@login_required
@role_required('student')
def student_applications():
    my_applications = Application.query.filter_by(
        student_id=session['user_id']
    ).order_by(Application.application_date.desc()).all()
    # print("student applications count:", len(my_applications))
    return render_template('student/applications.html', applications=my_applications)


@app.route('/student/placement-history')
@login_required
@role_required('student')
def student_placement_history():
    current_student = Student.query.get(session['user_id'])

    all_applications = Application.query.filter_by(
        student_id=current_student.student_id
    ).order_by(Application.application_date.desc()).all()

    selected_apps = []
    rejected_apps = []
    pending_apps = []
    for single_app in all_applications:
        if single_app.status == 'Selected':
            selected_apps.append(single_app)
        elif single_app.status == 'Rejected':
            rejected_apps.append(single_app)
        elif single_app.status in ('Applied', 'Shortlisted', 'Interview'):
            pending_apps.append(single_app)

    return render_template('student/placement_history.html',
        all_applications=all_applications,
        selected_applications=selected_apps,
        rejected_applications=rejected_apps,
        pending_applications=pending_apps
    )


@app.route('/student/application/<int:app_id>')
@login_required
@role_required('student')
def student_view_application(app_id):
    requested_application = Application.query.get_or_404(app_id)

    if requested_application.student_id != session['user_id']:
        log.warning("unauthorized view attempt: user=%s tried app=%d",
                     session['user_id'], app_id)
        return bail('You don\'t have access to this.', dest='student_applications')

    return render_template('student/view_application.html', application=requested_application)


@app.route('/student/notifications')
@login_required
@role_required('student')
def student_notifications():
    status_updates = Application.query.filter_by(
        student_id=session['user_id']
    ).order_by(Application.updated_at.desc()).all()
    return render_template('student/notifications.html', notifications=status_updates)


@app.route('/api/companies', methods=['GET'])
@api_login_required
def api_companies():
    if session.get('user_role') != 'admin':
        return _json_error('forbidden', 403)

    company_list = Company.query.order_by(Company.id.desc()).all()
    return jsonify({'ok': True, 'data': [_serialize_company(c) for c in company_list]})


@app.route('/api/students', methods=['GET'])
@api_login_required
def api_students():
    if session.get('user_role') != 'admin':
        return _json_error('forbidden', 403)

    student_list = Student.query.order_by(Student.student_id.desc()).all()
    return jsonify({'ok': True, 'data': [_serialize_student(s) for s in student_list]})


@app.route('/api/jobs', methods=['GET', 'POST'])
@api_login_required
def api_jobs():
    role = session.get('user_role')

    if request.method == 'GET':
        if role == 'admin':
            jobs = JobPosition.query.order_by(JobPosition.id.desc()).all()
        elif role == 'company':
            jobs = JobPosition.query.filter_by(company_id=session['user_id']).order_by(JobPosition.id.desc()).all()
        else:
            jobs = JobPosition.query.filter_by(status='Approved').order_by(JobPosition.id.desc()).all()
        return jsonify({'ok': True, 'data': [_serialize_job(job) for job in jobs]})

    if role != 'company':
        return _json_error('only company users can create jobs', 403)

    current_company = Company.query.get_or_404(session['user_id'])
    if current_company.approval_status != 'Approved' or current_company.is_blacklisted:
        return _json_error('company account is not allowed to create jobs', 403)

    payload = request.get_json(silent=True) or {}
    job_title = (payload.get('job_title') or '').strip()
    job_description = (payload.get('job_description') or '').strip()
    application_deadline = payload.get('application_deadline')

    if not job_title or not job_description or not application_deadline:
        return _json_error('job_title, job_description and application_deadline are required', 400)

    try:
        parsed_deadline = datetime.strptime(application_deadline, '%Y-%m-%d').date()
    except ValueError:
        return _json_error('application_deadline must be in YYYY-MM-DD format', 400)

    new_job = JobPosition(
        company_id=current_company.id,
        job_title=job_title,
        job_description=job_description,
        eligibility_criteria=payload.get('eligibility_criteria'),
        required_skills=payload.get('required_skills'),
        experience_required=payload.get('experience_required'),
        salary_range=payload.get('salary_range'),
        application_deadline=parsed_deadline,
        status='Pending'
    )
    db.session.add(new_job)
    db.session.commit()

    return jsonify({'ok': True, 'message': 'job created and sent for admin approval', 'data': _serialize_job(new_job)}), 201


@app.route('/api/applications', methods=['GET'])
@api_login_required
def api_applications():
    role = session.get('user_role')

    if role == 'admin':
        applications = Application.query.order_by(Application.application_date.desc()).all()
    elif role == 'company':
        applications = Application.query.join(JobPosition).filter(
            JobPosition.company_id == session['user_id']
        ).order_by(Application.application_date.desc()).all()
    else:
        applications = Application.query.filter_by(
            student_id=session['user_id']
        ).order_by(Application.application_date.desc()).all()

    return jsonify({'ok': True, 'data': [_serialize_application(a) for a in applications]})


@app.route('/api/jobs/<int:job_id>/apply', methods=['POST'])
@api_login_required
def api_apply_job(job_id):
    if session.get('user_role') != 'student':
        return _json_error('only student users can apply', 403)

    target_job = JobPosition.query.get_or_404(job_id)
    if target_job.status != 'Approved':
        return _json_error('job is not open for applications', 400)

    existing = Application.query.filter_by(student_id=session['user_id'], job_position_id=job_id).first()
    if existing:
        return _json_error('already applied to this job', 409)

    payload = request.get_json(silent=True) or {}
    new_application = Application(
        student_id=session['user_id'],
        job_position_id=job_id,
        cover_letter=payload.get('cover_letter'),
        status='Applied'
    )
    db.session.add(new_application)
    db.session.commit()

    return jsonify({'ok': True, 'message': 'application submitted', 'data': _serialize_application(new_application)}), 201


@app.route('/api/applications/<int:app_id>/status', methods=['PATCH'])
@api_login_required
def api_update_application_status(app_id):
    role = session.get('user_role')
    if role not in ['admin', 'company']:
        return _json_error('forbidden', 403)

    application = Application.query.get_or_404(app_id)

    if role == 'company' and application.job_position.company_id != session['user_id']:
        return _json_error('forbidden', 403)

    payload = request.get_json(silent=True) or {}
    status = payload.get('status')
    allowed_statuses = ['Applied', 'Shortlisted', 'Interview', 'Selected', 'Rejected']
    if status not in allowed_statuses:
        return _json_error('invalid status value', 400)

    application.status = status
    db.session.commit()

    return jsonify({'ok': True, 'message': 'application status updated', 'data': _serialize_application(application)})


if __name__ == '__main__':
    app.run(debug=True)