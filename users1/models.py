from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        DIRECTOR = 'DIRECTOR', 'Director'
        ADMINISTRATOR = 'ADMINISTRATOR', 'Administrator'
        TEACHER = 'TEACHER', "O'qituvchi"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TEACHER,
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")

    @property
    def is_director(self):
        return self.role == self.Role.DIRECTOR or self.is_superuser

    @property
    def is_administrator_role(self):
        return self.role == self.Role.ADMINISTRATOR

    @property
    def is_admin_access(self):
        """Returns True if the user has Director or Administrator access"""
        return self.role in [self.Role.DIRECTOR, self.Role.ADMINISTRATOR] or self.is_superuser

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.DIRECTOR
        super().save(*args, **kwargs)


class TeacherManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(role=User.Role.TEACHER)


class Teacher(User):
    objects = TeacherManager()

    class Meta:
        proxy = True
        verbose_name = "O'qituvchi"
        verbose_name_plural = "O'qituvchilar"

    def save(self, *args, **kwargs):
        self.role = User.Role.TEACHER
        super().save(*args, **kwargs)
