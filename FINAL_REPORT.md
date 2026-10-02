# YAKUNIY HISOBOT — audit, backend tuzatish, UI qayta loyihalash

Branch: `audit-and-redesign` (baseline: `main` = auditdan oldingi holat). 12 ta commit, har biri alohida mavzuda.
Tekshiruv: 107 test o'tdi (2 ta eski `skipTest`), `manage.py check --deploy` toza, `pip-audit` toza, bandit (o'rta+) toza, migratsiyalar toza bazada va eski `db.sqlite3` nusxasida oldinga va orqaga sinaldi.

## 1. Topilmalar statistikasi (AUDIT_REPORT.md)

| Kritik | Yuqori | O'rta | Past | Jami |
|---|---|---|---|---|
| 2 | 15 | 17 | 9 | 43 |

## 2. Nima tuzatildi

| Topilma | Holat | Commit mavzusi |
|---|---|---|
| K-1 `delete_teacher` ruxsatsiz | tuzatildi + test | fix(security): require director… |
| K-2 bot telefon bilan kirish, webhook sirsiz | tuzatildi + test | fix(bot): … |
| Y-1 xavfli standart sozlamalar | tuzatildi | fix(security): safe settings… |
| Y-2 bloklangan sessiya | tuzatildi (middleware) + test | |
| Y-3 davomat validatsiyasi | tuzatildi + test | fix(attendance,grades) |
| Y-4 dars rejasi IDOR | tuzatildi + test | |
| Y-5 override o'chirishi | audit snapshot bilan xavfsizlandi + test | |
| Y-6 bo'sh baho = 0% | tuzatildi + test | |
| Y-7 tahrirda a'zolik yo'qolishi | tuzatildi + test, "guruhdan chiqarish" tugmasi qo'shildi | fix(groups,students) |
| Y-8 to'lov idempotentligi / audit | idempotency_key + 60 s himoya + audit (soft-void **qilinmadi**, qarang §4) | fix(payments) |
| Y-9 sanani orqaga qo'yish | admin ≤ 7 kun (`PAYMENT_BACKDATE_DAYS`) | |
| Y-10 fayl yuklash | tuzatildi + test | |
| Y-11 token loglarda | tuzatildi + test | |
| Y-12 to'xtatilgan guruhga jarima | tuzatildi + test | fix(penalty,schedule) |
| Y-13 jadval xabarlari ketmasligi | tuzatildi + test | |
| Y-14 saqlangan XSS | to'lov formasi va aka-uka xabari tuzatildi | |
| Y-15 zaif paketlar | Django 6.0.8, Pillow 12.3.0, urllib3 2.8.0, sqlparse 0.6.0 | |
| O-1, O-2, O-3, O-4, O-5, O-6, O-7, O-9, O-11, O-12, O-14 (logs papkasi, proksi sarlavhasi, CSRF), O-15, O-16 | tuzatildi (qisman: O-3, O-10, O-14 — §4) | |
| P-1 (attendance), P-4 | tuzatildi | |

UI (4-bosqich): yagona dizayn tizimi `static/css/app.css` (tokenlar, kun/tun, hamma matn juftlari WCAG AA — hisoblab tekshirilgan), `static/js/theme-init.js` va `app.js`; `base.html` qayta yozildi (inline CSS/JS yo'q, veb-shrift yo'q, skip-link, `<main>`, xabarlar darajasi bo'yicha rangda); kirish sahifasi yangi; bosh sahifalarda bugungi darslar / qarzdorlar / bugungi to'lovlar; jadvallarda tezkor qidiruv va saralash; barcha shablonlardan gradient, blur, yorug'lik soyalari olib tashlandi; mobil: pastki navigatsiya, inline gridlar telefonda ustun bo'ladi, gorizontal siljish yo'q (tekshirilgan sahifalar: o'quvchilar, to'lovlar, guruh, to'lov formasi, xonalar, davomat hisoboti).

## 3. Tuzatilmay qoldi (sababi bilan)

- **O-8 DB cheklovlari** (`amount > 0`, `joined_at <= left_at`, telefon unikal): productiondagi mavjud ma'lumotni bilmay turib qo'shish migratsiyani yiqitishi mumkin. Avval prod'da tekshiruv so'rovi (dry-run) kerak.
- **Y-8 soft-void**: o'chirish hozircha qattiq (hard), lekin to'liq snapshot bilan auditga yoziladi. Soft-void barcha hisobot/billing so'rovlariga tegadi — alohida, ehtiyotkor ish.
- **O-3 (4)**: `admin_edit_lesson` guruhning doimiy vaqt/xonasini o'zgartiradi — bu niyatmi, aniq emas (savol §6).
- **O-10**: guruhlar/qarzdorlar/o'qituvchilar ro'yxatiga server tomonidan sahifalash qo'shilmadi (jadval ichida qidiruv/saralash bor).
- **O-13** scheduler ikki marta ishlashi: dasturiy o'zgartirish emas, deploy sozlamasi (`DISABLE_WEB_SCHEDULER=True` web jarayonida).
- **O-17** o'lik funksiyalar (eslatma/admin xabarlari), `send_payment_reminders` jadvali: qaror kerak.
- **P-2, P-3, P-5…P-9**: tozalash/takrorlanish refaktori — xavf/foyda nisbati past, qilinmadi.
- **UI**: 27 shablonda sahifaga xos `<style>` bloklari va inline uslublar saqlanib qoldi (ranglari tokenlarga o'tkazildi, lekin umumiy CSS'ga ko'chirilmadi). FontAwesome CDN'da qoldi. Eski inline `#ef4444` kabi ranglar ba'zi joyda kun rejimida AA dan sal past bo'lishi mumkin. Forma xatolari va "majburiy" belgisi faqat kirish sahifasida to'liq; boshqa formalarda sahifama-sahifa o'tish kerak. Lidlar, Sozlamalar, O'qituvchi maoshi, Kurslar — kodda umuman yo'q edi, qo'shilmadi ("mavjud funksiyalar o'zgarmasin" talabi).

## 4. PRODUCTIONGA CHIQARISH TARTIBI

**Diqqat — buzuvchi o'zgarishlar (oldindan sozlash shart):**
1. `SECRET_KEY` env **majburiy** (yo'q bo'lsa ilova ishga tushmaydi).
2. `DEBUG` standarti endi `False`. Agar prod'da hozir `DEBUG` berilmagan bo'lsa, u shu paytgacha `True` ishlagan: `False` bo'lganda cookie `Secure`, HSTS yoqiladi — HTTPS bo'lmasa kirish ishlamaydi.
3. Webhook rejimida `TELEGRAM_WEBHOOK_SECRET` majburiy; bo'lmasa webhook 503 qaytaradi. Telegram'da webhookni `secret_token` bilan qayta o'rnating. Polling (`run_bot`) ta'sirlanmaydi.
4. Proksi ortida: `USE_PROXY_SSL_HEADER=True`, `CSRF_TRUSTED_ORIGINS=https://domen`, kerak bo'lsa `TRUST_X_FORWARDED_FOR=True` (aks holda audit IP si proksi IP si bo'ladi).
5. Bot: matn orqali telefon yozib kirish olib tashlangan. Telegram'da tasdiqlangan foydalanuvchilar ta'sirlanmaydi (`is_verified` saqlanadi).
6. Parol qoidalari: eng kamida 8 belgi, oddiy/raqamli parollar rad etiladi (yangi parol belgilashda).
7. Tavsiya: bot tokenini aylantiring (eski loglarda URL ichida chiqqan bo'lishi mumkin).

**Tartib:**
1. Bazadan zaxira: `pg_dump -Fc` (SQLite bo'lsa fayl nusxasi). Zaxiradan tiklashni bir marta sinab ko'ring.
2. Staging'da prod nusxasiga `python manage.py migrate` ni sinang (ushbu branch migratsiyalari faqat qo'shimcha: `payments.0005` ustun, `payments.0006`, `attendance.0005`, `users1.0012` indekslar).
3. Env'larni yuqoridagicha o'rnating.
4. `pip install -r requirements.txt`, `python manage.py collectstatic --noinput` (yangi `static/css`, `static/js`).
5. `python manage.py migrate` (ma'lumotni o'zgartirmaydi, tezkor).
6. Ilovani qayta ishga tushiring; scheduler faqat bitta jarayonda ishlasin (`DISABLE_WEB_SCHEDULER=True` web'da).
7. Tekshiruv ro'yxati: kirish, to'lov qabul qilish (ikki marta bosib ko'ring), davomat, jadval, bot `/start`, kun/tun tugmasi.

**Qaytarish (rollback):**
- Kod: oldingi release'ga qaytish.
- DB: migratsiyalar orqaga qaytariladi: `python manage.py migrate users1 0011 && migrate attendance 0004 && migrate payments 0004` (sinalgan). Qo'shilgan `idempotency_key` ustuni oldingi kod uchun zararsiz (null), shuning uchun kod qaytarilganda DB'ni qaytarish shart emas.
- Eng xavfsiz yo'l: zaxiradan tiklash.

## 5. Mavjud ma'lumotni tekshirish (men o'zgartirmaganman)

Productionga chiqqach quyidagilarni **faqat o'qish** rejimida tekshirish tavsiya etiladi (men yozmadim, chunki prod bazasiga kirishim yo'q):
- Y-6: `GradeRecord` da `percentage = 0` yozuvlari (bo'sh deb 0 qo'yilgan bo'lishi mumkin).
- Y-12: to'xtatilgan guruhlar uchun berilgan `TeacherPenalty` (`penalty_type`, `group__is_paused`).
- Y-7: yaqinda `GroupStudent.left_at` o'rnatilgan, lekin boshqa guruhda faol bo'lgan talabalar.
- Y-3: `AttendanceRecord.status` ning `AttendanceStatus` dan tashqari qiymatlari.
Xohlasangiz bularni `--dry-run` management buyruqlari sifatida yozaman.

## 6. Menga qaror kerak (qolgan savollar)

1. Y-8: to'lovni o'chirish soft-void ("bekor qilingan") bilan almashtirilsinmi? (Hisobotlar va billing so'rovlariga tegadi.)
2. O-8: DB cheklovlari qo'shilsinmi? (Avval prod'da tekshiruv so'rovi kerak.)
3. Ketma-ket jarima qoidasi (hozir: ketma-ket 3-chi "kelmadi"da bir marta −10, oradagi o'tkazilgan dars zanjirni uzadi) — to'g'rimi? Oldin noto'g'ri berilgan jarimalar qaytarilsinmi?
4. `admin_edit_lesson` guruhning doimiy jadvalini o'zgartiradi — "bir kunlik o'zgarish" bo'lishi kerakmi?
5. Qolgan sahifalardagi `<style>` bloklarini `app.css` ga bosqichma-bosqich ko'chirish va FontAwesome'ni o'zimizning serverga olish kerakmi?
6. Lidlar, Kurslar, O'qituvchi maoshi, Sozlamalar sahifalari — alohida loyiha sifatida rejalashtiramizmi?
7. O-17: penalti eslatmalari/administratorga Telegram xabarlari (hozir hech kimga bormaydi) qayta yoqilsinmi yoki olib tashlansinmi?

## 7. Qanday ishga tushirish (lokal)

```
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
set DEBUG=True        # yoki .env faylida; SECRET_KEY ham kerak
python manage.py migrate && python manage.py runserver
python manage.py test  # 107 test
```
Audit dalil testlari: `audit/proof_tests/` (eski xatti-harakatni ko'rsatgan, endi tuzatilgani uchun `users1/test_audit_fixes.py` regressiya testlari bilan almashtirilgan; faqat tarixiy ma'lumot).
