from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Teacher, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(Teacher)
class TeacherAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('username', 'first_name', 'last_name', 'email')
    fieldsets = UserAdmin.fieldsets
    add_fieldsets = UserAdmin.add_fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role=User.Role.TEACHER)

    def save_model(self, request, obj, form, change):
        obj.role = User.Role.TEACHER
        super().save_model(request, obj, form, change)
