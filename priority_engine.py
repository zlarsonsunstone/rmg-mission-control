"""
RMG Mission Control — Priority Engine
Runs every 6 hours to re-assess project priorities.
"""
from datetime import datetime, timezone
from models import db, Task, Priority, User, Notification


def calculate_task_urgency(task, deadline_date):
    """Calculate urgency score for a single task."""
    if task.status in ('verified', 'closed'):
        return 0

    now = datetime.now(timezone.utc)
    if task.due_date:
        days_remaining = (task.due_date - now).total_seconds() / 86400
    else:
        days_remaining = (deadline_date - now).total_seconds() / 86400

    # Deadline pressure (exponential as deadline approaches)
    if days_remaining <= 0:
        deadline_penalty = 10  # overdue
    elif days_remaining <= 1:
        deadline_penalty = 8
    elif days_remaining <= 2:
        deadline_penalty = 5
    elif days_remaining <= 3:
        deadline_penalty = 3
    else:
        deadline_penalty = 1

    # Priority weight
    priority_weight = task.priority_weight

    # Dependency chain impact (how many tasks are waiting on this one)
    downstream_count = len([d for d in task.dependents if d.status not in ('verified', 'closed')])
    dependency_impact = 1 + (downstream_count * 0.5)

    # Integrity score impact
    integrity_factor = 1 + (task.integrity_impact / 20)

    # Blocked penalty (blocked tasks get lower priority since they can't be worked on)
    if task.is_blocked:
        blocked_penalty = 0.1
    else:
        blocked_penalty = 1

    # Status adjustment (in_progress gets slight boost, not_started gets urgency)
    status_factor = 1.0
    if task.status == 'in_progress':
        status_factor = 1.2
    elif task.status == 'submitted':
        status_factor = 0.5  # already submitted, lower urgency

    score = deadline_penalty * priority_weight * dependency_impact * integrity_factor * blocked_penalty * status_factor

    return round(score, 2)


def generate_task_summary(task):
    """Generate natural-language priority summary for a task."""
    parts = [f"{task.title} ({task.owner.name if task.owner else 'Unassigned'})"]

    if task.is_blocked:
        blockers = [t.title for t in task.blocking_tasks]
        parts.append(f"BLOCKED by: {', '.join(blockers)}")
    else:
        downstream = [d for d in task.dependents if d.status not in ('verified', 'closed')]
        if downstream:
            parts.append(f"{len(downstream)} task(s) waiting on this")

        if task.integrity_impact > 0:
            parts.append(f"+{task.integrity_impact} integrity points")

        if task.status == 'not_started':
            parts.append("Not yet started")
        elif task.status == 'in_progress':
            parts.append("In progress")
        elif task.status == 'submitted':
            parts.append("Awaiting verification")

    return " | ".join(parts)


def run_priority_engine(app, deadline_str='2026-02-20'):
    """Run the full priority re-assessment cycle."""
    with app.app_context():
        deadline_date = datetime.strptime(deadline_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        # Get all open tasks
        open_tasks = Task.query.filter(Task.status.notin_(['verified', 'closed'])).all()
        if not open_tasks:
            return {'global': [], 'users': {}}

        # Calculate scores
        scored_tasks = []
        for task in open_tasks:
            score = calculate_task_urgency(task, deadline_date)
            scored_tasks.append((task, score))

        # Sort by score descending
        scored_tasks.sort(key=lambda x: x[1], reverse=True)

        # Clear previous priorities
        Priority.query.delete()

        # Global Top 5
        global_priorities = []
        for rank, (task, score) in enumerate(scored_tasks[:5], 1):
            summary = generate_task_summary(task)
            p = Priority(
                cycle_timestamp=now,
                scope='global',
                rank=rank,
                task_id=task.id,
                score=score,
                summary=summary
            )
            db.session.add(p)
            global_priorities.append({
                'rank': rank,
                'task_id': task.id,
                'task_title': task.title,
                'owner': task.owner.name if task.owner else 'Unassigned',
                'score': score,
                'summary': summary
            })

        # Individual Top 3-5 per user
        users = User.query.all()
        user_priorities = {}

        for user in users:
            user_tasks = [(t, s) for t, s in scored_tasks if t.owner_id == user.id]
            user_top = user_tasks[:5]
            user_priorities[user.id] = []

            for rank, (task, score) in enumerate(user_top, 1):
                summary = generate_task_summary(task)
                p = Priority(
                    cycle_timestamp=now,
                    scope='user',
                    user_id=user.id,
                    rank=rank,
                    task_id=task.id,
                    score=score,
                    summary=summary
                )
                db.session.add(p)
                user_priorities[user.id].append({
                    'rank': rank,
                    'task_id': task.id,
                    'task_title': task.title,
                    'score': score,
                    'summary': summary
                })

            # Create notification for each user with priorities
            if user_top:
                lines = [f"{r+1}. {t.title}" for r, (t, s) in enumerate(user_top)]
                notif = Notification(
                    user_id=user.id,
                    type='priority_update',
                    content=f"Your updated priorities:\n" + "\n".join(lines),
                )
                db.session.add(notif)

        db.session.commit()

        return {'global': global_priorities, 'users': user_priorities}


def format_priorities_for_slack(priorities):
    """Format priority data for Slack message."""
    lines = ["*RMG Mission Control — Priority Update*\n"]
    lines.append("*Top 5 Global Priorities:*")

    for p in priorities.get('global', []):
        emoji = {1: ':one:', 2: ':two:', 3: ':three:', 4: ':four:', 5: ':five:'}.get(p['rank'], ':small_blue_diamond:')
        lines.append(f"{emoji} {p['task_title']} ({p['owner']}) — {p['summary']}")

    lines.append("\n*Individual Priorities:*")
    for user_id, user_tasks in priorities.get('users', {}).items():
        if user_tasks:
            user = User.query.get(user_id)
            if user:
                lines.append(f"\n_{user.name}:_")
                for p in user_tasks[:3]:
                    lines.append(f"  {p['rank']}. {p['task_title']}")

    return "\n".join(lines)
