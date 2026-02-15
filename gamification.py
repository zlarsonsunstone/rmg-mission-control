"""
RMG Mission Control — Gamification Engine
Points, levels, quality scoring, and leaderboard.
"""
from datetime import datetime, timezone
from models import db, User, Task, PointsLog, Notification, Announcement

# Character classes with descriptions
CHARACTER_CLASSES = {
    'data_warden': {
        'name': 'Data Warden',
        'icon': 'shield-alt',
        'color': '#2E86AB',
        'description': 'Guardian of accuracy and records. You protect the integrity of every data point.',
        'ability': 'Data Shield — Can spot a misplaced decimal from three spreadsheets away.'
    },
    'science_specialist': {
        'name': 'Science Specialist',
        'icon': 'flask',
        'color': '#A23B72',
        'description': 'Deep technical and polymer expertise. The lab is your domain.',
        'ability': 'Molecular Insight — Understands nitrile at the atomic level.'
    },
    'communications_specialist': {
        'name': 'Communications Specialist',
        'icon': 'broadcast-tower',
        'color': '#F18F01',
        'description': 'Connects people and manages information flow. Nothing gets lost on your watch.',
        'ability': 'Signal Boost — Messages you send are 2x more likely to get a response.'
    },
    'operations_commander': {
        'name': 'Operations Commander',
        'icon': 'cogs',
        'color': '#C73E1D',
        'description': 'Logistics, distribution, and execution. You make things happen.',
        'ability': 'Chain of Command — Can coordinate three tasks simultaneously.'
    },
    'contract_sage': {
        'name': 'Contract Sage',
        'icon': 'scroll',
        'color': '#3B1F2B',
        'description': 'Knows the history, holds the records. The oracle of federal contracts.',
        'ability': 'Total Recall — Can summon contract numbers from memory.'
    },
    'executive_strategist': {
        'name': 'Executive Strategist',
        'icon': 'chess-king',
        'color': '#274690',
        'description': 'Big decisions, vision, direction. You see the whole board.',
        'ability': 'Strategic Vision — Decisions made have 1.5x impact on project direction.'
    },
    'legal_guardian': {
        'name': 'Legal Guardian',
        'icon': 'balance-scale',
        'color': '#4A5859',
        'description': 'Compliance, risk, and regulatory mastery. The law is your sword.',
        'ability': 'Compliance Aura — Nearby documents automatically become more defensible.'
    },
    'field_agent': {
        'name': 'Field Agent',
        'icon': 'binoculars',
        'color': '#2A9D8F',
        'description': 'External relationships, sales, and outreach. You open doors.',
        'ability': 'Network Effect — Every new contact unlocks hidden opportunities.'
    }
}

# Suggested class for each user based on their role
SUGGESTED_CLASSES = {
    'rtillotson@appgloves.com': 'data_warden',
    'richren@rencogloves.com': 'contract_sage',
    'glen@rencoman.com': 'executive_strategist',
    'zack@rencoman.com': 'operations_commander',
    'jon@rencoman.com': 'operations_commander',
    'jonathan@rencoman.com': 'communications_specialist',
}


def award_points(user, task, action, reason=None):
    """Award or deduct points for an action."""
    points = 0

    if action == 'task_completed_ontime':
        points = task.base_points
        reason = reason or f"Completed: {task.title}"
    elif action == 'task_completed_early':
        points = int(task.base_points * 1.5)
        reason = reason or f"Early completion: {task.title}"
    elif action == 'task_completed_late':
        points = int(task.base_points * 0.5)
        reason = reason or f"Late completion: {task.title}"
    elif action == 'quality_bonus':
        points = 25
        reason = reason or f"High quality (90+): {task.title}"
    elif action == 'perfect_submission':
        points = 50
        reason = reason or f"Perfect first-try: {task.title}"
    elif action == 'revision_penalty':
        points = -10
        reason = reason or f"Revision required: {task.title}"
    elif action == 'help_given':
        points = 15
        reason = reason or "Helped a teammate"
    elif action == 'first_task_today':
        points = 10
        reason = reason or "First task of the day"
    elif action == 'streak_bonus':
        points = 5
        reason = reason or f"Streak bonus (day {user.streak_days})"
    elif action == 'faq_approved':
        points = 10
        reason = reason or "FAQ contribution approved"
    elif action == 'document_uploaded':
        points = 5
        reason = reason or "Document uploaded"

    if points != 0:
        log = PointsLog(
            user_id=user.id,
            task_id=task.id if task else None,
            action=action,
            points=points,
            reason=reason
        )
        db.session.add(log)
        user.points += points
        user.update_level()
        db.session.commit()

    return points


def get_leaderboard():
    """Get sorted leaderboard data."""
    users = User.query.order_by(User.points.desc()).all()
    leaderboard = []

    for rank, user in enumerate(users, 1):
        completed_tasks = Task.query.filter_by(owner_id=user.id).filter(
            Task.status.in_(['verified', 'closed'])
        ).count()
        total_tasks = Task.query.filter_by(owner_id=user.id).count()

        # Calculate quality average
        verified_tasks = Task.query.filter_by(owner_id=user.id).filter(
            Task.quality_score.isnot(None)
        ).all()
        quality_avg = 0
        if verified_tasks:
            quality_avg = sum(t.quality_score for t in verified_tasks) / len(verified_tasks)

        char_class = CHARACTER_CLASSES.get(user.character_class, {})
        leaderboard.append({
            'rank': rank,
            'user': user,
            'name': user.name,
            'character_class': char_class.get('name', 'Unclassed'),
            'character_icon': char_class.get('icon', 'user'),
            'character_color': char_class.get('color', '#666'),
            'points': user.points,
            'level': user.level,
            'level_title': user.level_title,
            'completed_tasks': completed_tasks,
            'total_tasks': total_tasks,
            'quality_avg': round(quality_avg, 1),
            'streak': user.streak_days
        })

    return leaderboard


def calculate_data_integrity_score():
    """Calculate overall data integrity score based on task completion."""
    # Base score from existing data (per architecture doc)
    category_scores = {
        'product_specs': {'weight': 25, 'base': 95},       # Already documented
        'historical_output': {'weight': 20, 'base': 10},   # Critical gap
        'capability_mfg': {'weight': 15, 'base': 88},
        'distribution': {'weight': 10, 'base': 45},
        'quality_qasp': {'weight': 10, 'base': 60},
        'contract_data': {'weight': 10, 'base': 58},
        'poc_admin': {'weight': 10, 'base': 80},
    }

    # Task completion boosts
    task_category_map = {
        1: ('historical_output', 40),   # Historical Output by SKU → huge boost
        2: ('historical_output', 30),   # Surge Capacity
        3: ('poc_admin', 10),           # Future Expansion %
        4: ('contract_data', 15),       # Contract Numbers
        5: ('contract_data', 10),       # Agency POCs
        6: ('distribution', 15),        # Lead Times
        7: ('distribution', 10),        # Expedited Delivery
        8: ('distribution', 10),        # Geographic Limits
        9: ('quality_qasp', 10),        # Recall/Stop-Ship
        10: ('quality_qasp', 5),        # Credit/Replacement
        11: ('distribution', 10),       # Tracking Process
        12: ('poc_admin', 5),           # Adverse Events
        13: ('poc_admin', 5),           # Financials
        14: ('quality_qasp', 10),       # 3rd-Party Testing
        15: ('quality_qasp', 10),       # DCMA Inspection
        16: ('contract_data', 10),      # Period of Performance
        17: ('contract_data', 5),       # Prime Contractor
    }

    # Check which tasks are verified/completed
    for task_num, (category, boost) in task_category_map.items():
        task = Task.query.filter_by(task_number=task_num).first()
        if task and task.status in ('verified', 'closed'):
            current = category_scores[category]['base']
            category_scores[category]['base'] = min(100, current + boost)

    # Calculate weighted total
    total = 0
    details = []
    for cat, data in category_scores.items():
        weighted = data['weight'] * data['base'] / 100
        total += weighted
        details.append({
            'category': cat.replace('_', ' ').title(),
            'weight': data['weight'],
            'score': data['base'],
            'weighted': round(weighted, 2)
        })

    return {'total': round(total, 1), 'details': details}


def create_auto_announcement(content):
    """Create a system announcement."""
    # Use first superadmin as author
    admin = User.query.filter_by(role='superadmin').first()
    if admin:
        ann = Announcement(author_id=admin.id, content=content)
        db.session.add(ann)
        db.session.commit()
        return ann
    return None
