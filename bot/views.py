import json

from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_update


def index(request):
    return HttpResponse('Bot app')


@csrf_exempt
@require_POST
def telegram_webhook(request):
    if settings.TELEGRAM_WEBHOOK_SECRET:
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != settings.TELEGRAM_WEBHOOK_SECRET:
            return JsonResponse({'detail': 'Forbidden'}, status=403)

    try:
        update = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    handle_update(update)
    return JsonResponse({'ok': True})
