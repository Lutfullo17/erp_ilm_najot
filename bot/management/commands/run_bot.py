import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from bot.services import handle_update

class Command(BaseCommand):
    help = 'Telegram botni polling rejimida ishga tushirish'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN topilmadi. .env faylini tekshiring.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Bot polling rejimida ishga tushirildi...'))
        
        offset = 0
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"

        while True:
            try:
                response = requests.get(url, params={'offset': offset, 'timeout': 30})
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get('result', []):
                        offset = update['update_id'] + 1
                        try:
                            handle_update(update)
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'Update xatoligi: {e}'))
                elif response.status_code == 409:
                    self.stdout.write(self.style.WARNING("Webhook faol. Polling uchun uni o'chirish kerak (deleteWebhook)."))
                    requests.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook")
                    self.stdout.write(self.style.SUCCESS("Webhook o'chirildi. Polling davom etadi..."))
                else:
                    self.stdout.write(self.style.ERROR(f'Xatolik: {response.status_code}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ulanish xatoligi: {e}'))
            
            time.sleep(1)
