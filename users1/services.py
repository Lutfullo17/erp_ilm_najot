from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from groups_app.models import Group
from attendance.models import AttendanceSession
from payments.models import StudentMonthBalance

def validate_teacher_deletion(teacher):
    """
    Teacher o'chirishdan oldin tekshirish:
    * Faol guruhlarga biriktirilganmi?
    * Kelajakdagi darslarga biriktirilganmi?
    * Tugallanmagan davomatlari mavjudmi?
    """
    # 1. Faol guruhlar
    if Group.objects.filter(teacher=teacher, is_active=True).exists():
        return False, "Ushbu o'qituvchi faol guruhlarga biriktirilganligi sababli o'chirib bo'lmaydi."

    # 2. Kelajakdagi darslar (AttendanceSession)
    # Taxmin: attendanceSession sanasi bugundan keyin bo'lsa, kelajakdagi dars
    if AttendanceSession.objects.filter(teacher=teacher, date__gt=timezone.now().date()).exists():
        return False, "Ushbu o'qituvchining kelajakdagi darslari mavjud."

    # 3. Tugallanmagan davomatlar
    # (Bu yerda "tugallanmagan" qanday aniqlanishini aniqlash kerak)
    # Masalan: status bo'yicha yoki yozuv yo'qligi?
    # Hozircha oddiyroq: dars sanasi o'tgan bo'lsa va hali yozuv olinmagan bo'lsa?
    # Loyiha tuzilishidan kelib chiqib, hozircha ushbu qismni keyinroq to'ldiramiz.

    return True, None

def validate_student_deletion(student):
    """
    Student o'chirishdan oldin tekshirish:
    Faqat jiddiy bloklaydigan holatlarni tekshiradi.
    Guruhga biriktirilgan yoki qarzdor bo'lsa ham o'chirishga ruxsat beriladi —
    guruh a'zoliklari avtomatik deaktivatsiya qilinadi.
    """
    # Soft delete har doim mumkin — faqat allaqachon o'chirilganini tekshiramiz
    if student.is_deleted:
        return False, "Ushbu o'quvchi allaqachon o'chirilgan."

    return True, None
