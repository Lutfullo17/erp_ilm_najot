/* Davomat: bir bosish = Keldi/Kelmadi; ⋯ = Kechikdi/Sababli. Hamma boshida "Keldi". */
(function () {
    'use strict';
    var app = document.getElementById('attApp');
    if (!app) return;
    var UX = window.UX;
    var editable = app.dataset.editable === '1';
    var LABEL = { PRESENT: ['Keldi', 'fa-check'], ABSENT: ['Kelmadi', 'fa-xmark'], LATE: ['Kechikdi', 'fa-clock'], EXCUSED: ['Sababli', 'fa-file-medical'] };
    var rows = Array.prototype.slice.call(app.querySelectorAll('[data-id]'));
    var current = null;

    function paint(row) {
        var b = row.querySelector('.att-row'), s = b.getAttribute('data-s');
        b.querySelector('.a-text').textContent = LABEL[s][0];
        b.querySelector('i').className = 'fa-solid ' + LABEL[s][1];
        b.setAttribute('aria-label', row.querySelector('.a-name').textContent + ': ' + LABEL[s][0]);
    }
    function counts() {
        var c = { PRESENT: 0, ABSENT: 0, LATE: 0, EXCUSED: 0 };
        rows.forEach(function (r) { c[r.querySelector('.att-row').getAttribute('data-s')]++; });
        return c;
    }
    function updateBtn() {
        var btn = document.getElementById('aSave'); if (!btn) return;
        var c = counts();
        var parts = [(c.PRESENT + c.LATE) + ' keldi', c.ABSENT + ' kelmadi'];
        if (c.EXCUSED) parts.push(c.EXCUSED + ' sababli');
        btn.textContent = 'Saqlash: ' + parts.join(', ');
    }
    rows.forEach(function (r) {
        paint(r);
        if (!editable) return;
        var b = r.querySelector('.att-row');
        b.addEventListener('click', function () {
            b.setAttribute('data-s', b.getAttribute('data-s') === 'PRESENT' ? 'ABSENT' : 'PRESENT');
            paint(r); updateBtn();
        });
        var more = r.querySelector('.more');
        if (more) more.addEventListener('click', function () {
            current = r;
            document.getElementById('stName').textContent = r.querySelector('.a-name').textContent;
            UX.openDlg('dlg-status');
        });
    });
    var choices = document.getElementById('stChoices');
    if (choices) choices.addEventListener('click', function (e) {
        var a = e.target.closest('a[data-v]'); if (!a) return;
        e.preventDefault();
        if (current) { current.querySelector('.att-row').setAttribute('data-s', a.getAttribute('data-v')); paint(current); updateBtn(); }
        document.getElementById('dlg-status').close();
    });
    var all = document.getElementById('allPresent');
    if (all) all.addEventListener('click', function () {
        rows.forEach(function (r) { r.querySelector('.att-row').setAttribute('data-s', 'PRESENT'); paint(r); }); updateBtn();
    });
    updateBtn();

    var save = document.getElementById('aSave');
    if (save) save.addEventListener('click', function () {
        var records = {};
        rows.forEach(function (r) { records[r.getAttribute('data-id')] = r.querySelector('.att-row').getAttribute('data-s'); });
        var c = counts();
        function send() {
            var err = document.getElementById('aErr'); err.textContent = '';
            save.classList.add('is-loading');
            UX.api(app.dataset.url, { body: { records: records, date: app.dataset.date,
                topic: document.getElementById('aTopic').value, homework: document.getElementById('aHw').value } })
            .then(function (r) {
                UX.toast('Davomat saqlandi: ' + r.present + ' keldi, ' + r.absent + ' kelmadi', { kind: 'ok' });
                setTimeout(function () { location.href = app.dataset.after; }, 900);
            }).catch(function (e) { save.classList.remove('is-loading'); err.textContent = e.message; window.scrollTo(0, document.body.scrollHeight); });
        }
        if (c.ABSENT > rows.length / 2 && rows.length > 3) {
            UX.confirm({ title: 'Ko\'pchilik kelmadimi?', text: c.ABSENT + ' ta o\'quvchi "Kelmadi" deb belgilangan. To\'g\'rimi?', ok: 'Ha, saqlash' }, send);
        } else send();
    });
})();
