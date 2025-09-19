
from .database import db
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import datetime

class User(db.Model):
    __tablename__='user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    address = db.Column(db.String(255))

    student = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher = db.relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    roles= db.relationship('UserRole', back_populates='user', cascade='all, delete-orphan')

class Role(db.Model):
    __tablename__='role'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)

    users= db.relationship('UserRole', back_populates='role', cascade='all, delete-orphan')


class UserRole(db.Model):
    __tablename__ = 'user_role'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uid= db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rid= db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)

    user = db.relationship('User', back_populates='roles')
    role = db.relationship('Role', back_populates='users')

class Teacher(db.Model):
    __tablename__ = 'teacher'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uid = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'))
    workload = db.Column(db.Integer, default=0, nullable=False)
    max_workload = db.Column(db.Integer, nullable=False, default=16)

    # ✅ Use back_populates (not backref)
    user = db.relationship('User', back_populates='teacher')

    routine_slots = db.relationship('RoutineSlot', back_populates='teacher')
    subject_assocs = db.relationship("TeacherSubject", back_populates="teacher", cascade="all, delete-orphan")
    subjects = association_proxy("subject_assocs", "subject")

    def set_max_workload(self, role_name):
        if role_name == "Professor":
            self.max_workload = 14
        elif role_name == "Assistant Professor":
            self.max_workload = 16
        elif role_name == "Lab Assistant":
            self.max_workload = 18
        else:
            # fallback for Dean, Lecturer, unknown roles, or None
            self.max_workload = 20   # or 25 if you want very high cap


class Subject(db.Model):
    __tablename__ = 'subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    distribution_type = db.Column(db.String(20), default="mixed")  

    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)

    credits = db.Column(db.Integer, nullable=False, default=3)   # credit system
    theory_hours = db.Column(db.Integer, nullable=False, default=0)  # derived from credits
    lab_hours = db.Column(db.Integer, nullable=False, default=0)     # derived from credits
    weekly_classes = db.Column(db.Integer, nullable=False, default=3)  # total slots

    routine_slots = db.relationship('RoutineSlot', back_populates='subject')
    teacher_assocs = db.relationship("TeacherSubject", back_populates="subject", cascade="all, delete-orphan")
    teachers = association_proxy("teacher_assocs", "teacher")

    # ✅ Add this function inside Subject
    def calculate_hours(self):
        # ensure no None values
        self.theory_hours = self.theory_hours or 0
        self.lab_hours = self.lab_hours or 0

        if self.credits == 4:
            if self.distribution_type == "lab":
                self.theory_hours, self.lab_hours = 0, 2
            elif self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 4, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 3, 1

        elif self.credits == 3:
            if self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 3, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 2, 1

        elif self.credits == 2:
            if self.distribution_type == "lab":
                self.theory_hours, self.lab_hours = 0, 1
            elif self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 2, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 1, 1

        # final safety net
        self.theory_hours = self.theory_hours or 0
        self.lab_hours = self.lab_hours or 0

        self.weekly_classes = int(self.theory_hours + (self.lab_hours * 2))



class TeacherSubject(db.Model):
    __tablename__ = 'teacher_subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'subject_id', name='uq_teacher_subject'),
    )

    teacher = db.relationship("Teacher", back_populates="subject_assocs")
    subject = db.relationship("Subject", back_populates="teacher_assocs")


class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uid = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)

    user = db.relationship(
        "User",
        back_populates="student"
    )
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'))
    batch = db.relationship('Batch', backref='students')


    # Relationship to association object
    extra_subjects_assoc = db.relationship(
        "StudentExtraSubject",
        back_populates="student",
        cascade="all, delete-orphan"
    )

    # Convenience proxy to access ExtraSubject objects directly
    extra_subjects = association_proxy(
        'extra_subjects_assoc',
        'extra_subject'
    )



class ClassRoom(db.Model):
    __tablename__ = 'classroom'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    capacity = db.Column(db.Integer, nullable=False, default=30)
    is_lab = db.Column(db.Boolean, default=False, nullable=False)
    
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)

    batches = db.relationship('Batch', backref='classroom', cascade="all, delete-orphan", passive_deletes=True)
    students = db.relationship('Student', backref='classroom', cascade="all, delete-orphan", passive_deletes=True)
    teachers = db.relationship('Teacher', backref='classroom', cascade="all, delete-orphan", passive_deletes=True)

class Batch(db.Model):
    __tablename__ = 'batch'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)  # Morning/Evening
    classroom_id = db.Column(
        db.Integer,
        db.ForeignKey('classroom.id', ondelete="CASCADE"),
        nullable=False
    )

    sections = db.relationship(
        "Section",
        backref="batch",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class Section(db.Model):
    __tablename__ = 'section'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(10), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id', ondelete="CASCADE"), nullable=False)
    selected_routine = db.Column(db.String(10), nullable=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id', ondelete="CASCADE"), nullable=True)
    
    
    students = db.relationship('Student', backref='section', cascade="all, delete-orphan", passive_deletes=True)
    routines = db.relationship('Routine', backref='section', cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint('name', 'department_id', name='uq_section_department'),
    )



class Department(db.Model):
    __tablename__ = 'department'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    teachers = db.relationship('Teacher', backref='department', cascade="all, delete-orphan")
    students = db.relationship('Student', backref='department', cascade="all, delete-orphan")
    sections = db.relationship('Section', backref='department', cascade="all, delete-orphan")
    subjects = db.relationship('Subject', backref='department', cascade="all, delete-orphan")
    extra_subjects = db.relationship('ExtraSubject', backref='department', cascade="all, delete-orphan")
    classrooms = db.relationship('ClassRoom', backref='department', cascade="all, delete-orphan")

class FixedSubject(db.Model):
    __tablename__ = 'fixed_subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)

    day = db.Column(db.String(10), nullable=False)      # e.g. "Mon"
    time_slot = db.Column(db.String(20), nullable=False) # e.g. "9-10 AM"

    section = db.relationship("Section", backref="fixed_subjects")
    subject = db.relationship("Subject")
    classroom = db.relationship("ClassRoom")


class ExtraSubject(db.Model):
    __tablename__ = 'extra_subject'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    distribution_type = db.Column(db.String(20), default="mixed")  
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)

    credits = db.Column(db.Integer, nullable=False, default=2)
    theory_hours = db.Column(db.Integer, nullable=False, default=0)
    lab_hours = db.Column(db.Integer, nullable=False, default=0)
    weekly_classes = db.Column(db.Integer, nullable=False, default=2)

    routine_slots = db.relationship('RoutineSlot', back_populates='extra_subject')

    # ✅ proper associations
    teacher_links = db.relationship("TeacherExtraSubject", back_populates="extra_subject", cascade="all, delete-orphan")
    student_links = db.relationship("StudentExtraSubject", back_populates="extra_subject", cascade="all, delete-orphan")


    def calculate_hours(self):
        # ensure no None values
        self.theory_hours = self.theory_hours or 0
        self.lab_hours = self.lab_hours or 0

        if self.credits == 4:
            if self.distribution_type == "lab":
                self.theory_hours, self.lab_hours = 0, 2
            elif self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 4, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 3, 1

        elif self.credits == 3:
            if self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 3, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 2, 1

        elif self.credits == 2:
            if self.distribution_type == "lab":
                self.theory_hours, self.lab_hours = 0, 1
            elif self.distribution_type == "theory":
                self.theory_hours, self.lab_hours = 2, 0
            elif self.distribution_type == "mixed":
                self.theory_hours, self.lab_hours = 1, 1

        # final safety net
        self.theory_hours = self.theory_hours or 0
        self.lab_hours = self.lab_hours or 0

        self.weekly_classes = int(self.theory_hours + (self.lab_hours * 2))


class TeacherExtraSubject(db.Model):
    __tablename__ = 'teacher_extra_subject'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    extra_subject_id = db.Column(db.Integer, db.ForeignKey('extra_subject.id'), nullable=False)

    teacher = db.relationship("Teacher", backref=db.backref("extra_subject_links", cascade="all, delete-orphan"))
    extra_subject = db.relationship("ExtraSubject", back_populates="teacher_links")

class StudentExtraSubject(db.Model):
    __tablename__ = 'student_extra_subject'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    extra_subject_id = db.Column(db.Integer, db.ForeignKey('extra_subject.id'), nullable=False)
    preferred_day = db.Column(db.String(10))
    preferred_period = db.Column(db.Integer)

    student = db.relationship("Student", back_populates="extra_subjects_assoc")
    extra_subject = db.relationship("ExtraSubject", back_populates="student_links")


class Routine(db.Model):
    __tablename__ = 'routine'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    finalized = db.Column(db.Boolean, default=False)

    slots = db.relationship('RoutineSlot', back_populates='routine', cascade="all, delete-orphan")


class RoutineSlot(db.Model):
    __tablename__ = 'routine_slot'   
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    routine_id = db.Column(db.Integer, db.ForeignKey('routine.id'), nullable=False)
    day = db.Column(db.String(10), nullable=False)
    period = db.Column(db.Integer, nullable=False)

    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=True)
    time_range = db.Column(db.String(20), nullable=False)

    extra_subject_id = db.Column(db.Integer, db.ForeignKey('extra_subject.id'), nullable=True)
    extra_subject = db.relationship("ExtraSubject", back_populates="routine_slots")

    routine = db.relationship('Routine', back_populates='slots')
    subject = db.relationship('Subject', back_populates='routine_slots')   
    teacher = db.relationship('Teacher', back_populates='routine_slots')   
    classroom = db.relationship('ClassRoom', backref='routine_slots')

class SubstituteLog(db.Model):
    __tablename__ = 'substitute_log'
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('routine_slot.id'))
    from_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))
    to_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    slot = db.relationship('RoutineSlot', backref='substitute_logs')
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

