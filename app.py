import math
from itertools import cycle
from collections import defaultdict
import random
import uuid
import os

from application.database import db
from application.models import *
from sqlalchemy.orm import joinedload

from flask import Flask, render_template, request, redirect, flash, url_for
from sqlalchemy import func, CheckConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_migrate import Migrate
import matplotlib.pyplot as plt

plt.switch_backend('Agg')  # Use a non-interactive backend for matplotlib

app = Flask(__name__)

# Set the secret key for flash messages
app.config['SECRET_KEY'] = 'sweet_and_sour'

# Configure the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ITERease.db'
db.init_app(app)

migrate = Migrate(app, db)

app.app_context().push()
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
        return render_template('tlogin.html', teacher=None)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Email does not exist. Please try again.')
            return redirect('/tlogin')

        if not check_password_hash(user.password, password):
            flash('Incorrect password. Please try again.')
            return redirect('/tlogin')

        teacher = Teacher.query.filter_by(uid=user.id).first()
        if not teacher:
            flash('You are not registered as a teacher.')
            return redirect('/')

        # Check teacher’s role via UserRole
        role_names = [ur.role.name for ur in user.roles]

        if "Dean" in role_names:
            return redirect(f'/deandashboard/{teacher.id}')
        else:
            return redirect(f'/teacherdashboard/{teacher.id}')

@app.route('/tforgotpassword', methods=['GET', 'POST'])
def tforgotpassword():
    if request.method == 'GET':
        return render_template('tforgotpassword.html')

    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        new_password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("User not found.")
            return redirect('/tforgotpassword')

        teacher = Teacher.query.filter_by(uid=user.id).first()
        if not teacher:
            flash("This user is not registered as a teacher.")
            return redirect('/')

        if user.phone != phone:
            flash("Phone number doesn't match our records.")
            return redirect('/tforgotpassword')

        # Update the password securely
        user.password = generate_password_hash(new_password)
        db.session.commit()

        flash("Password reset successful. Please log in.")
        return redirect('/tlogin')


@app.route("/teacherdashboard/<int:teacher_id>")
def teacherdashboard(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)

    # Slots that are currently assigned to this teacher (either originally or as a substitute)
    current_slots = (
        RoutineSlot.query
        .join(Routine, RoutineSlot.routine_id == Routine.id)
        .filter(RoutineSlot.teacher_id == teacher_id, Routine.finalized == True)
        .all()
    )

    # Slots that were originally this teacher's, but are now reassigned
    # We find these by looking at the latest SubstituteLog for each slot
    original_slots = (
        RoutineSlot.query
        .join(SubstituteLog, RoutineSlot.id == SubstituteLog.slot_id)
        .filter(SubstituteLog.from_teacher_id == teacher_id)
        .all()
    )

    # Combine both lists and use a set to get unique slots by ID
    all_slots = list(set(current_slots + original_slots))

    # Days of week
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    routine_by_batch = {}

    for slot in all_slots:
        # Determine if this slot is a reassignment FROM or TO the current teacher
        is_reassigned_from_me = any(log.from_teacher_id == teacher_id for log in slot.substitute_logs)
        is_reassigned_to_me = any(log.to_teacher_id == teacher_id for log in slot.substitute_logs)
        
        # Determine if this is a slot that the teacher is not currently assigned to
        is_not_my_current_slot = slot.teacher_id != teacher_id

        # Skip slots that are neither currently theirs nor originally theirs
        if not is_reassigned_from_me and is_not_my_current_slot and not is_reassigned_to_me:
             continue
        
        batch = slot.routine.section.batch if slot.routine and slot.routine.section else None
        batch_name = batch.name if batch else "Unassigned Batch"

        if batch_name not in routine_by_batch:
            routine_by_batch[batch_name] = {day: {} for day in days}

        subject_name = slot.subject.name if slot.subject else (slot.extra_subject.name if slot.extra_subject else "N/A")
        section_name = slot.routine.section.name if slot.routine and slot.routine.section else "N/A"
        classroom_name = slot.classroom.name if slot.classroom else "N/A"

        routine_by_batch[batch_name][slot.day].setdefault(slot.period, []).append({
            "id": slot.id,
            "subject": subject_name,
            "section": section_name,
            "classroom": classroom_name,
            "time_range": slot.time_range,
            "is_reassigned_from_me": is_reassigned_from_me,
            "is_reassigned_to_me": is_reassigned_to_me,
        })
    
    reassignments = (
        SubstituteLog.query
        .join(RoutineSlot, RoutineSlot.id == SubstituteLog.slot_id)
        .filter(
            (SubstituteLog.from_teacher_id == teacher_id) |
            (SubstituteLog.to_teacher_id == teacher_id)
        )
        .all()
    )

    return render_template(
        "teacherdashboard.html",
        teacher=teacher,
        routine_by_batch=routine_by_batch,
        reassignments=reassignments,
        days=days
    )

@app.route('/mark_absent', methods=['POST'])
def mark_absent():
    slot_id = request.form.get('slot_id', type=int)
    teacher_id = request.form.get('teacher_id', type=int)

    slot = RoutineSlot.query.get(slot_id)
    teacher = Teacher.query.get(teacher_id)

    if not slot or not teacher:
        flash("❌ Invalid slot or teacher.", "danger")
        return redirect(f'/teacherdashboard/{teacher_id or 0}')

    # Collect IDs of all teachers already involved in this slot's substitution chain
    tried_ids = {log.from_teacher_id for log in slot.substitute_logs}
    tried_ids.add(slot.teacher_id)

    # Find replacement within same department and workload limits
    next_teacher = Teacher.query.filter(
        Teacher.department_id == teacher.department_id,
        Teacher.workload < Teacher.max_workload,
        ~Teacher.id.in_(tried_ids)
    ).order_by(Teacher.workload).first()

    if next_teacher:
        old_teacher_id = slot.teacher_id
        slot.teacher_id = next_teacher.id
        next_teacher.workload += 1

        db.session.add_all([slot, next_teacher])
        db.session.commit()

        log = SubstituteLog(
            slot_id=slot.id,
            from_teacher_id=old_teacher_id,
            to_teacher_id=next_teacher.id
        )
        db.session.add(log)
        db.session.commit()

        flash(f"⚠️ Slot reassigned to {next_teacher.user.name}")
    else:
        # Fallback: find the teacher with the lowest workload regardless of workload limit
        fallback_teacher = Teacher.query.filter(
            Teacher.department_id == teacher.department_id,
            ~Teacher.id.in_(tried_ids)
        ).order_by(Teacher.workload).first()

        if fallback_teacher:
            old_teacher_id = slot.teacher_id
            slot.teacher_id = fallback_teacher.id
            db.session.add(slot)
            db.session.commit()

            log = SubstituteLog(
                slot_id=slot.id,
                from_teacher_id=old_teacher_id,
                to_teacher_id=fallback_teacher.id
            )
            db.session.add(log)
            db.session.commit()

            flash(f"⚠️ Slot reassigned (overload) to {fallback_teacher.user.name}")
        else:
            flash("❌ No available teacher to reassign.", "danger")

    return redirect(f'/teacherdashboard/{teacher_id}')

@app.route('/reassign_to_original', methods=['POST'])
def reassign_to_original():
    slot_id = request.form.get('slot_id', type=int)
    current_teacher_id = request.form.get('teacher_id', type=int)

    slot = RoutineSlot.query.get(slot_id)
    if not slot:
        flash("❌ Invalid slot.", "danger")
        return redirect(f'/teacherdashboard/{current_teacher_id}')

    # Find the original teacher for this slot from the oldest log
    first_log = SubstituteLog.query.filter_by(slot_id=slot.id).order_by(SubstituteLog.timestamp).first()

    if first_log and first_log.from_teacher_id == current_teacher_id:
        original_teacher = Teacher.query.get(first_log.from_teacher_id)
        substitute_teacher = Teacher.query.get(slot.teacher_id)

        if original_teacher and substitute_teacher:
            # Reassign the slot back to the original teacher
            slot.teacher_id = original_teacher.id
            substitute_teacher.workload = max(0, substitute_teacher.workload - 1)
            
            # Delete all substitution logs for this slot to reset the chain
            SubstituteLog.query.filter_by(slot_id=slot.id).delete()
            db.session.commit()
            
            flash(f"✅ Slot reassigned back to {original_teacher.user.name}.")
        else:
            flash("❌ Original teacher or current substitute not found.", "danger")
    else:
        flash("❌ No valid reassignment found for this slot.", "danger")

    return redirect(f'/teacherdashboard/{current_teacher_id}')


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

        if new_phone and new_phone != teacher.user.phone:
            if Teacher.user.query.filter_by(phone=new_phone).first():
                flash("⚠️ Phone number already in use.")
                return redirect(f'/teditprofile/{id}')

        teacher.user.phone = new_phone
        teacher.user.address = new_address

        teacher.user.name = new_name
        if new_password:
            teacher.user.password = generate_password_hash(new_password)

        db.session.commit()
        flash("✅ Profile updated successfully.")

        # Redirect based on role
        dean_role = Role.query.filter_by(name="Dean").first()
        if dean_role and any(ur.rid == dean_role.id for ur in teacher.user.roles):
            return redirect(f'/deandashboard/{teacher.id}')
        else:
            return redirect(f'/teacherdashboard/{teacher.id}')


# ------------------ STUDENT ROUTES ------------------

@app.route('/slogin', methods=['GET', 'POST'])
def slogin():
    if request.method == 'GET':
        return render_template('slogin.html', student=None)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        student = Student.query.filter_by(uid=user.id).first() if user else None

        if not student:
            flash('❌ Email does not exist. Please try again.')
            return redirect('/slogin')

        if check_password_hash(user.password, password):
            return redirect(f'/studentdashboard/{student.id}')
        else:
            flash('❌ Incorrect password. Please try again.')
            return redirect('/slogin')


@app.route('/sforgotpassword', methods=['GET', 'POST'])
def sforgotpassword():
    if request.method == 'GET':
        return render_template('sforgotpassword.html')

    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        new_password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        student = Student.query.filter_by(uid=user.id).first() if user else None

        if not student:
            flash("❌ Student not found.")
            return redirect('/sforgotpassword')

        if student.user.phone != phone:
            flash("⚠️ Phone number doesn't match our records.")
            return redirect('/sforgotpassword')

        # ✅ Update password securely
        user.password = generate_password_hash(new_password)
        db.session.commit()

        flash("✅ Password reset successful. Please log in.")
        return redirect('/slogin')

@app.route('/studentdashboard/<int:id>', methods=['GET', 'POST'])
def studentdashboard(id):
    student = Student.query.get_or_404(id)

    # --- Handle POST for extra subjects ---
    if request.method == 'POST':
        extra_subject_id = request.form.get('extra_subject_id')
        preferred_time = request.form.get('preferred_time')
        
        if extra_subject_id and preferred_time:
            day, period_str = preferred_time.split('|')
            period = int(period_str)
            extra_subject = ExtraSubject.query.get(int(extra_subject_id))

            if extra_subject:
                # Check if already selected by this student
                existing_student_choice = StudentExtraSubject.query.filter_by(
                    student_id=student.id,
                    extra_subject_id=extra_subject.id
                ).first()
                if existing_student_choice:
                    flash(f"❌ You've already chosen '{extra_subject.name}'.")
                    return redirect(f'/studentdashboard/{student.id}')

                # Find an available teacher
                qualified_teachers = [link.teacher for link in extra_subject.teacher_links]
                available_teacher = None

                for teacher in qualified_teachers:
                    # Check if teacher is busy at the chosen slot (for ANY subject)
                    existing_slot = RoutineSlot.query.filter(
                        RoutineSlot.teacher_id == teacher.id,
                        RoutineSlot.day == day,
                        RoutineSlot.period == period
                    ).first()

                    # Check workload capacity
                    if not existing_slot and teacher.workload < teacher.max_workload:
                        available_teacher = teacher
                        break
                
                # If a teacher is found, proceed with assignment
                if available_teacher:
                    # Get the latest routine to link the new slot
                    latest_routine = Routine.query.filter_by(
                        section_id=student.section.id,
                        finalized=True
                    ).order_by(Routine.version.desc()).first()

                    if latest_routine:
                        # Check if the slot is free for the student's section
                        is_section_slot_free = RoutineSlot.query.filter(
                            RoutineSlot.routine_id == latest_routine.id,
                            RoutineSlot.day == day,
                            RoutineSlot.period == period
                        ).first() is None

                        if is_section_slot_free:
                            # Create a new RoutineSlot entry for the extra subject
                            new_slot = RoutineSlot(
                                routine_id=latest_routine.id,
                                day=day,
                                period=period,
                                extra_subject_id=extra_subject.id,
                                teacher_id=available_teacher.id,
                                classroom_id=student.classroom_id,
                                subject_id=None,
                                time_range="N/A"
                            )
                            db.session.add(new_slot)
                            
                            # Create the student-extra_subject association
                            new_choice = StudentExtraSubject(
                                student_id=student.id,
                                extra_subject_id=extra_subject.id,
                                preferred_day=day,
                                preferred_period=period
                            )
                            db.session.add(new_choice)
                            
                            # Update teacher's workload
                            available_teacher.workload += 1

                            db.session.commit()
                            flash(f"✅ Added {extra_subject.name} with {available_teacher.user.name} on {day} Period {period}")
                        else:
                             flash("❌ This time slot is not free in your section's routine.")
                    else:
                        flash("❌ No finalized routine exists to add the extra subject to.")
                else:
                    flash(f"❌ No teacher is available for {extra_subject.name} at the selected time. Please try another slot.")

        return redirect(f'/studentdashboard/{student.id}')

    # --- Section routine ---
    section = student.section
    routines = Routine.query.filter_by(section_id=section.id, finalized=True).order_by(Routine.version).all()
    latest_routine = routines[-1] if routines else None
    
    # Get all slots for the latest routine, including extra subjects
    slots = latest_routine.slots if latest_routine else []

    # --- Build days and max_period safely ---
    days_list = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    if slots:
        max_period = max(slot.period for slot in slots)
        days_in_routine = sorted({slot.day for slot in slots}, key=lambda d: days_list.index(d))
    else:
        max_period = 10
        days_in_routine = days_list

    # --- Build personalized_slots for student ---
    periods = max_period
    personalized_slots = {day: [None]*periods for day in days_in_routine}

    # Fill personalized routine with ALL slots from the section's latest routine
    for slot in slots:
        # Check if the slot is an extra subject or a regular one
        if slot.extra_subject_id:
            subject_name = slot.extra_subject.name if slot.extra_subject else 'Extra Subject'
            is_extra = True
        else:
            subject_name = slot.subject.name if slot.subject else 'Regular Subject'
            is_extra = False
            
        personalized_slots[slot.day][slot.period-1] = {
            'subject_name': subject_name,
            'teacher_name': slot.teacher.user.name if slot.teacher else None,
            'slot_id': slot.id,
            'is_extra': is_extra
        }

    # --- Overlay extra subjects into preferred slots, with teacher name ---
    chosen_extra_subjects_assoc = student.extra_subjects_assoc
    free_slots = {day: [] for day in days_in_routine}

    # Mark free slots and then place extra subjects
    for day in days_in_routine:
        for p in range(1, periods + 1):
            if personalized_slots[day][p - 1] is None:
                free_slots[day].append(p)
                
    # The personalized slots are already built from the routine, including extra subjects.
    # The previous logic for overlaying is now redundant.

    # --- All extra subjects for selection dropdown ---
    all_extra_subjects = ExtraSubject.query.all()
    chosen_extra_subjects = [assoc.extra_subject for assoc in chosen_extra_subjects_assoc]
    
    return render_template(
        'studentdashboard.html',
        student=student,
        routine=latest_routine,
        slots=slots,
        days=days_in_routine,
        max_period=max_period,
        personalized_slots=personalized_slots,
        chosen_extra_subjects=chosen_extra_subjects,
        free_slots=free_slots,
        all_extra_subjects=all_extra_subjects
    )

@app.route('/choose_subjects/<int:student_id>', methods=['POST'])
def choose_subjects(student_id):
    selected_subjects = request.form.getlist('subject_ids')
    section_id = request.form.get('section_id')

    for sid in selected_subjects:
        choice = StudentSubjectChoice(
            student_id=student_id,
            subject_id=sid,
            section_id=section_id
        )
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
        if new_phone and new_phone != student.user.phone:
            if Student.user.query.filter_by(phone=new_phone).first():
                flash("⚠️ Phone number already in use.")
                return redirect(f'/seditprofile/{id}')

        # Update Student fields
        student.user.phone = new_phone
        student.user.address = new_address

        # Update User fields
        student.user.name = new_name
        if new_password:
            student.user.password = generate_password_hash(new_password)

        db.session.commit()
        flash("✅ Profile updated successfully.")
        return redirect(f'/studentdashboard/{student.id}')

# ------------------ PRINCIPAL(ADMIN) ROUTES ------------------
@app.route('/deandashboard/<int:id>', methods=['GET', 'POST'])
def deandashboard(id):
    if request.method == 'GET':
        dean = Teacher.query.filter_by(id=int(id)).first()
        if not dean:
            flash("❌ Dean not found.")
            return redirect('/')

        # ✅ Check Dean role
        dean_role = Role.query.filter_by(name="Dean").first()
        if not dean_role or not any(ur.rid == dean_role.id for ur in dean.user.roles):
            flash("⚠️ Access Denied")
            return redirect("/")

        classrooms = ClassRoom.query.filter_by(is_lab=False).all()
        labs = ClassRoom.query.filter_by(is_lab=True).all()

        batches = Batch.query.all()
        sections = Section.query.all()
        departments = Department.query.all()

        # ✅ Count allocated sections
        allocated_sections = Section.query.filter(Section.batch_id.isnot(None)).count()
        total_sections = len(sections)

        return render_template(
            'deandashboard.html',
            dean=dean,
            classrooms=classrooms,
            labs=labs,
            batches=batches,
            sections=sections,
            departments=departments,
            allocated_sections=allocated_sections,
            total_sections=total_sections
        )


@app.route('/departmentdetails/<int:id>', methods=['GET', 'POST'])
def departmentdetails(id):
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    if not dean:
        flash("❌ Dean not found.")
        return redirect('/')

    # ✅ Check Dean role
    if not dean_role or not any(ur.rid == dean_role.id for ur in dean.user.roles):
        flash("⚠️ Access Denied")
        return redirect('/')

    sections = Section.query.filter_by(department_id=dean.department_id).all()
    departments = Department.query.all()
    classrooms = ClassRoom.query.filter_by(department_id=dean.department_id).all()
    batches = (
        Batch.query.join(ClassRoom)
        .filter(ClassRoom.department_id == dean.department_id)
        .all()
    )

    return render_template(
        "departmentdetails.html",
        dean=dean,
        departments=departments,
        sections=sections,
        classrooms=classrooms,
        batches=batches
    )


@app.route('/adddepartment', methods=['GET', 'POST'])
def adddepartment():
    # ✅ Get the first Teacher who has Dean role
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    if request.method == 'GET':
        return render_template('adddepartment.html', dean=dean)

    if request.method == 'POST':
        dep_name = request.form.get('dep_name')
        student_count = int(request.form.get('student_count'))
        capacity = int(request.form.get('capacity'))

        dept, _ = create_department_structure(dep_name, student_count, capacity, assign_roles=True)
        if not dept:
            flash("❌ Department already exists.")
            return redirect('/adddepartment')

        flash("✅ Department created successfully.")
        return redirect(f'/departmentdetails/{dean.id}')


@app.route('/deletedepartment/<int:dept_id>', methods=['POST'])
def delete_department(dept_id):
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )
    department = Department.query.get(dept_id)
    if not department:
        flash("❌ Department not found.", "error")
        return redirect('/')

    try:
        db.session.delete(department)
        db.session.commit()
        flash(f"✅ Department '{department.name}' and all related data deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error deleting department: {str(e)}", "error")

    return redirect(f'/departmentdetails/{dean.id}')

@app.route('/addsubject/<int:dept_id>', methods=['POST'])
def addsubject(dept_id):
    department = Department.query.get_or_404(dept_id)

    # ✅ Get Dean
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    subject_name = request.form.get('subject_name', "").strip()
    credits = int(request.form.get('credits', 0))
    distribution_type = request.form.get('distribution_type')

    if not subject_name:
        flash("❌ Subject name cannot be empty.")
        return redirect(f'/departmentdetails/{dean.id}')

    created_extras = []

    # --- Theory Subject ---
    if distribution_type == "theory":
        new_extra = Subject(
            name=subject_name,
            department_id=department.id,
            credits=credits,
            distribution_type="theory"
        )
        new_extra.calculate_hours()
        db.session.add(new_extra)
        created_extras.append(new_extra)

    # --- Lab Subject ---
    elif distribution_type == "lab":
        new_extra = Subject(
            name=f"{subject_name} (Lab)",
            department_id=department.id,
            credits=credits,
            distribution_type="lab"
        )
        new_extra.calculate_hours()
        db.session.add(new_extra)
        created_extras.append(new_extra)

    # --- Mixed Subject (theory + lab parts) ---
    elif distribution_type == "mixed":
        # Theory part
        theory_extra = Subject(
            name=f"{subject_name} (Theory)",
            department_id=department.id,
            credits=credits,
            distribution_type="theory"
        )
        theory_extra.calculate_hours()
        db.session.add(theory_extra)
        created_extras.append(theory_extra)

        # Lab part
        lab_extra = Subject(
            name=f"{subject_name} (Lab)",
            department_id=department.id,
            credits=credits,
            distribution_type="lab"
        )
        lab_extra.calculate_hours()
        db.session.add(lab_extra)
        created_extras.append(lab_extra)

    db.session.flush()  # ✅ ensure IDs are available

    # --- Assign valid teachers automatically ---
    for extra in created_extras:
        teachers = (
            db.session.query(Teacher)
            .join(User, Teacher.uid == User.id)
            .join(UserRole, UserRole.uid == User.id)
            .filter(Teacher.department_id == department.id)
            .all()
        )

        for teacher in teachers:
            role = (
                db.session.query(Role)
                .join(UserRole, UserRole.rid == Role.id)
                .filter(UserRole.uid == teacher.uid)
                .first()
            )
            if not role:
                continue

            assign = False
            if role.name == "Lab Assistant" and extra.distribution_type == "lab":
                assign = True
            elif role.name == "Professor" and extra.distribution_type in ["theory", "mixed"]:
                assign = True
            elif role.name == "Assistant Professor" and extra.distribution_type in ["theory", "mixed"]:
                assign = True

            if assign:
                db.session.add(TeacherSubject(
                    teacher_id=teacher.id,
                    subject_id=extra.id
                ))

    db.session.commit()

    flash(f"✅ Subject(s) added successfully: {', '.join([s.name for s in created_extras])}")
    return redirect(f'/departmentdetails/{dean.id}')


@app.route('/addextrasubject/<int:dept_id>', methods=['POST'])
def add_extra_subject(dept_id):
    department = Department.query.get_or_404(dept_id)

    # ✅ Get Dean
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    extra_subject_name = request.form.get('extra_subject_name', "").strip()
    credits = int(request.form.get('credits', 0))
    distribution_type = request.form.get('distribution_type')

    if not extra_subject_name:
        flash("❌ Extra Subject name cannot be empty.")
        return redirect(f'/departmentdetails/{dean.id}')

    created_extras = []

    # --- Theory ExtraSubject ---
    if distribution_type == "theory":
        new_extra = ExtraSubject(
            name=extra_subject_name,
            department_id=department.id,
            credits=credits,
            distribution_type="theory"
        )
        new_extra.calculate_hours()
        db.session.add(new_extra)
        created_extras.append(new_extra)

    # --- Lab ExtraSubject ---
    elif distribution_type == "lab":
        new_extra = ExtraSubject(
            name=f"{extra_subject_name} (Lab)",
            department_id=department.id,
            credits=credits,
            distribution_type="lab"
        )
        new_extra.calculate_hours()
        db.session.add(new_extra)
        created_extras.append(new_extra)

    # --- Mixed ExtraSubject (theory + lab parts) ---
    elif distribution_type == "mixed":
        # Theory part
        theory_extra = ExtraSubject(
            name=f"{extra_subject_name} (Theory)",
            department_id=department.id,
            credits=credits,
            distribution_type="theory"
        )
        theory_extra.calculate_hours()
        db.session.add(theory_extra)
        created_extras.append(theory_extra)

        # Lab part
        lab_extra = ExtraSubject(
            name=f"{extra_subject_name} (Lab)",
            department_id=department.id,
            credits=credits,
            distribution_type="lab"
        )
        lab_extra.calculate_hours()
        db.session.add(lab_extra)
        created_extras.append(lab_extra)

    db.session.flush()  # ✅ ensure IDs are available

    # --- Assign valid teachers automatically ---
    for extra in created_extras:
        teachers = (
            db.session.query(Teacher)
            .join(User, Teacher.uid == User.id)
            .join(UserRole, UserRole.uid == User.id)
            .filter(Teacher.department_id == department.id)
            .all()
        )

        for teacher in teachers:
            role = (
                db.session.query(Role)
                .join(UserRole, UserRole.rid == Role.id)
                .filter(UserRole.uid == teacher.uid)
                .first()
            )
            if not role:
                continue

            assign = False
            if role.name == "Lab Assistant" and extra.distribution_type == "lab":
                assign = True
            elif role.name == "Professor" and extra.distribution_type in ["theory", "mixed"]:
                assign = True
            elif role.name == "Assistant Professor" and extra.distribution_type in ["theory", "mixed"]:
                assign = True

            if assign:
                db.session.add(TeacherExtraSubject(
                    teacher_id=teacher.id,
                    extra_subject_id=extra.id
                ))

    db.session.commit()

    flash(f"✅ Extra Subject(s) added successfully: {', '.join([s.name for s in created_extras])}")
    return redirect(f'/departmentdetails/{dean.id}')

@app.route('/routine/<int:dean_id>', methods=['GET', 'POST'])
def select_section(dean_id):
    dean = Teacher.query.get_or_404(dean_id)

    # ✅ Ensure dean role
    dean_role = Role.query.filter_by(name="Dean").first()
    has_role = (
        UserRole.query.filter_by(uid=dean.uid, rid=dean_role.id).first()
        if dean_role else None
    )
    if not has_role:
        flash("⚠️ Access Denied: Not a Dean")
        return redirect('/')

    # Only sections without a finalized routine
    pending_sections = [
        sec for sec in Section.query.all()
        if not any(r.finalized for r in sec.routines)
    ]

    return render_template('routine.html', dean=dean, sections=pending_sections)

@app.route("/generate_routine/<int:section_id>", methods=['GET', 'POST'])
def generate_routine(section_id):
    section = Section.query.get_or_404(section_id)

    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    if request.method == "GET":
        # fetch subjects only from this department
        subjects = Subject.query.all()
        for s in subjects:
            s.calculate_hours()
        return render_template(
            "generate_routine.html",
            dean=dean,
            section=section,
            subjects=subjects
        )

    # ----------------- POST -----------------
    selected_subject_ids = request.form.getlist('subject_ids')
    if not selected_subject_ids:
        flash("⚠️ Please select at least one subject.")
        return redirect(f'/generate_routine/{section_id}')

    class_counts = {}
    selected_int_ids = []

    for sid_str in selected_subject_ids:
        try:
            sid = int(sid_str)
        except ValueError:
            continue

        subject = Subject.query.get(sid)
        if subject:
            subject.calculate_hours()
            class_counts[sid] = subject.weekly_classes or 3
            selected_int_ids.append(sid)

    # optional fixed-subject
    fixed_subject_id = request.form.get("fixed_subject")
    fixed_period = request.form.get("fixed_period")
    fixed_subject_id = int(fixed_subject_id) if fixed_subject_id else None
    fixed_period = int(fixed_period) if fixed_period else None

    if fixed_subject_id and fixed_subject_id not in selected_int_ids:
        subject = Subject.query.get(fixed_subject_id)
        if subject:
            subject.calculate_hours()
            class_counts[fixed_subject_id] = subject.weekly_classes or 3
            selected_int_ids.append(fixed_subject_id)

    if not selected_int_ids:
        flash("⚠️ No valid subjects available to generate routine.")
        return redirect(f'/generate_routine/{section_id}')

    teacher_loads = {}

    # generate 3 routine options in memory
    options = generate_three_options(
        section_id,
        subject_ids=selected_int_ids,
        class_counts=class_counts,
        fixed_subject_id=fixed_subject_id,
        fixed_period=fixed_period,
        teacher_loads=teacher_loads
    )

    flash("✅ 3 routine options generated successfully! Please finalize one.")
    return render_template("show_routine_options.html", section=section, options=options, dean=dean)

@app.route("/routine/select/<int:section_id>/<int:option_version>", methods=["POST"])
def select_routine(section_id, option_version):
    section = Section.query.get_or_404(section_id)
    routine = Routine.query.filter_by(section_id=section_id, version=option_version).first()

    if not routine:
        flash("⚠️ Routine option not found.")
        return redirect(f'/routine/{section_id}')

    # save selected option
    section.selected_routine = str(option_version)

    Routine.query.filter_by(section_id=section_id).update({'finalized': False})
    routine.finalized = True

    db.session.commit()

    flash(f"✅ Routine Option {option_version} confirmed for {section.name}")

    # redirect dean back to pending sections
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )
    return redirect(f'/routine/{dean.id if dean else 1}')


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

    # ✅ fetch Dean via role
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    if not dean:
        flash("⚠️ Dean not found.", "danger")
        return redirect(f"/routine/1")  # safe fallback

    flash("✅ Routine confirmed successfully!", "success")
    return redirect(f"/routine/{dean.id}")


@app.route("/edit_routine_slot/<int:slot_id>", methods=["GET", "POST"])
def edit_routine_slot(slot_id):
    slot = RoutineSlot.query.get_or_404(slot_id)
    section = slot.routine.section

    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    subjects = Subject.query.all()
    extra_subjects=ExtraSubject.query.all()

    if request.method == "GET":
        return render_template(
            "edit_routine_slot.html",
            dean=dean,
            section=section,
            slot=slot,
            subjects=subjects,
            extra_subjects=extra_subjects
        )

    if request.method == "POST":
        new_subject_id = int(request.form.get("subject_id"))
        slot.subject_id = new_subject_id

        # Simple reassignment: pick first teacher in dept (could improve)
        subj = Subject.query.get(new_subject_id)
        new_teacher = Teacher.query.filter_by(department_id=subj.department_id).first()
        slot.teacher_id = new_teacher.id if new_teacher else slot.teacher_id

        db.session.commit()
        flash("✅ Routine slot updated successfully!", "success")
        return redirect(f"/show_routine/{section.id}/{section.batch_id}")
    
@app.route("/show_routine/<int:section_id>/<int:batch_id>")
def show_routine(section_id, batch_id):
    section = Section.query.get_or_404(section_id)

    # Fetch finalized routine for this section
    routine = Routine.query.filter_by(section_id=section.id, finalized=True).first()

    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )

    # ✅ Get only students in this section AND batch
    students = Student.query.filter_by(section_id=section.id, batch_id=batch_id).all()

    if not routine:
        flash("⚠️ No confirmed routine found for this section.", "warning")
        return render_template(
            "show_routine.html",
            section=section,
            routine=None,
            dean=dean,
            students=students
        )

    return render_template(
        "show_routine.html",
        section=section,
        routine=routine,
        dean=dean,
        students=students
    )

@app.route('/message/<int:dean_id>', methods=['GET', 'POST'])
def message(dean_id):
    # ✅ fetch dean via role check
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id, Teacher.id == dean_id)
        .first()
    )

    if not dean:
        flash("❌ Dean not found or access denied.")
        return redirect('/')

    if request.method == 'GET':
        logs = SubstituteLog.query.order_by(SubstituteLog.timestamp.desc()).all()
        return render_template('message.html', dean=dean, logs=logs)


@app.route('/showfaculty/<int:dean_id>', methods=['GET', 'POST'])
def showfaculty(dean_id):
    # ✅ fetch dean via role check
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id, Teacher.id == dean_id)
        .first()
    )

    if not dean:
        flash("❌ Dean not found or access denied.")
        return redirect('/')

    departments = Department.query.all()

    # ✅ base query with eager load for both normal and extra subjects
    query = Teacher.query.options(
        joinedload(Teacher.subject_assocs).joinedload(TeacherSubject.subject),
        joinedload(Teacher.extra_subject_links).joinedload(TeacherExtraSubject.extra_subject),
        joinedload(Teacher.department),
        joinedload(Teacher.user)
    )

    if request.method == 'POST':
        dept_id = request.form.get("department_id")
        if dept_id:
            teachers = query.filter_by(department_id=dept_id).all()
        else:
            teachers = []
    else:
        teachers = query.all()

    return render_template(
        'showfaculty.html',
        dean=dean,
        teachers=teachers,
        departments=departments
    )



@app.route('/deansummary/<int:dean_id>', methods=['GET'])
def deansummary(dean_id):
    # ✅ fetch dean via role check
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id, Teacher.id == dean_id)
        .first()
    )
    if not dean:
        flash("⚠️ Access Denied: Only deans can access this page.")
        return redirect('/')

    # =========================
    # Chart 1: Faculty Load Distribution
    # =========================
    teachers = Teacher.query.all()
    faculty_names = [t.user.name for t in teachers]   # ✅ from User
    class_counts = [len(t.routine_slots) for t in teachers]

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
    # Chart 2: Subject Allocation Summary
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

    plot_path_2 = "static/course_allocation.png"
    fig3.tight_layout()
    fig3.savefig(plot_path_2)
    plt.close(fig3)

    # =========================
    # Chart 3: Faculty by Department
    # =========================
    dept_faculty_count = {}
    for t in teachers:
        dept = t.department.name if t.department else "Unknown"
        dept_faculty_count[dept] = dept_faculty_count.get(dept, 0) + 1

    fig4, ax4 = plt.subplots()
    ax4.pie(dept_faculty_count.values(), labels=dept_faculty_count.keys(), autopct='%1.1f%%', startangle=90, shadow=True)
    ax4.set_title("Faculty by Department")

    plot_path_3 = "static/faculty_by_dept.png"
    fig4.savefig(plot_path_3)
    plt.close(fig4)

    return render_template(
        "dean_summary.html",
        dean=dean,
        plot_path_1=plot_path_1,
        plot_path_2=plot_path_2,
        plot_path_3=plot_path_3
    )

@app.route('/addteacher', methods=['GET', 'POST'])
def addteacher():
    # ✅ Dean role check
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )
    if not dean:
        flash("⚠️ Access Denied: Only deans can access this page.")
        return redirect('/')

    departments = Department.query.all()
    classrooms = ClassRoom.query.all()

    # ✅ Teacher roles (exclude Dean & Student)
    roles = Role.query.filter(Role.name.notin_(["Dean", "Student"])).all()
    subjects = Subject.query.all()
    extra_subjects = ExtraSubject.query.all()  # ✅ new

    if request.method == 'POST':
        # --- Collect form data ---
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password") or "Teacher@2025"
        phone = request.form.get("phone")
        address = request.form.get("address") or ""
        department_id = request.form.get("department_id")
        classroom_id = request.form.get("classroom_id") or None
        role_id = request.form.get("role_id")  # ✅ chosen teacher role

        # --- Subject preferences ---
        sub1_id = request.form.get("subject_pref1")

        # --- Extra subject preferences ---
        extra_sub1_id = request.form.get("extra_subject_pref1")

        # --- Prevent duplicates ---
        if User.query.filter_by(email=email).first():
            flash("❌ A user with this email already exists.")
            return redirect('/addteacher')
        if User.query.filter_by(phone=phone).first():
            flash("❌ A user with this phone already exists.")
            return redirect('/addteacher')

        # --- Create User ---
        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            phone=phone,
            address=address
        )
        db.session.add(user)
        db.session.flush()  # ensures user.id is available

        # --- Assign Role ---
        if role_id:
            db.session.add(UserRole(uid=user.id, rid=role_id))

        # --- Create Teacher entry ---
        new_teacher = Teacher(
            uid=user.id,
            department_id=department_id,
            classroom_id=classroom_id
        )
        db.session.add(new_teacher)
        db.session.flush()  # ensures teacher.id is available

        # --- Assign subjects ---
        if sub1_id:
            db.session.add(TeacherSubject(teacher_id=new_teacher.id, subject_id=sub1_id))
        if extra_sub1_id and extra_sub1_id != sub1_id:
            db.session.add(TeacherExtraSubject(teacher_id=new_teacher.id, extra_subject_id=extra_sub1_id))

        db.session.commit()
        flash("✅ Teacher added successfully.")
        return redirect(f'/showfaculty/{dean.id}')

    return render_template(
        'addteacher.html',
        dean=dean,
        departments=departments,
        classrooms=classrooms,
        roles=roles,
        subjects=subjects,
        extra_subjects=extra_subjects  # ✅ pass to template
    )

@app.route('/show_labroutine/<int:lab_id>')
def show_labroutine(lab_id):
    dean_role = Role.query.filter_by(name="Dean").first()
    dean = (
        Teacher.query.join(User, User.id == Teacher.uid)
        .join(UserRole, UserRole.uid == User.id)
        .filter(UserRole.rid == dean_role.id)
        .first()
    )
    lab = ClassRoom.query.filter_by(id=lab_id, is_lab=True).first()
    if not lab:
        flash("❌ Lab not found.")
        return redirect("/")

    # All slots scheduled in this lab
    lab_slots = RoutineSlot.query.filter_by(classroom_id=lab.id).all()

    # Days of week
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Separate morning & evening tables
    morning_routine_table = {day: {} for day in days}
    evening_routine_table = {day: {} for day in days}

    for slot in lab_slots:
        slot_data = {
            "subject": slot.subject.name if slot.subject else "N/A",
            "teacher": slot.teacher.user.name if slot.teacher else "N/A",
            "time_range": slot.time_range
        }

        # navigate: slot → routine → section → batch
        batch = slot.routine.section.batch if slot.routine and slot.routine.section else None
        if batch and "Morning" in batch.name:
            morning_routine_table[slot.day][slot.period] = slot_data
        elif batch and "Evening" in batch.name:
            evening_routine_table[slot.day][slot.period] = slot_data
        else:
            # fallback: put in morning if no batch info
            morning_routine_table[slot.day][slot.period] = slot_data

    return render_template(
        "labroutine.html",
        dean=dean,
        lab=lab,
        days=days,
        morning_routine_table=morning_routine_table,
        evening_routine_table=evening_routine_table
    )



# ----------------- FUNCTIONS -----------------
def assign_teacher_balanced(section_id, teacher_loads, subject_id, day, period, teacher_busy):
    """
    Assign a teacher for a subject with load balancing and conflict check.
    - Avoids overlapping across sections.
    - Balances load across available teachers.
    """

    teachers = Teacher.query.filter(
        Teacher.subjects.any(id=subject_id)
    ).all()
    if not teachers:
        return None

    teachers.sort(key=lambda t: teacher_loads.get(t.id, 0))

    for teacher in teachers:
        # Check if already busy in same day+period
        if (day, period) in teacher_busy.get(teacher.id, set()):
            continue

        # Assign
        teacher_loads[teacher.id] = teacher_loads.get(teacher.id, 0) + 1
        teacher_busy.setdefault(teacher.id, set()).add((day, period))
        return teacher.id

    return None

def generate_three_options(
    section_id,
    subject_ids=None,
    fixed_subject_id=None,
    fixed_period=None,
    teacher_loads=None,
    class_counts=None
):
    """
    Generates 3 alternative timetables for a section:
    - Fixed subjects locked same period across all days
    - Labs always 2 consecutive slots in lab classrooms
    - Theory/mixed in normal classrooms
    - Same subject max twice per day
    - No consecutive repetition > 2
    - Balances teacher load
    """

    section = Section.query.get_or_404(section_id)
    batch = Batch.query.get(section.batch_id)

    MORNING_PERIODS = {1: "08:00-08:55", 2: "09:00-09:55", 3: "10:00-10:55", 4: "11:00-11:55", 5: "12:00-12:55"}
    EVENING_PERIODS = {1: "14:00-14:55", 2: "15:00-15:55", 3: "16:00-16:55", 4: "17:00-17:55", 5: "18:00-18:55"}
    period_timings = MORNING_PERIODS if batch and batch.name.lower() == "morning" else EVENING_PERIODS

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods_per_day = len(period_timings)

    # default subjects if none given
    if not subject_ids:
        subject_ids = [s.id for s in Subject.query.filter_by(department_id=section.department_id).all()]

    # fetch classrooms for department
    theory_rooms = ClassRoom.query.filter_by(department_id=section.department_id, is_lab=False).all()
    lab_rooms = ClassRoom.query.filter_by(department_id=section.department_id, is_lab=True).all()

    all_versions = []
    for version in range(1, 4):   # ✅ three versions
        teacher_loads = teacher_loads or {}
        teacher_busy = {}

        routine = Routine(section_id=section_id, version=version, finalized=False)
        db.session.add(routine)
        db.session.flush()

        timetable = {day: [None] * periods_per_day for day in days}

        # --- Step 1: Lock fixed subject in same period for all days ---
        if fixed_subject_id and fixed_period:
            for day in days:
                teacher_id = assign_teacher_balanced(section_id, teacher_loads, fixed_subject_id, day, fixed_period, teacher_busy)
                if teacher_id:
                    subj = Subject.query.get(fixed_subject_id)
                    classroom = None
                    if subj and subj.lab_hours > 0:
                        classroom = random.choice(lab_rooms) if lab_rooms else None
                    else:
                        classroom = random.choice(theory_rooms) if theory_rooms else None

                    slot = RoutineSlot(
                        routine_id=routine.id,
                        day=day,
                        period=fixed_period,
                        subject_id=fixed_subject_id,
                        teacher_id=teacher_id,
                        classroom_id=classroom.id if classroom else None,
                        time_range=period_timings.get(fixed_period, ""),
                    )
                    db.session.add(slot)
                    timetable[day][fixed_period - 1] = (fixed_subject_id, teacher_id)

        # --- Step 2: Fill the rest ---
        subjects_order = subject_ids[:]
        random.shuffle(subjects_order)

        for sid in subjects_order:
            subj = Subject.query.get(sid)
            if not subj:
                continue

            required = class_counts.get(sid, subj.weekly_classes or 4) if class_counts else subj.weekly_classes or 4
            assigned = 0

            for day in days:
                if assigned >= required:
                    break
                slots = list(range(periods_per_day))
                random.shuffle(slots)

                daily_count = sum(1 for x in timetable[day] if x and x[0] == sid)

                for p in slots:
                    if assigned >= required:
                        break
                    if timetable[day][p] is not None:
                        continue

                    # prevent >2 times same subject per day
                    if daily_count >= 2:
                        break

                    # --- Labs need 2 consecutive ---
                    if subj.lab_hours > 0:
                        if p < periods_per_day - 1 and timetable[day][p + 1] is None:
                            teacher_id = assign_teacher_balanced(section_id, teacher_loads, sid, day, p + 1, teacher_busy)
                            if not teacher_id:
                                continue

                            classroom = random.choice(lab_rooms) if lab_rooms else None

                            slot1 = RoutineSlot(
                                routine_id=routine.id, day=day, period=p + 1,
                                subject_id=sid, teacher_id=teacher_id,
                                classroom_id=classroom.id if classroom else None,
                                time_range=period_timings.get(p + 1, "")
                            )
                            slot2 = RoutineSlot(
                                routine_id=routine.id, day=day, period=p + 2,
                                subject_id=sid, teacher_id=teacher_id,
                                classroom_id=classroom.id if classroom else None,
                                time_range=period_timings.get(p + 2, "")
                            )
                            db.session.add_all([slot1, slot2])
                            timetable[day][p] = (sid, teacher_id)
                            timetable[day][p + 1] = (sid, teacher_id)
                            assigned += 2
                            daily_count += 2
                    else:
                        # Prevent same subject being placed >2 consecutive
                        if (
                            (p > 0 and timetable[day][p - 1] and timetable[day][p - 1][0] == sid) and
                            (p > 1 and timetable[day][p - 2] and timetable[day][p - 2][0] == sid)
                        ):
                            continue  # would make 3 in a row

                        teacher_id = assign_teacher_balanced(section_id, teacher_loads, sid, day, p + 1, teacher_busy)
                        if not teacher_id:
                            continue

                        classroom = random.choice(theory_rooms) if theory_rooms else None

                        slot = RoutineSlot(
                            routine_id=routine.id, day=day, period=p + 1,
                            subject_id=sid, teacher_id=teacher_id,
                            classroom_id=classroom.id if classroom else None,
                            time_range=period_timings.get(p + 1, "")
                        )
                        db.session.add(slot)
                        timetable[day][p] = (sid, teacher_id)
                        assigned += 1
                        daily_count += 1

        all_versions.append(routine)

    db.session.commit()
    return all_versions

def create_department_structure(dep_name, student_count, capacity, assign_roles=True, phone_counter=None):
    """
    Core logic to create a department with classrooms, labs, sections, batches, and students.
    Can be used in both /adddepartment route and seeder.
    """

    # ❌ Prevent duplicates
    if Department.query.filter_by(name=dep_name).first():
        return None, phone_counter

    # 1️⃣ Create Department
    new_department = Department(name=dep_name)
    db.session.add(new_department)
    db.session.commit()

    # ✅ Phone counter block per department
    if phone_counter is None:
        # Each dept gets a unique block starting at 9 + dept.id padded
        phone_counter = new_department.id * 100000  

    # ✅ Always add 2 labs
    for i in range(2):
        lab_classroom = ClassRoom(
            name=f"{dep_name[:3].upper()}_LAB{i+1}",
            capacity=capacity,
            department_id=new_department.id,
            is_lab=True
        )
        db.session.add(lab_classroom)
    db.session.flush()

    # Number of classrooms and sections
    classroom_count = math.ceil(student_count / (capacity * 2))  # 2 batches per classroom
    section_count = math.ceil(student_count / capacity)

    classrooms, batches, sections = [], [], []

    # 2️⃣ Create normal classrooms and batches
    for i in range(classroom_count):
        classroom = ClassRoom(
            name=f"{dep_name[:3].upper()}_CR{i+1}",
            capacity=capacity,
            department_id=new_department.id,
            is_lab=False
        )
        db.session.add(classroom)
        db.session.flush()
        classrooms.append(classroom)

        # Morning + Evening batches
        morning = Batch(name="Morning", classroom_id=classroom.id)
        evening = Batch(name="Evening", classroom_id=classroom.id)
        db.session.add_all([morning, evening])
        db.session.flush()
        batches.extend([morning, evening])

    # 3️⃣ Create sections
    for i in range(section_count):
        assigned_batch = batches[i % len(batches)]
        section = Section(
            name=f"{dep_name}_SEC{i+1}",
            department_id=new_department.id,
            batch_id=assigned_batch.id
        )
        db.session.add(section)
        db.session.flush()
        sections.append(section)

    db.session.commit()

    # 4️⃣ Distribute students
    base_students_per_section = student_count // section_count
    remainder = student_count % section_count
    student_index = 1

    student_role = Role.query.filter_by(name="Student").first() if assign_roles else None
    if assign_roles and not student_role:
        raise ValueError("❌ Role 'Student' not found. Run seed_roles() first.")

    for idx, section in enumerate(sections):
        num_students = base_students_per_section + (1 if idx < remainder else 0)

        for i in range(num_students):
            # ✅ User record
            user = User(
                name=f"Student_{section.name}_{student_index}",
                email=f"{section.name.lower()}_student{student_index}@mail.com",
                password=generate_password_hash("Student@2025"),
                phone=f"9{phone_counter:09d}",   # unique per dept
                address=f"Address {student_index}, {section.name} Block"
            )
            db.session.add(user)
            db.session.flush()

            if assign_roles:
                db.session.add(UserRole(uid=user.id, rid=student_role.id))

            # ✅ Student record
            student = Student(
                uid=user.id,
                department_id=new_department.id,
                section_id=section.id,
                batch_id=section.batch_id,
                classroom_id=section.batch.classroom_id
            )
            db.session.add(student)

            student_index += 1
            phone_counter += 1

    db.session.commit()
    return new_department, phone_counter



def create_classrooms_for_department(department_id, capacity=30):
    department = Department.query.get(department_id)
    if not department:
        raise ValueError("Department not found")

    total_students = len(department.students)
    if total_students == 0:
        return [] 

    num_classrooms = math.ceil(total_students / capacity)

    classrooms = []
    for i in range(num_classrooms):
        classroom = ClassRoom(
            name=f"{department.name[:3].upper()}_CR{i+1}",
            capacity=capacity,
            department_id=department.id
        )
        db.session.add(classroom)
        classrooms.append(classroom)

    db.session.commit()
    return classrooms


# ------------------ DATABASE SEEDING ------------------

# ---- Create Roles ----
def seed_roles():
    roles = ["Dean", "Professor", "Assistant Professor", "Lab Assistant", "Student"]
    for r in roles:
        if not Role.query.filter_by(name=r).first():
            db.session.add(Role(name=r))
    db.session.commit()
    print("✅ Roles seeded successfully!")


# ---- Create Dean ----
def create_dean():
    existing_dean = User.query.filter_by(email="dean@example.com").first()
    if existing_dean:
        print("ℹ️ Dean already exists, skipping creation.")
        return

    dean_user = User(
        name="Dean of Engineering",
        email="dean@example.com",
        password=generate_password_hash("Dean@123"),
        phone="9876598765",
        address="University HQ"
    )
    db.session.add(dean_user)
    db.session.flush()

    dean_role = Role.query.filter_by(name="Dean").first()
    if not dean_role:
        dean_role = Role(name="Dean")
        db.session.add(dean_role)
        db.session.flush()

    db.session.add(UserRole(uid=dean_user.id, rid=dean_role.id))

    dean_teacher = Teacher(uid=dean_user.id, department_id=None, classroom_id=None)
    dean_teacher.set_max_workload("Professor")
    db.session.add(dean_teacher)

    db.session.commit()
    print("✅ Dean created successfully!")


# ---- Create Departments, Classrooms, Sections, Students ----
def create_departments_with_structure():
    departments = {
        "Literature": {"students": 12, "capacity": 6},
        "Maths": {"students": 18, "capacity": 6},
        "CSE": {"students": 24, "capacity": 8},
        "MSE": {"students": 12, "capacity": 6},
        "EEE": {"students": 18, "capacity": 6},
        "CE": {"students": 12, "capacity": 6},
    }

    phone_counter = 1
    for dep_name, info in departments.items():
        dept, phone_counter = create_department_structure(dep_name, info["students"], info["capacity"], assign_roles=True, phone_counter=phone_counter)
        if dept:
            print(f"✅ Department {dep_name} created.")
        else:
            print(f"ℹ️ Department {dep_name} already exists, skipped.")


# ---- Create Teachers ----
def seed_teachers():
    print("⚡ Seeding teachers...")

    # Roles
    professor_role = Role.query.filter_by(name="Professor").first()
    asst_prof_role = Role.query.filter_by(name="Assistant Professor").first()
    lab_asst_role = Role.query.filter_by(name="Lab Assistant").first()

    if not (professor_role and asst_prof_role and lab_asst_role):
        print("❌ Roles missing, seed roles first.")
        return

    departments = Department.query.all()
    counter = 1000  # base counter for unique values

    for dep in departments:
        # --- Professors ---
        for i in range(2):  
            name = f"Professor {dep.name} {i+1}"
            email = f"prof_{dep.name.lower()}{i+1}@example.com"
            phone = str(9100000000 + counter)
            address = f"{dep.name} Campus Block-{counter}"

            # ✅ Skip if exists
            if User.query.filter((User.email == email) | (User.phone == phone) | (User.address == address)).first():
                print(f"ℹ️ {name} already exists, skipping...")
                counter += 1
                continue

            user = User(
                name=name,
                email=email,
                password=generate_password_hash("Teacher@2025"),
                phone=phone,
                address=address
            )
            db.session.add(user)
            db.session.flush()

            db.session.add(UserRole(uid=user.id, rid=professor_role.id))

            teacher = Teacher(uid=user.id, department_id=dep.id)
            db.session.add(teacher)
            db.session.flush()

            # ✅ Assign 1 subject if available
            subject = Subject.query.filter_by(department_id=dep.id).first()
            if subject:
                db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subject.id))

            counter += 1

        # --- Assistant Professors ---
        for i in range(2):
            name = f"Assistant Professor {dep.name} {i+1}"
            email = f"asstprof_{dep.name.lower()}{i+1}@example.com"
            phone = str(9010000000 + counter)
            address = f"{dep.name} Campus Block-{counter}"

            if User.query.filter((User.email == email) | (User.phone == phone) | (User.address == address)).first():
                print(f"ℹ️ {name} already exists, skipping...")
                counter += 1
                continue

            user = User(
                name=name,
                email=email,
                password=generate_password_hash("Teacher@2025"),
                phone=phone,
                address=address
            )
            db.session.add(user)
            db.session.flush()

            db.session.add(UserRole(uid=user.id, rid=asst_prof_role.id))

            teacher = Teacher(uid=user.id, department_id=dep.id)
            db.session.add(teacher)
            db.session.flush()

            subject = Subject.query.filter_by(department_id=dep.id).first()
            if subject:
                db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subject.id))

            counter += 1

        # --- Lab Assistants ---
        for i in range(1):  
            name = f"Lab Assistant {dep.name} {i+1}"
            email = f"labasst_{dep.name.lower()}{i+1}@example.com"
            phone = str(9001000000 + counter)
            address = f"{dep.name} Campus Block-{counter}"

            if User.query.filter((User.email == email) | (User.phone == phone) | (User.address == address)).first():
                print(f"ℹ️ {name} already exists, skipping...")
                counter += 1
                continue

            user = User(
                name=name,
                email=email,
                password=generate_password_hash("Teacher@2025"),
                phone=phone,
                address=address
            )
            db.session.add(user)
            db.session.flush()

            db.session.add(UserRole(uid=user.id, rid=lab_asst_role.id))

            teacher = Teacher(uid=user.id, department_id=dep.id)
            db.session.add(teacher)
            db.session.flush()

            # ✅ Assign extra subject (only labs, credits=2 or 4)
            extra_lab = ExtraSubject.query.filter_by(department_id=dep.id, distribution_type="lab").first()
            if extra_lab:
                db.session.add(TeacherExtraSubject(teacher_id=teacher.id, extra_subject_id=extra_lab.id))

            counter += 1

    db.session.commit()
    print("✅ Teachers seeded safely (duplicates skipped, addresses unique).")

# ---- Create Subjects ----
SUBJECT_POOL = {
    "Literature": [
        "English Poetry", "Shakespeare Studies", "World Literature", "Modern Fiction"
    ],
    "Maths": [
        "Calculus", "Algebra", "Probability", "Geometry", "Linear Algebra"
    ],
    "CSE": [
        "Data Structures", "Algorithms", "Operating Systems", "Databases", "Computer Networks"
    ],
    "MSE": [
        "Materials Thermodynamics", "Metallurgy", "Polymer Science", "Nanomaterials", "Composite Materials"
    ],
    "EEE": [
        "Circuit Theory", "Electromagnetics", "Control Systems", "Digital Electronics", "Power Systems"
    ],
    "CE": [
        "Structural Analysis", "Geotechnical Engineering", "Fluid Mechanics", "Transportation Engineering", "Construction Management"
    ]
}

def create_subjects():
    role_distribution = {
        "Professor": "theory",
        "Assistant Professor": "mixed",
        "Lab Assistant": "lab"
    }

    departments = Department.query.all()

    for dep in departments:
        subjects_for_dep = SUBJECT_POOL.get(dep.name, [])
        sub_index = 0  # track subject assignment per department

        for role_name, distribution_type in role_distribution.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                continue

            teachers = (
                db.session.query(Teacher)
                .join(User, Teacher.uid == User.id)
                .join(UserRole, User.id == UserRole.uid)
                .filter(UserRole.rid == role.id, Teacher.department_id == dep.id)
                .limit(2)
                .all()
            )

            for teacher in teachers:
                # --- Credits selection based on role ---
                if distribution_type == "lab":
                    credits = random.choice([2, 4])   # ✅ only lab (2 or 4)
                elif distribution_type == "theory":
                    credits = random.choice([2, 3, 4])  # ✅ Professors flexible
                elif distribution_type == "mixed":
                    credits = random.choice([2, 3, 4])  # ✅ Assistants flexible
                else:
                    credits = 3  # fallback

                # --- Pick subject name from SUBJECT_POOL ---
                if sub_index >= len(subjects_for_dep):
                    continue  # no more subjects available

                sub_name = subjects_for_dep[sub_index]
                sub_index += 1

                # Avoid duplicates
                if Subject.query.filter_by(name=sub_name, department_id=dep.id).first():
                    continue

                subject = Subject(
                    name=sub_name,
                    department_id=dep.id,
                    distribution_type=distribution_type,
                    credits=credits
                )
                subject.calculate_hours()
                db.session.add(subject)
                db.session.flush()

                # Assign subject to teacher
                db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subject.id))

    db.session.commit()
    print("✅ Subjects created and assigned successfully!")


# ---- Create Extra Subjects ----
EXTRA_SUBJECT_POOL = {
    "Literature": ["Creative Writing", "Literary Criticism", "Journalism"],
    "Maths": ["Number Theory", "Statistics", "Graph Theory"],
    "CSE": ["Artificial Intelligence", "Machine Learning", "Cybersecurity"],
    "MSE": ["Ceramics", "Surface Engineering", "Corrosion Science"],
    "EEE": ["Renewable Energy", "Microprocessors", "VLSI Design"],
    "CE": ["Urban Planning", "Environmental Engineering", "Hydrology"],
}

def seed_extra_subjects():
    departments = Department.query.all()

    for dep in departments:
        if dep.name not in EXTRA_SUBJECT_POOL:
            continue

        for sub_name in EXTRA_SUBJECT_POOL[dep.name]:
            if ExtraSubject.query.filter_by(name=sub_name, department_id=dep.id).first():
                continue  # avoid duplicates

            # --- Create ExtraSubject ---
            # Random but valid type
            distribution_type = random.choice(["theory", "mixed", "lab"])
            if distribution_type == "lab":
                credits = random.choice([2, 4])  # labs only 2 or 4
            else:
                credits = random.choice([2, 3, 4])

            extra_sub = ExtraSubject(
                name=sub_name,
                department_id=dep.id,
                distribution_type=distribution_type,
                credits=credits,
            )
            extra_sub.calculate_hours()
            db.session.add(extra_sub)
            db.session.flush()

            # --- Assign Teachers based on role ---
            teachers = (
                db.session.query(Teacher)
                .join(User, Teacher.uid == User.id)
                .join(UserRole, UserRole.uid == User.id)
                .filter(Teacher.department_id == dep.id)
                .all()
            )

            if not teachers:
                continue

            # Filter by role
            for teacher in teachers:
                role = (
                    db.session.query(Role)
                    .join(UserRole, UserRole.rid == Role.id)
                    .filter(UserRole.uid == teacher.uid)
                    .first()
                )
                if not role:
                    continue

                assign = False
                if role.name == "Lab Assistant" and extra_sub.distribution_type == "lab":
                    assign = True
                elif role.name == "Professor" and extra_sub.distribution_type in ["theory", "mixed"]:
                    assign = True
                elif role.name == "Assistant Professor" and extra_sub.distribution_type in ["theory", "mixed"]:
                    assign = True

                if assign:
                    db.session.add(
                        TeacherExtraSubject(
                            teacher_id=teacher.id,
                            extra_subject_id=extra_sub.id
                        )
                    )

    db.session.commit()
    print("✅ Extra subjects seeded with correct teacher-role restrictions!")


if __name__ == '__main__':

    seed_roles()
    create_dean()
    create_departments_with_structure()
    create_subjects()
    seed_extra_subjects()
    seed_teachers()
    print("✅ Database seeded successfully with extra subjects!")

    with app.app_context():
        for t in Teacher.query.all():
            if t.workload is None:
                t.workload = 0
        db.session.commit()

        print("🎉 Database seeding completed!")

    # 3️⃣ Start Flask
    app.run(debug=True)
