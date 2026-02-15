"""
RMG Mission Control — Slack Integration
Handles posting to Slack channel. Falls back gracefully if not configured.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Will be None if slack_sdk not installed or not configured
slack_client = None
slack_channel = None
slack_webhook = None


def init_slack(app):
    """Initialize Slack client from environment variables."""
    global slack_client, slack_channel, slack_webhook

    token = os.environ.get('SLACK_BOT_TOKEN')
    slack_channel = os.environ.get('SLACK_CHANNEL_ID')
    slack_webhook = os.environ.get('SLACK_WEBHOOK_URL')

    if token:
        try:
            from slack_sdk import WebClient
            slack_client = WebClient(token=token)
            logger.info("Slack integration initialized successfully")
        except ImportError:
            logger.warning("slack_sdk not installed. Slack integration disabled.")
        except Exception as e:
            logger.warning(f"Slack init failed: {e}")
    else:
        logger.info("SLACK_BOT_TOKEN not set. Slack integration disabled.")


def post_to_slack(message, blocks=None):
    """Post a message to the configured Slack channel."""
    if not slack_client or not slack_channel:
        logger.debug(f"Slack not configured. Would have posted: {message[:100]}...")
        return False

    try:
        result = slack_client.chat_postMessage(
            channel=slack_channel,
            text=message,
            blocks=blocks
        )
        return result.get('ok', False)
    except Exception as e:
        logger.error(f"Slack post failed: {e}")
        return False


def post_webhook(message):
    """Post via incoming webhook (simpler, no bot token needed)."""
    if not slack_webhook:
        return False

    try:
        import json
        import urllib.request
        data = json.dumps({'text': message}).encode('utf-8')
        req = urllib.request.Request(slack_webhook, data=data,
                    headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        logger.error(f"Slack webhook failed: {e}")
        return False


def notify_task_completed(user_name, task_title):
    """Notify Slack when a task is completed."""
    msg = f":white_check_mark: *{user_name}* completed: _{task_title}_"
    return post_to_slack(msg) or post_webhook(msg)


def notify_task_unblocked(task_title, unblocked_tasks):
    """Notify Slack when a task is unblocked."""
    unblocked_names = ', '.join(unblocked_tasks)
    msg = f":unlock: *{task_title}* completed — now unblocked: _{unblocked_names}_"
    return post_to_slack(msg) or post_webhook(msg)


def notify_help_request(requester_name, helper_name, task_title):
    """Notify Slack about a help request."""
    msg = f":sos: *{requester_name}* is requesting help from *{helper_name}* on: _{task_title}_"
    return post_to_slack(msg) or post_webhook(msg)


def notify_announcement(author_name, content):
    """Post an announcement to Slack."""
    msg = f":mega: *Announcement from {author_name}:*\n{content}"
    return post_to_slack(msg) or post_webhook(msg)


def post_priority_update(formatted_message):
    """Post the 6-hour priority update to Slack."""
    return post_to_slack(formatted_message) or post_webhook(formatted_message)


def notify_deadline_warning(hours_remaining, task_count):
    """Post deadline warning to Slack."""
    msg = f":warning: *{hours_remaining} hours until VA submission deadline!* {task_count} tasks still open."
    return post_to_slack(msg) or post_webhook(msg)


def notify_leaderboard_change(user_name, new_rank):
    """Post when leaderboard rankings change."""
    msg = f":trophy: *{user_name}* moved to rank #{new_rank} on the leaderboard!"
    return post_to_slack(msg) or post_webhook(msg)


def notify_streak(user_name, streak_days):
    """Post when someone hits a streak milestone."""
    msg = f":fire: *{user_name}* is on a {streak_days}-day streak!"
    return post_to_slack(msg) or post_webhook(msg)
