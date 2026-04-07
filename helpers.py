"""helpers.py - utility functions pulled out of app.py
"""
from flask import session, flash, redirect, url_for
from models import Admin, Company, Student


ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}


def allowed_file(filename):
    if '.' not in filename:
        return False
    file_extension = filename.rsplit('.', 1)[1].lower()
    return file_extension in ALLOWED_EXTENSIONS


def grab_user():
    """Returns the current logged-in user object based on session role."""
    user_id = session.get('user_id')
    user_role = session.get('user_role')
    if not user_id or not user_role:
        return None

    if user_role == 'admin':
        return Admin.query.get(user_id)
    elif user_role == 'company':
        return Company.query.get(user_id)
    elif user_role == 'student':
        return Student.query.get(user_id)
    return None


def bail(msg, cat='danger', dest='index'):
    """Flash + redirect shortcut."""
    flash(msg, cat)
    return redirect(url_for(dest))
