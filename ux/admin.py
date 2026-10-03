from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'page', 'message')
    readonly_fields = ('created_at',)
