from django.apps import AppConfig


class GradesConfig(AppConfig):
    name = 'grades'

    def ready(self):
        import grades.signals
