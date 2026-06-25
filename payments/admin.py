from django.contrib import admin

from .models import PaymentAllocation, PaymentTransaction, StudentMonthBalance


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    autocomplete_fields = ('balance',)
    extra = 0
    readonly_fields = ('balance', 'amount')
    can_delete = False


@admin.register(StudentMonthBalance)
class StudentMonthBalanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'group', 'month', 'required_amount', 'paid_amount', 'debt_amount', 'advance_amount', 'status')
    list_filter = ('status', 'month', 'group')
    search_fields = ('student__first_name', 'student__last_name', 'group__name')
    autocomplete_fields = ('student', 'group')
    readonly_fields = ('debt_amount', 'advance_amount', 'status')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    inlines = (PaymentAllocationInline,)
    list_display = ('student', 'group', 'amount', 'payment_date', 'method', 'created_by')
    list_filter = ('payment_date', 'method', 'group')
    search_fields = ('student__first_name', 'student__last_name', 'group__name')
    autocomplete_fields = ('student', 'group', 'created_by')


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ('payment', 'balance', 'amount')
    search_fields = ('payment__student__first_name', 'payment__student__last_name', 'balance__group__name')
    autocomplete_fields = ('payment', 'balance')
