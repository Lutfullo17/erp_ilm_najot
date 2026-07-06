from django.db import migrations, models
import django.db.models.deletion


def create_parents_from_existing_data(apps, schema_editor):
    """
    Mavjud parent_phone ma'lumotlari asosida Parent obyektlarini yaratadi
    va Studentlarni ularga bog'laydi.
    """
    Student = apps.get_model('students', 'Student')
    Parent = apps.get_model('students', 'Parent')

    # parent_phone ga ega o'quvchilarni topamiz
    students_with_parent = Student.objects.filter(
        parent_phone__isnull=False
    ).exclude(parent_phone='').order_by('parent_phone')

    # Telefon raqamlari bo'yicha guruhlaymiz
    phone_groups = {}
    for student in students_with_parent:
        # Telefon raqamini normalizatsiya qilish
        digits = ''.join(ch for ch in student.parent_phone if ch.isdigit())
        if len(digits) == 9:
            digits = '998' + digits
        if len(digits) < 9:
            continue

        # Oxirgi 9 raqam bo'yicha indexlaymiz
        key = digits[-9:]
        if key not in phone_groups:
            phone_groups[key] = []
        phone_groups[key].append(student)

    # Har bir telefon raqami uchun Parent yaratamiz
    for phone_key, students in phone_groups.items():
        if not students:
            continue

        # Normalizatsiya qilgan telefon raqamni olish
        first_student = students[0]
        phone = first_student.parent_phone

        parent, created = Parent.objects.get_or_create(
            phone=phone,
            defaults={
                'first_name': '',
                'last_name': '',
            }
        )

        # Barcha o'quvchilarni bog'lash
        Student.objects.filter(pk__in=[s.pk for s in students]).update(parent=parent)


def reverse_func(apps, schema_editor):
    """Reverse migration — parent FK ni tozalash."""
    Student = apps.get_model('students', 'Student')
    Student.objects.all().update(parent=None)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0004_student_deleted_at_student_deleted_by_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Parent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(max_length=20, unique=True, verbose_name='Telefon raqami')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='Ism')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='Familiya')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': "Ota-ona",
                'verbose_name_plural': "Ota-onalar",
                'ordering': ('last_name', 'first_name'),
            },
        ),
        migrations.AddField(
            model_name='student',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='children_set',
                to='students.parent',
                verbose_name='Ota-ona',
            ),
        ),
        migrations.RunPython(create_parents_from_existing_data, reverse_func),
    ]
