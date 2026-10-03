# BIRLASHTIRILGAN RO'YXAT VA TUZATISH REJASI (QA 4-bosqich)

Manba: [BACKEND_TEST_REPORT.md](BACKEND_TEST_REPORT.md), [FRONTEND_TEST_REPORT.md](FRONTEND_TEST_REPORT.md). **Hech narsa tuzatilmagan** (QA-F-01 dan tashqari). Shu yerda to'xtab, tasdig'ingizni kutaman.

## Statistika
| Jiddiylik | Soni | Holat |
|---|---|---|
| Kritik | 1 | QA-F-01 — **tuzatilgan** (telefonda gorizontal scroll) |
| Yuqori | 2 | QA-B-04 (= QA-F-02, bitta sabab), QA-F-11 |
| O'rta | 13 | QA-B-03, -06, -08, -10, -12, -13, QA-N-01, -02, QA-F-03, -04, -05, -06, -12 (ba'zilari bitta tuzatishda) |
| Past | 13 | QA-B-01, -02, -05, -07, -09, -11, -14, QA-F-07..10, -13, -14 |

(Eslatma: QA-B-15 — ma'lumot, tuzatilgan.)

## Ustuvorlik bo'yicha ro'yxat
| # | ID | Jiddiylik | Nima | Hajm |
|---|---|---|---|---|
| 1 | QA-F-01 | Kritik | Telefonda sig'maslik — **tuzatilgan**, qayta tekshirildi | — |
| 2 | QA-B-04 / QA-F-02 | Yuqori | NULL `created_by` → direktor sahifalari 500 (eski bosh sahifa, yangi tarix va kvitansiya) | 3 shablon, 1 test — 30 daq. |
| 3 | QA-F-11 | Yuqori | Eski funksiyalar yo'qolgan: "Mening o'quvchilarim", "3+ dars davomat yo'q", arizalar tarixi (hammasi), direktor davomat statistikasi | 4 ekran/kartochka — 3–4 soat |
| 4 | QA-B-03 | O'rta | JSON turlari/`1e999` → 500 (~25 endpoint) | umumiy `json_body` + `parse_money` — 2 soat |
| 5 | QA-N-01, QA-N-02 | O'rta | `?page=abc`, katta id → 500 (yangi UI) | 1 yordamchi — 30 daq. |
| 6 | QA-F-03 | O'rta | Sessiya tugaganda kirish havolasi | `new.js` — 1 soat |
| 7 | QA-F-04, -05, -06, -12 | O'rta | To'lov sahifasi yopishqoq panel/telefon format; o'quvchi qo'shilgach takror tugma va "To'langan"; `select` label; telefon menyusida "Yana" | shablon/CSS — 2 soat |
| 8 | QA-B-08, -10 | O'rta | Eski direktor bosh sahifasi N+1; eski qarzdorlar sahifasiz; o'qituvchilar N+1 | 1 soat |
| 9 | QA-B-06 | O'rta | DB cheklovlari (`amount>0`, `left_at>=joined_at`) | migratsiya + **avval prod'da tekshiruv so'rovi (sizga ko'rsataman)** |
| 10 | QA-B-12 | O'rta | Sessiya muddati va umumiy kesh | **qaror kerak** (§Savollar) |
| 11 | QA-B-13 | O'rta | Ommaviy xabar sinxron | **backend arxitektura qarori** (navbat) — alohida ish |
| 12 | Past guruh | Past | QA-B-01, -02, -05, -07, -09, -11, -14; QA-F-07..10, -13, -14 | 2–3 soat |

Jami taxminiy hajm (qarorlar bo'lmasa): ~1 ish kuni. Har biri alohida commit, `expectedFailure` testini oddiy testga aylantirish bilan.

## Tuzatish tartibi (5-bosqich, tasdiqdan keyin)
1. #2 → #4 → #5 (xavfsiz, kichik, testlar bor).
2. #3 (yo'qolgan funksiyalar) → #7 → #6.
3. #8 va Past guruh.
4. #9 va #10, #11 — faqat sizning qaroringizdan keyin; #9 uchun avval **faqat o'qish** so'rovlarini bajaraman (prod nusxasida) va natijani ko'rsataman.
5. Har bosqichdan so'ng to'liq test (hozir 203), `check --deploy`, `pip-audit`, bandit, brauzerda qayta sinov (360/1280, kun/tun).

## Menga qaror kerak
1. **QA-B-12:** sessiya muddati (taklif: 12 soat, kassa uchun) va login limiti uchun umumiy kesh (DB kesh jadvali yoki Redis) — qabul qilasizmi?
2. **QA-B-06:** guruh sig'imi (capacity) kerakmi? Kerak bo'lsa nechta o'quvchi va ortiqchani rad etamizmi yoki ogohlantiramizmi?
3. **QA-B-13:** ommaviy xabarni orqa fon navbatiga o'tkazish (kichik `outbox` jadvali + mavjud scheduler) — ruxsat berasizmi? (Yangi jadval)
4. **QA-F-12:** telefondagi pastki menyuga 5-element "Yana" qo'shaymi (Guruhlar, Dars jadvali, Xabarlar)?
5. **QA-B-07:** minimal to'lov summasi (taklif: 1 000 so'm) va ilmiy yozuvni rad etish.
6. **QA-F-13:** "Login" so'zi "Foydalanuvchi nomi" bilan almashtirilsinmi?
7. Prod bazada NULL `created_by` to'lovlar bormi? (`SELECT count(*) FROM payments_paymenttransaction WHERE created_by_id IS NULL;` — faqat o'qish.) Bo'lsa QA-B-04 haqiqiy xavf.

**To'xtadim — 5-bosqichni boshlash uchun tasdig'ingizni kutaman.**
