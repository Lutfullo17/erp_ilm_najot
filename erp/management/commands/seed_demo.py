"""Demo ma'lumotlar (har bir bo'limga kamida 20 ta yozuv).

    python manage.py seed_demo            # faqat DEBUG=True bo'lsa ishlaydi
    python manage.py seed_demo --password "Parol-123!"

Productionda ishlamaydi (DEBUG=False bo'lsa rad etadi). Ikkinchi marta ishga tushirilsa, demo
ma'lumotlar allaqachon borligini aytib to'xtaydi (hech narsa o'chirilmaydi).
"""
import datetime
import random
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceSession, LessonPlan
from bot.models import TelegramAppeal, TelegramUser
from grades.models import GradeRecord, GradeSession
from groups_app.models import Group, GroupStudent
from payments.models import PaymentMethod
from payments.services import apply_payment
from students.models import Parent, Student
from users1.models import (
    AuditLog, MissedAttendanceAlert, ScheduleChangeRequest, TeacherPenalty, User,
)

DAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
DAY_PAIRS = [('Dushanba', 'Chorshanba'), ('Seshanba', 'Payshanba'), ('Juma', 'Shanba')]

MALE = ['Ali', 'Jasur', 'Sardor', 'Bobur', 'Otabek', 'Aziz', 'Dilshod', 'Sherzod', 'Bekzod', 'Rustam',
        'Javohir', 'Umid', 'Shaxzod', 'Doston', 'Islom', 'Nodir', 'Akmal', 'Farhod', 'Timur', 'Eldor']
FEMALE = ['Zilola', 'Madina', 'Dilnoza', 'Malika', 'Nilufar', 'Sevara', 'Gulnora', 'Shahlo', 'Kamola', 'Nigora',
          'Feruza', 'Mohira', 'Laylo', 'Zarina', 'Sabina', 'Mohinur', 'Aziza', 'Munisa', 'Barno', 'Ruxsora']
LAST_M = ['Valiyev', 'Karimov', 'Toshmatov', 'Rahimov', 'Abdullayev', 'Yusupov', 'Nazarov', 'Ismoilov',
          'Hasanov', 'Qodirov', 'Mirzayev', 'Sobirov', 'Ergashev', 'Raximov', 'Sharipov']
LAST_F = [n[:-2] + 'a' if n.endswith('ov') else n for n in LAST_M]
TEACHER_NAMES = [
    ('Aziza', 'Qodirova'), ('Bahodir', 'Sodiqov'), ('Charos', 'Ahmedova'), ('Davron', 'Xolmatov'),
    ('Elnora', 'Saidova'), ('Farrux', 'Normatov'), ('Gulchehra', 'Tursunova'), ('Hamid', 'Orifov'),
    ('Iroda', 'Mamatova'), ('Jahongir', 'Zokirov'), ('Kamila', 'Rustamova'), ('Lola', 'Bekmurodova'),
    ('Mansur', 'Haydarov'), ('Nargiza', 'Yoqubova'), ('Oybek', 'Ravshanov'), ('Parvina', 'Ismatova'),
    ('Qahramon', 'Eshonov'), ('Robiya', 'Abdurahmonova'), ('Sanjar', 'Tojiyev'), ('Tahmina', 'Umarova'),
    ('Ulug\'bek', 'Safarov'), ('Vohid', 'Nematov'),
]
SUBJECTS = [
    ('Ingliz tili', ['A1', 'A2', 'B1', 'B2']), ('Matematika', ['5-sinf', '7-sinf', '9-sinf']),
    ('Rus tili', ['Boshlang\'ich', 'O\'rta']), ('Fizika', ['8-sinf', '10-sinf']),
    ('Kimyo', ['8-sinf', '10-sinf']), ('Biologiya', ['9-sinf', '11-sinf']),
    ('IT (Python)', ['Boshlang\'ich', 'Davomli']), ('Ona tili', ['6-sinf', '9-sinf']),
    ('Tarix', ['7-sinf', '10-sinf']), ('Arab tili', ['Boshlang\'ich']),
]
TOPICS = ['Kirish darsi', 'Yangi mavzu: asosiy tushunchalar', 'Mashqlar ustida ishlash', 'Takrorlash',
          'Amaliy mashg\'ulot', 'Nazorat ishi', 'Mustaqil ish', 'Savol-javob']
HOMEWORKS = ['Darslikdagi 5-mashq', 'Yangi so\'zlarni yodlash', '10 ta masala yechish', 'Insho yozish',
             'Mavzuni takrorlash', 'Test topshirig\'i', 'Kitobdan 2 sahifa o\'qish']
APPEALS = ['Farzandim bugun kasal, darsga kela olmaydi.', 'To\'lovni ertaroq qilsam bo\'ladimi?',
           'Dars vaqtini o\'zgartirish mumkinmi?', 'Uyga vazifa tushunarsiz bo\'ldi, yordam bering.',
           'Qarzdorlik summasini aniqlashtirib bering.', 'Chegirma bormi? Ikkinchi farzandim ham o\'qimoqchi.',
           'Dars jadvalini yuboring, iltimos.', 'O\'qituvchi bilan gaplashishim mumkinmi?']
REASONS = ['Shifokorga borish kerak', 'Oilaviy sabab', 'Xona ta\'mirlanmoqda', 'Imtihon bilan to\'qnashuv',
           'Transport muammosi', 'Boshqa guruh bilan almashish']


class Command(BaseCommand):
    help = "Demo ma'lumotlarni yaratadi (faqat DEBUG=True)."

    def add_arguments(self, parser):
        parser.add_argument('--password', default='Demo-Parol-2026')

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo faqat DEBUG=True bo'lganda (lokal/test muhitda) ishlaydi.")
        if User.objects.filter(username='ustoz01').exists():
            self.stdout.write(self.style.WARNING("Demo ma'lumotlar allaqachon mavjud. Hech narsa o'zgartirilmadi."))
            return
        rnd = random.Random(2026)
        self.pw = opts['password']
        with transaction.atomic():
            self.run(rnd)

    # ------------------------------------------------------------------
    def user(self, username, role, first, last, phone=''):
        u = User(username=username, role=role, first_name=first, last_name=last, phone=phone)
        u.set_password(self.pw)
        u.save()
        return u

    def run(self, rnd):
        today = timezone.localdate()
        director = User.objects.filter(role='DIRECTOR').first() or self.user('direktor', 'DIRECTOR', 'Anvar', 'Karimov', '901000001')
        admin = User.objects.filter(role='ADMINISTRATOR').first() or self.user('admin1', 'ADMINISTRATOR', 'Nodira', 'Yusupova', '901000002')
        admins = [admin]
        for i, (f, l) in enumerate([('Shahnoza', 'Aliyeva'), ('Dilmurod', 'Qosimov')], 2):
            admins.append(self.user(f'admin{i}', 'ADMINISTRATOR', f, l, f'9010000{i:02d}'))

        teachers = [self.user(f'ustoz{i:02d}', 'TEACHER', f, l, f'9020000{i:02d}')
                    for i, (f, l) in enumerate(TEACHER_NAMES, 1)]
        self.stdout.write(f"O'qituvchilar: {len(teachers)}, administratorlar: {len(admins)}")

        # ---- Guruhlar (24 ta, to'qnashuvsiz jadval)
        names = [f'{s} {lvl}' for s, lvls in SUBJECTS for lvl in lvls]
        rnd.shuffle(names)
        groups, used = [], 0
        for idx, name in enumerate(names[:24]):
            teacher = teachers[idx % len(teachers)]
            fee = Decimal(rnd.choice([250000, 300000, 350000, 400000, 450000]))
            ok = None
            for attempt in range(200):
                pair = rnd.choice(DAY_PAIRS)
                hour = rnd.choice([8, 9, 10, 11, 14, 15, 16, 17])
                g = Group(
                    name=name, monthly_fee=fee, teacher=teacher,
                    start_date=today - datetime.timedelta(days=rnd.randint(60, 150)),
                    lesson_days=', '.join(pair), lesson_time=datetime.time(hour, rnd.choice([0, 30])),
                    duration=Decimal('1.5'), room=rnd.randint(1, 6),
                )
                try:
                    g.full_clean()
                except ValidationError:
                    continue
                g.save()
                ok = g
                break
            if ok:
                groups.append(ok)
        self.stdout.write(f"Guruhlar: {len(groups)}")

        # ---- Talabalar (64 ta) + ota-onalar + a'zolik
        students, parents = [], []
        for i in range(64):
            male = rnd.random() < 0.5
            first = rnd.choice(MALE if male else FEMALE)
            last = rnd.choice(LAST_M if male else LAST_F)
            parent_phone = f'9111{i:05d}'
            parent = Parent.objects.create(phone='998' + parent_phone, first_name=rnd.choice(MALE), last_name=last)
            s = Student.objects.create(
                first_name=first, last_name=last, phone=f'9012{i:05d}', parent_phone=parent_phone, parent=parent,
                birth_date=datetime.date(rnd.randint(2006, 2017), rnd.randint(1, 12), rnd.randint(1, 28)),
                gender='MALE' if male else 'FEMALE', address=f"Samarqand, {rnd.randint(1, 60)}-uy",
                has_discount=(i % 9 == 0), discount_type='PERCENTAGE', discount_value=Decimal('10') if i % 9 == 0 else 0,
            )
            students.append(s)
            parents.append(parent)
        memberships = []
        for i, s in enumerate(students):
            gs_list = [groups[i % len(groups)]]
            if i % 7 == 0:
                gs_list.append(groups[(i + 5) % len(groups)])
            for g in gs_list:
                if any(m.group_id == g.pk and m.student_id == s.pk for m in memberships):
                    continue
                joined = max(g.start_date, today - datetime.timedelta(days=rnd.randint(5, 110)))
                memberships.append(GroupStudent.objects.create(group=g, student=s, joined_at=joined))
        for s in students[-3:]:
            s.status = Student.Status.FROZEN
            s.save()
        self.stdout.write(f"Talabalar: {len(students)}, a'zoliklar: {len(memberships)}")

        # ---- To'lovlar (kamida 40 ta; ba'zi talabalar to'lamagan -> qarzdor)
        pay = 0
        for m in memberships:
            if rnd.random() < 0.35:
                continue  # to'lamagan: qarzdor bo'ladi
            fee = m.group.monthly_fee
            for k in range(rnd.randint(1, 2)):
                pdate = min(today, m.joined_at + datetime.timedelta(days=rnd.randint(0, 80)))
                amount = fee if rnd.random() < 0.7 else (fee / 2)
                try:
                    apply_payment(director, m.student_id, m.group_id, amount, pdate,
                                  rnd.choice(PaymentMethod.values), '')
                    pay += 1
                except Exception:
                    pass
        self.stdout.write(f"To'lovlar: {pay}")

        # ---- Davomat + mavzu/uyga vazifa (har guruhga 3 ta dars)
        sessions = 0
        for g in groups:
            days = {DAYS.index(d) for d in g.lesson_days.split(', ')}
            members = list(g.groupstudent_set.filter(is_active=True).select_related('student'))
            d, made = today - datetime.timedelta(days=1), 0
            while made < 3 and d > g.start_date:
                if d.weekday() in days:
                    s = AttendanceSession.objects.create(
                        group=g, teacher=g.teacher, date=d,
                        lesson_topic=rnd.choice(TOPICS), homework=rnd.choice(HOMEWORKS))
                    for m in members:
                        if m.joined_at <= d:
                            AttendanceRecord.objects.create(
                                session=s, student=m.student,
                                status=rnd.choices(['PRESENT', 'ABSENT', 'LATE', 'EXCUSED'], [80, 10, 6, 4])[0])
                    sessions += 1
                    made += 1
                d -= datetime.timedelta(days=1)
        self.stdout.write(f"Davomat sessiyalari: {sessions}")

        # ---- Baholar (har guruhga 1 ta nazorat)
        gs_n = 0
        for g in groups:
            members = list(g.groupstudent_set.filter(is_active=True).select_related('student'))
            if not members:
                continue
            gsn = GradeSession.objects.create(group=g, teacher=g.teacher, title='Nazorat ishi',
                                              date=today - datetime.timedelta(days=rnd.randint(2, 12)))
            for m in members:
                GradeRecord.objects.create(session=gsn, student=m.student,
                                           percentage=Decimal(rnd.randint(35, 100)), comment='')
            gs_n += 1
        self.stdout.write(f"Baho sessiyalari: {gs_n}")

        # ---- Dars rejalari (har guruhga 1–2 ta kelgusi dars)
        plans = 0
        for g in groups:
            for k in range(1, 3):
                d = today + datetime.timedelta(days=k * 3)
                LessonPlan.objects.get_or_create(group=g, date=d, defaults={
                    'teacher': g.teacher, 'topic': rnd.choice(TOPICS), 'is_exam': rnd.random() < 0.1})
                plans += 1
        self.stdout.write(f"Dars rejalari: {plans}")

        # ---- Jarimalar (25 ta) va davomat ogohlantirishlari (20 ta)
        for i in range(25):
            t = teachers[i % len(teachers)]
            TeacherPenalty.objects.create(
                teacher=t, group=rnd.choice(groups), date=today - datetime.timedelta(days=rnd.randint(1, 40)),
                reason=rnd.choice(['Dars davomatini o\'z vaqtida kiritmadi.', 'Darsga kech qoldi', 'Qo\'lda: tartib buzilishi']),
                points=rnd.choice([-5, -10, -10, -3]), penalty_type=rnd.choice(
                    ['ATTENDANCE_MISSED', 'CLASS_SKIPPED', 'MANUAL']), is_manual=(i % 3 == 0), given_by=director)
        alerts = 0
        for i in range(20):
            g = groups[i % len(groups)]
            try:
                MissedAttendanceAlert.objects.create(
                    teacher=g.teacher, group=g, lesson_date=today - datetime.timedelta(days=i + 1),
                    status='PENDING' if i < 6 else rnd.choice(['CAME', 'NOT_CAME', 'RESOLVED']),
                    penalty_applied=i >= 6)
                alerts += 1
            except Exception:
                pass
        self.stdout.write(f"Jarimalar: 25, davomat ogohlantirishlari: {alerts}")

        # ---- Jadval o'zgartirish arizalari (20 ta)
        for i in range(20):
            g = groups[i % len(groups)]
            status = ['PENDING'] * 8 + ['APPROVED'] * 7 + ['REJECTED'] * 5
            st = status[i]
            old_day = g.lesson_days.split(', ')[0]
            new_hour = rnd.choice([9, 10, 15, 16])
            ScheduleChangeRequest.objects.create(
                teacher=g.teacher, group=g, old_day=old_day, old_start_time=g.lesson_time,
                old_end_time=g.end_time or g.lesson_time, new_day=rnd.choice(DAYS[:6]),
                new_start_time=datetime.time(new_hour), new_end_time=datetime.time(new_hour + 1, 30),
                reason=rnd.choice(REASONS), status=st, change_date=today + datetime.timedelta(days=rnd.randint(1, 14)),
                reviewed_by=None if st == 'PENDING' else admin,
                reviewed_at=None if st == 'PENDING' else timezone.now(),
                effective_week_start=(today - datetime.timedelta(days=today.weekday())) if st == 'APPROVED' else None,
                change_type='TEACHER_REQUEST')
        self.stdout.write("Jadval arizalari: 20")

        # ---- Telegram foydalanuvchilar (20) va murojaatlar (28)
        tus = []
        for i, s in enumerate(students[:22]):
            tus.append(TelegramUser.objects.create(
                telegram_id=7000000 + i, username=f'ota_ona_{i}', first_name=s.parent.first_name if s.parent else 'Ota',
                phone='998' + s.parent_phone, student=s, is_verified=True, is_blocked=(i % 11 == 0)))
        for i in range(28):
            tu = tus[i % len(tus)]
            TelegramAppeal.objects.create(
                telegram_user=tu, student=tu.student, message=rnd.choice(APPEALS),
                sender_type='STUDENT', recipient_type='ADMIN', is_resolved=(i % 3 == 0))
        self.stdout.write(f"Telegram foydalanuvchilar: {len(tus)}, murojaatlar: 28")

        for i in range(20):
            AuditLog.objects.create(user=admin, role='ADMINISTRATOR', action=rnd.choice(
                ["O'quvchi qo'shildi", "Guruh tahrirlandi", "To'lov qabul qilindi", "Davomat qo'lda kiritildi"]))
        self.stdout.write(self.style.SUCCESS(
            "Tayyor. Kirish: dir (direktor) / admin1 / ustoz01..ustoz22. Parol: --password qiymati (standart Demo-Parol-2026)."))
