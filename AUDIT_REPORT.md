# AUDIT HISOBOTI (2-bosqich) — Ilm Najot ERP

Sana: 2026-10-02. Kod **o'zgartirilmagan** (faqat shu hujjat, `PROJECT_MAP.md` va `audit/proof_tests/` qo'shildi).
Production ma'lumotlar bazasiga va `db.sqlite3` ga tegilmadi; testlar vaqtinchalik xotira bazasida ishladi.

**Dalil darajalari**
- **ISBOTLANGAN** — haqiqiy so'rov/chaqiruv bilan test yozib takrorlandi (`audit/proof_tests/`, 15 test, hammasi muammoni tasdiqladi).
- **KOD** — kod o'qib aniq mantiqiy xato topildi, ishga tushirilmadi.
- **TASDIQLANMAGAN** — production muhiti (env, proksi, hosting) ko'rinmasa aniqlab bo'lmaydi.

Format: `[Jiddiylik] | Fayl:qator | Muammo | Nega xato | Taklif`

## Statistika

| Kritik | Yuqori | O'rta | Past | Jami |
|---|---|---|---|---|
| 2 | 15 | 17 | 9 | 43 |

Muvaffaqiyatli tomonlar (o'zgartirish shart emas): `payments/billing.py` deterministik, `Decimal` bilan, `select_for_update` va 39 testga ega; `apply_payment` `@atomic`; soft-delete + audit; `manage.py check` va `makemigrations --check` toza; bandit: 0 yuqori, 1 o'rta.

---

## KRITIK

**[Kritik] K-1 | `users1/views.py:696-715` | `delete_teacher` da autentifikatsiya/rol tekshiruvi umuman yo'q** — ISBOTLANGAN
- Nega xato: boshqa barcha director amallari `is_director` tekshiradi; bu view faqat `@require_http_methods(['POST'])`. Istalgan tizimga kirgan o'qituvchi `POST /users/teachers/<id>/delete/` bilan hamkasbini o'chiradi (`is_active=False` — u endi kira olmaydi). Test: o'qituvchi `t1` boshqa o'qituvchini o'chirdi (302, `is_deleted=True`).
- Tuzatish: `DirectorRequiredMixin` ekvivalenti (`is_director` + `is_blocked`), 403; test. Hamma FBV'lar uchun yagona dekorator (K-1, Y-2 ni birga yopadi).

**[Kritik] K-2 | `bot/services.py:752-754, 354-392`, `bot/views.py:19-22` | Bot kirishi faqat telefon raqami bilan; webhook maxfiy sarlavhasi ixtiyoriy** — ISBOTLANGAN
- Nega xato: `STATE_WAITING_PHONE` holatida har kim matn sifatida istalgan ota-ona raqamini yozsa, `is_verified=True` bo'ladi va bolaning davomati, baholari, **to'lovlari/qarzi** va murojaat yuborish ochiladi (raqam egaligi isbotlanmaydi). `handle_contact` ham `contact.user_id` bo'lmasa (kontaktlar kitobidan yuborilgan karta) tekshiruvdan o'tkazib yuboradi (:312). `TELEGRAM_WEBHOOK_SECRET` bo'sh bo'lsa webhook hamma uchun ochiq va soxta update yuborish mumkin (:19). Test: soxta chat, `/start` + `901112233` → `verified=True, student=Ali Valiyev`.
- Tuzatish: faqat Telegram `request_contact` (va `contact.user_id == from.id` majburiy); matn orqali telefon qabul qilinmasin; webhook sirini majburiy qilish (bo'sh bo'lsa 503) va `hmac.compare_digest`; ota-ona raqami bo'yicha mos kelish aniq (so'nggi 9 raqam `==`, `contains` emas).

---

## YUQORI

**[Yuqori] Y-1 | `erp/settings.py:16,19,21` | Xavfli standart qiymatlar** — KOD / prod env TASDIQLANMAGAN
- `DEBUG` env bo'lmasa `True`; `SECRET_KEY` ochiq repoga yozilgan zaxira qiymat; `ALLOWED_HOSTS` standartida `testserver`. `check --deploy` shu sababli W009 beradi. Prod `.env` ko'rinmaydi — to'g'ri berilgan bo'lsa zarar yo'q, lekin env tushib qolsa jim holda DEBUG=True bo'ladi.
- Tuzatish: `DEBUG` standart `False`, `SECRET_KEY` bo'lmasa ishga tushmasin, `testserver` ni olib tashlash. (Mavjud prod env ni buzmaydi.)

**[Yuqori] Y-2 | `payments/views.py:69,77,176,193,212`, `groups_app/views.py:206,224,276,330`, `students/views.py:179,216,257`, `attendance/views.py:14-22,160,211`, `users1/views.py:1770,1806,1821,975,2033…` | Bloklangan foydalanuvchi hamon ishlaydi** — ISBOTLANGAN
- Nega xato: `is_blocked` faqat mixinlarda (`users1/views.py:279-330`) tekshiriladi; `is_admin_access` va FBV'lar tekshirmaydi, blok qilish sessiyani ham bekor qilmaydi. Test: bloklangan administrator `POST /payments/api/create/` → 201; bloklangan o'qituvchi davomat yozdi.
- Tuzatish: `is_admin_access`/`is_teacher` ichiga `not is_blocked`; yoki middleware (bloklangan → logout); blok qilganda sessiyalarni o'chirish.

**[Yuqori] Y-3 | `attendance/views.py:141-148` | Davomat POST: status va o'quvchi tekshirilmaydi** — ISBOTLANGAN
- `status_<id>` qiymati `AttendanceStatus` ga solishtirilmaydi (`GARBAGE` saqlandi; Postgres'da `max_length` xatosi → 500); `student_id` shu guruh a'zosimi — tekshirilmaydi (o'qituvchi **boshqa guruh o'quvchisiga** `ABSENT` yozdi, signal esa o'sha ota-onaga "farzandingiz kelmadi" xabarini yuboradi). Mavjud bo'lmagan id → `IntegrityError` 500. Modeldagi `clean()` hech qachon chaqirilmaydi.
- Tuzatish: Form/serializer: status choices, student ∈ faol a'zolar, `@atomic`, `full_clean`.

**[Yuqori] Y-4 | `attendance/views.py:228-246` | `save_lesson_plan` IDOR** — ISBOTLANGAN
- Har qanday o'qituvchi istalgan guruhning dars rejasini yozadi/almashtiradi va `teacher` ni o'ziga o'zgartiradi (test: `t1` → `G2` rejasi 'HACK'). Davomat sahifasi `lesson_topic` ni shu rejadan to'ldiradi → ota-onaga Telegram'da ko'rinadi.
- Tuzatish: `group.teacher == user` (admin bundan mustasno).

**[Yuqori] Y-5 | `attendance/views.py:186` | Admin override mavjud davomatni qaytarib bo'lmas o'chiradi** — ISBOTLANGAN
- `session.records.all().delete()` — tasdiqsiz, eski qiymatlar auditga yozilmaydi (`:189-198` faqat guruh/sana). Javob matni "ochildi" deydi. Test: 1 yozuv → 0.
- Tuzatish: o'chirmaslik (qayta kiritishga ruxsat berish), yoki audit'ga eski yozuvlarni snapshot qilish + UI tasdiq.

**[Yuqori] Y-6 | `grades/views.py:80`, `grades/services.py:155-156`, `grades/signals.py:9` | Bo'sh baho 0% bo'lib saqlanadi, o'zgartirib bo'lmaydi, ota-onaga yuboriladi** — ISBOTLANGAN
- `percentage = value if value else '0'`; servis esa barcha o'quvchilar uchun qiymat talab qiladi, shu sabab kelmagan/baholanmagan o'quvchi 0% oladi va "O'tmadi ❌" xabari ketadi; qayta tahrir "allaqachon qo'yilgan" bilan rad etiladi. Signal `@atomic` ichida (xabar yuborilgach rollback bo'lsa ham ketib bo'lgan).
- Tuzatish: bo'sh = baholanmagan (yozuv yaratilmaydi); xabarni `transaction.on_commit` ga; tahrir/qayta kiritish yo'lini (admin) belgilash — **qaror kerak**.

**[Yuqori] Y-7 | `students/views.py:158-160` | Talabani tahrirlash uni boshqa guruhlaridan chiqarib yuboradi** — ISBOTLANGAN
- Forma faqat bitta guruhni (`current_group_id` = birinchisi) oldindan tanlaydi; saqlashda `.exclude(group=group)` bilan **qolgan hamma faol a'zoliklar** o'chiriladi. Telefon raqamini tuzatgan administrator 2 guruhli o'quvchini ikkinchi guruhdan chiqaradi → `left_at` qo'yiladi va **o'sha guruh bo'yicha hisoblash to'xtaydi** (pul yo'qotish). Test: ikki guruhdan biri qoldi.
- Tuzatish: tahrir formasi guruhlarni o'zgartirmasin; guruh boshqaruvi alohida (guruh sahifasi) — UX qayta loyihada.

**[Yuqori] Y-8 | `payments/services.py:185-230`, `payments/views.py:211-227,232-239` | To'lov: idempotentlik yo'q, audit yo'q, qattiq o'chirish** — ISBOTLANGAN (ikki marta) / KOD (audit)
- Bir xil so'rov ikki marta yuborilsa (tarmoq qayta urinishi, ikki tab, mobil) ikkita to'lov yaratiladi (test: 2 ta). `AuditLog` to'lov yaratish/o'chirishda umuman yozilmaydi (`payments/*.py` da yo'q) — kassirning o'zi kiritgan/ o'chirilgan pul izsiz. `delete_payment` yozuvni butunlay o'chiradi (qaytarish/reversal yozuvi yo'q).
- Tuzatish: `idempotency_key` (UUID, unique) + front-end; `AuditLog` yozuvi; o'chirish o'rniga `voided_at/voided_by/void_reason` (soft-void; migratsiya qo'shimcha ustun, ortga qaytariladigan).

**[Yuqori] Y-9 | `payments/services.py:195-199` | To'lov sanasini cheksiz orqaga qo'yish mumkin** — ISBOTLANGAN
- Faqat kelajak taqiqlangan. 2020-yil sanasi bilan to'lov qabul qilindi (201). Yopilgan oylar kassa hisobotini (`reports/views.py:112`) izsiz o'zgartiradi.
- Tuzatish: administratorga N kun (masalan 7) chegarasi, undan ortig'i faqat director; hammasi auditda — **chegara bo'yicha qaror kerak**.

**[Yuqori] Y-10 | `users1/views.py:470-492` | Profil rasmi yuklash: tur/hajm tekshirilmaydi** — ISBOTLANGAN
- `request.FILES['photo']` to'g'ridan modelga beriladi (forma validatsiyasi yo'q): `evil.html` `media/avatars/evil.html` ga saqlandi. Prod'da `/media/` ni kim va qanday xizmat qilishi ma'lum emas (`erp/urls.py:38` faqat DEBUG da) — agar bir origin'dan berilsa saqlangan XSS.
- Tuzatish: `ImageField.clean`/`Pillow.verify`, kengaytma ro'yxati, hajm limiti, tasodifiy fayl nomi, `Content-Disposition`/alohida domen.

**[Yuqori] Y-11 | `bot/services.py:101,122`, `bot/broadcast.py:82`, `bot/management/commands/run_bot.py:22,28,69-71` | Bot tokeni loglarga tushadi** — ISBOTLANGAN (kutubxona xulqi)
- `requests` istisnosi matnida to'liq URL bor: `...Max retries exceeded with url: /bot123456:SECRETTOKEN/sendMessage` (sinab ko'rildi) — `logger.error(f"...{e}")` shu matnni yozadi (fayl logi `logs/attendance_monitor.log` ham bor).
- Tuzatish: istisno matnini tozalash (`str(e).replace(token,'***')`) yoki `logging.Filter`; tokenni URL'da emas — `Session` bilan; mavjud token aylanishi (rotation) tavsiya — **qaror kerak**.

**[Yuqori] Y-12 | `users1/penalty_service.py:188-191` | To'xtatilgan/boshlanmagan guruh uchun o'qituvchi jarimalanadi** — ISBOTLANGAN (to'xtatilgan)
- Filtr faqat `is_active=True`. `is_paused=True` guruh uchun ham ogohlantirish + **−10 ball** (test). Shuningdek `start_date` kelajakda bo'lsa, haftalik override (tasdiqlangan ariza) ham hisobga olinmaydi, shu sabab ko'chirilgan darsga ham jarima ketishi mumkin (KOD).
- Tuzatish: `is_paused=False`, `start_date<=today`, override'ni hisobga olish; jarimani avto-qaytarish skripti (avval dry-run).

**[Yuqori] Y-13 | `users1/services.py:155-158` | Jadval o'zgargani haqidagi Telegram xabarlari hech qachon yuborilmaydi** — ISBOTLANGAN
- `.exclude(student__isnull=True, user__isnull=False)` — `TelegramUser.user` maydoni migratsiya 0007 da olib tashlangan → `FieldError`, keng `except Exception` (:171) yutib yuboradi (test log: `Cannot resolve keyword 'user'`). Ota-onalar dars o'zgarishini hech qachon olmaydi.
- Tuzatish: `.exclude(...)` qatorini olib tashlash + test.

**[Yuqori] Y-14 | `templates/payments/payment_form.html:357-362,391-395,458-462` | Saqlangan XSS** — KOD (brauzerda sinalmagan)
- `innerHTML` ichiga `${s.full_name}`, `${g.name}`, `${d.name}` escape qilinmasdan qo'yiladi. O'quvchi/guruh nomiga `<img onerror=…>` yozgan har qanday administrator direktor/kassir brauzerida kod bajaradi (to'lov API'lari sessiya bilan). Shu naqsh `templates/` da 27 ta `innerHTML` o'rnida.
- Tuzatish: `textContent`/`createElement` yoki umumiy `esc()`; CSP sarlavhasi.

**[Yuqori] Y-15 | `requirements.txt` | Zaif paketlar (pip-audit)** — ISBOTLANGAN
- `pillow 12.2.0` (13 ta advisory → 12.3.0; foydalanuvchi rasmi bilan ishlaydi), `urllib3 2.7.0` (3 → 2.8.0), `sqlparse 0.5.5` (5 → 0.6.0). 
- Tuzatish: versiyalarni yangilash, testlarni ishga tushirish.

---

## O'RTA

**[O'rta] O-1 | `users1/views.py:1451` | `?week_offset=abc` → 500** — ISBOTLANGAN. `int()` himoyasiz; shuningdek 1501-qatorda har dars uchun alohida so'rov (N+1). Tuzatish: try/except + clamp; `override` larni oldindan yuklash.

**[O'rta] O-2 | `users1/views.py:1360`, `templates/groups_app/group_list.html:89` | "O'quvchilar soni" noto'g'ri** — KOD. `group.students.count()` M2M `through` orqali **nofaol/chiqib ketgan a'zolarni ham** sanaydi va har guruhga alohida so'rov. Tuzatish: `annotate(Count('groupstudent', filter=Q(groupstudent__is_active=True)))`.

**[O'rta] O-3 | Jadval o'zgartirish arizalari (bir nechta mantiqiy xato)** — KOD
 1. `users1/views.py:226` — o'qituvchi faqat vaqt/xonani o'zgartira olmaydi: `new_day == old_day` bo'lsa xato (forma standarti shu kun).
 2. `users1/views.py:177,182` — `room` maydoni forma maydoni, model maydoni emas; saqlanmaydi — xona so'rovi jimgina tashlanadi.
 3. O'qituvchi arizasida ham, tasdiqlashda ham (`users1/views.py:1283-1333`) `validate_schedule_change` chaqirilmaydi → arizadan keyin paydo bo'lgan to'qnashuv tekshirilmaydi; tasdiqlash `@atomic`/blok'siz (ikki admin birdaniga).
 4. `groups_app/views.py:436-449` — "1 kun uchun" deb yozilgan `admin_edit_lesson` guruhning **doimiy** vaqt/xonasini o'zgartiradi.
 5. `groups_app/views.py:416-434` — `group.teacher` yoki `lesson_time` bo'sh bo'lsa `IntegrityError` → 500.
 Tuzatish: bitta `schedule_service` (validatsiya + atomic), formani qayta yozish.

**[O'rta] O-4 | Telegram xabar yuborish arxitekturasi** — KOD
 - `attendance/signals.py:5-12` har `save()` da (admin tahriri, `update_or_create`) qayta "kelmadi" xabari; `except: pass` xatoni yutadi.
 - Barcha yuborishlar so'rov ichida sinxron, `timeout=10-15s` × ota-onalar soni (`bot/broadcast.py:99`, `attendance`, `users1/views.py:1867`) → gunicorn 30s timeout.
 - `users1/views.py:1790-1796,1854,1912`, `bot/notifications.py` — foydalanuvchi matni `parse_mode=HTML` ga escape'siz; `<` bo'lsa Telegram 400 beradi va xato yutiladi.
 - `users1/views.py:1780-1798` — `is_resolved=True` yuborishdan oldin qo'yiladi, xato yutiladi, lekin "yuborildi" deb javob qaytadi.
 Tuzatish: navbat (DB outbox + scheduler) yoki kamida `on_commit` + `html.escape` + natijani qaytarish.

**[O'rta] O-5 | Xatolik matnlari va status kodlar** — KOD. `payments/views.py:136,188,226` va `grades/views.py:97,166,184`, `users1/views.py:988`: `except Exception as e: str(e)` — ichki xato foydalanuvchiga chiqadi; `PermissionDenied`/`Http404` ham 400 bo'ladi; kutilmagan xato 500 emas 400. Tuzatish: aniq istisnolar, qolganini loglash.

**[O'rta] O-6 | `bot/views.py:29` | Webhook'da `handle_update` istisnosi → 500** — KOD. Telegram 500 ni qayta-qayta jo'natadi (xabar takrorlanadi). Tuzatish: try/except + doim 200, update_id dedup.

**[O'rta] O-7 | Autentifikatsiya** — KOD. Loginda urinishlar limiti yo'q (`users1/views.py:350`); parol uzunligi qoidalari mos emas: forma 8 (`:130`), qolgan joylarda 6 (`:457,584,680,759`), `AUTH_PASSWORD_VALIDATORS` maxsus oqimlarda ishlatilmaydi (administrator yaratishda hatto 1 belgi, `:521`); `get_client_ip` birinchi `X-Forwarded-For` ni ishonib oladi (`:38-42`, audit IP soxtalashadi). Tuzatish: `django-axes`/oddiy throttle, `validate_password`, ishonchli proksi.

**[O'rta] O-8 | Ma'lumotlar bazasi cheklovlari yo'q** — KOD. `PaymentTransaction.amount` `MinValue(0)` (0 mumkin, DB `CheckConstraint` yo'q: `payments/models.py:147`); `GroupStudent` `left_at >= joined_at`, `Group` `end_time > lesson_time` cheklovi yo'q; `Student.phone` unique emas → takroriy talabalar; guruh sig'imi tushunchasi umuman yo'q; `Group.clean()` faqat Django formalarida (race-condition: ikki admin bir vaqtda bir xonani band qilishi mumkin). Tuzatish: `CheckConstraint`lar (mavjud ma'lumotni avval dry-run bilan tekshirib), xona/o'qituvchi uchun tranzaksiya+lock.

**[O'rta] O-9 | Indekslar yo'q** — KOD. Hisobot va ro'yxatlarda filtrlanadi, lekin indeks yo'q: `PaymentTransaction.payment_date`, `(student, group)`; `AttendanceSession.date`; `AuditLog.created_at`; `TelegramUser.phone`. (Faqat `StudentMonthBalance.due_date` indekslangan.) Tuzatish: qo'shimcha `Meta.indexes` (xavfsiz, qaytariladigan).

**[O'rta] O-10 | Sahifalash va og'ir so'rovlar** — KOD. Sahifasiz: guruhlar (`groups_app/views.py:92`), qarzdorlar (`payments/views.py:140,153`), o'qituvchilar, audit log (faqat `[:100]`, qidiruvsiz); `users1/notifications.py:56-60` — **har bir admin sahifasi** ochilganda 3 ta so'rov + `missing_attendance_groups()` (context processor) ishlaydi; dashboardlarda 10+ `count()`. Tuzatish: pagination, qisqa muddatli kesh.

**[O'rta] O-11 | `users1/penalty_service.py:258-266,313-324` | "Ketma-ket" jarima aslida ketma-ket emas** — KOD. Oxirgi 5 ta `NOT_CAME` ni sanaydi (sanalar ketma-ketligi va oradagi muvaffaqiyatli darslar hisobga olinmaydi) → 3-chi umumiy "kelmadi"dan boshlab har safar qo'shimcha −10. `:154` da avto-jarima turi `CONSECUTIVE_MISSED` deb noto'g'ri belgilanadi. Tuzatish: haqiqiy ketma-ketlikni hisoblash — **qoida bo'yicha qaror kerak**.

**[O'rta] O-12 | `groups_app/views.py:206-218, 223-243` | Guruhga qo'shishda tekshiruv yo'q** — KOD. Faol/o'chirilgan o'quvchi, `LEFT`/`FROZEN` status, guruh `is_active` tekshirilmaydi; `get_or_create` ro'yxatdan o'chirilgan o'quvchini ham jim qayta faollashtiradi; sig'im yo'q; `add_student_to_group` GET'da `redirect('users1:login')` (`:208`) noto'g'ri. Tuzatish: servis funksiya + `@atomic`.

**[O'rta] O-13 | `Procfile`, `erp/apps.py:8-34`, `erp/scheduler.py:68-89` | Scheduler ikki marta ishlashi mumkin** — TASDIQLANMAGAN. `web` jarayoni (`ready()`) ham, `clock` jarayoni ham scheduler ishga tushiradi; qulf faqat `127.0.0.1` porti (bitta host ichida). Alohida dynolarda (Heroku/Render) ikkalasi ishlaydi. Mavjud himoya (`select_for_update`) jarimani ikki marta bermaydi, lekin Telegram xabarlari/ish takrorlanadi. Tuzatish: `DISABLE_WEB_SCHEDULER=True` ni web'da majburan.

**[O'rta] O-14 | Deploy sozlamalari** — TASDIQLANMAGAN. (a) `.env.example` `SECURE_SSL_REDIRECT=True` bergan, lekin `SECURE_PROXY_SSL_HEADER` yo'q → proksi ortida cheksiz redirect; `CSRF_TRUSTED_ORIGINS` yo'q. (b) `erp/settings.py:186` `FileHandler(logs/…)` — `.gitignore` `*.log` ni o'tkazib yuboradi, `logs/` papkasi tozalangan klonda yo'q bo'lishi mumkin → ishga tushishda `FileNotFoundError`. (c) `/media/` faqat DEBUG'da beriladi (avatar prod'da 404 bo'lishi mumkin). Tuzatish: papkani yaratish/konsol logiga o'tish, headerlar.

**[O'rta] O-15 | Testlar** — ISBOTLANGAN. 56 ta: **4 ta xato** (`Missing staticfiles manifest entry for 'images/logo.png'` — `CompressedManifestStaticFilesStorage` testda `collectstatic`siz ishlamaydi: `users1/tests.py` MissedAttendanceWorkflowTestCase/ScheduleChangeRequestFormTestCase), **1 ta muvaffaqiyatsiz** (`users1/tests.py:134` — bugungi hafta kuniga bog'liq, vaqt o'tgan sayin tasodifiy), 2 ta `skipTest`. `attendance, grades, groups_app, students, reports, bot` ilovalarida **0 test**; ruxsatlar (RBAC) uchun test yo'q. Tuzatish: test `STORAGES` override, sana muzlatish, yuqoridagi dalil testlarini regressiya testiga aylantirish.

**[O'rta] O-16 | Audit izi to'liq emas** — KOD. AuditLog yozilmaydi: to'lov yaratish/o'chirish (Y-8), talaba yaratish/tahrir/**chegirma o'zgarishi** (`students/views.py:122-168`), guruh o'chirish va to'xtatish (`groups_app/views.py:255,275`), a'zolik o'zgarishi. Chegirma pulga bevosita ta'sir qiladi. Tuzatish: servis qatlamida yagona `audit()`.

**[O'rta] O-17 | O'lik/ishlamaydigan funksiyalar** — KOD. `penalty_service.py:58-66`: admin va o'qituvchi Telegram foydalanuvchilari doim bo'sh → eslatma/jarima xabari hech kimga bormaydi (`reminders_sent` har doim 0); `send_payment_reminders` hech qaysi jadvalga ulanmagan (faqat qo'lda); `bot/services.py:250` bo'sh `link_user_by_phone`. Tuzatish: qaror kerak (qayta yoqish yoki o'chirish).

---

## PAST

- **[Past] P-1** `attendance/views.py:26,28,95,96`: `date.today()/datetime.now()` (server vaqti) o'rniga `timezone.localdate()`; `users1/services.py:26` `timezone.now().date()` (UTC sanasi); `groups_app/views.py:480` `timezone.timedelta` (tasodifiy import). Linuxda Django `TZ` ni o'rnatgani uchun ko'rinmaydi, Windows/konteynerda xato beradi. — KOD
- **[Past] P-2** Axlat/xavfli fayllar: `check_db.py` (boshqa kompyuter yo'li), `.mimocode/` (6 reja fayli), `__pycache__/`, `server_*.txt`, `db.sqlite3` (282 KB, PII bo'lishi mumkin — arxivda tarqatilmasin), bo'sh `reports/models.py`, stub `index` view'lar (`grades/views.py:102`, `bot/views.py:12`), ishlatilmaydigan `openpyxl`.
- **[Past] P-3** Pul yig'indilarida `float`: `users1/views.py:1703`, `bot/services.py:481`, `students/views.py:273` (ko'rsatish uchun; hisob `Decimal`). `Student.get_effective_fee` va billing to'g'ri.
- **[Past] P-4** `reports/views.py:51,87`: `?month=9999-12` → `add_months` `ValueError` 500; `_percent` kutilgan 0 bo'lsa 100% ko'rsatadi.
- **[Past] P-5** `bot/management/commands/run_bot.py:22` `requests.get` timeoutsiz (bandit B113); webhook sir solishtirish `!=` (konstanta vaqtda emas) `bot/views.py:21`.
- **[Past] P-6** Aloqa ma'lumotlari (manzil, telefon, @username) kodga qotirilgan `bot/services.py:614-621`.
- **[Past] P-7** Takrorlanish: dars tugash vaqti/overlap mantiqi 5 joyda (`groups_app/models.py:60-126`, `users1/services.py:42-105`, `users1/views.py:54-92`, `groups_app/views.py:389-399`, `penalty_service.py:28-37`); rol satrlari (`'TEACHER'`) va hafta kunlari ro'yxati 8+ joyda.
- **[Past] P-8** `students/views.py:21-32` Parent telefoni normallashtirish `998`+9 raqam, `check_parent_phone` (:224-232) va `bot` boshqacha (so'nggi 9) — mos kelmaslik.
- **[Past] P-9** `users1/views.py:1704-1707` ko'rsatish: `sorted(...)[0]` bo'sh bo'lsa himoyalangan (`if`) — OK; `get_student_debt` `float(total_debt)` (:273) — Decimal bo'lishi kerak.

---

## C) Frontend / UX topilmalari

- `templates/base.html` (976 qator) barcha CSS/JS ni ichiga olgan; 0 ta umumiy CSS/JS fayl, har sahifada alohida inline `<style>` — dizayn tizimi yo'q, ranglar va tugmalar nomuvofiq.
- Tungi/kunduzgi rejim bor, lekin standart doim `dark` (`base.html:948`), `prefers-color-scheme` o'qilmaydi; fon gradient/shisha (glass) effektlari (`base.html:51-56`); kontrast WCAG bo'yicha tekshirilmagan.
- Tashqi CDN (Google Fonts, FontAwesome) ga bog'liqlik — oflayn/sekin tarmoqda sahifa buziladi, CSP qo'yib bo'lmaydi.
- To'lov qabul qilish oqimi (`payment_form.html`, 613 qator JS): qidirish → talaba → guruh → qarz → to'lov turi → sana → summa — 5-6 qadam; sana qo'lda `KK.OO.YYYY` niqoblanadi. `parseFloat` bilan summa.
- Ro'yxatlarda sahifalash/tartiblash/filtr yo'q (guruhlar, qarzdorlar, o'qituvchilar); bo'sh holat xabarlari bir xil emas.
- Mobil: pastki navigatsiya bor, lekin jadvallar uchun moslashuv tekshirilmagan; Director menyusida "Talabalar/Guruhlar/To'lovlar" bor, "Qarzdorlar" alohida havola yo'q (faqat to'lovlar ichidan).
- Accessibility: `aria-label`lar faqat tema tugmasida; ikonka-faqat tugmalar, forma xatolari `aria-describedby`siz; `onclick` inline (`confirm()`) — yagona modal yo'q.
- O'chirish tasdig'i bir xil emas (`delete_group`, `delete_teacher`, `delete_payment` turlicha).

---

## Taklif qilinadigan tuzatishlar rejasi (3-bosqich, tasdiq kutiladi)

Tartib: Kritik → Yuqori → O'rta. Har biri alohida commit, avval dalil testi (`audit/proof_tests/` dan regressiya testiga ko'chiriladi) so'ng tuzatish.

| # | Paket | Topilmalar | Ma'lumotga ta'siri |
|---|---|---|---|
| 1 | Ruxsatlar (yagona dekorator + `is_blocked`) | K-1, Y-2, Y-4 | Yo'q |
| 2 | Bot xavfsizligi | K-2, Y-11, O-6 | Mavjud `is_verified` bog'lanishlar qayta tasdiqlanishi kerak bo'lishi mumkin — **qaror** |
| 3 | Davomat/baho validatsiyasi | Y-3, Y-5, Y-6 | Yo'q (mavjud 0% baholarni ro'yxatlash dry-run skripti) |
| 4 | To'lov yaxlitligi | Y-8, Y-9, O-8 (amount>0), O-16 | Migratsiya: `idempotency_key` (null), `voided_*` ustunlari — qo'shimcha, qaytariladigan |
| 5 | Talaba/guruh a'zoligi | Y-7, O-12, O-2 | Yo'q; xato bilan chiqarilgan a'zoliklarni topish dry-run skripti |
| 6 | Jarima/jadval mantiqi | Y-12, Y-13, O-3, O-11 | Noto'g'ri berilgan jarimalar ro'yxati (dry-run, o'zgartirmasdan) |
| 7 | Fayl yuklash, XSS, sozlamalar | Y-1, Y-10, Y-14, Y-15, O-7, O-14 | Yo'q |
| 8 | Tezlik/indekslar/sahifalash/testlar | O-1, O-9, O-10, O-15, Past | Migratsiya: faqat indekslar |

## Menga qaror kerak bo'lgan savollar

1. **Git**: papka git repozitoriy emas (`.git` yo'q). Branch ochish uchun `git init` qilib, hozirgi holatni `baseline` commit sifatida saqlab, `audit-and-redesign` branchida ishlashimga ruxsat berasizmi?
2. **Productiondagi `.env`**: `DEBUG`, `SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `DB_*` qanday? (qiymatlarni yozmang — faqat o'rnatilganmi yo'qmi.) Hosting turi (Heroku/Render/VPS+nginx)? Media qaysi yo'l bilan beriladi?
3. **Bot kirishi** (K-2): faqat Telegram "kontakt yuborish" tugmasi qoladi (matn orqali telefon kiritish olib tashlanadi) — qabul qilasizmi? Mavjud tasdiqlangan ota-onalar qayta tasdiqlashi shartmi?
4. **Baholar** (Y-6): bo'sh baho = "baholanmagan" bo'lsinmi? Xato kiritilgan bahoni kim va qanday tuzatadi (faqat administrator audit bilan)?
5. **To'lov sanasi** (Y-9): administrator necha kun orqaga qo'ya olsin (taklif: 7 kun; undan ortig'i faqat director)?
6. **To'lovni o'chirish** (Y-8): "bekor qilingan" holat (soft-void) bilan almashtiramizmi? Mavjud o'chirish URL'i saqlanadi.
7. **Ketma-ket jarima qoidasi** (O-11): aniq qoida qanday? (masalan, ketma-ket 3 ta dars, oradan muvaffaqiyatli dars bo'lsa tiklanadi.) Noto'g'ri berilgan avvalgi jarimalar qaytarilsinmi?
8. **To'xtatilgan guruhlar uchun berilgan jarimalar** (Y-12) bor-yo'qligini dry-run bilan topib, ro'yxatini sizga ko'rsatamiz — qaytarish sizning qaroringizda.
9. **Mavjud emas funksiyalar**: Kurs, Lid (lead → talaba), O'qituvchi maoshi, Kassir roli, guruh sig'imi. Redizayn sahifalarida (Lidlar, Sozlamalar...) ular uchun faqat bo'sh maket qilinsinmi yoki bu alohida loyiha? "Mavjud funksiyalar o'zgarmasin" qoidasiga ko'ra ularni **qo'shmayman**, faqat tasdiqlasangiz.
10. **Redizayn texnologiyasi**: hozirgi Django shablonlari + oddiy CSS (tokenlar) saqlansinmi (taklif: ha, framework'siz, bitta `static/css/app.css` va `static/js/app.js`)?
11. **`db.sqlite3`, `.mimocode/`, `check_db.py`** kabi fayllarni repodan chiqarish (o'chirmasdan `.gitignore` ga qo'shish) mumkinmi?
