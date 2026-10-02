import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_update
from .utils import scrub

logger = logging.getLogger(__name__)


def index(request):
    return HttpResponse('Bot app')


@csrf_exempt
@require_POST
def telegram_webhook(request):
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected:
        # Sirsiz webhook hamma uchun ochiq bo'lardi.
        return JsonResponse({'detail': 'Webhook sozlanmagan'}, status=503)
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not hmac.compare_digest(secret.encode(), expected.encode()):
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    try:
        update = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    try:
        handle_update(update)
    except Exception as exc:
        # 500 qaytarilsa Telegram xuddi shu update'ni qayta-qayta yuboradi.
        logger.error("Webhook update xatosi: %s", scrub(exc), exc_info=False)
    return JsonResponse({'ok': True})
