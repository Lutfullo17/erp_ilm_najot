from django.apps import AppConfig


class ErpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'erp'

    def ready(self):
        """Django ishga tushganda scheduler ni ishga tushirish."""
        import os
        # Faqat asosiy ish jarayonida (worker emas) scheduler ni ishga tushiramiz
        # RUN_MAIN=true — bu Django dev server reload da qayta ishga tushmaslik uchun
        if os.environ.get('RUN_MAIN', 'false') == 'true' or not os.environ.get('WERKZEUG_RUN_MAIN'):
            try:
                from .scheduler import start
                start()
            except Exception:
                pass
