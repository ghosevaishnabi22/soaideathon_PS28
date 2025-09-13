import math
from itertools import cycle
from collections import defaultdict
import random
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, CheckConstraint
from datetime import datetime
from flask_migrate import Migrate
import matplotlib.pyplot as plt

plt.switch_backend('Agg')  # Use a non-interactive backend for matplotlib

app = Flask(__name__)

# Set the secret key for flash messages
app.config['SECRET_KEY'] = 'sweet_and_sour'

# Configure the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ITERease.db'
db = SQLAlchemy()
db.init_app(app)

migrate = Migrate(app, db)

app.app_context().push()

# ------------------ MODELS ------------------
class Teacher(db.Model):
    __tablename__ = 'teacher'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    address = db.Column(db.String(255))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'))
    is_dean = db.Column(db.Boolean, default=False)
    workload = db.Column(db.Integer, default=0, nullable=False)

    subjects = db.relationship('Subject', backref='teacher')
    # back_populates to match RoutineSlot.teacher
    routine_slots = db.relationship('RoutineSlot', back_populates='teacher')


class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    address = db.Column(db.String(255))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)

    extra_subjects = db.relationship('ExtraSubject', secondary='student_extra_subject', backref='students')


class ClassRoom(db.Model):
    __tablename__ = 'classroom'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    capacity = db.Column(db.Integer, nullable=False, default=30)

    batches = db.relationship('Batch', backref='classroom')
    students = db.relationship('Student', backref='classroom')
    teachers = db.relationship('Teacher', backref='classroom')


class Batch(db.Model):
    __tablename__ = 'batch'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)  # Morning/Evening
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey("section.id"), nullable=False)

    section = db.relationship('Section', backref='batches')


class Section(db.Model):
    __tablename__ = 'section'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(10), nullable=False, unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    selected_routine = db.Column(db.String(10), nullable=True)

    students = db.relationship('Student', backref='section')
    routines = db.relationship('Routine', backref='section')


class Department(db.Model):
    __tablename__ = 'department'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    teachers = db.relationship('Teacher', backref='department')
    students = db.relationship('Student', backref='department')
    sections = db.relationship('Section', backref='department')
    subjects = db.relationship('Subject', backref='department')
    extra_subjects = db.relationship('ExtraSubject', backref='department')


class Subject(db.Model):
    __tablename__ = 'subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)

    # FIXED relationship
    routine_slots = db.relationship('RoutineSlot', back_populates='subject')


class FixedSubject(db.Model):
    __tablename__ = 'fixed_subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    day = db.Column(db.String(10), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)


class ExtraSubject(db.Model):
    __tablename__ = 'extra_subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)


class StudentExtraSubject(db.Model):
    __tablename__ = 'student_extra_subject'
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), primary_key=True)
    extra_subject_id = db.Column(db.Integer, db.ForeignKey('extra_subject.id'), primary_key=True)

class Routine(db.Model):
    __tablename__ = 'routine'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    finalized = db.Column(db.Boolean, default=False)

    # backref on RoutineSlot is 'routine'
    slots = db.relationship('RoutineSlot', back_populates='routine', cascade="all, delete-orphan")

class RoutineSlot(db.Model):
    __tablename__ = 'routine_slot'   # singular name used by SubstituteLog below
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    routine_id = db.Column(db.Integer, db.ForeignKey('routine.id'), nullable=False)
    day = db.Column(db.String(10), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    # MAKE teacher_id NULLABLE so Lunch / Games can be teacher-less
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)

    routine = db.relationship('Routine', back_populates='slots')
    subject = db.relationship('Subject', back_populates='routine_slots')   # simple access to subject.name
    teacher = db.relationship('Teacher', back_populates='routine_slots')   # simple access to teacher.name

class SubstituteLog(db.Model):
    __tablename__ = 'substitute_log'
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('routine_slot.id'))
    from_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))
    to_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    slot = db.relationship('RoutineSlot')
    from_teacher = db.relationship('Teacher', foreign_keys=[from_teacher_id])
    to_teacher = db.relationship('Teacher', foreign_keys=[to_teacher_id])


class StudentSubjectChoice(db.Model):
    __tablename__ = 'student_subject_choice'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'subject_id', 'section_id', name='uq_student_subject_section'),
    )

    student = db.relationship('Student')
    subject = db.relationship('Subject')
    section = db.relationship('Section')


db.create_all()

# ------------------ COMMON ROUTES ------------------

@app.route('/') 
def default():
    return render_template('default.html')

@app.route('/logout', methods=['GET'])
def logout():
    flash("You have been logged out successfully.")
    return redirect('/')

# ------------------ TEACHER ROUTES ------------------
@app.route('/tlogin', methods=['GET', 'POST'])
def tlogin():
    if request.method == 'GET':
        # GET should render login page; don't attempt to read form
        return render_template('tlogin.html', teacher=None)
    if request.method == 'POST':
        email=request.form.get('email')
        password=request.form.get('password')
        teacher = Teacher.query.filter_by(email=email).first()
        if not teacher:
            flash('Email does not exist. Please try again.')
            return redirect('/tlogin')
        else:
            if teacher.password == password:
                if teacher.is_dean:
                    return redirect(f'/deandashboard/{teacher.id}')
                else:
                    return redirect(f'/teacherdashboard/{teacher.id}')
            else:
                flash('Incorrect password. Please try again.')
                return redirect('/tlogin')
            

@app.route('/tforgotpassword', methods=['GET', 'POST'])
def tforgotpassword():
    if request.method == 'GET':
        return render_template('tforgotpassword.html')

    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        teacher = Teacher.query.filter_by(email=email).first()

        if not teacher:
            flash("Teacher not found.")
            return redirect('/tforgotpassword')

        if teacher.phone != phone:
            flash("Phone number doesn't match our records.")
            return redirect('/tforgotpassword')

        # Update the password
        teacher.password = password
        db.session.commit()

        flash("Password reset successful. Please log in.")
        return redirect('/tlogin')

@app.route('/teacherdashboard/<int:id>', methods=['GET'])
def teacherdashboard(id):
    teacher = Teacher.query.get_or_404(id)

    if teacher.is_dean:
        flash("⚠️ Access Denied")
        return redirect("/")

    # Get teacher’s slots
    slots = RoutineSlot.query.filter_by(teacher_id=teacher.id).all()

    # Get routines tied to those slots
    routine_ids = {s.routine_id for s in slots}
    routines = Routine.query.filter(Routine.id.in_(routine_ids)).all() if routine_ids else []

    # Get logs (reassignments)
    logs = SubstituteLog.query.order_by(SubstituteLog.timestamp.desc()).all()

    # --- Add flags for highlighting ---
    # Mark slots that were reassigned (added)
    reassigned_slot_ids = {log.slot_id for log in logs if log.to_teacher_id == teacher.id}
    for s in slots:
        s.added = s.id in reassigned_slot_ids

    # Mark slots as absent (this assumes you already log absences in SubstituteLog or similar)
    absent_slot_ids = {log.slot_id for log in logs if log.from_teacher_id == teacher.id}
    for s in slots:
        s.absent = s.id in absent_slot_ids

    return render_template(
        'teacherdashboard.html',
        teacher=teacher,
        routines=routines,
        slots=slots,
        logs=logs
    )



# teacher accepts a routine
@app.route('/accept_routine', methods=['POST'])
def accept_routine():
    routine_id = request.form.get('routine_id')
    teacher_id = request.form.get('teacher_id')
    routine = Routine.query.get(routine_id)
    if routine:
        routine.finalized = True
        db.session.commit()
        flash("✅ Routine accepted.")
    return redirect(f"/teacherdashboard/{teacher_id}")

# teacher absent, reassign
@app.route('/mark_absent', methods=['POST'])
def mark_absent():
    slot_id = request.form.get('slot_id')
    teacher_id = request.form.get('teacher_id')

    slot = RoutineSlot.query.get(slot_id)
    teacher = Teacher.query.get(teacher_id)

    # find next best teacher in the same department
    next_teacher = Teacher.query.filter(
        Teacher.department_id == teacher.department_id,
        Teacher.id != teacher.id,
        Teacher.is_dean == False
    ).order_by(Teacher.workload).first()  # use workload column

    if next_teacher:
        old_teacher_id = slot.teacher_id
        slot.teacher_id = next_teacher.id
        db.session.commit()

        # log event
        log = SubstituteLog(slot_id=slot.id,
                            from_teacher_id=old_teacher_id,
                            to_teacher_id=next_teacher.id)
        db.session.add(log)
        db.session.commit()
        flash(f"⚠️ Slot reassigned to {next_teacher.name}")
    else:
        # assign to dean
        dean = Teacher.query.filter_by(is_dean=True).first()
        old_teacher_id = slot.teacher_id
        slot.teacher_id = dean.id
        db.session.commit()

        log = SubstituteLog(slot_id=slot.id,
                            from_teacher_id=old_teacher_id,
                            to_teacher_id=dean.id)
        db.session.add(log)
        db.session.commit()
        flash(f"⚠️ Slot reassigned to Dean")
    return redirect(f"/teacherdashboard/{teacher_id}")

@app.route('/teditprofile/<int:id>', methods=['GET', 'POST'])
def teditprofile(id):
    teacher = Teacher.query.filter_by(id=id).first()
    if not teacher:
        flash("❌ Teacher not found.")
        return redirect('/')

    if request.method == 'GET':
        return render_template('teditprofile.html', teacher=teacher)

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_phone = request.form.get('phone')
        new_address = request.form.get('address')
        new_password = request.form.get('password')

        # ✅ Check if phone is changing & already taken
        if new_phone != teacher.phone:
            if Teacher.query.filter_by(phone=new_phone).first():
                flash("⚠️ Phone number already in use.")
                return redirect(f'/teditprofile/{id}')

        # Update allowed fields
        teacher.name = new_name
        teacher.phone = new_phone
        teacher.address = new_address
        teacher.password = new_password  # (⚠️ ideally hash this)

        db.session.commit()
        flash("✅ Profile updated successfully.")
        if teacher.is_dean:
            return redirect(f'/deandashboard/{teacher.id}')
        else:
            return redirect(f'/teacherdashboard/{teacher.id}')


# ------------------ STUDENT ROUTES ------------------
@app.route('/slogin', methods=['GET', 'POST'])
def slogin():
    if request.method == 'GET':
        return render_template('slogin.html', student=None)
    if request.method == 'POST':
        email=request.form.get('email')
        password=request.form.get('password')
        student = Student.query.filter_by(email=email).first()
        if not student:
            flash('Email does not exist. Please try again.')
            return redirect('/slogin')
        else:
            if student.password == password:
                return redirect(f'/studentdashboard/{student.id}')
            else:
                flash('Incorrect password. Please try again.')
                return redirect('/slogin')

@app.route('/sforgotpassword', methods=['GET', 'POST'])
def sforgotpassword():
    if request.method == 'GET':
        return render_template('sforgotpassword.html')

    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        student = Student.query.filter_by(email=email).first()

        if not student:
            flash("Student not found.")
            return redirect('/sforgotpassword')

        if student.phone != phone:
            flash("Phone number doesn't match our records.")
            return redirect('/sforgotpassword')

        # Update the password
        student.password = password
        db.session.commit()

        flash("Password reset successful. Please log in.")
        return redirect('/slogin')


@app.route('/studentdashboard/<int:id>', methods=['GET', 'POST'])
def studentdashboard(id):
    student = Student.query.get(id)
    if not student:
        flash("❌ Student not found.")
        return redirect('/')

    # Handle POST (student choosing extra subjects)
    if request.method == 'POST':
        extra_subject_id = request.form.get('extra_subject_id')
        if extra_subject_id:
            extra_subject = ExtraSubject.query.get(int(extra_subject_id))
            if extra_subject and extra_subject not in student.extra_subjects:
                student.extra_subjects.append(extra_subject)
                db.session.commit()
                flash(f"✅ Added {extra_subject.name} to your subjects")

        return redirect(url_for('studentdashboard', id=student.id))

    # --- TIMETABLE ---
    section = student.section
    routines = (
        Routine.query.filter_by(section_id=section.id, finalized=True)
        .order_by(Routine.version)
        .all()
    )
    latest_routine = routines[-1] if routines else None
    slots = latest_routine.slots if latest_routine else []

    # --- EXTRA SUBJECTS ---
    all_extra_subjects = ExtraSubject.query.filter_by(
        department_id=student.department_id
    ).all()
    chosen_extra_subjects = student.extra_subjects

    return render_template(
        'studentdashboard.html',
        student=student,
        routine=latest_routine,
        slots=slots,
        all_extra_subjects=all_extra_subjects,
        chosen_extra_subjects=chosen_extra_subjects
    )


@app.route('/choose_subjects/<int:student_id>', methods=['POST'])
def choose_subjects(student_id):
    selected_subjects = request.form.getlist('subject_ids')
    section_id = request.form.get('section_id')

    for sid in selected_subjects:
        choice = StudentSubjectChoice(student_id=student_id, subject_id=sid, section_id=section_id)
        db.session.add(choice)
    db.session.commit()

    flash("✅ Your subject choices saved.")
    return redirect(f'/studentdashboard/{student_id}')

@app.route('/seditprofile/<int:id>', methods=['GET', 'POST'])
def seditprofile(id):
    student = Student.query.filter_by(id=id).first()
    if not student:
        flash("❌ Student not found.")
        return redirect('/')

    if request.method == 'GET':
        return render_template('seditprofile.html', student=student)

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_phone = request.form.get('phone')
        new_address = request.form.get('address')
        new_password = request.form.get('password')

        # ✅ Check if phone is changing & already taken
        if new_phone != student.phone:
            if Student.query.filter_by(phone=new_phone).first():
                flash("⚠️ Phone number already in use.")
                return redirect(f'/seditprofile/{id}')

        # Update allowed fields
        student.name = new_name
        student.phone = new_phone
        student.address = new_address
        student.password = new_password  # ⚠️ (ideally hash this)

        db.session.commit()
        flash("✅ Profile updated successfully.")
        return redirect(f'/studentdashboard/{student.id}')



# ------------------ PRINCIPAL(ADMIN) ROUTES ------------------
@app.route('/deandashboard/<id>', methods=['GET', 'POST'])
def deandashboard(id):
    if request.method == 'GET':
        dean = Teacher.query.filter_by(id=int(id)).first()
        if not dean:
            flash("❌ Dean not found.")
            return redirect('/') 

        if not dean.is_dean:
            flash("⚠️ Access Denied")
            return redirect("/")
        
        classrooms = ClassRoom.query.all()
        batches = Batch.query.all()
        sections = Section.query.all()
        departments = Department.query.all()

        allocated_sections = Batch.query.with_entities(Batch.section_id).distinct().count()
        total_sections = len(sections)
        return render_template('deandashboard.html',dean=dean,classrooms=classrooms,batches=batches,sections=sections,departments=departments,allocated_sections=allocated_sections,total_sections=total_sections)

@app.route('/addclassroom', methods=['GET', 'POST'])
def addclassroom():
    dean = Teacher.query.filter_by(is_dean=True).first()
    if request.method == 'GET':
        return render_template('addclassroom.html', dean=dean)

    if request.method == 'POST':
        capacity = request.form.get('capacity')

        # Create classroom first (temporary name)
        new_classroom = ClassRoom(name="TEMP", capacity=capacity)
        db.session.add(new_classroom)
        db.session.commit()

        # Rename after ID is assigned
        new_classroom.name = f"CR{new_classroom.id}"
        db.session.commit()

        # Get sections that are NOT already allocated
        allocated_section_ids = [b.section_id for b in Batch.query.all()]
        available_sections = Section.query.filter(~Section.id.in_(allocated_section_ids)).all()
        random.shuffle(available_sections)

        # Allocate to Morning batch
        if len(available_sections) >= 1:
            morning_batch = Batch(
                name="Morning",
                classroom_id=new_classroom.id,
                section_id=available_sections.pop().id
            )
            db.session.add(morning_batch)

        # Allocate to Evening batch
        if len(available_sections) >= 1:
            evening_batch = Batch(
                name="Evening",
                classroom_id=new_classroom.id,
                section_id=available_sections.pop().id
            )
            db.session.add(evening_batch)

        db.session.commit()

        flash(f"✅ Classroom {new_classroom.name} created with batches as available.")
        return redirect(f"/deandashboard/{dean.id}")


@app.route('/addsection', methods=['GET', 'POST'])
def addsection():
    dean = Teacher.query.filter_by(is_dean=True).first()
    id = dean.id

    if request.method == 'GET':
        departments = Department.query.all()
        return render_template('addsection.html', dean=dean, departments=departments)

    if request.method == 'POST':
        dept_id = request.form.get("department_id")
        dept = Department.query.get(dept_id)

        if not dept:
            flash("❌ Department not found.")
            return redirect(f'/deandashboard/{id}')

        # Create new section
        new_section = Section(
            name=f"{dept.name[:3].upper()}{len(dept.sections) + 1}",
            department_id=dept.id
        )
        db.session.add(new_section)
        db.session.commit()

        # Find last allocated batch
        last_batch = Batch.query.order_by(Batch.id.desc()).first()

        if not last_batch:
            classroom = ClassRoom.query.first()
            if not classroom:
                flash("⚠️ No classroom available.")
                return redirect(f'/deandashboard/{id}')

            batch = Batch(name="Morning", classroom_id=classroom.id, section_id=new_section.id)
            db.session.add(batch)
            db.session.commit()
            flash("✅ Section created & Morning batch allocated.")
            return redirect(f'/deandashboard/{id}')

        if last_batch.name == "Morning":
            batch = Batch(name="Evening", classroom_id=last_batch.classroom_id, section_id=new_section.id)
            db.session.add(batch)
            db.session.commit()
            flash("✅ Section created & Evening batch allocated.")
        else:
            flash("✅ Section created but waiting for classroom allocation.")

        return redirect(f'/deandashboard/{id}')

@app.route('/departmentdetails/<id>', methods=['GET', 'POST'])
def departmentdetails(id):
    dean = Teacher.query.filter_by(id=int(id)).first()
    
    if not dean or not dean.is_dean:
        flash("❌ Dean not found or access denied.")
        return redirect('/')
    sections = Section.query.filter_by(department_id=dean.department_id).all()
    departments = Department.query.all()
    return render_template('departmentdetails.html', dean=dean, departments=departments, sections=sections)

@app.route('/adddepartment', methods=['GET', 'POST'])
def adddepartment():
    dean = Teacher.query.filter_by(is_dean=True).first()
    if request.method == 'GET':
        return render_template('adddepartment.html', dean=dean)

    if request.method == 'POST':
        dep_name = request.form.get('dep_name')

        if Department.query.filter_by(name=dep_name).first():
            flash("❌ Department already exists.")
            return redirect('/adddepartment')

        new_department = Department(name=dep_name)
        db.session.add(new_department)
        db.session.commit()

        flash("✅ Department added successfully.")
        return redirect(f'/departmentdetails/{dean.id}')
 

@app.route('/addsubject/<dept_id>', methods=['GET', 'POST'])
def addsubject(dept_id):
    department = Department.query.filter_by(id=int(dept_id)).first()
    dean = Teacher.query.filter_by(is_dean=True).first()

    if request.method == 'GET':
        return render_template('addsubject.html', dean=dean, department=department)

    if request.method == 'POST':
        subject_name = request.form.get('subject_name')

        new_subject = Subject(name=subject_name, department_id=department.id)
        db.session.add(new_subject)
        db.session.commit()

        flash("✅ Subject added successfully.")
        return redirect(f'/departmentdetails/{dean.id}')
    
@app.route('/routine/<int:dean_id>')
def select_section(dean_id):
    dean = Teacher.query.get_or_404(dean_id)

    sections = Section.query.all()
    pending_sections = []
    for sec in sections:
        # if no routines exist at all → pending
        if not sec.routines or len(sec.routines) == 0:
            pending_sections.append(sec)
        # if routines exist but none finalized → hide (do nothing)
        # if at least one finalized → hide (do nothing)

    return render_template('routine.html', dean=dean, sections=pending_sections)



@app.route('/generate_routine/<int:section_id>', methods=['GET', 'POST'])
def generate_routine(section_id):
    dean = Teacher.query.filter_by(is_dean=True).first()
    section = Section.query.get_or_404(section_id)
    subjects = Subject.query.all()

    if request.method == 'GET':
        return render_template(
            'generate_routine.html',
            dean=dean,
            section=section,
            subjects=subjects,
            fixed_subjects=[]
        )

    if request.method == 'POST':
        selected_subject_ids = request.form.getlist('subject_ids')
        if not selected_subject_ids:
            flash("⚠ Please select at least one subject.", "warning")
            return redirect(request.url)

        # build class counts from the form (default 3 per subject)
        class_counts = {}
        for sid in selected_subject_ids:
            class_counts[int(sid)] = int(request.form.get(f'classes_{sid}', 3))

        # ✅ Generate and save 3 routine options into DB
        routines = generate_three_options(
            section.id,
            [int(s) for s in selected_subject_ids],
            class_counts
        )

        # Query them back with slots loaded (get the newly generated versions)
        options = Routine.query.filter_by(section_id=section.id, finalized=False).order_by(Routine.version).all()


        return render_template(
            'show_routine_options.html',
            dean=dean,
            section=section,
            options=options
        )


@app.route("/routine/select/<int:section_id>/<int:option_version>", methods=["POST"])
def select_routine(section_id, option_version):
    section = Section.query.get_or_404(section_id)
    routine = Routine.query.filter_by(section_id=section_id, version=option_version).first()

    if not routine:
        flash("⚠️ Routine option not found.", "danger")
        return redirect(request.referrer)

    # save selected option
    section.selected_routine = str(option_version)

    # mark only this one finalized
    Routine.query.filter_by(section_id=section_id).update({'finalized': False})
    routine.finalized = True

    db.session.commit()

    flash(f"✅ Routine Option {option_version} confirmed for {section.name}", "success")
    # Redirect safe fallback
    dean = Teacher.query.filter_by(is_dean=True).first()
    return redirect(url_for("select_section", dean_id=dean.id if dean else 1))


@app.route("/save_selected_routine/<int:section_id>", methods=["POST"])
def save_selected_routine(section_id):
    section = Section.query.get_or_404(section_id)
    selected_id = request.form.get("selected_routine")

    if not selected_id:
        flash("⚠️ Please select a routine first.", "warning")
        return redirect(request.referrer)

    routine = Routine.query.filter_by(id=int(selected_id), section_id=section_id).first()
    if not routine:
        flash("⚠️ Selected routine option not found.", "danger")
        return redirect(request.referrer)

    # Save selection
    section.selected_routine = str(routine.id)

    # mark only this routine finalized
    Routine.query.filter_by(section_id=section_id).update({'finalized': False})
    routine.finalized = True

    db.session.commit()

    dean = Teacher.query.filter_by(is_dean=True).first()
    if not dean:
        flash("⚠️ Dean not found for this department.", "danger")
        return redirect(url_for("select_section", dean_id=1))  # fallback

    flash("✅ Routine confirmed successfully!", "success")
    return redirect(url_for("select_section", dean_id=dean.id))

@app.route("/show_routine/<int:section_id>")
def show_routine(section_id):
    section = Section.query.get_or_404(section_id)

    routine = Routine.query.filter_by(section_id=section_id, finalized=True).first()

    dean = Teacher.query.filter_by(is_dean=True).first()

    if not routine:
        flash("⚠️ No confirmed routine found for this section.", "warning")
        return redirect(url_for("routine_management", dean_id=dean.id if dean else 1))

    return render_template("show_routine.html", section=section, routine=routine, dean=dean)


@app.route('/message/<int:dean_id>', methods=['GET', 'POST'])
def message(dean_id):
    dean = Teacher.query.filter_by(id=int(dean_id)).first()
    if not dean or not dean.is_dean:
        flash("❌ Dean not found or access denied.")
        return redirect('/')
    if request.method == 'GET':
        logs = SubstituteLog.query.order_by(SubstituteLog.timestamp.desc()).all()
        return render_template('message.html', dean=dean, logs=logs)

@app.route('/showfaculty/<int:dean_id>', methods=['GET', 'POST'])
def showfaculty(dean_id):
    dean = Teacher.query.filter_by(id=int(dean_id)).first()
    if not dean or not dean.is_dean:
        flash("❌ Dean not found or access denied.")
        return redirect('/')

    departments = Department.query.all()  # 🔹 send all departments

    if request.method == 'POST':
        dept_id = request.form.get("department_id")
        if dept_id:
            teachers = Teacher.query.filter_by(department_id=dept_id).all()
        else:
            teachers = []
    else:
        teachers = Teacher.query.all()

    return render_template(
        'showfaculty.html',
        dean=dean,
        teachers=teachers,
        departments=departments
    )

@app.route('/deansummary/<int:dean_id>', methods=['GET'])
def deansummary(dean_id):
    dean = Teacher.query.filter_by(id=dean_id, is_dean=True).first()
    if not dean:
        flash("⚠️ Access Denied: Only deans can access this page.")
        return redirect('/')

    # =========================
    # Chart 1: Faculty Load Distribution
    # =========================
    teachers = Teacher.query.all()
    faculty_names = [t.name for t in teachers]
    class_counts = [len(t.routine_slots) for t in teachers]  # using Teacher.routine_slots relationship

    fig1, ax1 = plt.subplots()
    ax1.bar(faculty_names, class_counts, color="skyblue", edgecolor="black")
    ax1.set_title("Faculty Load Distribution")
    ax1.set_xlabel("Faculty")
    ax1.set_ylabel("Number of Classes")
    plt.xticks(rotation=45, ha="right")

    plot_path_1 = "static/faculty_load.png"
    fig1.tight_layout()
    fig1.savefig(plot_path_1)
    plt.close(fig1)

    # =========================
    # Chart 2: Routine Utilization
    # =========================
    total_slots = RoutineSlot.query.count()
    filled_slots = RoutineSlot.query.filter(RoutineSlot.teacher_id.isnot(None)).count()
    free_slots = total_slots - filled_slots

    labels2 = ["Filled Slots", "Free Slots"]
    sizes2 = [filled_slots, free_slots]
    colors2 = ["lightcoral", "lightgreen"]

    fig2, ax2 = plt.subplots()
    ax2.pie(sizes2, labels=labels2, autopct='%1.1f%%', startangle=90, colors=colors2, shadow=True)
    ax2.set_title("Routine Utilization")

    plot_path_2 = "static/routine_utilization.png"
    fig2.savefig(plot_path_2)
    plt.close(fig2)

    # =========================
    # Chart 3: Course Allocation Summary
    # =========================
    courses = Subject.query.all()
    dept_course_count = {}
    for c in courses:
        dept_name = c.department.name if c.department else "Unknown"
        dept_course_count[dept_name] = dept_course_count.get(dept_name, 0) + 1

    fig3, ax3 = plt.subplots()
    ax3.bar(dept_course_count.keys(), dept_course_count.values(), color="orange", edgecolor="black")
    ax3.set_title("Course Allocation Summary")
    ax3.set_xlabel("Department")
    ax3.set_ylabel("Courses Count")
    plt.xticks(rotation=45, ha="right")

    plot_path_3 = "static/course_allocation.png"
    fig3.tight_layout()
    fig3.savefig(plot_path_3)
    plt.close(fig3)

    # =========================
    # Chart 4: Faculty by Department
    # =========================
    dept_faculty_count = {}
    for t in teachers:
        dept = t.department.name if t.department else "Unknown"
        dept_faculty_count[dept] = dept_faculty_count.get(dept, 0) + 1

    fig4, ax4 = plt.subplots()
    ax4.pie(dept_faculty_count.values(), labels=dept_faculty_count.keys(), autopct='%1.1f%%', startangle=90, shadow=True)
    ax4.set_title("Faculty by Department")

    plot_path_4 = "static/faculty_by_dept.png"
    fig4.savefig(plot_path_4)
    plt.close(fig4)

    # =========================
    # Render Template
    # =========================
    return render_template(
        "dean_summary.html",
        dean=dean,
        plot_path_1=plot_path_1,
        plot_path_2=plot_path_2,
        plot_path_3=plot_path_3,
        plot_path_4=plot_path_4
    )


#------------------- FUNCTIONS ------------------
def assign_teacher_balanced(section_id):
    """
    Return teacher_id of the least loaded teacher in the section's department.
    Load measured by number of RoutineSlot rows currently assigned to the teacher.
    """
    section = Section.query.get(section_id)
    if not section:
        return None

    teachers = Teacher.query.filter_by(department_id=section.department_id, is_dean=False).all()
    if not teachers:
        # fallback: assign dean
        dean = Teacher.query.filter_by(is_dean=True).first()
        return dean.id if dean else None

    # Build list of (teacher, load)
    teacher_loads = []
    for teacher in teachers:
        current_load = RoutineSlot.query.filter_by(teacher_id=teacher.id).count()
        teacher_loads.append((teacher, current_load))

    # sort by load then by id to be deterministic
    teacher_loads.sort(key=lambda x: (x[1], x[0].id))

    return teacher_loads[0][0].id

def get_or_create_special_subjects():
    """
    Ensure fallback 'General' department and the special subjects 'Lunch Break' and 'Games' exist.
    Returns (lunch_subject, games_subject).
    NOTE: We do NOT create a dummy teacher; RoutineSlot.teacher_id is nullable for fixed slots.
    """
    general_dep = Department.query.filter_by(name="General").first()
    if not general_dep:
        general_dep = Department(name="General")
        db.session.add(general_dep)
        db.session.commit()

    lunch_subject = Subject.query.filter_by(name="Lunch Break").first()
    if not lunch_subject:
        lunch_subject = Subject(
            name="Lunch Break",
            department_id=general_dep.id,
            teacher_id=None
        )
        db.session.add(lunch_subject)

    games_subject = Subject.query.filter_by(name="Games").first()
    if not games_subject:
        games_subject = Subject(
            name="Games",
            department_id=general_dep.id,
            teacher_id=None
        )
        db.session.add(games_subject)

    db.session.commit()
    return lunch_subject, games_subject


def generate_three_options(section_id, subject_ids, class_counts, periods_per_day=10, max_classes_per_batch=60):
    """
    Generate exactly 3 Routine rows (persisted) and associated RoutineSlot rows.

    Rules:
    - period 7 (13:00–14:00) → fixed "Lunch Break"
    - period 10 (18:00–19:00) → fixed "Games"
    - ensures Mon–Sat all periods are filled
    - max 2 consecutive classes of same subject
    - max 2 classes/day per subject
    - same teacher always teaches same subject for same section
    - deletes old non-finalized routines before generating
    """
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    all_options = []

    # 🔹 Step 1: Delete old non-finalized routines
    old_routines = Routine.query.filter_by(section_id=section_id, finalized=False).all()
    for r in old_routines:
        db.session.delete(r)
    db.session.commit()

    # 🔹 Step 2: Ensure special subjects exist
    lunch_subject, games_subject = get_or_create_special_subjects()

    # 🔹 Step 3: Filter out Lunch/Games from academic subjects
    valid_subjects = [
        s.id for s in Subject.query.filter(Subject.id.in_(subject_ids)).all()
        if s.name not in ("Lunch Break", "Games")
    ]

    # 🔹 Step 4: Generate exactly 3 routine versions
    for version in range(1, 4):
        routine = Routine(section_id=section_id, version=version, finalized=False)
        db.session.add(routine)
        db.session.flush()

        timetable = {day: [None] * periods_per_day for day in days}
        total_assigned = 0

        # Track per-day subject counts
        subject_day_counts = {day: {} for day in days}

        # Track teacher assignment consistency
        teacher_map = {}  # (section_id, subject_id) -> teacher_id

        # 🔹 Step 5: Add fixed Lunch + Games slots
        for day in days:
            # Period 7 → Lunch
            timetable[day][6] = (lunch_subject.id, None)
            db.session.add(RoutineSlot(
                routine_id=routine.id, day=day, period=7,
                subject_id=lunch_subject.id, teacher_id=None
            ))

            # Period 10 → Games
            timetable[day][9] = (games_subject.id, None)
            db.session.add(RoutineSlot(
                routine_id=routine.id, day=day, period=10,
                subject_id=games_subject.id, teacher_id=None
            ))

        # 🔀 Shuffle subjects to vary each version
        subjects_order = valid_subjects[:]
        random.shuffle(subjects_order)

        # 🔹 Step 6: Fill remaining slots
        for sid in subjects_order:
            required = int(class_counts.get(sid, 0))
            if required <= 0:
                continue

            assigned = 0
            day_order = days[version - 1:] + days[:version - 1]

            for day in day_order:
                period_indices = list(range(periods_per_day))
                random.shuffle(period_indices)

                for p in period_indices:
                    if (p + 1) in (7, 10):  # Skip fixed Lunch & Games
                        continue
                    if assigned >= required or total_assigned >= max_classes_per_batch:
                        break
                    if timetable[day][p] is not None:
                        continue

                    # ✅ Rule 1: Prevent >2 consecutive same subject
                    if p >= 2 and timetable[day][p-1] and timetable[day][p-2]:
                        if timetable[day][p-1][0] == sid and timetable[day][p-2][0] == sid:
                            continue
                    if p >= 1 and p < periods_per_day - 1:
                        if timetable[day][p-1] and timetable[day][p+1]:
                            if timetable[day][p-1][0] == sid and timetable[day][p+1][0] == sid:
                                continue

                    # ✅ Rule 2: Max 2/day for same subject
                    if subject_day_counts[day].get(sid, 0) >= 2:
                        continue

                    # ✅ Rule 3: Same teacher for same subject in section
                    if (section_id, sid) in teacher_map:
                        teacher_id = teacher_map[(section_id, sid)]
                    else:
                        teacher_id = assign_teacher_balanced(section_id)
                        teacher_map[(section_id, sid)] = teacher_id

                    # Assign slot
                    slot = RoutineSlot(
                        routine_id=routine.id, day=day, period=p + 1,
                        subject_id=int(sid), teacher_id=teacher_id
                    )
                    db.session.add(slot)
                    timetable[day][p] = (sid, teacher_id)

                    # Update trackers
                    assigned += 1
                    total_assigned += 1
                    subject_day_counts[day][sid] = subject_day_counts[day].get(sid, 0) + 1

                if assigned >= required or total_assigned >= max_classes_per_batch:
                    break

            if total_assigned >= max_classes_per_batch:
                break

        db.session.commit()
        all_options.append(Routine.query.get(routine.id))

    return all_options



# ------------------ DATABASE SEEDING ------------------
def create_dean():
    existing_dean = Teacher.query.filter_by(is_dean=True).first()
    if not existing_dean:
        dean = Teacher(
            email='dean@iterease.com',
            password='Dean@2025',
            name='Dean ITEREase',
            phone='9876543210',
            address='101 Admin Plaza, Bhubaneswar',
            department_id=None,
            is_dean=True
        )
        db.session.add(dean)
        db.session.commit()
        print("✅ Dean user created successfully.")
    else:
        print("ℹ️ Dean user already exists.")


def create_departments():
    departments = ['Literature', 'Maths', 'CSE', 'MSE', 'EEE', 'CE']
    for dep in departments:
        if not Department.query.filter_by(name=dep).first():
            db.session.add(Department(name=dep))
    db.session.commit()
    print("✅ Departments created successfully.")


def create_sections():
    dept = Department.query.all()
    dept_names = [d.name for d in dept]
    for dept_name in dept_names:
        dept = Department.query.filter_by(name=dept_name).first()
        for i in range(1, 4):  # 4 sections each
            if dept:
                sec_name = f"{dept_name}{i}"
                if not Section.query.filter_by(name=sec_name, department_id=dept.id).first():
                    section = Section(name=sec_name, department_id=dept.id)
                    db.session.add(section)
    db.session.commit()
    print("✅ Sections created successfully.")


def create_classrooms():
    # shuffle sections so batches get distributed
    sections = Section.query.all()
    random.shuffle(sections)

    for _ in range(15):  # create 8 classrooms
        classroom = ClassRoom(capacity=30, name="TEMP")
        db.session.add(classroom)
        db.session.commit()  # to get id

        classroom.name = f"CR{classroom.id}"
        db.session.commit()

        # Assign batches if sections available
        if len(sections) >= 1:
            morning_section = sections.pop()
            morning_batch = Batch(
                name="Morning",
                classroom_id=classroom.id,
                section_id=morning_section.id
            )
            db.session.add(morning_batch)

        if len(sections) >= 1:
            evening_section = sections.pop()
            evening_batch = Batch(
                name="Evening",
                classroom_id=classroom.id,
                section_id=evening_section.id
            )
            db.session.add(evening_batch)

        db.session.commit()

    print("✅ Classrooms with Morning/Evening batches created.")


def create_teachers():
    teacher_data = [
        # Literature
        ('Amit', 'amit@iterease.com', 'Teacher@2025', '9000000001', '1 Lit Lane, City', 'Literature'),
        ('Neha', 'neha@iterease.com', 'Teacher@2025', '9000000002', '2 Lit Lane, City', 'Literature'),
        ('Ravi', 'ravi@iterease.com', 'Teacher@2025', '9000000003', '3 Lit Lane, City', 'Literature'),
        ('Pooja', 'pooja@iterease.com', 'Teacher@2025', '9000000004', '4 Lit Lane, City', 'Literature'),
        ('Kiran', 'kiran@iterease.com', 'Teacher@2025', '9000000005', '5 Lit Lane, City', 'Literature'),

        # Maths
        ('Arun', 'arun@iterease.com', 'Teacher@2025', '9000000006', '6 Maths Lane, City', 'Maths'),
        ('Sunita', 'sunita@iterease.com', 'Teacher@2025', '9000000007', '7 Maths Lane, City', 'Maths'),
        ('Manoj', 'manoj@iterease.com', 'Teacher@2025', '9000000008', '8 Maths Lane, City', 'Maths'),
        ('Kavita', 'kavita@iterease.com', 'Teacher@2025', '9000000009', '9 Maths Lane, City', 'Maths'),
        ('Deepak', 'deepak@iterease.com', 'Teacher@2025', '9000000010', '10 Maths Lane, City', 'Maths'),

        # CSE
        ('Suresh', 'suresh@iterease.com', 'Teacher@2025', '9000000011', '11 CSE Lane, City', 'CSE'),
        ('Meena', 'meena@iterease.com', 'Teacher@2025', '9000000012', '12 CSE Lane, City', 'CSE'),
        ('Rajesh', 'rajesh@iterease.com', 'Teacher@2025', '9000000013', '13 CSE Lane, City', 'CSE'),
        ('Anita', 'anita@iterease.com', 'Teacher@2025', '9000000014', '14 CSE Lane, City', 'CSE'),
        ('Vikas', 'vikas@iterease.com', 'Teacher@2025', '9000000015', '15 CSE Lane, City', 'CSE'),

        # MSE
        ('Ajay', 'ajay@iterease.com', 'Teacher@2025', '9000000016', '16 MSE Lane, City', 'MSE'),
        ('Seema', 'seema@iterease.com', 'Teacher@2025', '9000000017', '17 MSE Lane, City', 'MSE'),
        ('Rahul', 'rahul@iterease.com', 'Teacher@2025', '9000000018', '18 MSE Lane, City', 'MSE'),
        ('Lata', 'lata@iterease.com', 'Teacher@2025', '9000000019', '19 MSE Lane, City', 'MSE'),
        ('Nitin', 'nitin@iterease.com', 'Teacher@2025', '9000000020', '20 MSE Lane, City', 'MSE'),

        # EEE
        ('Prakash', 'prakash@iterease.com', 'Teacher@2025', '9000000021', '21 EEE Lane, City', 'EEE'),
        ('Geeta', 'geeta@iterease.com', 'Teacher@2025', '9000000022', '22 EEE Lane, City', 'EEE'),
        ('Mukesh', 'mukesh@iterease.com', 'Teacher@2025', '9000000023', '23 EEE Lane, City', 'EEE'),
        ('Shweta', 'shweta@iterease.com', 'Teacher@2025', '9000000024', '24 EEE Lane, City', 'EEE'),
        ('Harish', 'harish@iterease.com', 'Teacher@2025', '9000000025', '25 EEE Lane, City', 'EEE'),

        # CE
        ('Anil', 'anil@iterease.com', 'Teacher@2025', '9000000026', '26 CE Lane, City', 'CE'),
        ('Rita', 'rita@iterease.com', 'Teacher@2025', '9000000027', '27 CE Lane, City', 'CE'),
        ('Santosh', 'santosh@iterease.com', 'Teacher@2025', '9000000028', '28 CE Lane, City', 'CE'),
        ('Jyoti', 'jyoti@iterease.com', 'Teacher@2025', '9000000029', '29 CE Lane, City', 'CE'),
        ('Mahesh', 'mahesh@iterease.com', 'Teacher@2025', '9000000030', '30 CE Lane, City', 'CE'),
    ]

    for name, email, pwd, phone, address, dep_name in teacher_data:
        if not Teacher.query.filter_by(email=email).first():
            dep = Department.query.filter_by(name=dep_name).first()
            if dep:
                t = Teacher(
                    name=name,
                    email=email,
                    password=pwd,
                    phone=phone,
                    address=address,
                    department_id=dep.id,
                    is_dean=False
                )
                db.session.add(t)

    db.session.commit()
    print("✅ 5 teachers created per department successfully.")


def create_students():
    sections = Section.query.all()
    for section in sections:
        # Get batches for this section
        batches = Batch.query.filter_by(section_id=section.id).all()
        if not batches:
            continue

        for i in range(1, 6):  # 5 students per section
            student_email = f"{section.name.lower()}student{i}@iterease.com"
            if not Student.query.filter_by(email=student_email).first():
                batch = random.choice(batches)  # assign batch
                student = Student(
                    name=f"Student {section.name}{i}",
                    email=student_email,
                    password="Student@2025",
                    phone=str(8000000000 + i + section.id * 10),
                    address=f"{i} Student Lane, {section.name} Block",
                    section_id=section.id,
                    department_id=section.department_id,
                    classroom_id=batch.classroom_id
                )
                db.session.add(student)
    db.session.commit()
    print("✅ Students created successfully.")


def create_subjects():
    subject_data = {
        "Literature": [
            "English Poetry", "Modern Drama", "Indian Literature", 
            "World Literature", "Literary Criticism"
        ],
        "Maths": [
            "Algebra", "Calculus", "Geometry", 
            "Probability", "Statistics"
        ],
        "CSE": [
            "Data Structures", "Algorithms", "Operating Systems", 
            "Computer Networks", "Database Systems", "Artificial Intelligence"
        ],
        "MSE": [
            "Material Science", "Thermodynamics", "Metallurgy", 
            "Nanomaterials", "Composite Materials"
        ],
        "EEE": [
            "Circuits", "Electromagnetics", "Power Systems", 
            "Control Systems", "Digital Electronics"
        ],
        "CE": [
            "Structural Analysis", "Hydraulics", "Transportation Engineering", 
            "Geotechnical Engineering", "Construction Management"
        ]
    }

    for dep_name, subjects in subject_data.items():
        department = Department.query.filter_by(name=dep_name).first()
        if not department:
            continue
        for sub_name in subjects:
            if not Subject.query.filter_by(name=sub_name, department_id=department.id).first():
                subject = Subject(name=sub_name, department_id=department.id)
                db.session.add(subject)

    db.session.commit()
    print("✅ Subjects created successfully (5+ per department).")


def create_fixed_subjects():
    classrooms = ClassRoom.query.all()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    
    # Define the fixed subject you want
    fixed_subject_name = "Games"
    last_period_time = "6:00-7:00"   # evening batch, last slot

    for classroom in classrooms:
        for day in days:
            # Check if already exists for this classroom + day
            existing = FixedSubject.query.filter_by(
                name=fixed_subject_name,
                classroom_id=classroom.id,
                day=day,
                time_slot=last_period_time
            ).first()

            if not existing:
                fixed_sub = FixedSubject(
                    name=fixed_subject_name,
                    classroom_id=classroom.id,
                    day=day,
                    time_slot=last_period_time
                )
                db.session.add(fixed_sub)

    db.session.commit()
    print("✅ Fixed subject 'Games' added for all classrooms (last period each day).")



def create_extra_subjects():
    extra_subject_data = {
        "Literature": ["Creative Writing", "Comparative Literature", "Linguistics"],
        "Maths": ["Number Theory", "Discrete Mathematics", "Mathematical Modelling"],
        "CSE": ["AI Lab", "Robotics", "Cloud Computing"],
        "MSE": ["Nano Tech", "Advanced Materials", "Corrosion Engineering"],
        "EEE": ["Power Lab", "Control Systems", "Renewable Energy"],
        "CE": ["Surveying", "Environmental Studies", "Urban Planning"]
    }

    for dep_name, extras in extra_subject_data.items():
        department = Department.query.filter_by(name=dep_name).first()
        if not department:
            continue
        for extra_name in extras:
            if not ExtraSubject.query.filter_by(name=extra_name, department_id=department.id).first():
                extra_sub = ExtraSubject(name=extra_name, department_id=department.id)
                db.session.add(extra_sub)

    db.session.commit()
    print("✅ 3 extra subjects created per department successfully.")



if __name__ == '__main__':
    create_dean()
    create_departments()
    create_sections()
    create_teachers()
    create_classrooms()
    create_students()
    create_subjects()
    create_fixed_subjects()
    create_extra_subjects()
    print("🎉 Database seeding completed!")

    # ✅ Initialize workload for all teachers if missing
    with app.app_context():
        for t in Teacher.query.all():
            if t.workload is None:
                t.workload = 0
        db.session.commit()

    app.run(debug=True)
