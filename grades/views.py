import json

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.utils import timezone

from .models import GradeSession
from .services import GradeInputError, get_grade_snapshot, get_teacher_groups, save_grades


class TeacherGradeListView(LoginRequiredMixin, ListView):
    template_name = 'grades/grade_list.html'
    context_object_name = 'grade_sessions'

    def get_queryset(self):
        return GradeSession.objects.filter(
            teacher=self.request.user
        ).order_by('-date')[:20]


def index(request):
    return HttpResponse('Grades app')


def teacher_api_required(view_func):
    def wrapped(request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if user is None or not hasattr(user, 'is_authenticated') or not hasattr(user, 'is_teacher'):
            return JsonResponse({'detail': 'Foydalanuvchi obyektida kerakli atributlar yo\'q.'}, status=401)
        if not user.is_authenticated:
            return JsonResponse({'detail': 'Login talab qilinadi.'}, status=401)
        if not user.is_teacher:
            return JsonResponse({'detail': "Faqat o'qituvchi uchun ruxsat bor."}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapped


def json_error(message, status=400):
    # Xatoliklarni logga yozish uchun (kelajakda log qo'shish mumkin)
    return JsonResponse({'detail': str(message)}, status=status)


def get_json_body(request):
    if not request.body:
        return {}

    try:
        return json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise GradeInputError("JSON ma'lumot noto'g'ri yoki UTF-8 formatda emas.")


@require_http_methods(['GET'])
@teacher_api_required
def teacher_groups(request):
    try:
        groups = get_teacher_groups(request.user)
    except PermissionDenied as error:
        return json_error(error, status=403)

    return JsonResponse({
        'groups': [
            {'id': group.id, 'name': group.name}
            for group in groups
        ]
    })


@require_http_methods(['GET', 'POST'])
@teacher_api_required
def group_grades(request, group_id):
    if request.method == 'GET':
        grade_date = request.GET.get('date')
        title = request.GET.get('title', 'Dars bahosi')
        if not grade_date:
            return json_error("date parametri kerak. Masalan: ?date=2026-06-25")

        try:
            data = get_grade_snapshot(request.user, group_id, grade_date, title)
        except GradeInputError as error:
            return json_error(error)
        except PermissionDenied as error:
            return json_error(error, status=403)
        except Exception as error:
            return json_error(f"Kutilmagan xatolik: {error}", status=500)

        return JsonResponse(data)

    try:
        payload = get_json_body(request)
        data = save_grades(
            request.user,
            group_id,
            payload.get('date'),
            payload.get('title', 'Dars bahosi'),
            payload.get('records'),
        )
    except GradeInputError as error:
        return json_error(error)
    except PermissionDenied as error:
        return json_error(error, status=403)
    except Exception as error:
        return json_error(f"Kutilmagan xatolik: {error}", status=500)

    return JsonResponse(data)
