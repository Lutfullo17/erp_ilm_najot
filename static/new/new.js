/* Yangi UI umumiy skripti: tema, oynalar, tasdiqlash, qidiruv, yordam, tanishtiruv, toast, formalar. */
(function () {
    'use strict';
    var root = document.documentElement;
    var $ = function (s, c) { return (c || document).querySelector(s); };
    var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
    var UX = window.UX = window.UX || {};

    function el(tag, attrs, children) {
        var n = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'text') n.textContent = attrs[k];
            else if (k === 'class') n.className = attrs[k];
            else n.setAttribute(k, attrs[k]);
        });
        (children || []).forEach(function (c) { n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
        return n;
    }
    UX.el = el;
    function csrf() {
        var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    /* ---- Kun / tun ---- */
    var themeBtn = $('#themeBtn');
    function paintTheme() {
        if (!themeBtn) return;
        var dark = root.getAttribute('data-theme') === 'dark';
        themeBtn.innerHTML = '<i class="fa-solid fa-' + (dark ? 'sun' : 'moon') + '" aria-hidden="true"></i>';
        themeBtn.setAttribute('aria-label', dark ? "Kun rejimiga o'tish" : "Tun rejimiga o'tish");
    }
    paintTheme();
    if (themeBtn) themeBtn.addEventListener('click', function () {
        var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        try { localStorage.setItem('erp-theme', next); } catch (e) { /* maxfiy rejim */ }
        paintTheme();
    });

    /* ---- Oynalar (dialog) ---- */
    function openDlg(id) {
        var d = document.getElementById(id);
        if (d && !d.open) { d.showModal(); var f = $('input,textarea,select', d); if (f && id !== 'dlg-quick') setTimeout(function () { f.focus(); }, 30); }
        return d;
    }
    UX.openDlg = openDlg;
    document.addEventListener('click', function (e) {
        var t = e.target.closest('[data-open]');
        if (t) { e.preventDefault(); var id = t.getAttribute('data-open'); var d = $('#dlg-user'); if (d && d.open && id !== 'dlg-user') d.close(); openDlg(id); return; }
        var c = e.target.closest('[data-close]');
        if (c) { var dlg = c.closest('dialog'); if (dlg) dlg.close(); return; }
        if (e.target.tagName === 'DIALOG') e.target.close();  /* orqa fonni bosish */
        var act = e.target.closest('[data-action="tour"]');
        if (act) { e.preventDefault(); var du = $('#dlg-user'); if (du) du.close(); startTour(true); }
    });
    document.addEventListener('keydown', function (e) {
        var tag = (e.target.tagName || '').toLowerCase();
        if (e.key === '/' && tag !== 'input' && tag !== 'textarea' && tag !== 'select') { e.preventDefault(); openDlg('dlg-search'); }
    });

    /* ---- Toast ---- */
    UX.toast = function (msg, opts) {
        opts = opts || {};
        var box = $('#toasts');
        var t = el('div', { class: 'toast ' + (opts.kind || ''), role: 'status' }, [el('span', { text: msg })]);
        if (opts.action) {
            var b = el('button', { type: 'button', text: opts.action });
            b.addEventListener('click', function () { t.remove(); if (opts.onAction) opts.onAction(); });
            t.appendChild(b);
        }
        box.appendChild(t);
        setTimeout(function () { t.remove(); }, opts.ms || (opts.action ? 10000 : 4500));
        return t;
    };

    /* ---- Sessiya tugaganda: aniq xabar va kirish havolasi ---- */
    function sessionExpired() {
        var url = '/users/login/?next=' + encodeURIComponent(location.pathname + location.search);
        UX.toast("Sessiya tugadi. Qayta kiring (sahifadagi ma'lumot o'zgarishsiz qoladi).", { kind: 'bad', ms: 20000, action: 'Kirish', onAction: function () { window.open(url, '_blank', 'noopener'); } });
        var e = new Error('Sessiya tugadi. Qayta kiring.'); e.status = 401; e.handled = true; throw e;
    }

    /* ---- API (JSON) ---- */
    UX.api = function (url, opts) {
        opts = opts || {};
        var init = { method: opts.method || 'GET', headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' };
        if (opts.body !== undefined) {
            init.method = opts.method || 'POST';
            init.headers['Content-Type'] = 'application/json';
            init.headers['X-CSRFToken'] = csrf();
            init.body = JSON.stringify(opts.body);
        }
        return fetch(url, init).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (data) {
                if (r.status === 401) return sessionExpired();
                if (!r.ok) { var err = new Error(data.detail || data.error || 'Xatolik yuz berdi'); err.status = r.status; err.data = data; throw err; }
                return data;
            });
        }, function () { var e = new Error("Internet bilan aloqa yo'q. Qayta urinib ko'ring."); e.network = true; throw e; });
    };


    /* Eski endpointlar uchun (form-urlencoded yoki multipart) */
    UX.post = function (url, fields, files) {
        var body;
        if (files) { body = new FormData(); Object.keys(fields || {}).forEach(function (k) { body.append(k, fields[k]); }); Object.keys(files).forEach(function (k) { body.append(k, files[k]); }); }
        else { body = new URLSearchParams(); Object.keys(fields || {}).forEach(function (k) { body.append(k, fields[k]); }); }
        return fetch(url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } })
            .then(function (r) {
                return r.json().catch(function () { return {}; }).then(function (data) {
                    if (r.status === 401) return sessionExpired();
                    if (!r.ok) { var e = new Error(data.detail || data.error || 'Xatolik yuz berdi'); e.status = r.status; throw e; }
                    return data;
                });
            }, function () { throw new Error("Internet bilan aloqa yo'q. Qayta urinib ko'ring."); });
    };

    /* ---- Tasdiqlash dialogi ---- */
    var pendingConfirm = null;
    function askConfirm(opts, onYes) {
        var d = $('#dlg-confirm');
        $('#dc-t').textContent = opts.title || 'Tasdiqlang';
        $('#dc-p').textContent = opts.text || '';
        var yes = $('#dc-yes');
        yes.textContent = opts.ok || 'Ha';
        yes.className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');
        pendingConfirm = onYes;
        $$('dialog.sheet[open]').forEach(function (o) { o.close(); });
        d.showModal();
    }
    UX.confirm = askConfirm;
    var dcYes = $('#dc-yes'), dcNo = $('#dc-no');
    if (dcYes) dcYes.addEventListener('click', function () { $('#dlg-confirm').close(); var f = pendingConfirm; pendingConfirm = null; if (f) f(); });
    if (dcNo) dcNo.addEventListener('click', function () { $('#dlg-confirm').close(); pendingConfirm = null; });

    /* ---- Formalar: tasdiqlash, qayta yuborishdan himoya, yuklanish ---- */
    function normalizeMoneyText(raw) {
        var text = String(raw || '').trim();
        if (!text) return '';
        var negative = text.charAt(0) === '-';
        text = text.replace(/-/g, '');
        text = text.replace(/\s+/g, '');
        if (text.indexOf(',') !== -1 && text.indexOf('.') !== -1) {
            var lastDot = text.lastIndexOf('.');
            var lastComma = text.lastIndexOf(',');
            text = (lastDot > lastComma) ? text.replace(/,/g, '') : text.replace(/\./g, '').replace(',', '.');
        } else if (text.indexOf(',') !== -1) {
            var parts = text.split(',');
            if (parts.length > 2 || parts[parts.length - 1].length <= 2) {
                text = parts.join('.');
            } else {
                text = parts.join('');
            }
        }
        text = text.replace(/[^\d.]/g, '');
        if (text.indexOf('.') !== -1) {
            var parts = text.split('.');
            if (parts.length > 2) {
                text = parts.shift() + '.' + parts.join('');
            }
            parts = text.split('.');
            if (parts.length > 1) {
                text = parts[0] + '.' + parts[1].slice(0, 2);
            }
        }
        return (negative ? '-' : '') + text;
    }

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (form.hasAttribute('data-ajax')) return;
        var sub = e.submitter;
        var src = (sub && sub.hasAttribute('data-confirm-title')) ? sub : form;
        if (src.hasAttribute('data-confirm-title') && !form.__confirmed) {
            e.preventDefault();
            askConfirm({ title: src.getAttribute('data-confirm-title'), text: src.getAttribute('data-confirm-text'),
                ok: src.getAttribute('data-confirm-ok'), danger: src.hasAttribute('data-danger') }, function () {
                form.__confirmed = true;
                if (form.requestSubmit) form.requestSubmit(sub || undefined); else form.submit();
            });
            return;
        }
        $$('input[data-money]', form).forEach(function (i) { i.value = normalizeMoneyText(i.value); });
        if (form.dataset.busy === '1') { e.preventDefault(); return; }
        form.dataset.busy = '1';
        var btn = sub || $('button[type=submit]', form);
        if (btn) { btn.classList.add('is-loading'); }
        setTimeout(function () { form.dataset.busy = '0'; if (btn) btn.classList.remove('is-loading'); }, 15000);
    });

    /* ---- Pul va telefon maydonlari ---- */
    function fmtMoney(s) {
        var normalized = normalizeMoneyText(s);
        if (!normalized) return '';
        var negative = normalized.charAt(0) === '-';
        var num = normalized.replace(/-/g, '');
        var p = num.split('.');
        var whole = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        var frac = p.length > 1 ? '.' + p[1] : '';
        return (negative ? '-' : '') + whole + frac;
    }
    function fmtPhone(s) {
        var d = s.replace(/\D/g, '');
        if (d.indexOf('998') === 0 && d.length > 9) d = d.slice(3);
        d = d.slice(0, 9);
        var out = d.slice(0, 2);
        if (d.length > 2) out += ' ' + d.slice(2, 5);
        if (d.length > 5) out += ' ' + d.slice(5, 7);
        if (d.length > 7) out += ' ' + d.slice(7, 9);
        return out;
    }
    UX.fmtMoney = fmtMoney;
    document.addEventListener('input', function (e) {
        var t = e.target;
        if (t.matches && t.matches('input[data-money]')) t.value = fmtMoney(t.value);
        if (t.matches && t.matches('input[data-phone]')) t.value = fmtPhone(t.value);
    });
    $$('input[data-money],input[data-phone]').forEach(function (i) {
        if (i.value) i.value = i.hasAttribute('data-money') ? fmtMoney(i.value) : fmtPhone(i.value);
    });

    /* ---- Global qidiruv ---- */
    var gs = $('#gsInput'), gsRes = $('#gsResults'), gsTimer = null, gsSeq = 0;
    function gsMessage(text, retry) {
        gsRes.textContent = '';
        var p = el('p', { class: 'muted', text: text });
        gsRes.appendChild(p);
        if (retry) { var b = el('button', { type: 'button', class: 'btn btn-secondary', text: 'Qayta urinish' }); b.addEventListener('click', runSearch); gsRes.appendChild(b); }
    }
    function renderResults(data) {
        gsRes.textContent = '';
        var any = false;
        (data.groups || []).forEach(function (grp) {
            if (!grp.items.length) return;
            any = true;
            gsRes.appendChild(el('div', { class: 'sr-group', text: grp.title }));
            grp.items.forEach(function (it) {
                var main = el('a', { class: 'i-main', href: it.url }, [el('div', { class: 'i-title', text: it.title }), el('div', { class: 'i-sub', text: it.sub || '' })]);
                var acts = el('div', { class: 'i-act' }, (it.actions || []).map(function (a) { return el('a', { class: 'btn btn-secondary btn-sm', href: a.url, text: a.label }); }));
                gsRes.appendChild(el('div', { class: 'item' }, [main, acts]));
            });
        });
        if (!any) {
            gsRes.appendChild(el('div', { class: 'empty' }, [el('p', { text: '"' + gs.value + '" bo\'yicha hech narsa topilmadi.' })]));
            if (data.empty_url) gsRes.appendChild(el('a', { class: 'btn btn-primary', href: data.empty_url, text: data.empty_label }));
        }
    }
    function runSearch() {
        var q = gs.value.trim();
        if (q.length < 2) { gsMessage('Kamida 2 ta harf yozing.'); return; }
        var seq = ++gsSeq;
        gsRes.textContent = '';
        for (var i = 0; i < 3; i++) gsRes.appendChild(el('div', { class: 'skeleton' }));
        UX.api(gs.getAttribute('data-url') + '?q=' + encodeURIComponent(q)).then(function (d) { if (seq === gsSeq) renderResults(d); })
            .catch(function (err) { if (seq === gsSeq) gsMessage(err.message, true); });
    }
    if (gs) gs.addEventListener('input', function () { clearTimeout(gsTimer); gsTimer = setTimeout(runSearch, 250); });

    /* ---- Yordam ---- */
    var tpl = $('#helpTpl');
    if (tpl && tpl.innerHTML.trim()) {
        var hb = $('#helpBtn'); hb.hidden = false;
        hb.addEventListener('click', function () { $('#helpBody').innerHTML = tpl.innerHTML; });
    }

    /* ---- Tanishtiruv (birinchi kirishda) ---- */
    var TOURS = {
        administrator: [
            ['Bu yerda bugungi ishlaringiz', "\"Bugun\" sahifasida qarzdorlar, to'lovlar va davomat holati ko'rinadi. Har kartada bitta tugma bor."],
            ['"+" tugmasi — tez amallar', "Yangi o'quvchi, to'lov qabul qilish, davomat va yangi guruh — hamma sahifadan 1 bosishda."],
            ['Qidiruv', "Tepadagi lupa orqali o'quvchi ismi, telefon yoki guruh nomini yozing — natijadan to'g'ridan to'lov qabul qilasiz."],
            ['Kun va tun rejimi', "Ko'zingiz charchasa, yuqoridagi tugma bilan rejimni almashtiring. Tanlovingiz saqlanadi."]],
        director: [
            ['Bugungi holat', "\"Bugun\" sahifasida tushum, qarzdorlar, davomat olinmagan darslar va kutilayotgan so'rovlar bor."],
            ['"+" tugmasi', "Yangi o'quvchi, to'lov, davomat va yangi guruh — tez amallar."],
            ['Qidiruv', "O'quvchi, guruh va o'qituvchilarni bir joydan qidiring."],
            ['Pul va xodimlar', "\"Pul\" bo'limida hisobot va qarzdorlar, \"Xodimlar\" da o'qituvchilar va jarima ballari."]],
        teacher: [
            ['Bugungi darslaringiz', "\"Bugun\" sahifasida hozirgi dars va bugungi jadval ko'rinadi."],
            ['Davomat qanday olinadi', "Hamma o'quvchi avtomatik \"Keldi\" bo'ladi. Faqat kelmaganlarni bosing, keyin \"Saqlash\"."],
            ['Baho qo\'yish', "\"Baholash\" bo'limida o'quvchilarga 0–100 foiz kiriting. Saqlangan bahoni administrator o'zgartiradi."],
            ['Kerak bo\'lsa yordam', "Har sahifadagi (?) tugmasi shu sahifa nima uchunligini tushuntiradi."]]
    };
    var tourI = 0, tourData = null;
    function tourKey() { return 'ux-tour-' + (document.body.getAttribute('data-user') || ''); }
    function showStep() {
        var s = tourData[tourI];
        $('#dt-t').textContent = s[0]; $('#dt-p').textContent = s[1];
        $('#tourStep').textContent = (tourI + 1) + '/' + tourData.length;
        $('#tourBar').style.width = ((tourI + 1) / tourData.length * 100) + '%';
        $('#tourNext').textContent = tourI === tourData.length - 1 ? 'Boshlash' : 'Keyingi';
    }
    function endTour() { try { localStorage.setItem(tourKey(), '1'); } catch (e) { /* */ } var d = $('#dlg-tour'); if (d.open) d.close(); }
    function startTour(force) {
        tourData = TOURS[UX.role]; if (!tourData) return;
        if (!force) { try { if (localStorage.getItem(tourKey())) return; } catch (e) { return; } }
        tourI = 0; showStep(); $('#dlg-tour').showModal();
    }
    if ($('#tourNext')) {
        $('#tourNext').addEventListener('click', function () { if (tourI >= tourData.length - 1) endTour(); else { tourI++; showStep(); } });
        $('#tourSkip').addEventListener('click', endTour);
        if (location.pathname.replace(/\/$/, '') === UX.home.replace(/\/$/, '')) setTimeout(function () { startTour(false); }, 600);
    }

    /* ---- Fikr bildirish ---- */
    var fb = $('#feedbackForm');
    if (fb) fb.addEventListener('submit', function (e) {
        e.preventDefault(); e.stopImmediatePropagation();
        var data = new FormData(fb);
        UX.api(fb.action, { body: { message: data.get('message'), page: data.get('page') } }).then(function () {
            $('#dlg-feedback').close(); fb.reset(); UX.toast('Rahmat! Fikringiz yuborildi.', { kind: 'ok' });
        }).catch(function (err) { UX.toast(err.message, { kind: 'bad' }); });
    }, true);

    /* ---- Ro'yxatda tezkor filtr: <input data-filter="#listId"> ---- */
    $$('input[data-filter]').forEach(function (inp) {
        inp.addEventListener('input', function () {
            var q = inp.value.trim().toLowerCase();
            $$(inp.getAttribute('data-filter') + ' > [data-search]').forEach(function (r) {
                r.hidden = q && r.getAttribute('data-search').toLowerCase().indexOf(q) === -1;
            });
        });
    });
})();
