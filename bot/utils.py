from django.conf import settings


def scrub(value):
    """Xato matnidan bot tokenini olib tashlaydi (requests istisnosida URL bor)."""
    text = str(value)
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    return text.replace(token, '***') if token else text
