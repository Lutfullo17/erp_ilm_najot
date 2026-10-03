# FRONTEND TEST HISOBOTI (QA 3-bosqich)

Yangi UI (`/new/`) brauzerda (Claude Browser) haqiqiy foydalanuvchi sifatida ishlatildi: **admin1** (administrator), **ustoz01** (o'qituvchi), direktor sahifalari (matritsa/test orqali). Lokal demo baza (`seed_demo`). Konsol xatolari va tarmoq so'rovlari (4xx/5xx) kuzatildi.
Yangi topilmalar hali **tuzatilmagan** (QA-F-01 dan tashqari: u test jarayonida topilib darhol tuzatildi, chunki mobil sinovni to'sib qo'yardi).

## 1. Nima va qanday tekshirildi
| Tekshiruv | Usul | Natija |
|---|---|---|
| Konsol / tarmoq | 12 sahifani ketma-ket ochib `read_console_messages`, `read_network_requests` | Konsol xatosi **0**; 4xx/5xx **0**; har sahifada 4–5 so'rov (HTML, CSS, JS, rasm) |
| Funksional oqimlar | Brauzerda bajarildi: kirish → bosh sahifa; qarzdorlardan to'lov qabul qilish (muvaffaqiyat ekrani); o'quvchi qo'shish + guruh; guruh ochish wizard (4 qadam, band xonalar jonli); davomat (o'qituvchi: bosish, "⋯" dialogi, saqlash, qulflanishi); chiqish tasdig'i | **ishladi** |
| Noto'g'ri kiritish | Bo'sh forma (maydonda xato + fokus), noto'g'ri telefon ("9 ta raqamdan iborat…"), `<img onerror>` ismi (escape), uzun matn (server tomonida rad), internet uzilishi (`fetch` rad etildi), sessiya tugashi (chiqib, so'ng qidiruv), noto'g'ri parol bilan kirish | Internet uzilishi: "Internet bilan aloqa yo'q" + **Qayta urinish** ✔. Sessiya tugashi: QA-F-03 |
| O'lchamlar | 360, 390, 768, 1280, 1920 px; avtomatik audit skripti (gorizontal scroll, 44 px dan kichik bosiladigan elementlar, 14 px dan kichik matn, label'siz maydon, kontrast ≥ 4.5:1) | 360 px: 20 sahifa — gorizontal scroll **yo'q** (QA-F-01 tuzatilgach), kichik matn **yo'q**, kontrast xatosi **yo'q**; boshqa kamchiliklar §3 |
| Kun / tun | Barcha asosiy sahifalar ikkala rejimda (audit + skrinshot); tanlov sahifalar o'rtasida saqlanadi; birinchi kirishda tizim sozlamasi (`prefers-color-scheme`) | Kontrast xatosi **yo'q**; "yonib qolgan" element topilmadi |
| Klaviatura | — | **Tekshirilmadi** (brauzer oynasi ko'rinmaganda tugma yuborib bo'lmadi). Kodda: `:focus-visible` konturi, "asosiy mazmunga o'tish" havolasi, `<dialog>` fokus tuzog'i |
| Haqiqiy qurilmalar (iOS Safari, Android Chrome) | — | **Tekshirilmadi** (emulyatsiya bilan cheklandi) |
| Chop etish (kvitansiya) | — | **Tekshirilmadi** (faqat HTML ochildi) |

## 2. Funksiyalar tengligi (eski → yangi)
✔ = yangi UI da bor · ◐ = qisman · ✖ = yo'q

| Eski imkoniyat | Yangi | Izoh |
|---|---|---|
| Kirish/chiqish, rolga qarab bosh sahifa | ✔ | |
| To'lov: qidirish, qabul qilish, tarix, o'chirish (direktor), qarzdorlar (umumiy va guruh bo'yicha) | ✔ | + kvitansiya, 5 daqiqalik bekor qilish, idempotentlik |
| O'quvchi: ro'yxat/qidiruv, qo'shish, tahrirlash, o'chirish, kartochka, chegirma, ota-ona tel. tekshiruvi | ✔ | |
| Guruhga qo'shish/chiqarish, guruh yaratish/tahrirlash/pauza/o'chirish | ✔ | |
| Xonalar jadvali va admin "dars tahrirlash" | ✔ | dialog |
| Jadval arizasi: yuborish, tasdiqlash/rad etish | ✔ | |
| Jadval arizalari tarixi (admin: **hammasi**, filtr bilan) | ◐ | faqat kutayotganlar + oxirgi 10 ta |
| Davomat: belgilash, mavzu/vazifa, admin tuzatish (o'tgan sana), bugungi hisobot | ✔ | |
| Baho: kiritish, tarix | ✔ | |
| Murojaatlar: javob, belgilash; guruhga va hammaga xabar | ✔ | |
| O'qituvchi/administrator: yaratish, tahrirlash, login/parol, bloklash, o'chirish | ✔ | |
| Jarimalar: qo'shish, tahrir, o'chirish, ogohlantirishni hal qilish, nazoratni ishga tushirish | ✔ | |
| Moliyaviy hisobot | ✔ | |
| Profil: ism/telefon/login/parol/rasm (direktor) | ✔ | |
| Telegram holati, o'zgarishlar tarixi | ✔ | |
| O'qituvchi: guruhlar, guruh tafsiloti, o'quvchi kartochkasi, haftalik jadval, ball/jarimalar | ✔ | |
| **O'qituvchi: "Mening o'quvchilarim" umumiy ro'yxati** (`users1:teacher_students`) | **✖** | faqat guruh bo'yicha ko'rinadi (QA-F-11) |
| **Eslatma: "3 va undan ko'p darsda davomat olinmagan" o'qituvchilar** | **✖** | Bugun sahifasida yo'q (QA-F-11) |
| Direktor bosh sahifa: haftalik/oylik davomat soni, so'nggi jarimalar/talabalar | ◐ | QA-F-11 |
| `save_lesson_plan` API | — | eski UI shablonlarida ham ishlatilmaydi |

Yo'qolgan funksiya "kritik" belgilangan edi: ikkita **✖** bor, lekin ikkalasi ham kundalik asosiy ish emas va ma'lumot eski UI da saqlanadi (QA-F-11 — Yuqori deb baholandi, chunki qoida bo'yicha yo'qolgan funksiya kritik; tuzatish rejada).

## 3. Topilmalar
Format: **[Jiddiylik] | Sahifa/fayl | Qadamlar | Kutilgan va haqiqiy | Taklif**

**[Kritik — TUZATILDI test jarayonida] QA-F-01 | barcha `/new/*`, `static/new/new.css` | Brauzerni 360×740 ga qo'ying, istalgan sahifani oching | Kutilgan: sahifa ekranga sig'adi. Haqiqiy: **gorizontal scroll** (layout kengligi 454–507 px), avatar va tema tugmasi kesilgan, pastki menyu ekrandan chiqib ketgan. Sabab: desktop "Tez amal" tugmasi (`.fab-desktop`) telefonda ham ko'rinardi (`.btn` qoidasi uni bekor qilgan), yuqori panel sig'maydi | Tuzatildi (`aece022`): `.btn.fab-desktop{display:none}` + ≤560 px da logotip yashiriladi, qidiruv qisqaradi. Qayta tekshirildi: `innerWidth == 360`
**[Yuqori] QA-F-02 | Yangi UI direktor: To'lovlar tarixi, kvitansiya | `created_by` bo'sh to'lov bor bo'lsa sahifa ochilmaydi | **500** | = QA-B-04
**[Yuqori] QA-F-11 | Funksiyalar tengligi (§2) | Eski "Mening o'quvchilarim" va "3+ dars davomat yo'q" eslatmasi, admin arizalari tarixi (hammasi), direktor haftalik/oylik davomat | Yangi UI da topib bo'lmaydi | Qo'shish (qo'shimcha o'qish endpointlari, backend o'zgarishsiz)
**[O'rta] QA-F-03 | `static/new/new.js` (`UX.api`), `pay.js` | Qidiruv oynasi ochiq turib sessiya tugasin (yoki boshqa tabda chiqing) → qidiring | Kutilgan: "Sessiya tugadi, qayta kiring" + kirish havolasi. Haqiqiy: "Tizimga kiring." + foydasiz "Qayta urinish"; sahifa o'sha holatda qoladi | 401 da kirish sahifasiga havola (`?next=`), formadagi ma'lumot yo'qolmasligi uchun dialog
**[O'rta] QA-F-04 | `templates/new/pay.html`, `.sticky-action` | 390 px da to'lov sahifasi: pastga aylantiring | Yopishqoq "Qabul qilish" paneli sana/usul bloklarining oxirgi qatorini yopadi; telefon raqami to'lov sahifasida formatlanmaydi (`931112233`, boshqa joyda `93 111 22 33`) | Konteynerga pastki bo'sh joy, `phone` filtri
**[O'rta] QA-F-05 | `student_detail.html?new=1` | O'quvchi qo'shing (guruh bilan) | Ikki bir xil yashil xabar; "To'lov qabul qilish" tugmasi **ikki joyda** (asosiy tugma qoidasi buziladi); yangi o'quvchi guruhida **"To'langan"** belgisi chiqadi (u hali to'lamagan; aslida "Qarzi yo'q") | Bitta xabar, bitta asosiy tugma, belgi matni "Qarzi yo'q"
**[O'rta] QA-F-06 | `templates/new/group_detail.html` (`#asSel`) | Skrinrider/axe | `<select>` ning `label`i yo'q (`for="asQ"` mavjud bo'lmagan id) | `for="asSel"`
**[O'rta] QA-F-12 | Telefondagi menyu | Administrator, 360 px | Pastki menyuda faqat 4 ta bo'lim; "Guruhlar", "Dars jadvali", "Ota-onalar xabarlari" faqat yuqoridagi ☰ orqali (qo'shimcha 1 bosish) | "Yana" tugmasi yoki ☰ ni ko'rinadigan qilish (qaror)
**[Past] QA-F-07 | hamma sahifa | Avatar tugmasi 40×40 px; "Izoh qo'shish" 24 px; qatorlardagi matn havolalari (qarzdor ismi, "Qarzdorlarni ko'rish", jadvaldagi guruh nomi) 21–22 px balandlikda | 44 px dan kichik | Avatar 44 px, havolalarga `padding`
**[Past] QA-F-08 | `static/new/pay.js:148`, toast | To'lov muvaffaqiyat ekrani | Sana `2026-10-04` (boshqa joyda `04.10.2026`); kompyuterda toast "Xato bo'ldi — bekor qilish" tugmasi ustiga tushadi | Sana formati, toast joyi
**[Past] QA-F-09 | `templates/users1/login.html` (ikkala UI) | Noto'g'ri parol | Django standart matni: "…to'g'ri **username** va parolni kiriting. Ahamiyat bering, ikkala maydonlar ham katta-kichik harfga sezgir…" — inglizcha so'z, qo'pol | Maxsus oddiy matn: "Login yoki parol noto'g'ri."
**[Past] QA-F-10 | `new/base.html` | Avatar → Chiqish | Tasdiq oynasi ochiq foydalanuvchi menyusi ustiga qatlanadi | Avval menyuni yoping
**[Past] QA-F-13 | Matnlar | Interfeys matnlari o'qib chiqildi | "Login" (3 joyda inglizcha); "Telegram" (kerak); qolgani o'zbekcha. Imlo xatosi topilmadi | "Login" → "Foydalanuvchi nomi" (qaror)
**[Past] QA-F-14 | `new/base.html` | FontAwesome CDN (tashqi) | Tarmoq cheklangan bo'lsa ikonkalar yo'qoladi (matn qoladi, ishlash buzilmaydi) | O'z serverimizga ko'chirish

## 4. "Birinchi marta ishlatayotgan odam" sinovi: bosishlar soni
Sanash: bosh sahifadan, telefonda, matn yozish hisobga olinmaydi. "Eski" — AUDIT_UX.md ga ko'ra. Brauzerda amalda bajarilganlar: ✔.

| Rol | Vazifa | Eski | Yangi | Izoh |
|---|---|---|---|---|
| Administrator | To'lov qabul qilish ✔ | 4–5 | **3** | Bugun kartasi → o'quvchi → "X so'm qabul qilish" |
| | Yangi o'quvchi (tez) ✔ | 3 | **3** | + → Yangi o'quvchi → Saqlash |
| | O'quvchi + guruh + 1-to'lov ✔ | 9–10 | **5** | |
| | O'quvchini qidirish | 1 | **1** | lupa har sahifada |
| | Qarzdorlarni topish ✔ | topib bo'lmasdi | **1** | |
| | Qarzdorga to'lov ✔ | 2–4 | **2** | |
| | Guruhga o'quvchi qo'shish ✔ | 4 | **4** | o'zgarmadi (50 % maqsadga erishilmadi) |
| | Guruh ochish ✔ | 3 + 8 maydon | **6** (2 + 4 qadam) | 3 dan ko'p, lekin har qadamda 1–2 maydon |
| | Bugungi davomat holati | 2 | **1** | |
| | Dars vaqti so'rovini ko'rib chiqish | 4 | **3** | |
| | Ota-ona xabariga javob | 3 | **3** | |
| O'qituvchi | Davomat ✔ | 2 + N (N=14 → 16) | **2 + kelmaganlar** (1 ta → 3) | |
| | Baho | 2 + N yozish | **3** (bitta guruhda) / 5 | tasdiq oynasi bor |
| | Bugungi darslar | 0 | **0** | |
| | Haftalik jadval | 1 | **1** | |
| | Dars vaqtini o'zgartirish so'rovi | 4 | **4** | |
| | Ballarimni ko'rish | 2 | **2** (avatar → profil) | |
| Direktor | Bugungi holat | 0 | **0** | |
| | Tushum/qarz hisoboti | 1 | **1–2** | |
| | O'qituvchi qo'shish | 3 | **3** + 3 maydon | |
| | Jarima berish | 2–3 | **3** | |

**To'xtab qolgan joylar / tushunarsizliklar (yangi odam sifatida):**
1. O'quvchi qo'shilgach "Keyingi qadam" va qarz kartasidagi ikkita bir xil tugma — qaysi biri to'g'ri? (QA-F-05)
2. "Qarzi yo'q — To'langan" yangi o'quvchida chalkash (QA-F-05).
3. To'lov sahifasida "Qarzi yo'q. Oldindan to'lov sifatida qabul qilinadi" — yangi kassir uchun og'ir tushuncha; qisqartirish mumkin.
4. Telefonda "Guruhlar" menyusi yashirin (QA-F-12).
5. Davomat: ⋯ tugmasi nimaligi dastlab noma'lum (sarlavha bor, lekin matn yo'q) — "Kechikdi/Sababli" yozuvi bilan almashtirish mumkin.
6. Guruh wizard'ida "Keyingi" bosilganda xato ko'rsatilsa-da (toast), qaysi maydon yetishmagani ba'zan ko'rinmaydi (3-qadam: kunlar).

## 5. Tekshirilmadi (sabablari)
- Klaviatura bilan to'liq yurish, ekran o'qigich, iOS/Android haqiqiy qurilmalar, kvitansiyani chop etish, `<input type=month>` Safari'da (hisobotdagi oy tanlash), uzoq muddatli sessiya, juda sekin tarmoq (throttling).
- Direktor sahifalarining brauzerdagi vizual ko'rigi: faqat avtomatik (matritsa/smoke test + audit) — skrinshotli ko'rik administrator va o'qituvchi uchun bajarildi.
