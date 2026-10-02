# Loyiha xaritasi (1-bosqich) — Ilm Najot ERP

> Hujjat faqat o'qish natijasi. Kod o'zgartirilmagan.

## 1. Stek va joylashuv

| Qism | Qiymat |
|---|---|
| Til / freymvork | Python 3.14 (lokal), **Django 6.0.6**, server-render shablonlar (DRF yo'q) |
| Server | gunicorn 26 (`Procfile`: `web`, `clock`), whitenoise 6.12 (static) |
| DB | `DB_NAME` env bo'lsa PostgreSQL (`psycopg2-binary`), aks holda SQLite (`db.sqlite3`) |
| Vaqt | `TIME_ZONE='Asia/Tashkent'`, `USE_TZ=True`, `LANGUAGE_CODE='uz'` |
| Fon ishlar | `django-apscheduler` / APScheduler: davomat nazorati (har 5 daq.), balans sinxroni (00:10) |
| Tashqi | Telegram Bot API (`requests`), Google Fonts + FontAwesome CDN |
| Fayllar | `openpyxl` (ishlatilishi topilmadi), `pillow` (avatar) |
| Deploy | `Procfile`, `.env.example` (Heroku/Render uslubi); Docker/CI yo'q |

Ilovalar: `users1` (foydalanuvchi, rol, jarima, jadval arizalari, audit), `students`, `groups_app`, `attendance`, `grades`, `payments`, `reports`, `bot`, `erp` (sozlama, scheduler).
Hajm: ~8 650 qator Python, 205 fayl, 0 ta JS/CSS fayl (hammasi shablon ichida inline; `base.html` 976 qator).

## 2. ER diagramma (matn ko'rinishida)

```
User (role: DIRECTOR|ADMINISTRATOR|TEACHER, is_blocked, is_deleted)
 ├─< Group.teacher (PROTECT, null)
 ├─< TeacherPenalty.teacher (CASCADE) ; .given_by (SET_NULL) ; .group (SET_NULL)
 ├─< MissedAttendanceAlert (teacher CASCADE, group CASCADE)  uniq(teacher,group,lesson_date)
 ├─< ScheduleChangeRequest (teacher CASCADE, group CASCADE, reviewed_by SET_NULL)
 ├─< AuditLog (user SET_NULL, target_user SET_NULL)
 ├─< AttendanceSession.teacher (PROTECT) , LessonPlan.teacher (CASCADE), GradeSession.teacher (PROTECT)
 └─< PaymentTransaction.created_by (PROTECT)

Group (name uniq, monthly_fee Decimal null, start_date, lesson_days "A, B", lesson_time, duration, end_time,
       room 1..6 (IntegerChoices), is_active, is_paused)           ← sig'im (capacity) maydoni YO'Q, kurs (Course) modeli YO'Q
 └─< GroupStudent (group CASCADE, student CASCADE, joined_at, left_at, is_active)  uniq(group,student)
        >─ Student

Student (status ACTIVE|FROZEN|LEFT, is_active, is_deleted soft, has_discount, discount_type %|FIXED, discount_value)
 ├─> Parent (phone uniq) SET_NULL
 ├─< PaymentTransaction (PROTECT) ──< PaymentAllocation (CASCADE) >── StudentMonthBalance (PROTECT)
 ├─< StudentMonthBalance (student PROTECT, group PROTECT)  uniq(student,group,month)
 │      required_amount, paid_amount, due_date, status OPEN|PARTIAL|CLOSED
 ├─< BillingPause (student|group|both, start/end)  — muzlatish, guruh pauzasi, chiqib-qaytish oralig'i
 ├─< AttendanceRecord (PROTECT) >─ AttendanceSession (group PROTECT)  uniq(group,date) ; record uniq(session,student)
 ├─< GradeRecord (PROTECT) >─ GradeSession (group PROTECT)  uniq(group,date,title) ; percentage 0..100
 └─< TelegramUser (PROTECT) ──< TelegramAppeal (telegram_user CASCADE, student PROTECT)
LessonPlan (group CASCADE, teacher CASCADE) uniq(group,date)
```

Eslatma: prompt'da so'ralgan **Kurs, Lid (lead), O'qituvchi maoshi, Kassir roli, guruh sig'imi** — kodda mavjud emas. Rollar: `DIRECTOR`, `ADMINISTRATOR` (kassir vazifasini ham bajaradi), `TEACHER`. "Talaba" tizimga kirmaydi — faqat Telegram bot orqali ota-ona.

## 3. Ruxsatlar (RBAC)

Mixinlar `users1/views.py:279-330`: `TeacherRequiredMixin`, `DirectorRequiredMixin`, `AdministratorRequiredMixin`, `AdminAccessRequiredMixin` (director+administrator). `is_blocked` faqat shu mixinlarda tekshiriladi.
Funksional (FBV) view'larda ruxsat qo'lda yoziladi — bir xil emas (qarang AUDIT_REPORT).

| URL prefiks | Kim |
|---|---|
| `/users/admin/*`, `/users/teachers/*`, `/users/administrators/*`, `/reports/finance/` | Director |
| `/students/*`, `/groups/*`, `/payments/*`, `/users/messages/`, `/users/notifications/`, `/reports/attendance/today/` | Director + Administrator |
| `/users/teacher/*`, `/grades/*` | Teacher |
| `/attendance/mark/<id>/` | Teacher (o'z guruhi) yoki admin |
| `/bot/telegram/webhook/` | Hamma (csrf_exempt; ixtiyoriy maxfiy sarlavha) |
| `/admin/` | Django admin (superuser) |

## 4. Asosiy URL / view lar

- **Auth**: `users/login/` (LoginView), `users/logout/`.
- **Talabalar** `students/`: ro'yxat (20 ta/sahifa, qidiruv), yaratish/tahrirlash (`StudentQuickForm`, bitta guruh tanlanadi), soft-delete (director), API: `check-parent-phone`, `<id>/debt`.
- **Guruhlar** `groups/`: ro'yxat, yaratish/tahrirlash (`Group.clean` — o'qituvchi/xona to'qnashuvi), `add-student`, `delete` (director), `toggle-pause`, `rooms/` (xona jadvali), `edit-lesson` (admin bevosita dars o'zgartirish).
- **To'lovlar** `payments/`: ro'yxat, `new/` (JS sahifa → `api/create/`), qarzdorlar, API: qidiruv, qarz holati, o'chirish (director).
- **Davomat** `attendance/`: belgilash (o'qituvchi faqat dars vaqtida, bir marta), admin override, dars rejasi API.
- **Baholar** `grades/`: kiritish (o'zgartirib bo'lmaydi), ro'yxat, JSON API.
- **Hisobot** `reports/`: moliyaviy hisobot (kassa + hisoblangan), bugungi davomat.
- **Boshqaruv** `users/`: dashboardlar (3 rol), o'qituvchilar/administratorlar CRUD, jarimalar, audit log, jadval o'zgartirish arizalari, murojaatlar, broadcast, bot holati.

## 5. Asosiy biznes oqimlari (qanday ishlaydi)

1. **Talaba qo'shish**: `StudentQuickForm.save()` ism-familiyani bo'ladi, `parent_phone` bo'yicha `Parent` get_or_create; ixtiyoriy bitta guruhga `GroupStudent`. Signal (`payments/signals.py`) balanslarni qayta quradi.
2. **Guruhga qo'shish/chiqarish**: `GroupStudent.is_active`; `pre_save` signal chiqish sanasini (`left_at`) yozadi, qaytganda `BillingPause` oralig'i ochadi. Sig'im tekshiruvi yo'q.
3. **Qarz hisoblash** (`payments/billing.py::sync_pair`): har (talaba, guruh) juftligi uchun oylik `StudentMonthBalance` deterministik qayta quriladi: oy `group.start_date` kuniga qarab `due_date` oladi; pauza/chiqish oylari o'tkaziladi; o'tgan oy narxi "muzlatiladi"; to'lovlar FIFO bo'yicha eng eski qarzdan taqsimlanadi; ortiqcha — kelgusi oylarga (maks. 36) yoki avans. Kunlik job ham ishga tushiradi.
4. **Chegirma**: `Student.get_effective_fee` — foiz yoki qat'iy summa, 0 dan pastga tushmaydi (Decimal).
5. **To'lov qabul qilish** (`payments/services.py::apply_payment`, `@atomic`): tekshiruvlar → `PaymentTransaction` → `sync_pair` → `on_commit` Telegram xabari. O'chirish faqat director, qattiq (hard) delete + qayta taqsimlash.
6. **Davomat**: o'qituvchi faqat o'z guruhi, dars kuni/vaqti ichida, bir marta; `ABSENT` bo'lsa signal orqali ota-onaga Telegram xabari.
7. **Nazorat/jarima**: scheduler har 5 daq.: dars tugagach 15 daq. eslatma, 30 daq. dan keyin `-10` ball avtomatik jarima; director qo'lda ham hal qiladi.
8. **Jadval**: o'qituvchi ariza yuboradi → administrator tasdiqlaydi → faqat shu hafta uchun "override" (guruh o'zgarmaydi); administrator bevosita o'zgartirsa guruhning o'zi o'zgaradi.
9. **O'qituvchi maoshi, Lid → talaba**: **mavjud emas**. Faqat jarima ballari bor.

## 6. Test holati

56 test (payments 39, users1 17); `attendance, grades, groups_app, students, reports, bot` — **0 ta test**. Hozir: 51 o'tdi, 4 xato, 1 muvaffaqiyatsiz, 2 o'tkazib yuborilgan (qarang AUDIT_REPORT §Testlar).
