import io
import uuid

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

MAX_PHOTO_BYTES = 2 * 1024 * 1024
_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}


def get_client_ip(request):
    if getattr(settings, 'TRUST_X_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def check_new_password(password, user=None):
    """Xato bo'lsa o'zbekcha matn qaytaradi, aks holda None."""
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return ' '.join(exc.messages)
    return None


def clean_profile_photo(upload):
    """Rasmni tekshiradi (hajm, haqiqiy rasm, JPEG/PNG/WEBP) va tasodifiy nomli ContentFile qaytaradi."""
    from PIL import Image, UnidentifiedImageError

    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError("Rasm hajmi 2 MB dan oshmasligi kerak.")
    data = upload.read()
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        fmt = image.format
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("Faqat rasm fayli (JPEG, PNG, WEBP) yuklash mumkin.")
    if fmt not in _FORMATS:
        raise ValidationError("Faqat JPEG, PNG yoki WEBP rasm yuklash mumkin.")
    return ContentFile(data, name=f"{uuid.uuid4().hex}.{_FORMATS[fmt]}")


LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 15 * 60


def _login_key(request, username):
    return f"login-fail:{get_client_ip(request)}:{(username or '').lower()}"


def login_locked(request, username):
    return cache.get(_login_key(request, username), 0) >= LOGIN_MAX_FAILS


def login_failed(request, username):
    key = _login_key(request, username)
    cache.add(key, 0, LOGIN_WINDOW)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, LOGIN_WINDOW)


def login_succeeded(request, username):
    cache.delete(_login_key(request, username))
