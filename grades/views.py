import json
import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView
from django.utils import timezone

from groups_app.models import Group
from users1.views import TeacherRequiredMixin
from .models import GradeSession
logger = logging.getLogger(__name__)

from .services import GradeInputError, get_grade_snapshot, get_teacher_groups, save_grades


class TeacherGradeListView(LoginRequiredMixin, TeacherRequiredMixin, ListView):
    template_name = 'grades/grade_list.html'
    context_object_name = 'grade_sessions'

    def get_queryset(self):
        return GradeSession.objects.filter(
            teacher=self.request.user
        ).order_by('-date')[:20]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(teacher=self.request.user, is_active=True).order_by('name')
        return context


class GradeInputView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'grades/grade_input.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()

        groups = Group.objects.filter(teacher=user, is_active=True).order_by('name')
        context['groups'] = groups

        group_id = self.request.GET.get('group')
        grade_date = self.request.GET.get('date', today.isoformat())
        title = self.request.GET.get('title', 'Dars bahosi')

        context['selected_group_id'] = group_id
        context['selected_date'] = grade_date
        context['selected_title'] = title
        context['today'] = today

        if group_id:
            try:
                snapshot = get_grade_snapshot(user, group_id, grade_date, title)
                context['snapshot'] = snapshot
                context['students'] = snapshot['students']
            except (GradeInputError, PermissionDenied):
                context['students'] = []
                context['error'] = "Baholash uchun ma'lumot topilmadi yoki ruxsat yo'q."

        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        group_id = request.POST.get('group_id')
        grade_date = request.POST.get('grade_date')
        title = request.POST.get('title', 'Dars bahosi')

        if not group_id or not grade_date:
            messages.error(request, "Guruh va sana tanlash shart.")
            return redirect('grades:grade_input')

        records = []
        for key, value in request.POST.items():
            if key.startswith('percentage_'):
                try:
                    student_id = int(key.split('_')[1])
                except (IndexError, ValueError):
                    continue
                # Bo'sh maydon = baholanmagan (0% emas).
                if not str(value).strip():
                    continue
                comment_key = f'comment_{student_id}'
                comment = request.POST.get(comment_key, '')
                percentage = value
                records.append({
                    'student_id': student_id,
                    'percentage': percentage,
                    'comment': comment,
                })

        if not records:
            messages.error(request, "Kamida bitta baho kiriting.")
            return redirect(f'/grades/input/?group={group_id}&date={grade_date}&title={title}')

        try:
            save_grades(user, group_id, grade_date, title, records)
            messages.success(request, "Baholar muvaffaqiyatli saqlandi!")
        except (GradeInputError, PermissionDenied) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, "Kutilmagan xatolik yuz berdi. Qayta urinib ko'ring.")

        return redirect(f'/grades/input/?group={group_id}&date={grade_date}&title={title}')


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
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise GradeInputError("JSON ma'lumot noto'g'ri yoki UTF-8 formatda emas.")
    if not isinstance(data, dict):
        raise GradeInputError("JSON obyekt bo'lishi kerak.")
    return data


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
        except Http404:
            return json_error("Guruh topilmadi.", status=404)
        except Exception:
            logger.exception('Baholarni olishda xatolik')
            return json_error("Server xatosi.", status=500)

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
    except Http404:
        return json_error("Guruh topilmadi.", status=404)
    except Exception:
        logger.exception('Baholarni saqlashda xatolik')
        return json_error("Server xatosi.", status=500)

    return JsonResponse(data)
