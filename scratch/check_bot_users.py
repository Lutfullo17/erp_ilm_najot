import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from bot.models import TelegramUser
from users1.models import User

total = TelegramUser.objects.count()
verified = TelegramUser.objects.filter(is_verified=True).count()
staff = TelegramUser.objects.filter(user__isnull=False).count()
students_linked = TelegramUser.objects.filter(student__isnull=False).count()

print(f"Total TelegramUsers: {total}")
print(f"Verified TelegramUsers: {verified}")
print(f"Staff TelegramUsers: {staff}")
print(f"Students Linked: {students_linked}")

# Sample verified non-staff users
non_staff_verified = TelegramUser.objects.filter(is_verified=True).exclude(
    user__role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR, User.Role.TEACHER]
)
print(f"Non-staff Verified: {non_staff_verified.count()}")

for u in non_staff_verified[:5]:
    print(f"ID: {u.telegram_id}, Phone: {u.phone}, Student: {u.student}")
