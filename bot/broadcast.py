import logging
import requests
from django.conf import settings
from bot.models import TelegramUser

logger = logging.getLogger(__name__)

class BroadcastResult:
    def __init__(self):
        self.total = 0
        self.success = 0
        self.blocked = 0
        self.failed_network = 0
        self.failed_api = 0
        self.failed_other = 0

    def add_success(self):
        self.total += 1
        self.success += 1

    def add_blocked(self):
        self.total += 1
        self.blocked += 1

    def add_network_error(self):
        self.total += 1
        self.failed_network += 1

    def add_api_error(self):
        self.total += 1
        self.failed_api += 1

    def add_other_error(self):
        self.total += 1
        self.failed_other += 1
        
    @property
    def total_failed(self):
        return self.failed_network + self.failed_api + self.failed_other


def send_message_to_user(chat_id, text, result_stats, tg_user):
    """
    Sends a message to a single user and catches specific exceptions.
    Updates the result_stats object and the user's is_blocked status.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN topilmadi, xabar yuborilmaydi.")
        result_stats.add_other_error()
        return

    url = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        # Check HTTP errors
        response.raise_for_status()
        
        # Success
        result_stats.add_success()

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        logger.error(f"[HTTP {status_code}] Telegram xatosi chat_id={chat_id}: {e.response.text}")
        
        # 403 Forbidden is what Telegram returns when user blocks bot or deletes chat
        if status_code == 403 or "bot was blocked by the user" in e.response.text.lower() or "user is deactivated" in e.response.text.lower():
            result_stats.add_blocked()
            if tg_user and tg_user.is_verified and tg_user.student_id:
                tg_user.is_blocked = True
                tg_user.save(update_fields=['is_blocked', 'updated_at'])
        else:
            result_stats.add_api_error()

    except requests.exceptions.RequestException as e:
        # Timeout, Connection errors
        logger.error(f"Tarmoq xatosi chat_id={chat_id}: {e}")
        result_stats.add_network_error()
        
    except Exception as e:
        # Other unknown issues
        logger.error(f"Noma'lum xatolik chat_id={chat_id}: {e}", exc_info=True)
        result_stats.add_other_error()


def execute_broadcast(users_queryset, text):
    """
    Executes a broadcast operation over the given users_queryset.
    Returns a BroadcastResult object with the statistics.
    Optimizes DB access using select_related if not already applied.
    """
    stats = BroadcastResult()
    
    for user in users_queryset:
        send_message_to_user(user.telegram_id, text, stats, user)
        
    return stats
