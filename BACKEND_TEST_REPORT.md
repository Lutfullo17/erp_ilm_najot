# BACKEND TEST HISOBOTI (QA 1–2-bosqich)

Branch `redesign-ux`. Test faqat test bazasida (xotira SQLite), lokal demo bazada (`seed_demo`) va **scratch nusxadagi** katta ma'lumotda o'tkazildi. Production bazasiga tegilmadi. Yangi topilmalar hali **tuzatilmagan** (4-bosqichda tasdiq kutiladi); har biri `expectedFailure` testi bilan takrorlanadi (`ux/test_qa_known_bugs.py`, `ux/test_qa_fuzz.py`).

## 1. Test muhiti
| Narsa | Natija |
|---|---|
| Mavjud (eski) testlar | 56 ta: 54 o'tdi, 2 `skipTest` (vaqtga bog'liq, eski). **Qoplama: 42 %** (hozirgi kod bazasi bo'yicha) |
| Hozirgi to'plam | **203 ta test**: 192 o'tdi, 2 skip, **9 ta `expectedFailure`** (ma'lum xatolar). **Qoplama: 76 %** (`coverage`) |
| Test tezligi | 800 s → **18 s** (testlarda MD5 xesh; PBKDF2 sekin edi) |
| Rollar | Direktor, Administrator, O'qituvchi. **"Menejer", "kassir" (alohida rol) va "lid" tizimda mavjud emas** — sinalmadi (kassir vazifasini administrator bajaradi) |
| Namunaviy ma'lumot | `seed_demo`: 22 o'qituvchi, 3 administrator, 22 guruh, 64 o'quvchi, 67 to'lov, 55 qarzdor, 218 davomat, 74 baho, 25 jarima, 20 ariza |
| Katta ma'lumot (scratch nusxa) | 5 000 o'quvchi, 80 guruh, 50 000 to'lov, ~5 000 oylik hisob |
| Eski va yangi UI parallel | Ikkalasi ham ishga tushirildi: `/users/...` (eski) va `/new/...` (yangi), cookie/flag orqali almashadi (test: `HomeAndSwitchTests`) |

**Tekshirilmadi:** PostgreSQL (lokal yo'q) — parallel so'rovlar (race) va `select_for_update` xulqi faqat kod orqali ko'rib chiqildi, haqiqiy parallel testi o'tkazilmadi (SQLite yozuvlarni ketma-ket bajaradi). Haqiqiy Telegram yuborish (token yo'q).

## 2. Nimalar sinaldi va natijasi
| Soha | Qanday | Natija |
|---|---|---|
| Ruxsat matritsasi | `ux/test_qa_matrix.py`: **barcha nomli URL (~140)** × 4 rol (anonim, o'qituvchi, administrator, direktor) × GET/POST | 500 faqat QA-B-01; anonim hech qaysi himoyalangan sahifani ocha olmaydi (QA-B-02 dan tashqari); o'qituvchi administrator, administrator direktor sahifalarini ocha olmaydi |
| CSRF | CSRFsiz POST hamma URLga (webhook/login/logout dan tashqari) | Hammasi 403 — **o'tdi** |
| IDOR | Boshqa o'qituvchining guruhi/o'quvchisi/baholari (eski + yangi URL), boshqa administratorning to'lovi (kvitansiya, bekor qilish, o'chirish), o'chirilgan o'quvchi ID | **o'tdi** (QA-B-05 holati 500, lekin ma'lumot sizmaydi) |
| XSS | `<script>` va `"><img onerror>` ni o'quvchi/guruh/o'qituvchi/murojaat/audit/fikr/izoh maydonlariga yozib, 24 ta sahifani render qildim | **o'tdi** (hamma escape qilingan); JSON javoblar `application/json` + `nosniff` |
| SQL injection | `' OR 1=1 --` va boshqa matnlar barcha qidiruv/filtr/JSON maydonlarida | ma'lumot sizmadi, buzilmadi (ORM). Faqat tur xatolari 500 beradi (QA-B-03/N-01/N-02) |
| Sessiya/cookie | `HttpOnly`, `SameSite=Lax`, `X-Frame-Options: DENY`, `nosniff`; bloklangan/o'chirilgan foydalanuvchi kira olmaydi; parol tiklangach eski sessiya yaroqsiz | **o'tdi** |
| Login | 5 muvaffaqiyatsiz urinishdan keyin bloklanadi; xato matni login mavjudligini bildirmaydi | **o'tdi** (QA-B-12 ga qarang) |
| Pul yaxlitligi | `payments/test_qa_money.py` (19 test): noto'g'ri summalar (0, manfiy, NaN, Infinity, 10¹⁰), chegirma yaxlitlash, tasodifiy 6×25 amal ketma-ketligida "to'lovlar = taqsimot = oylik to'langan" invarianti, o'chirish holatni aniq tiklaydi, to'lov tartibi kiritish tartibiga bog'liq emas, ikki marta qo'shish (`unique`), sobiq a'zo ortiqcha to'lovi rad etiladi, **Asia/Tashkent**: 31-okt 19:30 UTC = 1-noyabr 00:30, oy oxiri (28/29/30/31), yil chegarasi | **hammasi o'tdi** (yangi pul xatosi topilmadi) |
| Hisobot | Kassa jami = oy to'lovlari yig'indisi; "shu oy + oldingi + oldindan" = jami | o'tdi |
| Fuzz | 22 ta JSON endpoint × ~20 maydon × 23 xil yolg'on qiymat; 19 ta GET sahifa × parametrlar × 15 qiymat | QA-B-03, QA-N-01..03 (pastda) |
| Statik tahlil | `manage.py check --deploy` (production env: DEBUG=False, SECRET_KEY, SSL) | **toza**. (Lokal `.env` da `DEBUG=True` bo'lgani uchun W018 chiqadi — kutilgan) |
| | `bandit` | O'rta+ **0 ta**; past: 6 `try/except/pass`, test parollari |
| | `pip-audit` | **toza** |
| | `flake8` (xatolik turlari) | ~30 ta ishlatilmagan import/o'zgaruvchi (Past) |
| Migratsiya | Toza bazada va ma'lumot nusxasida oldinga, `ux zero` va `payments 0004` ga orqaga, qayta oldinga; `makemigrations --check` | **o'tdi** |
| Samaradorlik | Katta ma'lumotda 31 sahifa (qarang §4) | QA-B-08, -10, -11 |

## 3. Topilmalar
Format: **[Jiddiylik] | Fayl:qator | Qanday takrorlanadi | Kutilgan va haqiqiy | Taklif**

**[Yuqori] QA-B-04 | `templates/users1/admin_dashboard.html:116`, `templates/new/payments.html`, `templates/new/receipt.html` | `created_by` bo'sh (NULL) to'lov yarating (model `null=True`: Django admin/import/skript orqali mumkin) → direktor `/users/admin/` (eski bosh sahifa), `/new/payments/?p=all`, `/new/payments/<id>/receipt/` | Kutilgan: sahifa ochiladi ("—"). Haqiqiy: **500** (`default:p.created_by.username` argumenti `None.username` da `VariableDoesNotExist`). Katta ma'lumotda isbotlandi (50 000 NULL to'lov) | Shablonda `{{ p.created_by.get_full_name|default:"—" }}` ko'rinishiga o'tkazing yoki `{% if p.created_by %}`. Test: `test_QA_B04…`
**[O'rta] QA-B-03 | ~25 JSON endpoint: `payments/services.py::parse_money`, `payments/views.py:create_payment`, `ux/views_pay.py::api_pay_create`, `ux/views_students.py::api_student_group`, `users1/views.py` (broadcast, penalty, profile…), `groups_app/views.py::admin_edit_lesson` | `POST /payments/api/create/ {"amount":"1e999"}` yoki `amount: 10**30`, `student_id:"abc"`, tana `[]`/`null`/`123`, `message: 123` | Kutilgan: 400 + aniq xabar. Haqiqiy: **500** (`decimal.InvalidOperation`, `AttributeError: 'list' has no attribute 'get'`, `ValueError`). To'lov formasiga 30 xonali son yozsa ham 500 | Yagona `json_body()` + tur tekshiruvi (`isinstance(dict)`), `parse_money` da `InvalidOperation` ni ushlash, id larni `int()` bilan tekshirish. Testlar: `test_QA_B03…`, `FuzzTests`
**[O'rta] QA-N-01 | `ux/utils.py::paginate` | Yangi UI ning har qanday ro'yxatida `?page=abc` (students, groups, payments, debtors, messages, telegram, log) | Kutilgan: 1-sahifa. Haqiqiy: **500** (`PageNotAnInteger` ushlanmaydi) | `InvalidPage` ni ushlash. Test: `test_QA_N01…`
**[O'rta] QA-N-02 | `ux/views_students.py`, `ux/views_pay.py` | `?group=99999999999999999999` (qo'lda yozilgan/eski havola) | **500** (`OverflowError`/DB diapazon xatosi) | id ni `int` ga o'tkazib, diapazonni cheklash. Test: `test_QA_N02…`
**[O'rta] QA-B-06 | `groups_app/models.py:129-143`, `payments/models.py` | ORM bilan `left_at < joined_at` yoki `PaymentTransaction(amount=0)` saqlash; guruh sig'imi (`capacity`) tushunchasi yo'q | Kutilgan: DB/model rad etadi. Haqiqiy: saqlanadi (`test_left_before_joined…`, `test_no_group_capacity…`) | `CheckConstraint`lar (avval prod'da mavjud ma'lumotni tekshirish so'rovi bilan); sig'im — **biznes qarori**
**[O'rta] QA-B-08 | `users1/views.py::AdminDashboardView` (eski direktor bosh sahifasi) | 5 000 o'quvchi/50 000 to'lov bilan `/users/admin/` | 500 ga yetguncha **207 so'rov, 895 ms** (N+1: qarzdorlar guruhlash, har guruh uchun alohida so'rovlar) | `select_related/annotate`, kesh; yangi UI da 12 so'rov / 114 ms
**[O'rta] QA-B-10 | `payments/views.py::DebtorListView`, `GroupDebtorView` (eski) | `/payments/debtors/` 5 000 o'quvchida | Sahifalashsiz, **1 509 ms** (yangi UI: 46 ms, sahifalangan). `/users/teachers/` 34 so'rov (30 o'qituvchiga N+1) | Eski sahifalarga `paginate_by`; `annotate`
**[O'rta] QA-B-12 | `erp/settings.py` | Sessiya muddati standart 2 hafta, bo'sh turganda tugamaydi; login limiti `LocMemCache`da (har gunicorn jarayoni alohida hisoblaydi) | Umumiy kassa kompyuterida tizimdan chiqmagan foydalanuvchi 2 hafta kirgan holda qoladi; limit workerlar soniga ko'payadi | `SESSION_COOKIE_AGE` (masalan 12 soat), umumiy kesh (Redis/DB) — **qaror kerak**
**[O'rta] QA-B-13 | `users1/views.py::broadcast_to_group/broadcast_all`, `bot/broadcast.py` | Ko'p ota-onali guruhga xabar | Telegram so'rovlari so'rov ichida ketma-ket (10 s timeout) → gunicorn 30 s dan oshsa yarim yuboriladi, foydalanuvchi xato ko'radi. **Kod bo'yicha; Telegram yo'qligi uchun ishga tushirilmadi** | Orqa fon navbati (jadvaldagi job yoki `outbox` jadvali) — backend qarori
**[Past] QA-B-01 | `users1/views.py::AdministratorCreateView` | Direktor `GET /users/administrators/new/` | **500** (`users1/administrator_form.html` yo'q) | `get()` → ro'yxatga redirect. Test: `test_QA_B01…`
**[Past] QA-B-02 | `students/views.py::check_parent_phone` | Anonim/o'qituvchi `GET /students/api/check-parent-phone/` | 403 o'rniga bo'sh `{"siblings": []}` 200 (ma'lumot sizmaydi) | 403 qaytarish
**[Past] QA-B-05 | `grades/views.py:165,183` | O'qituvchi boshqa guruhga `GET /grades/teacher/groups/<id>/?date=…` | 404 o'rniga **500** ("Kutilmagan xatolik") — `except Exception` `Http404` ni yutadi. Ma'lumot sizmaydi | `Http404` ni alohida ushlash. Test: `test_QA_B05…`
**[Past] QA-B-07 | `payments/services.py::parse_money` | `"1e3"` → 1000.00 qabul qilinadi; `100.555` → 100.56 (banker yaxlitlash); 0.01 so'm to'lov mumkin | Hujjatlangan xulq (`test_scientific_notation_accepted`) | Minimal summa (masalan 1 000 so'm) va ilmiy yozuvni rad etish — qaror
**[Past] QA-B-09 | `ux/views_staff.py::PersonForm` | Yangi xodim paroli `t1t1t1t1` (loginga o'xshash) | Qabul qilinadi: `validate_password` ga `user` berilmaydi (o'xshashlik tekshiruvi ishlamaydi) | Vaqtinchalik `User(username=…)` ni uzating
**[Past] QA-B-11 | `ux/views_reports.py` | 5 000 o'quvchi, 80 guruh: `/new/reports/` **725 ms**, eski `/reports/finance/` 262 ms (bir xil 17 so'rov) | Shablon render sekinroq | Profilga olish; kerak bo'lsa 12 oylik jadvalni soddalashtirish
**[Past] QA-B-14 | Kod sifati | `flake8`: ~30 ishlatilmagan import/o'zgaruvchi; ikki marta aniqlangan `create_audit_log` (`students/views.py:8,191`) | — | Tozalash
**[Ma'lumot] QA-B-15 | `ux/` | `ux/__init__.py` yo'q edi → standart `manage.py test` yangi testlarni **topmadi** (107 ta, 50 ta ux testi o'tkazib yuborilardi) | **Tuzatildi** (fayl qo'shildi, commit `77803ca`); CI da test soni kuzatilsin

## 4. Samaradorlik (5 000 o'quvchi · 50 000 to'lov · SQLite, bitta so'rov)
| Sahifa | So'rovlar | ms |
|---|---|---|
| Eski administrator bosh sahifa | 16 | 24 |
| **Eski direktor bosh sahifa** | 207+ | **895 → 500 (QA-B-04)** |
| Yangi Bugun (admin / direktor / o'qituvchi) | 10 / 12 / 6 | 55 / 114 / 6 |
| Eski qarzdorlar (sahifasiz) | 4 | **1 509** |
| Yangi qarzdorlar (1-sahifa / 40-sahifa) | 5 | 46 / 49 |
| Hisobot: eski / yangi | 17 / 17 | 262 / 725 |
| O'quvchilar: eski / yangi / "faqat qarzdor" | 7 / 8 / 8 | 117 / 36 / 143 |
| To'lovlar ro'yxati, qidiruv | 3–4 | 10–13 |
| Qidiruv API (global / to'lov) | 4 | 9–10 |
| Davomat ro'yxati, mening guruhlarim | 4–5 | 10–46 |
| Eski o'qituvchilar ro'yxati | **34** (N+1) | 63 |

Indekslar (oldingi bosqichda qo'shilgan `payment_date`, `(student, group)`, `session.date`) ishlayapti: 50 000 to'lovda filtrlar < 15 ms. Kunlik `sync_all(active_only=True)` 5 000 juftlik uchun ~100–125 s (SQLite) — tungi job uchun maqbul, lekin PostgreSQL'da qayta o'lchash tavsiya etiladi.

## 5. Tekshirilmadi
- Parallel so'rovlar / `select_for_update` (PostgreSQL kerak).
- Telegram yuborish/qabul qilish (haqiqiy token yo'q): faqat mock bilan.
- Fayl yuklash: faqat profil rasmi (oldingi bosqichda sinalgan; yangi UI da yangi yuklash yo'q).
- Cookie `Secure`, HSTS: `check --deploy` orqali; haqiqiy HTTPS proksi ortida tekshirilmadi.
- Production ma'lumotidagi mavjud nomuvofiqliklar (qarang FINAL_REPORT §5 so'rovlari) — prod bazaga kirish yo'q.
