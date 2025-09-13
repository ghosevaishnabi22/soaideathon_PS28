SMART TIMETABLE SCHEDULER
---
About The Project:

This project is made by Vaishnabi Ghose, for the Modern Application Development 1 course project.

The main theme of this project is to build a multi-user Smart Timetable Scheduler which supports three roles: Admin/Dean, Teacher, and Student. Each user has specific functionalities, and a superuser (Admin/Dean) gets automatically added whenever a new database is created.

ROLES & FEATURES
-----------------

ADMIN/DEAN:
===========
- Can create Classrooms, Subjects, Departments, and Batches.
- Inside each classroom, sections are auto-generated, and sections get randomly assigned to batches.
- Can generate 3 alternative routines for a section and choose the best one.
- Can view all faculties and search them by department.
- Can view rearrangement messages when teachers apply for leave.
- Can view a Summary Dashboard showing 4 analytical charts:
  - Chart 1: Faculty Load Distribution
  - Chart 2: Routine Utilization
  - Chart 3: Subject Allocation Summary
  - Chart 4: Faculty by Department

TEACHER:
========
- Can view their own assigned routine.
- Can apply for leave, after which the system reassigns that particular class to the next best available teacher.
- Can view rearrangement messages (updates on classes shifted due to leaves).

STUDENT:
========
- Can view their own section routine.
- Can choose extra subjects of their choice to add into their profile.

COMMON FEATURES:
-----------------

- Forgot Password – Users can reset their password via email.
- Edit Profile – Users can update their personal details.

Technologies Used:
------------------

- Python – Backend logic implementation.
- Flask – Web framework used for routing and server-side functionality.
- SQLite – Lightweight file-based database to store users, routines, subjects, departments, and classrooms.
- SQLAlchemy – ORM used for interacting with the SQLite database via Python classes.
- Flask-Migrate – To handle schema updates (add new columns/tables without losing existing data).
- HTML with Jinja2 – To create dynamic server-rendered web pages.
- Matplotlib – Used for generating analytical charts for the Summary Dashboard.
- VS Code – Code editor used to write and manage the project.

How to Run:
-------------

1. Set Root Folder:
   Ensure the root folder includes app.py, requirements.txt, and subfolders like templates/ and static/.

2. Create Virtual Environment:
   python -m venv ANY_NAME_OF_VIRTUAL_ENVIRONMENT

3. Activate Environment:
   - On Windows:
     ANY_NAME_OF_VIRTUAL_ENVIRONMENT\Scripts\activate
   - On Mac/Linux:
     source ANY_NAME_OF_VIRTUAL_ENVIRONMENT/bin/activate

4. Prerequisites:
   - Python installed on your system.
   - Packages listed in requirements.txt.

5. Install Dependencies:
   pip install -r requirements.txt

6. Run the Application:
   python app.py

Project Link:
--------------

Smart Timetable Scheduler – GitHub Repository: https://github.com/ghosevaishnabi22/soaideathon_PS28
