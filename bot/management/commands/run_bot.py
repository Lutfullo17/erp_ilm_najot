import time
import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from bot.services import handle_update

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Telegram botni polling rejimida ishga tushirish'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN topilmadi. .env faylini tekshiring.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Bot polling rejimida ishga tushirildi...'))

        # Webhookni o'chirish
        try:
            webhook_response = requests.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook")
            webhook_data = webhook_response.json()
            if webhook_data.get('ok'):
                self.stdout.write(self.style.SUCCESS("Webhook o'chirildi."))
            else:
                self.stdout.write(self.style.WARNING(f"Webhook o'chirishda xatolik: {webhook_data}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Webhook o'chirishda xatolik: {e}"))

        offset = 0
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"

        while True:
            try:
                logger.info(f"Polling with offset={offset}")
                response = requests.get(url, params={'offset': offset, 'timeout': 10})
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('result', [])
                    logger.info(f"Received {len(results)} updates")
                    for update in results:
                        offset = update['update_id'] + 1
                        logger.info(f"Processing update_id={update['update_id']}, type={list(update.keys())}")
                        try:
                            handle_update(update)
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'Update xatoligi: {e}'))
                            logger.error(f'Update xatoligi: {e}', exc_info=True)
                elif response.status_code == 409:
                    self.stdout.write(self.style.WARNING("Webhook faol. Polling uchun uni o'chirish kerak (deleteWebhook)."))
                    requests.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook")
                    self.stdout.write(self.style.SUCCESS("Webhook o'chirildi. Polling davom etadi..."))
                else:
                    self.stdout.write(self.style.ERROR(f'Xatolik: {response.status_code}'))
                    logger.error(f'Polling xatolik: {response.status_code}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ulanish xatoligi: {e}'))
                logger.error(f'Ulanish xatoligi: {e}', exc_info=True)

            time.sleep(1)
