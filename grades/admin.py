from django.contrib import admin

from .models import GradeRecord, GradeSession


class GradeRecordInline(admin.TabularInline):
    model = GradeRecord
    autocomplete_fields = ('student',)
    extra = 0


@admin.register(GradeSession)
class GradeSessionAdmin(admin.ModelAdmin):
    inlines = (GradeRecordInline,)
    list_display = ('group', 'teacher', 'title', 'date', 'updated_at')
    list_filter = ('date', 'group', 'teacher')
    search_fields = ('group__name', 'teacher__username', 'teacher__first_name', 'teacher__last_name', 'title')
    autocomplete_fields = ('group', 'teacher')


@admin.register(GradeRecord)
class GradeRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'percentage', 'graded_at')
    list_filter = ('session__date', 'session__group')
    search_fields = ('student__first_name', 'student__last_name', 'session__group__name', 'session__title')
    autocomplete_fields = ('session', 'student')
