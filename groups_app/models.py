from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Room(models.IntegerChoices):
    ROOM_1 = 1, '1-xona'
    ROOM_2 = 2, '2-xona'
    ROOM_3 = 3, '3-xona'
    ROOM_4 = 4, '4-xona'
    ROOM_5 = 5, '5-xona'
    ROOM_6 = 6, '6-xona'


class Group(models.Model):
    name = models.CharField(max_length=150, unique=True)
    monthly_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Oylik to'lov",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='teaching_groups',
        limit_choices_to={'role': 'TEACHER'},
        null=True,
        blank=True,
        verbose_name="O'qituvchi",
    )
    students = models.ManyToManyField(
        'students.Student',
        through='GroupStudent',
        related_name='groups',
        blank=True,
    )
    start_date = models.DateField(null=True, blank=True, verbose_name="Boshlanish sanasi")
    lesson_days = models.CharField(max_length=100, blank=True, verbose_name="Dars kunlari")
    lesson_time = models.TimeField(null=True, blank=True, verbose_name="Dars vaqti")
    duration = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Davomiyligi (soat)")
    end_time = models.TimeField(null=True, blank=True, verbose_name="Tugash vaqti")
    room = models.IntegerField(choices=Room.choices, null=True, blank=True, verbose_name="Xona")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    is_paused = models.BooleanField(default=False, verbose_name="Vaqtincha to'xtatilgan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Guruh'
        verbose_name_plural = 'Guruhlar'

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}

        # O'qituvchi tekshiruvi
        if self.teacher_id and not self.teacher.is_teacher:
            errors['teacher'] = "Guruh o'qituvchisi TEACHER role'da bo'lishi kerak."

        import datetime
        # Calculate end_time based on lesson_time and duration
        if self.lesson_time and self.duration:
            hours = int(self.duration)
            minutes = int((self.duration - hours) * 60)
            td = datetime.timedelta(hours=hours, minutes=minutes)
            start_dt = datetime.datetime.combine(datetime.date.today(), self.lesson_time)
            self.end_time = (start_dt + td).time()

        # Vaqt va kun bo'yicha konflikt tekshiruvi
        if self.lesson_time and self.end_time and self.lesson_days:
            # Dars kunlari ro'yxati
            self_days = set(d.strip() for d in self.lesson_days.split(',') if d.strip())

            # Shu o'qituvchi o'sha vaqtda boshqa guruhda ham dars beradimi?
            if self.teacher_id:
                teacher_conflict = Group.objects.filter(
                    teacher_id=self.teacher_id,
                    is_active=True,
                    lesson_time__isnull=False,
                    end_time__isnull=False
                ).exclude(pk=self.pk)

                for cg in teacher_conflict:
                    if not cg.lesson_days:
                        continue
                    cg_days = set(d.strip() for d in cg.lesson_days.split(',') if d.strip())
                    overlap = self_days & cg_days
                    if overlap:
                        # overlap logic: start_A < end_B AND end_A > start_B
                        if self.lesson_time < cg.end_time and self.end_time > cg.lesson_time:
                            errors['teacher'] = (
                                f"Tanlangan o'qituvchi ushbu vaqt oralig'ida boshqa guruhda dars o'tmoqda ({cg.name})."
                            )
                            break

            # Shu xona o'sha vaqtda band emasmi?
            if self.room:
                room_conflict = Group.objects.filter(
                    room=self.room,
                    is_active=True,
                    lesson_time__isnull=False,
                    end_time__isnull=False
                ).exclude(pk=self.pk)

                for cg in room_conflict:
                    if not cg.lesson_days:
                        continue
                    cg_days = set(d.strip() for d in cg.lesson_days.split(',') if d.strip())
                    overlap = self_days & cg_days
                    if overlap:
                        # overlap logic: start_A < end_B AND end_A > start_B
                        if self.lesson_time < cg.end_time and self.end_time > cg.lesson_time:
                            errors['room'] = (
                                f"Tanlangan xona ushbu vaqt oralig'ida band ({cg.name})."
                            )
                            break

        if errors:
            raise ValidationError(errors)


class GroupStudent(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE)
    # To'lov shu sanadagi oydan boshlab hisoblanadi (tahrirlash mumkin).
    joined_at = models.DateField(default=timezone.localdate, verbose_name="Qo'shilgan sana")
    # Guruhdan chiqqan sana: shu sanadan keyin boshlanadigan oylar hisoblanmaydi.
    left_at = models.DateField(null=True, blank=True, verbose_name="Chiqqan sana")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('group', 'student')
        verbose_name = "Guruh o'quvchisi"
        verbose_name_plural = "Guruh o'quvchilari"

    def __str__(self):
        return f'{self.student} - {self.group}'
