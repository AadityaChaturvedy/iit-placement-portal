from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Admin, Company, Student
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

"""Making login requirement compulsory"""
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

"""Making role requirement compulsory"""
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Index route
@app.route('/')
def index():
    return render_template('index.html')

# Login route for all users
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not email or not password or not role:
            flash('Please fill all fields.', 'danger')
            return render_template('login.html')
        
        user = None
        
        # Admin login and validation
        if role == 'admin':
            user = Admin.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['user_role'] = 'admin'
                session['username'] = user.username
                flash(f'Welcome Admin {user.username}!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials.', 'danger')

        # Company Login, verification, blacklisting and redirection based on approval status
        elif role == 'company':
            user = Company.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('Your account has been blacklisted. Contact admin.', 'danger')
                    return render_template('login.html')
                
                session['user_id'] = user.id
                session['user_role'] = 'company'
                session['username'] = user.company_name
                session['approval_status'] = user.approval_status
                
                flash(f'Welcome {user.company_name}!', 'success')
                
                if user.approval_status == 'Approved':
                    return redirect(url_for('company_dashboard'))
                else:
                    return redirect(url_for('company_pending'))
            else:
                flash('Invalid company credentials.', 'danger')
        
        # Student Login, verification, blacklisting check and redirection
        elif role == 'student':
            user = Student.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_blacklisted:
                    flash('Your account has been blacklisted. Contact admin.', 'danger')
                    return render_template('login.html')
                
                session['user_id'] = user.student_id
                session['user_role'] = 'student'
                session['username'] = user.name
                flash(f'Welcome {user.name}!', 'success')
                return redirect(url_for('student_dashboard'))
            else:
                flash('Invalid student credentials.', 'danger')
    
    return render_template('login.html')

# Logging out, clearing session, redirecting to index and making login compulsory 
@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

# Student registration
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':

        # Getting data from the form
        student_id = request.form.get('student_id')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        contact = request.form.get('contact')
        degree = request.form.get('degree')
        branch = request.form.get('branch')
        cgpa = request.form.get('cgpa')
        graduation_year = request.form.get('graduation_year')
        skills = request.form.get('skills')
        
        # Validating if all the values are present in the form
        if not all([student_id, name, email, password, confirm_password, contact]):
            flash('Please fill all required fields.', 'danger')
            return render_template('student_register.html')
        
        # Confirming if the entered password and confirm password are same
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('student_register.html')
        
        # Checking if student already exists
        if Student.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('student_register.html')
        
        # Checking if student already registered with the same student ID
        if Student.query.filter_by(student_id=student_id).first():
            flash('Student ID already registered.', 'danger')
            return render_template('student_register.html')
        
        # Creating new student and adding basic details of the student to the database
        new_student = Student(
            student_id=student_id,
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            contact=contact,
            degree=degree,
            branch=branch,
            cgpa=float(cgpa) if cgpa else None,
            graduation_year=int(graduation_year) if graduation_year else None,
            skills=skills
        )
        
        # Adding the new student to the database and commiting the changes
        db.session.add(new_student)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('student_register.html')

# Company registration
@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if request.method == 'POST':

        # Getting data from the form
        company_name = request.form.get('company_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        hr_contact = request.form.get('hr_contact')
        website = request.form.get('website')
        industry = request.form.get('industry')
        description = request.form.get('description')
        
        # Validation of the form data
        if not all([company_name, email, password, confirm_password, hr_contact]):
            flash('Please fill all required fields.', 'danger')
            return render_template('company_register.html')
        
        # Password confirmation check
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('company_register.html')
        
        # Checking if company already exists
        if Company.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('company_register.html')
        
        # Creating new company 
        new_company = Company(
            company_name=company_name,
            email=email,
            password_hash=generate_password_hash(password),
            hr_contact=hr_contact,
            website=website,
            industry=industry,
            description=description,
            approval_status='Pending'
        )
        
        # Adding the new company to the database and commiting the changes
        db.session.add(new_company)
        db.session.commit()
        
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))
    
    return render_template('company_register.html')

# Admin Dashboard
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    return render_template('admin/dashboard.html')

# Company Dashboard
@app.route('/company/dashboard')
@login_required
@role_required('company')
def company_dashboard():
    # Check approval status
    if session.get('approval_status') != 'Approved':
        return redirect(url_for('company_pending'))
    return render_template('company/dashboard.html')

# Company Pending Approval Page
@app.route('/company/pending')
@login_required
@role_required('company')
def company_pending():
    company = Company.query.get(session['user_id'])
    return render_template('company/pending_approval.html', company=company)

# Student Dashboard
@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    return render_template('student/dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)