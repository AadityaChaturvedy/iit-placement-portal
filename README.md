# IIT Placement Portal

A comprehensive, role-based web application designed to manage the end-to-end college placement process for students, recruiters, and administrators. 

## Features

- **Role-based Access Control**: Dedicated dashboards and permissions for Students, Companies, and Admins.
- **Student Portal**: Manage profiles, upload resumes, browse active job postings, application submission, and track application statuses in real-time.
- **Company Portal**: Post and manage job openings, set application deadlines, review applicants, and shortlist or select candidates.
- **Admin Center**: Approve and verify company accounts, blacklist or manage users, and oversee system-wide placement data and metrics.
- **Data Analytics**: Visual reporting dashboards and trend visualization leveraging Chart.js.
- **RESTful Endpoints**: Internal APIs to dynamically fetch platform data resources securely (`/api/...`).

## Technology Stack

| Technology / Library | Purpose |
| :--- | :--- |
| **Flask** | Core backend web framework |
| **Flask-SQLAlchemy** | Object Relational Mapper for database interaction with Python |
| **Werkzeug** | Security utilities, including secure password hashing |
| **Jinja2** | Template engine for rendering dynamic HTML pages |
| **HTML5 & CSS3** | Core markup structure and custom frontend styling |
| **Bootstrap 5** | Frontend styling framework for rapid, responsive design |
| **Chart.js** | Data visualization for administrative reports and platform activity trends |
| **SQLite** | Lightweight local database for storing application data |

## Architecture Overview

- **`app.py`** – Main Flask application entry point, containing controllers and routing logic.
- **`models.py`** – Database models and schema definitions leveraging SQLAlchemy.
- **`helpers.py`** – Reusable utility functions, session validation decorators, and logic.
- **`/templates`** – Jinja2 HTML templates, organized into subdirectories by user role (`admin`, `company`, `student`) and reusable component layouts (`_macros.html`, `base.html`).
- **`/static`** – Global static assets including custom CSS, charts, and client-side JavaScript.

## Getting Started

### Prerequisites

- Python 3.8+

### Local Installation

1. Navigate to the project directory:
   ```bash
   cd IIT_Placement_Portal
   ```

2. Set up a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install Flask Flask-SQLAlchemy Werkzeug
   ```

4. Initialize the database schema:
   ```bash
   python create_db.py
   ```

5. Start the web server:
   ```bash
   python app.py
   ```

6. Open your web browser and navigate to `http://127.0.0.1:5000`.

### Student Login

For student login after registration the email address is: <Student ID>@iit.edu.in
