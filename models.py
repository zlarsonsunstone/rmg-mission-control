"""
RMG Mission Control — Database Models
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'superadmin' or 'user'
    character_class = db.Column(db.String(50), nullable=True)
    character_title = db.Column(db.String(100), nullable=True)
    special_ability = db.Column(db.String(200), nullable=True)
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    streak_days = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.String(10), nullable=True)
    first_login_complete = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    tasks = db.relationship('Task', backref='owner', lazy=True, foreign_keys='Task.owner_id')
    comments = db.relationship('Comment', backref='author', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    points_log = db.relationship('PointsLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_superadmin(self):
        return self.role == 'superadmin'

    @property
    def level_title(self):
        titles = {1: 'Recruit', 2: 'Specialist', 3: 'Veteran', 4: 'Commander', 5: 'Legend'}
        return titles.get(self.level, 'Recruit')

    def update_level(self):
        if self.points >= 1000:
            self.level = 5
        elif self.points >= 500:
            self.level = 4
        elif self.points >= 250:
            self.level = 3
        elif self.points >= 100:
            self.level = 2
        else:
            self.level = 1

    def update_streak(self):
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if self.last_active_date == today:
            return
        yesterday = (datetime.now(timezone.utc).date() - 
            __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d')
        if self.last_active_date == yesterday:
            self.streak_days += 1
        else:
            self.streak_days = 1
        self.last_active_date = today


# Task dependency association table
task_dependencies = db.Table('task_dependencies',
    db.Column('task_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True),
    db.Column('depends_on_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True)
)


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    task_number = db.Column(db.Integer, nullable=False)  # 1-17
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    spreadsheet_location = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.String(20), default='medium')  # critical, high, medium, low
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='not_started')  # not_started, in_progress, submitted, verified, closed
    due_date = db.Column(db.DateTime, nullable=True)
    points_value = db.Column(db.Integer, default=50)
    quality_score = db.Column(db.Integer, nullable=True)  # 0-100, set by superadmin
    revision_count = db.Column(db.Integer, default=0)
    integrity_impact = db.Column(db.Integer, default=0)  # points added to integrity score
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    completion_notes = db.Column(db.Text, nullable=True)
    verification_notes = db.Column(db.Text, nullable=True)
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    dependencies = db.relationship('Task',
        secondary=task_dependencies,
        primaryjoin=(id == task_dependencies.c.task_id),
        secondaryjoin=(id == task_dependencies.c.depends_on_id),
        backref='dependents',
        lazy=True
    )
    comments = db.relationship('Comment', backref='task', lazy=True, order_by='Comment.created_at')
    files = db.relationship('File', backref='task', lazy=True)

    @property
    def is_blocked(self):
        for dep in self.dependencies:
            if dep.status not in ('submitted', 'verified', 'closed'):
                return True
        return False

    @property
    def blocking_tasks(self):
        return [dep for dep in self.dependencies if dep.status not in ('submitted', 'verified', 'closed')]

    @property
    def priority_weight(self):
        weights = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
        return weights.get(self.priority, 1)

    @property
    def base_points(self):
        pts = {'critical': 100, 'high': 75, 'medium': 50, 'low': 25}
        return pts.get(self.priority, 25)


class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)
    version = db.Column(db.Integer, default=1)
    file_size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    uploader = db.relationship('User', backref='uploaded_files')


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_system = db.Column(db.Boolean, default=False)  # system-generated messages
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # task_assigned, task_unblocked, help_request, mention, announcement, deadline_warning
    content = db.Column(db.Text, nullable=False)
    reference_type = db.Column(db.String(20), nullable=True)  # task, comment, file, announcement
    reference_id = db.Column(db.Integer, nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class PointsLog(db.Model):
    __tablename__ = 'points_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship('User', backref='announcements')


class FAQ(db.Model):
    __tablename__ = 'faqs'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(50), default='general')
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    submitter = db.relationship('User', foreign_keys=[submitted_by])
    approver = db.relationship('User', foreign_keys=[approved_by])


class HelpRequest(db.Model):
    __tablename__ = 'help_requests'
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    helper_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, declined, resolved
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    requester = db.relationship('User', foreign_keys=[requester_id])
    helper = db.relationship('User', foreign_keys=[helper_id])
    task = db.relationship('Task')


class AccessRequest(db.Model):
    __tablename__ = 'access_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(db.Integer, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    requester = db.relationship('User', foreign_keys=[user_id])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])


class Priority(db.Model):
    __tablename__ = 'priorities'
    id = db.Column(db.Integer, primary_key=True)
    cycle_timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    scope = db.Column(db.String(10), nullable=False)  # 'global' or 'user'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rank = db.Column(db.Integer, nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    summary = db.Column(db.Text, nullable=True)

    task = db.relationship('Task')
