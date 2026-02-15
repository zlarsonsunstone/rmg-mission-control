"""
RMG Mission Control — Database Initialization & Seed Script
Run this once to create all tables and seed users + tasks.
Usage: python init_db.py
"""
from datetime import datetime, timezone
from app import app
from models import db, User, Task, FAQ, task_dependencies

def seed_database():
    with app.app_context():
        db.create_all()
        print("Tables created.")

        # Check if already seeded
        if User.query.first():
            print("Database already seeded. Skipping.")
            return

        # ==== USERS ====
        users_data = [
            {'email': 'jonathan@rencoman.com', 'name': 'Jonathan Sweetser', 'role': 'superadmin', 'password': 'mission2026'},
            {'email': 'zack@rencoman.com', 'name': 'Zack Larson', 'role': 'superadmin', 'password': 'mission2026'},
            {'email': 'glen@rencoman.com', 'name': 'Glen Jackson', 'role': 'user', 'password': 'changeme123'},
            {'email': 'jon@rencoman.com', 'name': 'Jon Anderson', 'role': 'user', 'password': 'changeme123'},
            {'email': 'richren@rencogloves.com', 'name': 'Rich Renehan', 'role': 'user', 'password': 'changeme123'},
            {'email': 'rtillotson@appgloves.com', 'name': 'Rick Tillotson', 'role': 'user', 'password': 'changeme123'},
        ]

        users = {}
        for u in users_data:
            user = User(email=u['email'], name=u['name'], role=u['role'])
            user.set_password(u['password'])
            db.session.add(user)
            users[u['email']] = user

        db.session.flush()  # Get IDs assigned
        print(f"Created {len(users)} users.")

        # ==== TASKS ====
        due_critical = datetime(2026, 2, 16, 23, 59, tzinfo=timezone.utc)
        due_high = datetime(2026, 2, 16, 23, 59, tzinfo=timezone.utc)
        due_medium = datetime(2026, 2, 17, 23, 59, tzinfo=timezone.utc)
        due_low = datetime(2026, 2, 16, 23, 59, tzinfo=timezone.utc)

        tasks_data = [
            # CRITICAL
            {'num': 1, 'title': 'Historical Output by SKU (Feb 25-Jan 26)',
             'desc': 'Provide exact case counts by product/SKU for the 12-month period February 2025 through January 2026. Source: APP plant production records.',
             'loc': 'Data Tab, Col H (all rows)', 'priority': 'critical',
             'owner': 'rtillotson@appgloves.com', 'due': due_critical, 'integrity': 8, 'deps': []},
            {'num': 2, 'title': 'Surge Capacity % (validated)',
             'desc': 'Validate the surge capacity percentage based on actual production data. Currently shows 15% sample — needs ops confirmation.',
             'loc': 'Data Col J / Capability Row 25', 'priority': 'critical',
             'owner': 'rtillotson@appgloves.com', 'due': due_critical, 'integrity': 5, 'deps': [1]},
            {'num': 3, 'title': 'Future Expansion % (validated)',
             'desc': 'Executive decision on future expansion percentage. Currently shows 5% sample — needs confirmed percentage from Glen.',
             'loc': 'Data Col L / Capability Row 11', 'priority': 'critical',
             'owner': 'glen@rencoman.com', 'due': due_critical, 'integrity': 3, 'deps': []},
            {'num': 4, 'title': 'All Contract Numbers',
             'desc': 'Pull contract numbers for all 7 known government contracts (DPA Title III, Air Force, DLA, DHS, VA, State Dept). Source: Renco Corp/APP historical records.',
             'loc': 'Contract Data, Col B', 'priority': 'critical',
             'owner': 'richren@rencogloves.com', 'due': due_critical, 'integrity': 5, 'deps': []},
            {'num': 5, 'title': 'Agency POC Names/Phone/Email',
             'desc': 'Provide agency point-of-contact details for each government contract. Depends on contract numbers being identified first.',
             'loc': 'Contract Data, Cols E-G', 'priority': 'critical',
             'owner': 'richren@rencogloves.com', 'due': due_critical, 'integrity': 4, 'deps': [4]},

            # HIGH
            {'num': 6, 'title': 'Delivery Lead Times by Region',
             'desc': 'Document standard delivery lead times broken down by geographic region (CONUS). Include 53-ft trailer logistics.',
             'loc': 'Capability, Row 23', 'priority': 'high',
             'owner': 'zack@rencoman.com', 'due': due_high, 'integrity': 4, 'deps': []},
            {'num': 7, 'title': 'Expedited Delivery Capability',
             'desc': 'Define expedited delivery options, timelines, and any additional costs. Depends on standard lead times being established.',
             'loc': 'Capability, Row 24', 'priority': 'high',
             'owner': 'zack@rencoman.com', 'due': due_high, 'integrity': 3, 'deps': [6]},
            {'num': 8, 'title': 'Geographic Limitations',
             'desc': 'Document any geographic limitations on delivery (CONUS only? Alaska/Hawaii? OCONUS?)',
             'loc': 'Capability, Row 26', 'priority': 'high',
             'owner': 'zack@rencoman.com', 'due': due_high, 'integrity': 3, 'deps': []},
            {'num': 9, 'title': 'Recall/Stop-Ship Procedures',
             'desc': 'Provide QA standard operating procedures for product recall and stop-ship scenarios.',
             'loc': 'Capability, Row 30', 'priority': 'high',
             'owner': 'rtillotson@appgloves.com', 'due': due_high, 'integrity': 3, 'deps': []},
            {'num': 10, 'title': 'Credit/Replacement Timeline',
             'desc': 'Document the process and timeline for issuing credits or replacements for defective products.',
             'loc': 'Capability, Row 31', 'priority': 'high',
             'owner': 'jon@rencoman.com', 'due': due_high, 'integrity': 2, 'deps': []},
            {'num': 11, 'title': 'Delivery Tracking Process Detail',
             'desc': 'Describe the delivery tracking process including EDI capabilities, carrier tracking integration, and customer visibility.',
             'loc': 'Capability, Row 19', 'priority': 'high',
             'owner': 'zack@rencoman.com', 'due': due_high, 'integrity': 3, 'deps': []},

            # MEDIUM
            {'num': 12, 'title': 'Adverse Events (CPARS, liens)',
             'desc': 'Disclosure of any adverse events including CPARS ratings, liens, or legal issues. Requires Steptoe legal review before finalization.',
             'loc': 'Capability, Row 35', 'priority': 'medium',
             'owner': 'glen@rencoman.com', 'due': due_medium, 'integrity': 2, 'deps': []},
            {'num': 13, 'title': 'Financials Willingness',
             'desc': 'Executive decision on willingness to provide financial information to VA if requested.',
             'loc': 'Capability, Row 36', 'priority': 'medium',
             'owner': 'glen@rencoman.com', 'due': due_medium, 'integrity': 2, 'deps': []},
            {'num': 14, 'title': '3rd-Party Testing Frequency',
             'desc': 'Document frequency and scope of third-party testing (SGS, Toxikon, etc.) for nitrile glove products.',
             'loc': 'Capability, Row 32', 'priority': 'medium',
             'owner': 'rtillotson@appgloves.com', 'due': due_medium, 'integrity': 3, 'deps': []},
            {'num': 15, 'title': 'DCMA Inspection Details',
             'desc': 'Provide details on DCMA inspection history, current status, and scope at APP/Colebrook facility.',
             'loc': 'Capability, Row 34', 'priority': 'medium',
             'owner': 'richren@rencogloves.com', 'due': due_medium, 'integrity': 3, 'deps': []},

            # LOW
            {'num': 16, 'title': 'Period of Performance Details',
             'desc': 'Provide exact start and end dates for all government contracts. Depends on contract numbers.',
             'loc': 'Contract Data, Col J', 'priority': 'low',
             'owner': 'richren@rencogloves.com', 'due': due_low, 'integrity': 2, 'deps': [4]},
            {'num': 17, 'title': 'Prime Contractor (if subK)',
             'desc': 'Identify if RMG/APP was prime or sub on each contract. If sub, identify the prime contractor.',
             'loc': 'Contract Data, Col H', 'priority': 'low',
             'owner': 'richren@rencogloves.com', 'due': due_low, 'integrity': 1, 'deps': [4]},
        ]

        task_objects = {}
        for t in tasks_data:
            task = Task(
                task_number=t['num'],
                title=t['title'],
                description=t['desc'],
                spreadsheet_location=t['loc'],
                priority=t['priority'],
                owner_id=users[t['owner']].id,
                due_date=t['due'],
                points_value=t.get('points', {'critical': 100, 'high': 75, 'medium': 50, 'low': 25}[t['priority']]),
                integrity_impact=t['integrity']
            )
            db.session.add(task)
            task_objects[t['num']] = (task, t['deps'])

        db.session.flush()  # Get task IDs

        # Set dependencies
        for num, (task, deps) in task_objects.items():
            for dep_num in deps:
                dep_task = task_objects[dep_num][0]
                task.dependencies.append(dep_task)

        print(f"Created {len(task_objects)} tasks with dependencies.")

        # ==== SEED FAQs ====
        faqs_data = [
            {'q': 'How do I log in?', 'a': 'Navigate to the app URL, enter your email and password, then click Log In. First-time users complete a character creation step.', 'cat': 'general'},
            {'q': 'How do I reset my password?', 'a': 'Click Forgot Password on the login screen, enter your email, and follow the reset link sent to your inbox.', 'cat': 'general'},
            {'q': 'How do I see the entire team\'s project?', 'a': 'Click "Global View" in the view toggle at the top of your dashboard.', 'cat': 'general'},
            {'q': 'How do I see just my responsibilities?', 'a': 'Click "My Dashboard" in the view toggle. Enable Focus Mode for distraction-free view.', 'cat': 'tasks'},
            {'q': 'How do I upload documents?', 'a': 'Open a task and click Upload, or go to the Files section and use the Upload button. Drag-and-drop is supported.', 'cat': 'files'},
            {'q': 'How do I mark a task complete?', 'a': 'Open your task, click "Submit Deliverable," attach your work, add notes, and click Submit. A SuperAdmin will verify.', 'cat': 'tasks'},
            {'q': 'How do I see what I should be working on?', 'a': 'Check your Top Priorities at the top of your Individual Dashboard. These update every 6 hours.', 'cat': 'tasks'},
            {'q': 'How do I flag someone for help?', 'a': 'Open your task, click "Flag for Help," select the teammate, and describe what you need.', 'cat': 'communication'},
            {'q': 'How does the points system work?', 'a': 'Points are earned for task completion (25-100 based on priority), early delivery (1.5x), quality (90+ = +25), and helping teammates (+15). Late = 0.5x, revisions = -10 each.', 'cat': 'points'},
            {'q': 'What is Focus Mode?', 'a': 'Focus Mode hides the leaderboard, activity feed, and announcements — showing only your tasks and priorities. Toggle it from your Individual Dashboard.', 'cat': 'general'},
        ]

        admin = users['jonathan@rencoman.com']
        for f in faqs_data:
            faq = FAQ(question=f['q'], answer=f['a'], category=f['cat'],
                    submitted_by=admin.id, approved_by=admin.id, approved=True)
            db.session.add(faq)

        print(f"Created {len(faqs_data)} FAQs.")

        db.session.commit()
        print("\nDatabase seeded successfully!")
        print("\n--- Login Credentials ---")
        for u in users_data:
            print(f"  {u['name']:25s} | {u['email']:30s} | {u['password']}")
        print(f"\nSuperAdmins: Jonathan Sweetser, Zack Larson")
        print(f"Standard Users: Glen Jackson, Jon Anderson, Rich Renehan, Rick Tillotson")


if __name__ == '__main__':
    seed_database()
