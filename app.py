"""
RMG Mission Control — Main Flask Application
VA MSPV Gen-Z V1 Market Research Response Dashboard
"""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, flash,
                   jsonify, session, send_from_directory, abort)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models import (db, User, Task, File, Comment, Notification, PointsLog,
                    Announcement, FAQ, HelpRequest, AccessRequest, Priority)
from gamification import (award_points, get_leaderboard, calculate_data_integrity_score,
                    CHARACTER_CLASSES, SUGGESTED_CLASSES, create_auto_announcement)
from priority_engine import run_priority_engine, format_priorities_for_slack
from slack_integration import (init_slack, notify_task_completed, notify_task_unblocked,
                    notify_help_request, notify_announcement,
                    post_priority_update, notify_deadline_warning)

load_dotenv()

# --- App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///rmg_mission_control.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# Mail config
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@rencoman.com')

db.init_app(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Slack
init_slack(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Scheduler (6-hour priority engine) ---
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()

    def scheduled_priority_run():
        logger.info("Priority engine running — scheduled cycle")
        result = run_priority_engine(app)
        with app.app_context():
            formatted = format_priorities_for_slack(result)
            post_priority_update(formatted)

    scheduler.add_job(scheduled_priority_run, 'interval', hours=6, id='priority_engine',
                    next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5))
    scheduler.start()
    logger.info("APScheduler started — priority engine every 6 hours")
except ImportError:
    logger.warning("APScheduler not available. Set up external cron for priority engine.")


# --- Helpers ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        acting_user = get_acting_user()
        if not acting_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def get_acting_user():
    """Get the user we're acting as (supports clone mode)."""
    clone_id = session.get('clone_user_id')
    if clone_id and current_user.is_superadmin:
        cloned = User.query.get(clone_id)
        if cloned:
            return cloned
    return current_user


def create_notification(user_id, notif_type, content, ref_type=None, ref_id=None):
    """Create a notification for a user."""
    n = Notification(
        user_id=user_id,
        type=notif_type,
        content=content,
        reference_type=ref_type,
        reference_id=ref_id
    )
    db.session.add(n)
    db.session.commit()


ALLOWED_EXTENSIONS = {'xlsx', 'docx', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'txt', 'pptx', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Context Processors ---
@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        unread_count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        acting = get_acting_user()
        is_cloning = session.get('clone_user_id') is not None and current_user.is_superadmin
        active_announcements = Announcement.query.filter_by(active=True).order_by(
            Announcement.created_at.desc()).limit(3).all()
        return {
            'unread_count': unread_count,
            'acting_user': acting,
            'is_cloning': is_cloning,
            'announcements': active_announcements,
            'character_classes': CHARACTER_CLASSES,
            'deadline': datetime(2026, 2, 20, tzinfo=timezone.utc),
            'now': datetime.now(timezone.utc)
        }
    return {}


# ====
# AUTH ROUTES
# ====

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.update_streak()
            db.session.commit()

            if not user.first_login_complete:
                return redirect(url_for('character_creation'))
            return redirect(request.args.get('next') or url_for('dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.pop('clone_user_id', None)
    logout_user()
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            from itsdangerous import URLSafeTimedSerializer
            s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
            token = s.dumps(email, salt='password-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            try:
                msg = Message('RMG Mission Control — Password Reset',
                    recipients=[email])
                msg.body = f"Click here to reset your password: {reset_url}\n\nThis link expires in 1 hour."
                mail.send(msg)
            except Exception as e:
                logger.warning(f"Email send failed: {e}")
                flash(f'Email service not configured. Reset link: {reset_url}', 'info')
                return render_template('forgot_password.html')

        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset', max_age=3600)
    except (SignatureExpired, BadSignature):
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        if password != confirm:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                user.set_password(password)
                db.session.commit()
                flash('Password reset successfully. Please log in.', 'success')
                return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


# ====
# CHARACTER CREATION
# ====

@app.route('/character-creation', methods=['GET', 'POST'])
@login_required
def character_creation():
    if request.method == 'POST':
        char_class = request.form.get('character_class')
        if char_class in CHARACTER_CLASSES:
            current_user.character_class = char_class
            current_user.character_title = CHARACTER_CLASSES[char_class]['name']
            current_user.special_ability = CHARACTER_CLASSES[char_class]['ability']
            current_user.first_login_complete = True
            db.session.commit()
            flash(f'Welcome, {current_user.name} the {CHARACTER_CLASSES[char_class]["name"]}!', 'success')
            return redirect(url_for('dashboard'))

    suggested = SUGGESTED_CLASSES.get(current_user.email)
    return render_template('character_creation.html',
                    classes=CHARACTER_CLASSES,
                    suggested=suggested)


# ====
# DASHBOARD ROUTES
# ====

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    acting = get_acting_user()
    view = request.args.get('view', 'individual' if not acting.is_superadmin else 'global')
    focus = request.args.get('focus', 'false') == 'true'

    # Get all tasks
    all_tasks = Task.query.order_by(Task.priority.desc(), Task.due_date.asc()).all()
    my_tasks = [t for t in all_tasks if t.owner_id == acting.id]

    # Get priorities
    global_priorities = Priority.query.filter_by(scope='global').order_by(Priority.rank).limit(5).all()
    user_priorities = Priority.query.filter_by(scope='user', user_id=acting.id).order_by(Priority.rank).limit(5).all()

    # Data integrity score
    integrity = calculate_data_integrity_score()

    # Leaderboard
    leaderboard = get_leaderboard()

    # Recent activity (comments + system events)
    recent_activity = Comment.query.order_by(Comment.created_at.desc()).limit(20).all()

    # Stats
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.status in ('verified', 'closed')])
    in_progress_tasks = len([t for t in all_tasks if t.status == 'in_progress'])
    blocked_tasks = len([t for t in all_tasks if t.is_blocked and t.status not in ('verified', 'closed')])

    return render_template('dashboard.html',
                    view=view,
                    focus=focus,
                    all_tasks=all_tasks,
                    my_tasks=my_tasks,
                    global_priorities=global_priorities,
                    user_priorities=user_priorities,
                    integrity=integrity,
                    leaderboard=leaderboard,
                    recent_activity=recent_activity,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    in_progress_tasks=in_progress_tasks,
                    blocked_tasks=blocked_tasks,
                    acting=acting,
                    users=User.query.all())


# ====
# TASK ROUTES
# ====

@app.route('/task/<int:task_id>')
@login_required
def task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    comments = Comment.query.filter_by(task_id=task_id).order_by(Comment.created_at.asc()).all()
    files = File.query.filter_by(task_id=task_id).order_by(File.created_at.desc()).all()
    help_requests = HelpRequest.query.filter_by(task_id=task_id).all()
    users = User.query.all()
    return render_template('task_detail.html',
                    task=task,
                    comments=comments,
                    files=files,
                    help_requests=help_requests,
                    users=users)


@app.route('/task/<int:task_id>/start', methods=['POST'])
@login_required
def task_start(task_id):
    task = Task.query.get_or_404(task_id)
    acting = get_acting_user()

    if task.owner_id != acting.id and not current_user.is_superadmin:
        abort(403)

    if task.is_blocked:
        flash('This task is blocked by dependencies.', 'warning')
        return redirect(url_for('task_detail', task_id=task_id))

    task.status = 'in_progress'
    task.started_at = datetime.now(timezone.utc)
    db.session.add(Comment(task_id=task_id, user_id=acting.id,
                    content=f"{acting.name} started working on this task.", is_system=True))
    db.session.commit()
    flash('Task started!', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/submit', methods=['POST'])
@login_required
def task_submit(task_id):
    task = Task.query.get_or_404(task_id)
    acting = get_acting_user()

    if task.owner_id != acting.id and not current_user.is_superadmin:
        abort(403)

    notes = request.form.get('completion_notes', '')
    task.status = 'submitted'
    task.submitted_at = datetime.now(timezone.utc)
    task.submitted_by = acting.id
    task.completion_notes = notes

    # Handle file upload
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            file.save(filepath)
            file_size = os.path.getsize(filepath)
            f = File(filename=unique_name, filepath=filepath,
                    original_filename=filename, task_id=task_id,
                    uploaded_by=acting.id, file_size=file_size,
                    description=notes)
            db.session.add(f)
            award_points(acting, task, 'document_uploaded')

    # System comment
    db.session.add(Comment(task_id=task_id, user_id=acting.id,
                    content=f"{acting.name} submitted this task for verification.", is_system=True))

    # Notify superadmins
    for admin in User.query.filter_by(role='superadmin').all():
        if admin.id != acting.id:
            create_notification(admin.id, 'task_submitted',
                    f'{acting.name} submitted: {task.title}',
                    'task', task_id)

    db.session.commit()

    # Slack notification
    notify_task_completed(acting.name, task.title)

    flash('Task submitted for verification!', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/verify', methods=['POST'])
@login_required
@superadmin_required
def task_verify(task_id):
    task = Task.query.get_or_404(task_id)
    quality = int(request.form.get('quality_score', 75))
    notes = request.form.get('verification_notes', '')

    task.status = 'verified'
    task.verified_at = datetime.now(timezone.utc)
    task.verified_by = current_user.id
    task.quality_score = quality
    task.verification_notes = notes

    # Calculate points
    owner = task.owner
    if owner:
        now = datetime.now(timezone.utc)
        if task.due_date and task.submitted_at and task.submitted_at < task.due_date:
            points = award_points(owner, task, 'task_completed_early')
        elif task.due_date and task.submitted_at and task.submitted_at > task.due_date:
            points = award_points(owner, task, 'task_completed_late')
        else:
            points = award_points(owner, task, 'task_completed_ontime')

        if quality >= 90:
            award_points(owner, task, 'quality_bonus')
        if task.revision_count == 0:
            award_points(owner, task, 'perfect_submission')

        create_notification(owner.id, 'task_verified',
                    f'Your task "{task.title}" was verified! Quality: {quality}/100',
                    'task', task_id)

    # Check if this unblocks any tasks
    unblocked = []
    for dependent in task.dependents:
        if not dependent.is_blocked and dependent.status == 'not_started':
            unblocked.append(dependent.title)
            if dependent.owner:
                create_notification(dependent.owner_id, 'task_unblocked',
                    f'Task "{dependent.title}" is now unblocked!',
                    'task', dependent.id)

    if unblocked:
        notify_task_unblocked(task.title, unblocked)
        create_auto_announcement(f"Task \"{task.title}\" completed — now unblocked: {', '.join(unblocked)}")

    db.session.add(Comment(task_id=task_id, user_id=current_user.id,
                    content=f"Verified by {current_user.name}. Quality: {quality}/100. {notes}",
                    is_system=True))
    db.session.commit()

    flash(f'Task verified! Quality score: {quality}/100', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/return', methods=['POST'])
@login_required
@superadmin_required
def task_return(task_id):
    task = Task.query.get_or_404(task_id)
    feedback = request.form.get('feedback', '')

    task.status = 'in_progress'
    task.revision_count += 1
    task.verification_notes = feedback

    owner = task.owner
    if owner:
        award_points(owner, task, 'revision_penalty')
        create_notification(owner.id, 'task_returned',
                    f'Task "{task.title}" returned with feedback: {feedback}',
                    'task', task_id)

    db.session.add(Comment(task_id=task_id, user_id=current_user.id,
                    content=f"Returned by {current_user.name}: {feedback}", is_system=True))
    db.session.commit()

    flash('Task returned with feedback.', 'warning')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/reassign', methods=['POST'])
@login_required
@superadmin_required
def task_reassign(task_id):
    task = Task.query.get_or_404(task_id)
    new_owner_id = int(request.form.get('new_owner_id'))
    new_owner = User.query.get_or_404(new_owner_id)

    old_owner = task.owner
    task.owner_id = new_owner_id

    create_notification(new_owner_id, 'task_assigned',
                    f'Task "{task.title}" has been assigned to you.',
                    'task', task_id)

    db.session.add(Comment(task_id=task_id, user_id=current_user.id,
                    content=f"Reassigned from {old_owner.name if old_owner else 'unassigned'} to {new_owner.name}.",
                    is_system=True))
    db.session.commit()

    flash(f'Task reassigned to {new_owner.name}.', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/comment', methods=['POST'])
@login_required
def task_comment(task_id):
    task = Task.query.get_or_404(task_id)
    acting = get_acting_user()
    content = request.form.get('content', '').strip()

    if not content:
        flash('Comment cannot be empty.', 'warning')
        return redirect(url_for('task_detail', task_id=task_id))

    comment = Comment(task_id=task_id, user_id=acting.id, content=content)
    db.session.add(comment)

    # Check for @mentions
    for user in User.query.all():
        if f'@{user.name.lower()}' in content.lower() or f'@{user.name.split()[0].lower()}' in content.lower():
            if user.id != acting.id:
                create_notification(user.id, 'mention',
                    f'{acting.name} mentioned you in {task.title}: "{content[:100]}"',
                    'task', task_id)

    db.session.commit()
    return redirect(url_for('task_detail', task_id=task_id))


# ====
# HELP / FLAG ROUTES
# ====

@app.route('/task/<int:task_id>/flag-help', methods=['POST'])
@login_required
def flag_help(task_id):
    task = Task.query.get_or_404(task_id)
    acting = get_acting_user()
    helper_id = int(request.form.get('helper_id'))
    message = request.form.get('message', '')

    hr = HelpRequest(requester_id=acting.id, helper_id=helper_id,
                    task_id=task_id, message=message)
    db.session.add(hr)

    helper = User.query.get(helper_id)
    create_notification(helper_id, 'help_request',
                    f'{acting.name} needs your help with: {task.title}. "{message}"',
                    'task', task_id)

    db.session.add(Comment(task_id=task_id, user_id=acting.id,
                    content=f"{acting.name} flagged {helper.name} for help: {message}",
                    is_system=True))
    db.session.commit()

    notify_help_request(acting.name, helper.name, task.title)
    flash(f'Help request sent to {helper.name}!', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/task/<int:task_id>/offer-help', methods=['POST'])
@login_required
def offer_help(task_id):
    task = Task.query.get_or_404(task_id)
    acting = get_acting_user()
    message = request.form.get('message', 'I can help with this task.')

    hr = HelpRequest(requester_id=task.owner_id, helper_id=acting.id,
                    task_id=task_id, message=f"[OFFER] {message}", status='pending')
    db.session.add(hr)

    if task.owner:
        create_notification(task.owner_id, 'help_offered',
                    f'{acting.name} offered to help with: {task.title}',
                    'task', task_id)

    db.session.commit()
    flash('Help offer sent!', 'success')
    return redirect(url_for('task_detail', task_id=task_id))


@app.route('/help-request/<int:hr_id>/<action>', methods=['POST'])
@login_required
def respond_help_request(hr_id, action):
    hr = HelpRequest.query.get_or_404(hr_id)
    acting = get_acting_user()

    if action == 'accept':
        hr.status = 'accepted'
        create_notification(hr.helper_id if hr.requester_id == acting.id else hr.requester_id,
                    'help_accepted', f'Help request accepted for: {hr.task.title}',
                    'task', hr.task_id)
        flash('Help request accepted!', 'success')
    elif action == 'decline':
        hr.status = 'declined'
        flash('Help request declined.', 'info')
    elif action == 'resolve':
        hr.status = 'resolved'
        helper = User.query.get(hr.helper_id)
        if helper:
            award_points(helper, hr.task, 'help_given')
        flash('Help request resolved! Points awarded.', 'success')

    db.session.commit()
    return redirect(url_for('task_detail', task_id=hr.task_id))


# ====
# FILE ROUTES
# ====

@app.route('/files')
@login_required
def file_library():
    search = request.args.get('search', '')
    task_filter = request.args.get('task_id', '')

    query = File.query
    if search:
        query = query.filter(File.original_filename.ilike(f'%{search}%'))
    if task_filter:
        query = query.filter_by(task_id=int(task_filter))

    files = query.order_by(File.created_at.desc()).all()
    tasks = Task.query.all()
    return render_template('files.html', files=files, tasks=tasks,
                    search=search, task_filter=task_filter)


@app.route('/files/upload', methods=['POST'])
@login_required
def upload_file():
    acting = get_acting_user()
    if 'file' not in request.files:
        flash('No file selected.', 'warning')
        return redirect(url_for('file_library'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('file_library'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        file_size = os.path.getsize(filepath)

        task_id = request.form.get('task_id') or None
        if task_id:
            task_id = int(task_id)

        f = File(filename=unique_name, filepath=filepath,
                 original_filename=filename, task_id=task_id,
                 uploaded_by=acting.id, file_size=file_size,
                 description=request.form.get('description', ''))
        db.session.add(f)
        award_points(acting, Task.query.get(task_id) if task_id else None, 'document_uploaded')
        db.session.commit()

        flash(f'File "{filename}" uploaded successfully!', 'success')
    else:
        flash('File type not allowed.', 'error')

    return redirect(url_for('file_library'))


@app.route('/files/download/<int:file_id>')
@login_required
def download_file(file_id):
    f = File.query.get_or_404(file_id)
    directory = os.path.dirname(f.filepath)
    return send_from_directory(directory, os.path.basename(f.filepath),
                    as_attachment=True, download_name=f.original_filename)


# ====
# NOTIFICATIONS
# ====

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()).limit(50).all()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if n.user_id == current_user.id:
        n.read = True
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    return jsonify({'ok': True})


# ====
# ADMIN / SUPERADMIN ROUTES
# ====

@app.route('/admin')
@login_required
@superadmin_required
def admin_panel():
    users = User.query.all()
    pending_faqs = FAQ.query.filter_by(approved=False).all()
    access_requests = AccessRequest.query.filter_by(status='pending').all()
    return render_template('admin.html', users=users,
                    pending_faqs=pending_faqs,
                    access_requests=access_requests)


@app.route('/admin/clone/<int:user_id>', methods=['POST'])
@login_required
@superadmin_required
def clone_user(user_id):
    user = User.query.get_or_404(user_id)
    session['clone_user_id'] = user_id
    flash(f'Now acting as {user.name}. You see what they see.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/admin/unclone', methods=['POST'])
@login_required
@superadmin_required
def unclone_user():
    session.pop('clone_user_id', None)
    flash('Returned to your own view.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/admin/announcement', methods=['POST'])
@login_required
@superadmin_required
def post_announcement():
    content = request.form.get('content', '').strip()
    if content:
        ann = Announcement(author_id=current_user.id, content=content)
        db.session.add(ann)

        # Notify all users
        for user in User.query.all():
            if user.id != current_user.id:
                create_notification(user.id, 'announcement', content)

        db.session.commit()
        notify_announcement(current_user.name, content)
        flash('Announcement posted!', 'success')

    return redirect(url_for('dashboard'))


@app.route('/admin/add-user', methods=['POST'])
@login_required
@superadmin_required
def add_user():
    email = request.form.get('email', '').strip().lower()
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'user')
    password = request.form.get('password', 'changeme123')

    if User.query.filter_by(email=email).first():
        flash('User with that email already exists.', 'error')
        return redirect(url_for('admin_panel'))

    user = User(email=email, name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f'User {name} ({email}) created with password: {password}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/run-priorities', methods=['POST'])
@login_required
@superadmin_required
def manual_priority_run():
    result = run_priority_engine(app)
    formatted = format_priorities_for_slack(result)
    post_priority_update(formatted)
    flash('Priority engine ran successfully!', 'success')
    return redirect(url_for('dashboard'))


# ====
# HELP / FAQ ROUTES
# ====

@app.route('/help')
@login_required
def help_page():
    faqs = FAQ.query.filter_by(approved=True).order_by(FAQ.category, FAQ.created_at).all()
    categories = list(set(f.category for f in faqs))
    return render_template('help.html', faqs=faqs, categories=categories)


@app.route('/help/submit-faq', methods=['POST'])
@login_required
def submit_faq():
    acting = get_acting_user()
    question = request.form.get('question', '').strip()
    category = request.form.get('category', 'general')

    if question:
        faq = FAQ(question=question, category=category, submitted_by=acting.id)
        db.session.add(faq)
        db.session.commit()

        # Notify superadmins
        for admin in User.query.filter_by(role='superadmin').all():
            create_notification(admin.id, 'faq_submitted',
                    f'{acting.name} submitted a new FAQ: "{question[:100]}"')

        flash('FAQ submitted for review!', 'success')

    return redirect(url_for('help_page'))


@app.route('/admin/faq/<int:faq_id>/approve', methods=['POST'])
@login_required
@superadmin_required
def approve_faq(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    faq.approved = True
    faq.approved_by = current_user.id
    faq.answer = request.form.get('answer', '')

    # Award points to submitter
    submitter = User.query.get(faq.submitted_by)
    if submitter:
        award_points(submitter, None, 'faq_approved')

    db.session.commit()
    flash('FAQ approved and published!', 'success')
    return redirect(url_for('admin_panel'))


# ====
# ACCESS REQUESTS
# ====

@app.route('/request-access', methods=['POST'])
@login_required
def request_access():
    acting = get_acting_user()
    resource_type = request.form.get('resource_type', '')
    resource_id = request.form.get('resource_id')
    reason = request.form.get('reason', '')

    ar = AccessRequest(user_id=acting.id, resource_type=resource_type,
                    resource_id=int(resource_id) if resource_id else None,
                    reason=reason)
    db.session.add(ar)
    db.session.commit()

    for admin in User.query.filter_by(role='superadmin').all():
        create_notification(admin.id, 'access_request',
                    f'{acting.name} requested access to {resource_type}: {reason}')

    flash('Access request submitted!', 'info')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/admin/access-request/<int:ar_id>/<action>', methods=['POST'])
@login_required
@superadmin_required
def handle_access_request(ar_id, action):
    ar = AccessRequest.query.get_or_404(ar_id)
    ar.status = 'approved' if action == 'approve' else 'denied'
    ar.reviewed_by = current_user.id

    create_notification(ar.user_id, 'access_response',
                    f'Your access request was {ar.status}.')
    db.session.commit()

    flash(f'Access request {ar.status}.', 'success')
    return redirect(url_for('admin_panel'))


# ====
# API ENDPOINTS (for external cron / Slack bot)
# ====

@app.route('/api/run-priority-engine', methods=['POST'])
def api_run_priorities():
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {app.config['SECRET_KEY']}":
        return jsonify({'error': 'unauthorized'}), 401

    result = run_priority_engine(app)
    formatted = format_priorities_for_slack(result)
    post_priority_update(formatted)
    return jsonify({'ok': True, 'global_count': len(result['global'])})


@app.route('/api/status', methods=['GET'])
def api_status():
    """Public status endpoint for Slack bot."""
    with app.app_context():
        integrity = calculate_data_integrity_score()
        total = Task.query.count()
        completed = Task.query.filter(Task.status.in_(['verified', 'closed'])).count()
        return jsonify({
            'integrity_score': integrity['total'],
            'tasks_total': total,
            'tasks_completed': completed,
            'tasks_remaining': total - completed,
            'deadline': '2026-02-20'
        })


# ====
# MAIN
# ====

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=8000, debug=False)
