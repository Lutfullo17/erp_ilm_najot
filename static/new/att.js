/* Davomat: har bir Keldi/Kelmadi toggle darhol saqlanadi; xabar Telegram orqali yuboriladi. */
(function () {
    'use strict';
    var app = document.getElementById('attApp');
    if (!app) return;
    var UX = window.UX;
    var editable = app.dataset.editable === '1';
    var rows = Array.prototype.slice.call(app.querySelectorAll('[data-id]'));
    function counts() {
        var c = { PRESENT: 0, ABSENT: 0 };
        rows.forEach(function (r) { c[r.querySelector('.js-attendance-toggle').checked ? 'PRESENT' : 'ABSENT']++; });
        return c;
    }
    function updateBtn() {
        var btn = document.getElementById('aSave'); if (!btn) return;
        var c = counts();
        btn.textContent = 'Dars ma’lumotlarini saqlash (' + c.PRESENT + ' keldi, ' + c.ABSENT + ' kelmadi)';
    }
    rows.forEach(function (r) {
        var toggle = r.querySelector('.js-attendance-toggle');
        if (toggle && editable) toggle.addEventListener('change', function () {
            var wasChecked = !toggle.checked;
            var state = r.querySelector('.attendance-state');
            toggle.disabled = true;
            state.textContent = toggle.checked ? 'Saqlanmoqda…' : 'Saqlanmoqda…';
            UX.api(app.dataset.toggleUrl, { body: {
                student_id: toggle.dataset.studentId,
                status: toggle.checked ? 'PRESENT' : 'ABSENT',
                date: app.dataset.date,
                topic: document.getElementById('aTopic').value,
                homework: document.getElementById('aHw').value
            } }).then(function () {
                toggle.setAttribute('aria-checked', toggle.checked ? 'true' : 'false');
                state.textContent = toggle.checked ? 'Keldi' : 'Kelmadi';
                updateBtn();
            }).catch(function (error) {
                toggle.checked = wasChecked;
                toggle.setAttribute('aria-checked', wasChecked ? 'true' : 'false');
                state.textContent = wasChecked ? 'Keldi' : 'Kelmadi';
                document.getElementById('aErr').textContent = error.message;
            }).finally(function () { toggle.disabled = false; });
        });

        var messageBtn = r.querySelector('.js-attendance-message');
        if (messageBtn) messageBtn.addEventListener('click', function () {
            var dialog = document.getElementById('dlg-attendance-message');
            dialog.dataset.studentId = messageBtn.dataset.studentId;
            document.getElementById('attMessageTitle').textContent = messageBtn.dataset.studentName + 'ga xabar yuborish';
            document.getElementById('attMessageText').value = '';
            document.getElementById('attMessageError').textContent = '';
            UX.openDlg('dlg-attendance-message');
            document.getElementById('attMessageText').focus();
        });
    });
    updateBtn();

    var messageSend = document.getElementById('attMessageSend');
    messageSend.addEventListener('click', function () {
        var dialog = document.getElementById('dlg-attendance-message');
        var text = document.getElementById('attMessageText').value.trim();
        var error = document.getElementById('attMessageError');
        if (!text) { error.textContent = 'Xabar matnini kiriting.'; return; }
        messageSend.disabled = true;
        error.textContent = '';
        UX.api(app.dataset.messageUrl, { body: { student_id: dialog.dataset.studentId, message: text } })
            .then(function (result) {
                dialog.close();
                UX.toast(result.detail || 'Xabar yuborildi.', { kind: 'ok' });
            }).catch(function (e) { error.textContent = e.message; })
            .finally(function () { messageSend.disabled = false; });
    });

    var save = document.getElementById('aSave');
    if (save) save.addEventListener('click', function () {
        var records = {};
        rows.forEach(function (r) { records[r.getAttribute('data-id')] = r.querySelector('.js-attendance-toggle').checked ? 'PRESENT' : 'ABSENT'; });
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
