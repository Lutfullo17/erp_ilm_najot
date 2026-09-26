from django.apps import AppConfig


class ErpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'erp'

    def ready(self):
        """Django ishga tushganda scheduler ni ishga tushirish."""
        import os
        import sys
        import logging
        logger = logging.getLogger(__name__)

        # Scheduler faqat web-server jarayonida ishga tushadi: migrate, shell, sync_balances,
        # run_scheduler kabi boshqa manage.py buyruqlarida emas.
        if os.environ.get('DISABLE_WEB_SCHEDULER') == 'True':
            return
        argv = ' '.join(sys.argv)
        if 'test' in sys.argv or 'pytest' in argv:
            return
        is_manage = os.path.basename(sys.argv[0]) in ('manage.py', 'django-admin', 'django-admin.py')
        if is_manage and (len(sys.argv) < 2 or sys.argv[1] != 'runserver'):
            return
        if is_manage and os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in argv:
            return  # runserver autoreload'ning kuzatuvchi jarayoni

        try:
            from .scheduler import start
            start()
        except Exception as e:
            logger.error(f"APScheduler ishga tushirishda xatolik: {e}", exc_info=True)
