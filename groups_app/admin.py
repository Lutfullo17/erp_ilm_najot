from django.contrib import admin

from .models import Group, GroupStudent


class GroupStudentInline(admin.TabularInline):
    model = GroupStudent
    autocomplete_fields = ('student',)
    extra = 1


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    inlines = (GroupStudentInline,)
    list_display = ('name', 'teacher', 'monthly_fee', 'student_count', 'start_date', 'is_active')
    list_filter = ('is_active', 'start_date', 'teacher')
    search_fields = ('name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')
    autocomplete_fields = ('teacher',)

    def student_count(self, obj):
        return obj.students.count()

    student_count.short_description = "O'quvchilar soni"


@admin.register(GroupStudent)
class GroupStudentAdmin(admin.ModelAdmin):
    list_display = ('group', 'student', 'joined_at', 'is_active')
    list_filter = ('is_active', 'joined_at', 'group')
    search_fields = ('group__name', 'student__first_name', 'student__last_name')
    autocomplete_fields = ('group', 'student')
