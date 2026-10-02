from django.contrib import admin

from .models import AttendanceRecord, AttendanceSession


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    autocomplete_fields = ('student',)
    extra = 0


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    inlines = (AttendanceRecordInline,)
    list_display = ('group', 'teacher', 'date', 'updated_at')
    list_filter = ('date', 'group', 'teacher')
    search_fields = ('group__name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')
    autocomplete_fields = ('group', 'teacher')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'status', 'marked_at')
    list_filter = ('status', 'session__date', 'session__group')
    search_fields = ('student__first_name', 'student__last_name', 'session__group__name')
    autocomplete_fields = ('session', 'student')
