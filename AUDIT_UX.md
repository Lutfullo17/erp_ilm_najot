# UX AUDIT (1-bosqich) — boshlovchi foydalanuvchi ko'zi bilan

Kod o'zgartirilmagan. Branch: `redesign-ux`.
**Dalil usuli:** har bir band aniq shablon/view'ga asoslangan. "Bosish soni" kodga ko'ra hisoblangan (telefon, bosh sahifadan boshlab; matn yozish bosishga kirmaydi, alohida "yozish" deb belgilangan). Qo'lda brauzerda sinalmagan joylar "kod bo'yicha" deb yozilgan.

## 0. Foydalanuvchilar (sizning javoblaringiz bo'yicha)
- 1 administrator (kassir vazifasini ham bajaradi), 15+ o'qituvchi, direktor. **Asosan telefondan** ishlashadi.
- Hamma bo'limlarda qiynalishgan, bir qator amallarni umuman bajara olmagan. Tizim faqat lotin o'zbekchada; shrift yo'nalishi o'zgarmaydi. Lidlar kerak emas (rejadan chiqarildi).

## 1. Eng muhim topilmalar (qisqa)
1. **Qarzdorlarni topib bo'lmaydi.** Asl menyuda (`main:templates/base.html`) administrator uchun "Qarzdorlar" havolasi yo'q; qarzdorlar ro'yxati faqat direktor bosh sahifasidagi kartadan ochiladi (`admin_dashboard.html:44`). Yagona administrator uchun u umuman ko'rinmaydi.
2. **Menyu "bo'limlar ro'yxati"**: Dashboard, Bildirishnomalar, O'quvchilar, Guruhlar, Xonalar Bandligi, To'lovlar, Xabarlar. Ish nomi emas, modul nomi. "Bugungi davomat", "Jadval arizalari" kabi muhim joylar bosh menyuda yo'q (kartalar ichida yashirin).
3. **Davomat — eng og'ir amal.** Har bir o'quvchi uchun 4 tugmadan birini majburiy tanlash (`mark_attendance.html`: `required` radio). 20 o'quvchi = kamida 20 bosish + "Saqlash". "Hammasi keldi" tugmasi yo'q.
4. **O'qituvchi davomatni faqat dars davomida ocha oladi** (`users1/views.py:_get_current_teacher_lesson`, `attendance/views.py` vaqt tekshiruvi). Bu biznes qoidasi, lekin ekran buni yetarlicha tushuntirmaydi: kech qolgan o'qituvchi "Hozirgi vaqtda dars mavjud emas" matnini ko'radi, nima qilish kerakligi (administratorga murojaat, qaysi tugma) aytilmaydi.
5. **Inglizcha/texnik so'zlar** hamma joyda (qarang §3).
6. **Mobil:** matnlarning katta qismi 11–13 px (shablonlarda `font-size: 0.5–0.8rem` 303 marta), ikonka-faqat tugmalar (ko'z, qalam, chiqindi) 32–36 px, jadvallar telefonda tor.
7. **Xatolardan keyin yo'l yo'q:** muvaffaqiyatdan so'ng "keyingi qadam" taklifi yo'q (masalan, talaba qo'shilgach to'lov/guruhga qo'shish taklif qilinmaydi).

## 2. Har bir rol uchun TOP-10 kundalik vazifa va hozirgi qadamlar

### 2.1 Administrator (kassir)

| # | Vazifa | Hozirgi yo'l | Bosish | Muammo |
|---|---|---|---|---|
| 1 | To'lov qabul qilish | Bosh sahifa "Tezkor amallar" → qidiruv (yozish) → talaba → (ko'p guruh bo'lsa guruh) → "To'lov turi: To'liq/Qisman/Qo'shimcha" → summa → sana (Bugun) → usul → "To'lovni tasdiqlash" | **4–5** (+1 yozish; qarz bo'lmasa summani qo'lda yozish) | Bir ekranda 6 blok; "Qo'shimcha", "To'liq" so'zlari noaniq; sana `KK.OO.YYYY` qo'lda; kvitansiya yo'q |
| 2 | Yangi talaba qo'shish | O'quvchilar → Yangi O'quvchi → ism, telefon, ota-ona tel., tug'ilgan sana, jins, holat, guruh, chegirma (8 maydon) → Saqlash | **3** (+ 4–7 yozish) | Telefon 2 ta, "holat" maydoni boshlovchiga keraksiz; saqlagach ro'yxatga qaytadi (to'lov/guruh taklif qilinmaydi) |
| 3 | Talaba + guruh + birinchi to'lov | Yuqoridagi 3 + O'quvchilar ichida qidirish → talaba → "To'lov" → 4–5 | **9–10** | Bitta ish uchun 3 alohida sahifa |
| 4 | Talabani qidirish | O'quvchilar → qidiruv (yozish) | **1** + yozish | Qidiruv faqat o'quvchilar sahifasida; har sahifada global qidiruv yo'q |
| 5 | Qarzdorlar ro'yxatini ko'rish | Menyuda yo'q (asl). Faqat to'lovlar/hisobot ichidan | **topib bo'lmaydi** | §1.1 |
| 6 | Qarzdorga to'lov qildirish | Qarzdorlar → "To'lov qilish" → payment_form (qayta qidirishsiz ochiladi) | 2–4 | Yaxshi: o'quvchi oldindan tanlanadi |
| 7 | Guruhga o'quvchi qo'shish | Guruhlar → guruh → "O'quvchi izlash" → "Qo'shish" yoki O'quvchi → "Guruhga qo'shish" | 4 | Ikki xil joy, ikki xil nom |
| 8 | Guruh ochish | Guruhlar → Yangi Guruh → 11 maydon (nom, narx, o'qituvchi, boshlanish sana `KK.OO.YYYY`, kunlar, vaqt `SS:DD`, davomiylik, xona) → Saqlash | **3** (+ 8 maydon) | Xona/o'qituvchi to'qnashuvi faqat saqlagandan keyin xato bo'lib chiqadi |
| 9 | Bugungi davomat holatini ko'rish | Bosh sahifa kartasi "Bugungi davomat" (faqat raqam) → ro'yxat | 2 | Raqam nimani anglatadi (yozuv soni, guruh soni emas) noaniq |
| 10 | O'qituvchi jadval o'zgartirish arizasini ko'rib chiqish | Xonalar Bandligi → "Jadval o'zgartirish arizalari" → ariza → qaror (yoki Bildirishnomalar) | 4 | Ariza "Xonalar" sahifasi ichida yashirin |
| + | Telegram orqali ota-onaga xabar | Bosh sahifa pastida "Guruhga xabar yuborish" | 3 | Sahifaning eng pastida |

### 2.2 O'qituvchi (15+, deyarli hammasi telefonda)

| # | Vazifa | Hozirgi yo'l | Bosish | Muammo |
|---|---|---|---|---|
| 1 | Davomat olish | Pastki menyu "Davomat" → (dars bo'lmasa xato sahifa) → har o'quvchi uchun 1 tugma (4 variant) → Saqlash | **2 + N** (N=o'quvchilar soni, ~10–20) | "Hammasi keldi" yo'q, 4 tugma kichik, saqlagach bosh sahifaga qaytadi |
| 2 | Baho qo'yish | "Baholash" → guruh/sana/nom avtomatik → har o'quvchiga son → Saqlash | 2 + N yozish | Sahifa 8 maydon; bo'sh qoldirsa nima bo'lishi aniq emas (hozir bo'sh = baholanmagan, lekin matn yo'q); bahoni keyin o'zgartirib bo'lmaydi va buni oldindan aytmaydi |
| 3 | Bugungi darslarni ko'rish | Bosh sahifa "O'qituvchi Dashboard" | 0 | Ro'yxat bor, lekin sarlavha "Dashboard" (ingliz) |
| 4 | Dars mavzusi/uyga vazifa yozish | Davomat sahifasi yuqorida "Dars haqida" | 0 (davomat bilan) | Maydonlar majburiy emasligi aytilmagan |
| 5 | Haftalik jadvalni ko'rish | Pastki menyu "Jadval" | 1 | Yaxshi, lekin hafta almashtirish tugmalari kichik |
| 6 | Guruhlarini ko'rish | "Guruhlar" | 1 | |
| 7 | O'quvchi ma'lumotini ko'rish | Guruhlar → guruh → o'quvchi | 3 | "Mening o'quvchilarim" menyuda yo'q (URL bor: `users1:teacher_students`) |
| 8 | Dars vaqtini o'zgartirish so'rash | Jadval → dars → ariza formasi → sabab → yuborish | 4 | Forma sarlavhasi "Jadval o'zgartirish arizasi" (rasmiy); javob holati boshqa sahifada |
| 9 | O'z jarimalarini ko'rish | Profil menyusi → Profil | 2 | Jarima "ball" nimaga ketishi tushuntirilmagan |
| 10 | Davomat o'tkazib yuborilsa | Xato sahifasi: "Davomatni tiklash uchun Administrator bilan bog'laning" | — | Qanday bog'lanish aytilmaydi (telefon/chat yo'q) |

### 2.3 Direktor

| # | Vazifa | Hozirgi yo'l | Bosish | Muammo |
|---|---|---|---|---|
| 1 | Bugungi umumiy holat | Boshqaruv Paneli | 0 | Juda ko'p blok (statistika, bot holati, jarimalar, ariza, xabar, xabar yuborish) — nimaga birinchi qarash noma'lum |
| 2 | Oylik tushum / qarz | Tushum Hisoboti | 1 | Hisobot sahifasi 266 qator, 5 xil jadval; "kassa" va "hisoblangan" farqi tushuntirilmagan |
| 3 | Qarzdorlar | Bosh sahifa kartasi | 1–2 | Menyuda yo'q |
| 4 | O'qituvchi qo'shish | O'qituvchilar → qo'shish → forma → Saqlash | 3 | |
| 5 | Davomat olmagan o'qituvchi | Bildirishnomalar | 1 | "Bildirishnomalar" nom tushunarsiz; ichida "O'qituvchi darsga keldimi?" |
| 6 | Jarima berish / ko'rish | O'qituvchilar... Jarimalar (alohida sahifa) | 2–3 | "Penalty/ball" tizimi tushunarsiz |
| 7 | Administrator login/parol almashtirish | Profil → bo'lim | 3–4 | Profil sahifasi 330 qator, ko'p vazifa bitta joyda |
| 8 | To'lovni o'chirish/tuzatish | To'lovlar → qator → chiqindi ikonkasi | 3 | Faqat ikonka, nima bo'lishi tasdiq matnida aytilmaydi (qarz qayta hisoblanadi) |
| 9 | Hamma ota-onaga e'lon | Boshqaruv Paneli pastida "hammaga xabar" | 3 | Yashirin |
| 10 | Audit log ko'rish | URL orqali (menyuda yo'q) | — | Yashirin |

## 3. Tushunarsiz joylar

**Inglizcha / texnik so'zlar:** "Dashboard" (menyu, sarlavha, o'qituvchi sahifasi), "Home" (pastki menyu), "Edit" (talaba kartasi, `student_detail.html`), "Admin Override", "Block/Unblock", "Audit Log", "Bot holati", "O'quvchilar ro'yxati"/"Ro'yxat", "Yangi Administrator", "Home" va "Xabarlar" (aslida: ota-ona murojaatlari).
**Noaniq nomlar:** "Xonalar Bandligi" / "Haftalik Ish Tartibi" (aslida: xonalar jadvali), "Jadval o'zgartirish arizalari", "Bildirishnomalar", "Boshqaruv Paneli", "Tushum Hisoboti", "Hal qilish" (nimani?), "Davomatni ochish" (admin override: aslida "Davomatni qayta tahrirlash"), "Qulflangan" (davomat), "Qisman"/"Qo'shimcha" (to'lov turi), "Vaqtincha to'xtatish" (guruh).
**Yashirin funksiyalar:** qarzdorlar (asl menyuda yo'q), bugungi davomat, jadval arizalari, audit log, jarimalar (faqat direktor, ichkarida), o'qituvchining "Mening o'quvchilarim" (menyuda yo'q), bot holati.
**Ortiqcha maydonlar:** talaba formasida "Holat", ikkita telefon; guruh formasida davomiylik + vaqt + xona bir vaqtda majburiy-ko'rinishda; baho formasida "Baholash nomi" (standart bor, lekin boshlovchiga savol).
**Birinchi tugma noaniq:** talaba ro'yxatida har qatorda 3 ta bir xil ikonka-tugma (ko'z, qalam, chiqindi); `students/student_list.html`. Sahifada nechta ko'k tugma — "Yangi O'quvchi" (asosiy) lekin boshqa joylarda (guruh detalida) 4–5 ta teng vaznli tugma ("Tahrirlash", "To'xtatish", "O'chirish", "Qo'shish", "Davomat olish").
**Sana/vaqt:** qo'lda `KK.OO.YYYY` va `SS:DD` yozish (group_form, payment_form), davomat sarlavhasida `2026-10-04` formati.

## 4. Xato holatlari
- **O'chirish:** `confirm()` bor (talaba, guruh, to'lov, o'qituvchi), lekin matn natijani aytmaydi (qarz/hisob nima bo'ladi) va hammasi brauzer standart oynasi — telefonda kichik, tilsiz tugmalar ("OK/Cancel").
- **Undo yo'q:** hech qayerda "Bekor qilish" imkoni yo'q.
- **Forma xatosi:** Django xato matnlari maydon ustida emas (ko'p joyda sahifa tepasida yoki umuman alert); to'lov formasida xato JS orqali tepada.
- **Muvaffaqiyat:** yashil xabar bor (yangi asos), lekin "keyingi qadam" taklifi yo'q; saqlagach ro'yxatga qaytariladi.
- **Adashganda:** dars bo'lmasa o'qituvchiga yagona "Dashboardga qaytish" tugmasi; davomat qulflansa "Admin bilan bog'laning" (qanday?).
- **Tarmoq xatosi:** to'lov formasi `fetch` da xato matni bor; boshqa JS sahifalarda (xabar yuborish, ariza) yuklanish yo'q/xato yo'q.
- **Yuklanish:** skeleton yo'q; faqat tugmadagi aylana (yangi qo'shilgan).

## 5. Mobil, bo'sh holat, kontrast
- **Mobil:** pastki menyu bor (administrator 6 element — sig'masligi mumkin: 11px yozuv), o'qituvchida 5. Jadvallar `mobile-card-table` bilan kartaga aylanadi, lekin faqat ba'zi jadvallarda `data-label` bor. 303 joyda 0.5–0.8rem shrift.
- **Bosiladigan o'lcham:** ro'yxat qatorlaridagi ikonka-tugmalar ~32–36 px, davomat tugmalari ~34 px balandlikda (44 px dan kichik).
- **Bo'sh holat:** ba'zilarida bor ("Qarzdorlar yo'q. Baraka toping!"), ko'pida oddiy "...yo'q." matni, harakat tugmasi yo'q ("Hali guruh yo'q" → "Birinchi guruhni yarating" yo'q).
- **Kontrast:** yangi tokenlar AA, lekin eski inline ranglar (`#10b981`, `#ef4444`, `#8b5cf6` — davomat tugmasi "Kechikdi") kun rejimida 3:1–4:1 oralig'ida. Rang bilan birga belgi: davomatda faqat matn ("Keldi/Kelmadi") bor — yaxshi; qarz/to'langanda badge matni bor, lekin ikonka-faqat holatlar ham uchraydi.
- **Til izchilligi:** bir xil narsa 2–3 xil nom: "O'quvchi"/"Talaba", "Guruhga qo'shish"/"O'quvchi qo'shish"/"Qo'shish", "To'lov"/"To'lov qilish"/"To'lov qabul qilish".

## 6. Eski UI funksiyalari ro'yxati (5-bosqichdagi "tenglik jadvali" uchun asos)
Eski URL'lar (hammasi saqlanadi, `/new/` ostida yangi ekran xaritasi alohida): `users1`: login, admin/teacher/administrator dashboard, profil (+login/parol/foto/ma'lumot), administratorlar CRUD, o'qituvchilar CRUD+detail+login/parol, jarimalar (qo'shish/tahrir/o'chirish/ogohlantirishni hal qilish/qo'lda tekshirish), audit log, jadval arizalari (yaratish/tarix/ko'rish/qaror), murojaatlar (javob/hal), broadcast (guruh/hamma), bot holati, bildirishnomalar, o'qituvchi: guruhlar, guruh detali, jadval, o'quvchilar, o'quvchi detali; `students`: ro'yxat/qidiruv, qo'shish, tahrirlash, o'chirish, qarz API, ota-ona telefon tekshiruvi; `groups`: ro'yxat/qidiruv, qo'shish, tahrirlash, detali, o'quvchi qo'shish/chiqarish, pauza, o'chirish, xonalar jadvali, dars tahrirlash; `payments`: ro'yxat, yangi to'lov (JSON API), qarzdorlar (umumiy/guruh), o'chirish; `attendance`: belgilash, admin override, dars rejasi; `grades`: kiritish, ro'yxat; `reports`: moliyaviy hisobot, bugungi davomat.

## 7. Xulosa va keyingi qadam
Asosiy muammo — tizim "modullar" mantig'ida qurilgan, foydalanuvchi esa "bugun nima qilishim kerak?" deb so'raydi. Eng yaqqol yutuqlar: (1) davomatni "hammasi keldi + faqat kelmaganlarni belgilash" ga aylantirish (N+1 → ~3 bosish), (2) menyuni vazifaga aylantirish va qarzdorlarni ko'rinadigan qilish, (3) to'lovni 3 bosishga tushirish (talaba tanlash → summa tasdiqlash → tayyor), (4) mobil o'lchamlar (16 px matn, 44 px tugma), (5) bir xil so'zlar lug'ati.

**To'xtadim — 2-bosqichga (yangi axborot tuzilmasi, dizayn tizimi, ekran maketlari) o'tish uchun tasdig'ingizni kutaman.**
