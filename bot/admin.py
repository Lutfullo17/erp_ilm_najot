from django.contrib import admin

from .models import TelegramAppeal, TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'phone', 'student', 'user', 'is_verified', 'state', 'updated_at')
    list_filter = ('is_verified', 'state', 'updated_at')
    search_fields = ('telegram_id', 'username', 'first_name', 'phone', 'student__first_name', 'student__last_name')
    autocomplete_fields = ('student', 'user')


@admin.register(TelegramAppeal)
class TelegramAppealAdmin(admin.ModelAdmin):
    list_display = ('student', 'telegram_user', 'sender_type', 'is_resolved', 'created_at')
    list_filter = ('sender_type', 'is_resolved', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'message')
    autocomplete_fields = ('telegram_user', 'student')
