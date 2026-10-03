/* To'lov qabul qilish: topish -> summa -> tayyor. Mavjud apply_payment() ni /new/api/payments/ orqali chaqiradi. */
(function () {
    'use strict';
    var UX = window.UX, el = UX.el;
    var app = document.getElementById('payApp');
    if (!app) return;
    var $ = function (id) { return document.getElementById(id); };
    var cfg = { search: app.dataset.search, info: app.dataset.info, create: app.dataset.create, today: app.dataset.today };
    var state = { student: null, group: null, key: null, payment: null, timer: null, seq: 0 };

    function uuid() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) { var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); });
    }
    function som(v) { return UX.fmtMoney(String(Math.round(Number(v) || 0))); }
    function show(id) { ['stepFind', 'stepPay', 'stepDone'].forEach(function (s) { $(s).hidden = s !== id; }); window.scrollTo(0, 0); }
    function setErr(id, text, input) {
        $(id).textContent = text || '';
        if (input) { if (text) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid'); }
    }

    /* ---- 1. Qidirish ---- */
    var q = $('payQ'), res = $('payResults');
    function say(text, retry) {
        res.textContent = '';
        res.appendChild(el('p', { class: 'muted', text: text }));
        if (retry) { var b = el('button', { type: 'button', class: 'btn btn-secondary', text: 'Qayta urinish' }); b.addEventListener('click', run); res.appendChild(b); }
    }
    function run() {
        var term = q.value.trim();
        if (term.length < 2) { res.textContent = ''; return; }
        var seq = ++state.seq;
        res.textContent = '';
        for (var i = 0; i < 3; i++) res.appendChild(el('div', { class: 'skeleton' }));
        UX.api(cfg.search + '?q=' + encodeURIComponent(term)).then(function (d) {
            if (seq !== state.seq) return;
            res.textContent = '';
            if (!d.students.length) {
                res.appendChild(el('div', { class: 'empty' }, [el('p', { text: '"' + term + "\" bo'yicha o'quvchi topilmadi." }),
                    el('a', { class: 'btn btn-primary', href: app.dataset.newStudent, text: "Yangi o'quvchi qo'shish" })]));
                return;
            }
            d.students.forEach(function (s) {
                var debt = Number(s.debt) > 0;
                var b = el('button', { type: 'button', class: 'item', style: 'width:100%;text-align:left;font:inherit;color:inherit;cursor:pointer' }, [
                    el('div', { class: 'i-main' }, [el('div', { class: 'i-title', text: s.name }), el('div', { class: 'i-sub', text: s.phone || 'Telefon kiritilmagan' })]),
                    el('span', { class: 'badge ' + (debt ? 'bad' : 'ok'), text: debt ? 'Qarzi: ' + som(s.debt) + " so'm" : "Qarzi yo'q" })]);
                b.addEventListener('click', function () { load(s.id); });
                res.appendChild(b);
            });
        }).catch(function (e) { if (seq === state.seq) say(e.message, true); });
    }
    q.addEventListener('input', function () { clearTimeout(state.timer); state.timer = setTimeout(run, 250); });

    /* ---- 2. O'quvchi yuklash va summa ---- */
    function load(id) {
        say('Yuklanmoqda...');
        UX.api(cfg.info.replace('/0/', '/' + id + '/')).then(showPay).catch(function (e) { say(e.message, true); });
    }
    function selectedGroup() {
        var r = document.querySelector('input[name=group]:checked');
        if (!r) return null;
        return state.student.groups.filter(function (g) { return String(g.id) === r.value; })[0];
    }
    function refreshAmount(force) {
        var g = selectedGroup(); if (!g) return;
        state.group = g;
        var debt = Number(g.debt), fee = Number(g.fee);
        var amt = $('pAmount');
        if (force || !amt.dataset.touched) amt.value = som(debt > 0 ? debt : fee);
        $('pAmountHint').textContent = debt > 0 ? 'Qarzi: ' + som(debt) + " so'm (" + g.months + ' oy)' : "Qarzi yo'q. Oldindan to'lov sifatida qabul qilinadi (bir oylik: " + som(fee) + " so'm).";
        var chips = $('pChips'); chips.textContent = '';
        if (debt > 0) chips.appendChild(chip("Qarzni to'liq yopish: " + som(debt), debt));
        if (fee > 0 && fee !== debt) chips.appendChild(chip('Bir oylik: ' + som(fee), fee));
        updateBtn();
    }
    function chip(label, val) {
        var b = el('button', { type: 'button', class: 'chip', text: label });
        b.addEventListener('click', function () { $('pAmount').value = som(val); $('pAmount').dataset.touched = '1'; setErr('pAmountErr', ''); updateBtn(); });
        return b;
    }
    function updateBtn() {
        var n = Number($('pAmount').value.replace(/\D/g, '')) || 0;
        $('pSubmit').textContent = n > 0 ? som(n) + " so'm qabul qilish" : 'Qabul qilish';
    }
    function showPay(info) {
        state.student = info; state.key = uuid();
        $('pName').textContent = info.name; $('pPhone').textContent = info.phone || '';
        var box = $('pGroups'); box.textContent = '';
        var pre = app.dataset.preGroup;
        if (!info.groups.length) {
            box.appendChild(el('div', { class: 'alert warn' }, [el('span', { text: "Bu o'quvchi hech qaysi guruhga qo'shilmagan. Avval guruhga qo'shing." })]));
            $('pSubmit').disabled = true;
        } else $('pSubmit').disabled = false;
        info.groups.forEach(function (g, i) {
            var checked = pre ? String(g.id) === pre : i === 0;
            var inp = el('input', { type: 'radio', name: 'group', value: String(g.id) });
            if (checked) inp.checked = true;
            var lab = el('label', { class: 'choice' }, [inp, el('span', { class: 'grow' }, [el('b', { text: g.name }), el('div', { class: 'muted small', text: Number(g.debt) > 0 ? 'Qarzi: ' + som(g.debt) + " so'm" : "Qarzi yo'q" })])]);
            if (!g.has_fee) lab.appendChild(el('span', { class: 'badge warn', text: 'Narx belgilanmagan' }));
            inp.addEventListener('change', function () { $('pAmount').dataset.touched = ''; refreshAmount(true); });
            box.appendChild(lab);
        });
        $('groupCard').hidden = info.groups.length < 2 ? false : false;
        $('pAmount').dataset.touched = '';
        refreshAmount(true);
        show('stepPay');
        $('pAmount').focus();
    }
    $('pChange').addEventListener('click', function () { show('stepFind'); q.focus(); });
    $('pAmount').addEventListener('input', function () { this.dataset.touched = '1'; setErr('pAmountErr', '', this); setErr('pFormErr', ''); updateBtn(); });
    document.querySelectorAll('input[name=dateMode]').forEach(function (r) {
        r.addEventListener('change', function () {
            var other = r.value === 'other' && r.checked;
            $('dField').hidden = !other;
            $('dToday').classList.toggle('on', !other); $('dOther').classList.toggle('on', other);
        });
    });

    /* ---- Yuborish ---- */
    $('payForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var amtInput = $('pAmount');
        var amount = Number(amtInput.value.replace(/\D/g, ''));
        setErr('pFormErr', '');
        if (!amount || amount <= 0) { setErr('pAmountErr', "Summa 0 dan katta bo'lishi kerak. Masalan: 300 000", amtInput); amtInput.focus(); return; }
        var g = selectedGroup();
        if (!g) { setErr('pFormErr', 'Guruhni tanlang.'); return; }
        if (!g.has_fee) { setErr('pFormErr', "Bu guruhning oylik narxi belgilanmagan. Avval guruh narxini kiriting."); return; }
        var other = document.querySelector('input[name=dateMode]:checked').value === 'other';
        var btn = $('pSubmit'); btn.classList.add('is-loading');
        UX.api(cfg.create, { body: {
            student_id: state.student.id, group_id: g.id, amount: amount,
            payment_date: other ? $('pDate').value : cfg.today,
            method: document.querySelector('input[name=method]:checked').value, note: $('pNote').value,
            idempotency_key: state.key } })
        .then(done).catch(function (err) {
            btn.classList.remove('is-loading');
            setErr('pFormErr', err.network ? err.message : err.message);
        });
    });

    /* ---- 3. Tayyor ---- */
    function done(r) {
        state.payment = r.payment;
        $('dTitle').textContent = som(r.payment.amount) + " so'm qabul qilindi";
        var dl = $('dInfo'); dl.textContent = '';
        [["O'quvchi", r.student.full_name], ['Guruh', r.group.name], ['Sana', r.payment.payment_date.split('-').reverse().join('.')],
         ['Guruh bo\'yicha qolgan qarz', Number(r.left_debt) > 0 ? som(r.left_debt) + " so'm" : "Yo'q"],
         ['Jami qarzi', Number(r.total_left_debt) > 0 ? som(r.total_left_debt) + " so'm" : "Yo'q"]].forEach(function (p) {
            dl.appendChild(el('dt', { text: p[0] })); dl.appendChild(el('dd', { text: p[1] }));
        });
        $('dReceipt').href = r.payment.receipt_url;
        show('stepDone');
        UX.toast("To'lov saqlandi", { kind: 'ok' });
    }
    $('dUndo').addEventListener('click', function () {
        UX.confirm({ title: "To'lovni bekor qilamizmi?", text: "To'lov o'chiriladi va o'quvchining qarzi qayta hisoblanadi.", ok: 'Ha, bekor qilish', danger: true }, function () {
            UX.api(state.payment.undo_url, { method: 'POST', body: {} }).then(function () {
                UX.toast("To'lov bekor qilindi", { kind: 'ok' });
                $('dUndo').disabled = true;
                $('dTitle').textContent = "To'lov bekor qilindi";
            }).catch(function (err) { UX.toast(err.message, { kind: 'bad' }); });
        });
    });

    /* ---- Tayyor ma'lumot (qarzdorlar ro'yxatidan: ?student=ID) ---- */
    var pre = document.getElementById('preData');
    if (pre) showPay(JSON.parse(pre.textContent));
})();
