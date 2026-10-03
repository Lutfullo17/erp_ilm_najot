"""Yangi UI formalari: mavjud form/validatsiyalarni qayta ishlatadi, xabarlarni oddiy o'zbekchaga o'tkazadi."""
import datetime

from django import forms

from groups_app.models import Group
from students.models import Student
from students.views import StudentQuickForm

PHONE_ERROR = "Telefon raqami 9 ta raqamdan iborat bo'lishi kerak. Masalan: 90 123 45 67"


def normalize_phone(value, required=False):
    """Faqat raqamlar; +998 va bo'sh joylar olib tashlanadi. 9 raqam qaytaradi yoki ''."""
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if digits.startswith('998') and len(digits) == 12:
        digits = digits[3:]
    if not digits:
        if required:
            raise forms.ValidationError("Telefon raqamini kiriting. Masalan: 90 123 45 67")
        return ''
    if len(digits) != 9:
        raise forms.ValidationError(PHONE_ERROR)
    return digits


class UxStudentForm(StudentQuickForm):
    """StudentQuickForm + oddiy xato xabarlari, telefon tekshiruvi, takrorlanishdan himoya."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fields
        f['full_name'].error_messages['required'] = "Ism va familiyani kiriting. Masalan: Ali Valiyev"
        f['status'].required = False
        f['gender'].required = False
        f['has_discount'].required = False
        f['discount_type'].required = False
        f['discount_value'].required = False
        f['birth_date'].required = False
        f['phone'].required = False
        f['parent_phone'].required = False
        f['birth_date'].error_messages['invalid'] = "Sanani to'g'ri kiriting."

    def clean_full_name(self):
        name = ' '.join(self.cleaned_data.get('full_name', '').split())
        if len(name) < 2:
            raise forms.ValidationError("Ism va familiyani kiriting. Masalan: Ali Valiyev")
        if len(name) > 300:
            raise forms.ValidationError("Ism juda uzun (300 belgidan oshmasin).")
        return name

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))

    def clean_parent_phone(self):
        return normalize_phone(self.cleaned_data.get('parent_phone'))

    def clean_birth_date(self):
        d = self.cleaned_data.get('birth_date')
        if d and (d > datetime.date.today() or d.year < 1940):
            raise forms.ValidationError("Tug'ilgan sanani to'g'ri kiriting.")
        return d

    def clean_status(self):
        return self.cleaned_data.get('status') or Student.Status.ACTIVE

    def clean_gender(self):
        return self.cleaned_data.get('gender') or Student.Gender.MALE

    def clean_discount_value(self):
        has = self.cleaned_data.get('has_discount')
        typ = self.cleaned_data.get('discount_type') or Student.DiscountType.PERCENTAGE
        val = self.cleaned_data.get('discount_value') or 0
        if has:
            if val <= 0:
                raise forms.ValidationError("Chegirma qiymati 0 dan katta bo'lishi kerak.")
            if typ == Student.DiscountType.PERCENTAGE and val > 100:
                raise forms.ValidationError("Foiz chegirma 100% dan oshmasligi kerak.")
        return val

    def clean(self):
        data = super().clean()
        if not data.get('discount_type'):
            data['discount_type'] = Student.DiscountType.PERCENTAGE
        name = data.get('full_name')
        phone = data.get('phone')
        if name and phone and not self.errors:
            parts = name.split(None, 1)
            dup = Student.objects.filter(first_name__iexact=parts[0], last_name__iexact=parts[1] if len(parts) > 1 else '',
                                         phone=phone, is_deleted=False)
            if self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            existing = dup.first()
            if existing:
                self.add_error('full_name', "Bu ism va telefon bilan o'quvchi allaqachon mavjud.")
                self.duplicate_of = existing
        return data


class GroupSlotForm(forms.Form):
    pass
