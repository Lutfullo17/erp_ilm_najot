# YANGI UX REJASI (2- va 3-bosqich) — kodgacha

Branch: `redesign-ux`. Bu hujjat faqat reja va matn-maketlar; **kod yozilmagan**. Lidlar sahifasi sizning javobingizga ko'ra rejadan chiqarilgan.
Asos: [AUDIT_UX.md](AUDIT_UX.md). Foydalanuvchilar: 1 administrator (kassir), 15–22 o'qituvchi, direktor; asosan **telefon**; faqat lotin o'zbekcha.

---

## 1. Yangi UI eskisi bilan qanday parallel ishlaydi (qaror: "eng qulayi")

- Yangi UI **`/new/`** prefiksida, alohida shablon papkasi (`templates/new/`), alohida CSS/JS (`static/new/`). **Eski UI (`/users/…`, `/students/…`) bir satr ham o'zgarmaydi.**
- Yangi ekranlar eskisining **xizmat funksiyalarini** (`apply_payment`, `add_student`, `remove_student`, `StudentQuickForm`, davomat/baho servislari) qayta ishlatadi. Biznes mantiq, DB va mavjud API'lar o'zgarmaydi.
- **O'tish tugmasi (ikki tomonlama):** har bir eski sahifada pastki burchakda "Yangi ko'rinishni sinab ko'rish", yangi UI da "Eski ko'rinishga qaytish". Tanlov **cookie**da (`ui=new|old`) — DB o'zgarishsiz.
- **Bosqichma-bosqich yoqish (feature flag):** env `NEW_UI_USERS=ustoz01,admin1` (yoki `*` = hamma). Ro'yxatdagi foydalanuvchi kirgach `/new/` ga yo'naltiriladi, boshqalar eski UI da qoladi. Cookie tanlovi flag'dan ustun. Flag bo'sh bo'lsa hammasi eskicha — **xavfsiz standart**.
- Qaytish: flag'dan foydalanuvchini olib tashlash yoki cookie'ni "old" qilish (bir bosish). Kod o'chirmasdan.

## 2. Backendga o'zgartirish kerakmi? — **Sizdan so'raladigan ro'yxat**

Mavjud logika/DB buzilmaydi. Yangi UI uchun quyidagi **qo'shimcha** (faqat o'qish yoki mavjud servislarni chaqiradigan) endpointlar kerak, `ux` nomli yangi Django ilovasida (eski ilovalarga tegmaydi):

| # | Nima | Nega | Turi | Ta'sir |
|---|---|---|---|---|
| B1 | `GET /new/api/search/?q=` — talaba/guruh/o'qituvchi (rolga qarab) | Global qidiruv, natijadan to'g'ridan amal | faqat o'qish | Yo'q |
| B2 | `GET /new/api/today/` va server-render "Bugun" ma'lumoti (darslar, davomat kutayotganlar, bugungi to'lovlar, qarzdorlar soni) | Bosh sahifa kartalari | faqat o'qish | Yo'q |
| B3 | `POST /new/api/payments/` — mavjud `apply_payment()` ni chaqiradi (idempotentlik bilan) | Yangi to'lov oqimi (JSON tuzilishi soddalashadi) | mavjud servis | Yo'q |
| B4 | `GET /new/payments/<id>/receipt/` — kvitansiya (chop etish) | "Kvitansiyani chop etish" | faqat o'qish | Yo'q |
| B5 | `POST /new/api/students/quick/` — `StudentQuickForm` + `add_student()` (+ ixtiyoriy to'lov) bitta so'rovda | Talaba qo'shish wizard'i | mavjud servis | Yo'q |
| B6 | `POST /new/api/attendance/<group>/` — mavjud davomat qoidalarini (vaqt oynasi, a'zolik, status tekshiruvi) chaqiradi; JSON javob | Tezkor davomat (JS), xato xabarlari maydon darajasida | mavjud mantiq | Yo'q |
| B7 | `GET /new/api/groups/check-slot/` — xona/o'qituvchi to'qnashuvini oldindan tekshirish (`validate_schedule_change`) | Guruh ochish wizard'ida jonli tekshiruv | faqat o'qish | Yo'q |
| B8 | **(qaror kerak)** To'lovni "bekor qilish (undo)" administrator uchun 5 daqiqa ichida | Hozir faqat direktor o'chira oladi (`payments/services.py::delete_payment`) | **ruxsat qoidasi o'zgaradi** | Ha — tasdiq kerak |
| B9 | **(qaror kerak)** "Fikr bildirish" uchun yangi `Feedback` modeli (matn, sahifa, foydalanuvchi) + migratsiya | 6-bosqich fikr yig'ish | yangi jadval (qo'shimcha) | Ha — tasdiq kerak |
| B10 | **(qaror kerak)** O'qituvchi davomat oynasi: dars boshlanishidan 15 daqiqa oldin ochilsinmi? | Hozir faqat dars davomida (kech qolish muammosi) | biznes qoidasi | Ha — tasdiq kerak |

B1–B7 — "faqat o'qish yoki mavjud servisni chaqirish": men ularni sizdan **alohida tasdiq** kutib qo'shaman. B8–B10 — qaror sizniki; ular tasdiqlanmasa, UI shu imkoniyatlarsiz ishlaydi (B8 o'rniga: "Tuzatish uchun direktorga yuborish" matni).

---

## 3. Yangi axborot tuzilmasi (navigatsiya)

Qoida: menyu — **ish** nomi bilan, 6–8 dan oshmaydi, har rol faqat o'ziga kerakli narsani ko'radi. Telefonda: pastda 4 ta bo'lim + markazda katta "**+**" (tez amal); qolgani "Yana" varag'ida. Kompyuterda: chap panel.

### Administrator (kassir)
| Menyu | Ichida | Eski sahifa(lar) |
|---|---|---|
| **Bugun** | Bugungi darslar, davomat kutayotganlar, bugungi to'lovlar, qarzdorlar | administrator_dashboard, bildirishnomalar, bugungi davomat |
| **To'lov** | To'lov qabul qilish · Qarzdorlar · To'lovlar tarixi | payment_form, debtor_list, payment_list |
| **Davomat** | Bugungi guruhlar holati; o'zi belgilash/tuzatish | attendance_mark, admin override, today_attendance |
| **O'quvchilar** | Qidirish, yangi qo'shish, kartochka | student_* |
| **Guruhlar** | Ro'yxat, yangi guruh, a'zolar, to'xtatish | group_* |
| **Dars jadvali** | Xonalar jadvali, o'qituvchi arizalari | room_availability, schedule requests |
| **Ota-onalar xabarlari** | Kelgan murojaatlar, javob, guruhga xabar | admin_messages, broadcast |
Telefonda pastki 4: **Bugun · To'lov · Davomat · O'quvchilar**; "Yana": Guruhlar, Dars jadvali, Ota-onalar xabarlari.

### Direktor
**Bugun · Pul** (tushum hisoboti, qarzdorlar, to'lovlar) **· O'quvchilar · Guruhlar · Xodimlar** (o'qituvchilar, administratorlar, jarimalar) **· Dars jadvali · Ota-onalar xabarlari · Sozlamalar** (parol, profil, bot holati, audit tarixi). Pastki 4: Bugun · Pul · O'quvchilar · Xodimlar; qolgani "Yana".

### O'qituvchi
**Bugun · Davomat · Baholash · Guruhlarim · Jadval**; profil/ballarim — yuqoridagi avatar menyusida ("Mening ballarim"). Pastki 5 (sig'adi).

## 4. "Bugun" bosh sahifa (har rol uchun "Bugun nima qilish kerak?")

Katta kartalar, har birida **bitta aniq tugma**; hech narsa bo'lmasa karta ko'rinmaydi yoki "Hammasi joyida" deydi.

**Administrator**
```
┌──────────────────────────────────────────┐
│ Assalomu alaykum, Nodira!   4-oktyabr    │  [🔍 Talaba yoki guruh qidirish]   (+)
├──────────────────────────────────────────┤
│ 🔴 12 ta qarzdor           [Qarzdorlarni ko'rish]
│ 💰 Bugun qabul qilindi: 1 450 000 so'm (5 ta) [To'lov qabul qilish]
│ 📋 Davomat kutilmoqda: 3 ta guruh   [Davomatni ko'rish]
│ ✉  2 ta yangi xabar (ota-onalardan) [Javob berish]
│ 📅 1 ta jadval arizasi kutmoqda      [Ko'rib chiqish]
│ 🎂 Bugun tug'ilgan kun: 2 ta o'quvchi (karta, tugmasiz)
└──────────────────────────────────────────┘
```
**O'qituvchi**
```
┌──────────────────────────────────────────┐
│ ⏰ HOZIR DARS: Ingliz tili A1 (09:00–10:30), 14 ta o'quvchi
│     [ Davomat belgilash ]            ← bitta katta tugma
├──────────────────────────────────────────┤
│ Bugungi darslar:  09:00 Ingliz A1 ✔ davomat olingan
│                   15:30 Matematika B2 — 5 soat qoldi
│ ⚠ Kecha davomat olinmagan: Fizika 8-sinf  [Administratorga yozish]
│ Mening ballarim: −10 (shu oy) [Batafsil]
└──────────────────────────────────────────┘
```
**Direktor**: Bugungi tushum · Qarzdorlar (jami summa) · Davomat olinmagan darslar (o'qituvchi nomi bilan) · Kutilayotgan arizalar · Yangi xabarlar · Oylik tushum (kichik, bosilsa hisobot). Har kartada tugma: "Pulni ko'rish", "Qarzdorlar", "Ogohlantirishlar", "Ko'rib chiqish".

## 5. "+ Tez amal" va global qidiruv

- **"+" tugmasi** doim ko'rinadi (telefonda pastki markaz, kompyuterda yuqori o'ng). Bosilganda pastdan chiqadigan varaq (bottom sheet):
  - Administrator/Direktor: **Yangi o'quvchi · To'lov qabul qilish · Davomat · Yangi guruh**.
  - O'qituvchi: **Davomat belgilash · Baho qo'yish**.
- **Global qidiruv** har sahifa tepasida (telefonda lupa ikonkasi → to'liq ekran qidiruv). 2 harfdan keyin natija (ism, familiya, telefon, guruh nomi). Natija qatori ichida tugmalar: o'quvchi → **[To'lov qabul qilish] [Ochish]**; guruh → **[Davomat] [Ochish]**. Klaviatura: `/` qidiruvga fokus, `↑↓ Enter`.

## 6. Dizayn tizimi

**Tokens** (mavjud `static/css/app.css` tokenlari asosida kengaytiriladi; kun/tun, WCAG AA saqlanadi, tanlov saqlanadi, birinchi marta `prefers-color-scheme`):
- Shrift: tizim shrifti (o'zgarmaydi). **Asosiy matn 16 px** (18 px — qatorlarning bosh matni), sarlavhalar 22–28 px, yordamchi matn kamida **14 px** (hozirgi 11–13 px yo'q qilinadi).
- Oraliq: 4 px shkala (4/8/12/16/24/32); karta paddingi 16–20 px; keng "nafas".
- Bosiladigan o'lcham: **kamida 44×44 px** (asosiy tugmalar 48–56 px); ikonka-tugma yonida **doim matn yorlig'i**.
- Burchak 12 px, soya yo'q (faqat chegara), gradient yo'q, animatsiya yo'q (faqat 150 ms fokus/ochilish; `prefers-reduced-motion` hurmat).
- **Bitta sahifada bitta asosiy (ko'k to'ldirilgan) tugma.** Qolganlari: ikkilamchi (kontur), uchlamchi (matn), xavfli (qizil kontur).
- **Rang = ma'no + belgi + matn:** yashil ✔ "To'langan / Keldi"; qizil ✖ "Qarz / Kelmadi"; sariq ⚠ "Ogohlantirish / Kechikdi / Sababli"; ko'k — asosiy amal/havola. Hech qachon faqat rang bilan.

**Komponentlar:** Button (4 xil), Field (yorliq + izoh/misol + xato matni + majburiy belgi `*`), Select, DateField (`<input type=date>` + "Bugun/Kecha" chiplari; qo'lda `KK.OO.YYYY` yo'q), MoneyInput (bo'sh joy bilan ming ajratish), Card/TaskCard, Badge (ikonka+matn), ListRow (telefonda karta, kompyuterda jadval), FilterChips ("Faqat qarzdorlar"), Stepper ("Qadam 2/4"), BottomSheet/Modal, ConfirmDialog (oqibatni aytadi), Toast (+ "Qaytarish"), EmptyState (tugma bilan), Skeleton, ErrorRetry, HelpDrawer ("Bu sahifa nima uchun?"), Pagination.

## 7. Atamalar lug'ati (butun tizimda bir xil)

| Hozir | Yangi |
|---|---|
| Dashboard / Boshqaruv Paneli / Ishchi Paneli / Home | **Bugun** |
| O'quvchi / Talaba | **O'quvchi** (yagona) |
| Enrollment / Guruhga qo'shish / O'quvchi qo'shish / Qo'shish | **Guruhga qo'shish** |
| Balance / hisob-kitob | **Hisob** (qarz: "Qarzi bor", ortiqcha: "Oldindan to'langan") |
| To'lov / To'lov qilish / To'lovni tasdiqlash | **To'lov qabul qilish** (tugma: "Qabul qilish") |
| To'lov turi: To'liq / Qisman / Qo'shimcha | "Qarzni to'liq yopish" / "Bir qismini to'lash" / "Oldindan to'lash" |
| Xonalar Bandligi / Haftalik Ish Tartibi | **Dars jadvali** (xonalar bo'yicha) |
| Jadval o'zgartirish arizalari | **Dars vaqtini o'zgartirish so'rovlari** |
| Bildirishnomalar | **Eslatmalar** (Bugun sahifasida) |
| Xabarlar (murojaatlar) | **Ota-onalar xabarlari** |
| Hal qilish | **Javob berildi deb belgilash** |
| Admin Override / Davomatni ochish | **Davomatni tuzatish** |
| Qulflangan | **Saqlangan (tuzatish uchun administratorga yozing)** |
| Vaqtincha to'xtatish (guruh) | **Guruhni pauzaga qo'yish** |
| Edit | **Tahrirlash** |
| Block / Unblock | **Kirishni to'xtatish / Qayta ruxsat berish** |
| Penalty / ball | **Jarima ballari** |
| Audit Log | **O'zgarishlar tarixi** |
| Bot holati | **Telegram ulanishi** |
| Tushum Hisoboti | **Pul hisoboti** |

## 8. Asosiy ekranlar — matn-maket (telefon)

**To'lov qabul qilish — 3 bosish:** Bugun → [To'lov qabul qilish] (1) → qidiruv (2 harf yozing) → natijani bosish (2) → ekran:
```
Ali Valiyev · Ingliz tili A1
Qarzi: 600 000 so'm  (oktyabr — 300 000, noyabr — 300 000)
─ Qancha qabul qilasiz? ─
 [ 600 000 ] so'm   ← qarz bilan oldindan to'ldirilgan; ( ) Boshqa summa
─ Qanday? ─ (•) Naqd  ( ) Karta  ( ) O'tkazma
 Sana: Bugun ▾
          [ 600 000 so'm qabul qilish ]   ← bitta asosiy tugma (3)
```
Muvaffaqiyat: `✔ 600 000 so'm qabul qilindi. Ali Valiyev qarzi: 0` — [Kvitansiyani chop etish]  [Yana to'lov qabul qilish]  [Bosh sahifa]. Ko'p guruhli o'quvchida guruhlar qarz bilan ro'yxatda, eng katta qarzlisi tanlangan. Xato: "Summa 0 dan katta bo'lishi kerak" — maydon tagida.

**Davomat (o'qituvchi):** Bugun → [Davomat belgilash] (1) →
```
Ingliz tili A1 · 09:00–10:30        14 ta o'quvchi
Hammasi "Keldi" deb belgilangan. Kelmaganlarni bosing.
 Ali Valiyev      [ ✔ Keldi ]   ← qatorni bosish: Keldi → Kelmadi → Kechikdi → Sababli
 Zilola Karimova  [ ✖ Kelmadi ]
 …
 Mavzu (ixtiyoriy): [__________]  Uyga vazifa (ixtiyoriy): [__________]
        [ Saqlash: 13 keldi, 1 kelmadi ]
```
Maqsad: `1 + (kelmaganlar soni) + 1`. "Saqlandi. Davomat tuzatish kerak bo'lsa administratorga yozing" + [Administratorga yozish] (Telegram/telefon havolasi).

**O'quvchi qo'shish (tez):** [+] → Yangi o'quvchi (2 bosish) → *Ism-familiya*, *Telefon* (misol: 90 123 45 67), *Guruh* (ro'yxatdan tanlash) → [Saqlash] (3) → `✔ Ali qo'shildi` [To'lov qabul qilish] [Yana o'quvchi qo'shish]. "Qo'shimcha ma'lumot" (ota-ona tel., tug'ilgan sana, chegirma) yig'iladigan bo'lim yoki 4-qadamli wizard (§9).

**Qarzdorlar:** filtr chiplari `[Hammasi] [Faqat shu hafta] [Guruh ▾]`, qidiruv; qator: *Ali V. — 600 000 so'm, 2 oy* — tugma **[To'lov qabul qilish]**; yuqorida jami qarz. Bo'sh holat: "Qarzdor yo'q 🎉".

**Guruhlar:** qator: nom, o'qituvchi, kunlar/vaqt, o'quvchilar soni, holat badge (Faol / Pauzada) — tugma [Davomat] ; ochilsa: a'zolar (har birida [To'lov]), [O'quvchi qo'shish], "Yana ⋯": Tahrirlash, Pauzaga qo'yish, O'chirish (oqibat matni bilan).

## 9. Boshlovchi uchun qulaylik (3-bosqich) — aniq rejalar

1. **Wizard'lar** (har qadamda bitta savol, "Qadam 2/4", Orqaga/Keyingi, saqlanmagan ma'lumot yo'qolmaydi):
   - *Yangi o'quvchi:* 1) Ism va telefon → 2) Qaysi guruh (ixtiyoriy, "Keyinroq") → 3) Ota-ona va chegirma (ixtiyoriy) → 4) Birinchi to'lov (ixtiyoriy "Hozir qabul qilaman / Keyinroq"). Tez rejim (§8) bilan birga.
   - *Guruh ochish:* 1) Nomi va oylik narx → 2) O'qituvchi → 3) Kunlar va vaqt (standart: Du-Chor / Sesh-Pay / Jum-Shan tugmalari) → 4) Xona (**faqat bo'sh xonalar** ko'rsatiladi, B7) → Tasdiq.
   - *Dars vaqtini o'zgartirish so'rovi (o'qituvchi):* 1) Qaysi dars → 2) Qachonga → 3) Sabab (tayyor variantlar + yozish) → Yuborish.
2. **Formalar:** har maydon ostida qisqa izoh/misol (Telefon: "90 123 45 67"), `*` majburiy, aqlli standartlar (sana — bugun, to'lov usuli — naqd, davomiylik — 1,5 soat), telefon avtomatik formatlanadi, xato maydonning o'zida va oddiy tilda ("Telefon raqami 9 ta raqamdan iborat bo'lishi kerak"). Saqlashdan oldin sahifa tepasida xatolar ro'yxati emas, birinchi xato maydonga fokus.
3. **Tanishtiruv (birinchi kirishda):** har rol uchun 3–4 qadamli qisqa tur ("Bu yerda bugungi ishlaringiz", "+ tugmasi tez amallar", "Qidiruv", o'qituvchiga: "Davomat qanday olinadi"). "O'tkazib yuborish" doim bor; qayta ko'rish: avatar menyusida "Tanishtiruvni qayta ko'rish". Holat `localStorage`da.
4. **"Bu sahifa nima uchun?" (?)** tugmasi har sahifada: 2–3 gap + 3 qadam; HelpDrawer; matnlar bitta faylda (`new/help.md` → JS).
5. **Bo'sh holatlar** (nima qilish kerakligini aytadi):

| Joy | Matn | Tugma |
|---|---|---|
| O'quvchilar | Hali o'quvchi yo'q | Birinchi o'quvchini qo'shing |
| Guruhlar | Hali guruh yo'q | Birinchi guruhni yarating |
| Guruhda o'quvchi yo'q | Bu guruhda hali o'quvchi yo'q | O'quvchi qo'shish |
| Qarzdorlar | Qarzdor yo'q 🎉 | — |
| To'lovlar | Bugun to'lov qabul qilinmagan | To'lov qabul qilish |
| O'qituvchi: dars yo'q | Hozir dars yo'q. Keyingi dars: 15:30 Matematika B2 | Jadvalni ko'rish |
| Qidiruv topilmadi | "…" bo'yicha hech narsa topilmadi | Yangi o'quvchi qo'shish |

6. **Xavfsiz amallar:** o'chirish/chiqarish uchun maxsus dialog **oqibatni aytadi** ("Ali Ingliz A1 guruhidan chiqariladi. Shu sanadan keyin to'lov hisoblanmaydi. Oldingi to'lovlar saqlanadi."); xavfli tugma qizil, "Bekor qilish" standart. **Undo toast** (10 soniya): "Guruhdan chiqarildi — [Qaytarish]" (mavjud `add_student` orqali, backend o'zgarishsiz). Muvaffaqiyatdan keyin doim **keyingi qadam** tugmalari (§8).
7. **Ro'yxatlar:** qidiruv + chiplar ("Faqat qarzdorlar", "Faqat pauzadagilar"), sahifalash (20 tadan), telefonda karta qator (har qatorda **bitta asosiy amal tugmasi**, qolgani "⋯"), kompyuterda jadval.
8. **Mobil birinchi:** pastki navigatsiya + "+" ; sticky asosiy tugma; katta bosish zonasi; klaviatura turi (`inputmode=numeric`, `type=tel`).
9. **Yuklanish/xato:** skeleton (ro'yxat/kartalar), tarmoq xatosi — "Internet bilan aloqa yo'q. [Qayta urinish]", tugma bosilganda "Saqlanmoqda…".

## 10. Eski → yangi funksiyalar mosligi (qisqa; to'liq tekshiruv ro'yxati 5-bosqichda)

| Eski imkoniyat | Yangi joyi |
|---|---|
| To'lov qabul qilish / tarix / o'chirish (direktor) | To'lov → Qabul qilish / Tarix / ⋯ O'chirish |
| Qarzdorlar (umumiy, guruh bo'yicha) | To'lov → Qarzdorlar (guruh filtri) |
| O'quvchi: qo'shish/tahrir/o'chirish/qidirish/kartochka/chegirma/ota-ona tel. tekshiruvi | O'quvchilar (+ wizard) |
| Guruh: yaratish/tahrir/pauza/o'chirish/a'zo qo'shish-chiqarish | Guruhlar |
| Xonalar jadvali va "dars tahrirlash" (admin) | Dars jadvali |
| Jadval arizasi (yuborish/ko'rish/tasdiqlash/rad) | Dars jadvali → so'rovlar |
| Davomat (belgilash, mavzu/uyga vazifa, admin tuzatish, bugungi hisobot, dars rejasi) | Davomat |
| Baho (kiritish, tarix) | Baholash |
| Murojaatlar (javob/belgilash), guruhga/hammaga xabar | Ota-onalar xabarlari |
| O'qituvchilar CRUD, login/parol tiklash | Xodimlar |
| Administratorlar (yaratish, login/parol, kirishni to'xtatish) | Xodimlar |
| Jarimalar (qo'lda, tahrir, o'chirish, ogohlantirishni hal qilish, tekshiruvni ishga tushirish) | Xodimlar → Jarima ballari |
| Moliyaviy hisobot | Pul → Hisobot |
| Bot holati, audit log, profil (login/parol/foto/ma'lumot) | Sozlamalar |
| Eslatmalar (davomat olinmagan, 3 ta ketma-ket, tug'ilgan kunlar) | Bugun kartalari |

## 11. Bajarish tartibi (4-bosqich) va bosish maqsadlari

Tartib: **0)** umumiy komponentlar + layout (`/new/` skeleti, tema, navigatsiya, "+", qidiruv) → **1)** Bugun → **2)** To'lov → **3)** Davomat → **4)** O'quvchi qo'shish/qidirish → **5)** Guruhlar → **6)** Qarzdorlik → **7)** Jadval → **8)** Hisobotlar → **9)** Sozlamalar. (Lidlar — rejadan chiqarilgan.) Har sahifadan keyin qisqa hisobot va sizning tasdig'ingiz.

| Vazifa | Hozir | Maqsad |
|---|---|---|
| To'lov qabul qilish | 4–5 (+ yozish) | **3** |
| O'qituvchi davomati | 2 + N | **2 + kelmaganlar** (odatda 3–5) |
| O'quvchi qo'shish (tez) | 3 (+ maydonlar) | **3** (ism, telefon, guruh) |
| Qarzdorlarni topish | topib bo'lmaydi | **1** |
| Talaba + guruh + 1-to'lov | 9–10 | **4–5** |
| Guruh ochish | 3 + 8 maydon | wizard 4 qadam, har qadamda 1–2 maydon |

---

**To'xtadim.** Quyidagilar tasdig'ingizni kutadi:
1. §1 parallel ishlash usuli (`/new/` + cookie + `NEW_UI_USERS` flag) to'g'rimi?
2. §2 backend ro'yxati: **B1–B7** (faqat o'qish/mavjud servisni chaqirish) qo'shilishiga ruxsat bormi? **B8, B9, B10** bo'yicha qaror (ha/yo'q)?
3. §3 navigatsiya va §7 lug'at (so'zlar) to'g'rimi? O'zgartirmoqchi bo'lgan so'zlaringiz bormi?
4. §8 maketlar, ayniqsa davomat ("hammasi Keldi" boshlang'ich holati) — qabul qilasizmi?
Tasdiqdan keyin 4-bosqichni **umumiy komponentlar + layout** dan boshlayman.
