/* Guruh formasi: 4 qadam, kun tanlash, band xonalarni jonli ko'rsatish (B7). */
(function () {
    'use strict';
    var form = document.getElementById('gForm');
    if (!form) return;
    var UX = window.UX;
    var edit = form.dataset.edit === '1';
    var steps = Array.prototype.slice.call(form.querySelectorAll('[data-step]'));
    var cur = parseInt(form.dataset.openStep || '1', 10);
    var next = document.getElementById('gNext'), back = document.getElementById('gBack'), save = document.getElementById('gSave');
    var $ = function (id) { return document.getElementById(id); };

    function days() { return Array.prototype.slice.call(form.querySelectorAll('.js-day:checked')).map(function (i) { return i.value; }); }
    function setDays(list) {
        form.querySelectorAll('.js-day').forEach(function (i) { i.checked = list.indexOf(i.value) !== -1; i.parentNode.classList.toggle('on', i.checked); });
        checkSlot();
    }
    form.querySelectorAll('.js-day').forEach(function (i) { i.addEventListener('change', function () { i.parentNode.classList.toggle('on', i.checked); checkSlot(); }); });
    form.querySelectorAll('.js-preset').forEach(function (b) { b.addEventListener('click', function () { setDays(b.dataset.days.split(', ')); }); });

    var timer = null, seq = 0;
    function checkSlot() {
        clearTimeout(timer);
        timer = setTimeout(function () {
            var t = $('id_lesson_time').value, d = $('id_duration').value, ds = days();
            if (!t || !ds.length) return;
            var mine = ++seq;
            var url = form.dataset.check + '?days=' + encodeURIComponent(ds.join(',')) + '&time=' + t + '&duration=' + d +
                '&teacher=' + ($('id_teacher').value || '') + '&exclude=' + (form.dataset.exclude || '');
            UX.api(url).then(function (r) {
                if (mine !== seq) return;
                r.rooms.forEach(function (rm) {
                    var lab = form.querySelector('[data-room="' + rm.id + '"]'); if (!lab) return;
                    var inp = lab.querySelector('input'), span = lab.querySelector('span');
                    span.textContent = rm.label + (rm.free ? '' : ' — band (' + rm.busy_by + ')');
                    inp.disabled = !rm.free && !inp.checked ? true : false;
                    if (!rm.free && inp.checked) { lab.style.borderColor = 'var(--danger)'; } else lab.style.borderColor = '';
                    lab.style.opacity = rm.free ? '' : '.6';
                });
                $('roomNote').textContent = "Band xonalar belgilangan. Bo'sh xonani tanlang.";
                var w = $('teacherWarn');
                w.hidden = !r.teacher_busy; w.textContent = r.teacher_busy;
            }).catch(function () { /* tekshiruv ixtiyoriy: saqlashda server yana tekshiradi */ });
        }, 300);
    }
    ['id_lesson_time', 'id_duration', 'id_teacher'].forEach(function (id) { $(id).addEventListener('change', checkSlot); });

    function summary() {
        var t = $('id_teacher'), r = form.querySelector('input[name=room]:checked');
        var rows = [['Guruh', $('id_name').value || '—'], ["Oylik to'lov", ($('id_monthly_fee').value || '0') + " so'm"],
            ["O'qituvchi", t.options[t.selectedIndex].text], ['Kunlar', days().join(', ') || '—'],
            ['Vaqt', ($('id_lesson_time').value || '—') + ' (' + $('id_duration').options[$('id_duration').selectedIndex].text + ')'],
            ['Xona', r && r.value ? r.parentNode.textContent.trim() : 'Keyinroq']];
        var box = $('gSummary'); box.textContent = '';
        var dl = UX.el('dl', { class: 'kv' });
        rows.forEach(function (p) { dl.appendChild(UX.el('dt', { text: p[0] })); dl.appendChild(UX.el('dd', { text: p[1] })); });
        box.appendChild(UX.el('h3', { text: 'Tekshirib ko\'ring' })); box.appendChild(dl);
    }

    function render() {
        if (edit) { checkSlot(); return; }
        steps.forEach(function (s) { s.hidden = parseInt(s.dataset.step, 10) !== cur; });
        $('gStepTxt').textContent = 'Qadam ' + cur + '/4'; $('gBar').style.width = (cur * 25) + '%';
        back.hidden = cur === 1; next.hidden = cur === 4; save.hidden = cur !== 4;
        if (cur === 4) { summary(); checkSlot(); }
        window.scrollTo(0, 0);
    }
    function err(id, text, input) { var e = $(id); e.textContent = text; if (input) { if (text) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid'); } }
    function validate(step) {
        if (step === 1) {
            var ok = true;
            if (!$('id_name').value.trim()) { err('e_name', 'Guruh nomini kiriting. Masalan: Ingliz tili A1', $('id_name')); ok = false; } else err('e_name', '', $('id_name'));
            if (!$('id_monthly_fee').value.trim()) { err('e_fee', 'Oylik narxni kiriting. Masalan: 300 000', $('id_monthly_fee')); ok = false; } else err('e_fee', '', $('id_monthly_fee'));
            if (!ok) ($('id_name').value.trim() ? $('id_monthly_fee') : $('id_name')).focus();
            return ok;
        }
        if (step === 3) {
            if (!days().length) { UX.toast('Kamida bitta dars kunini tanlang', { kind: 'bad' }); return false; }
            if (!$('id_lesson_time').value) { UX.toast('Dars boshlanish vaqtini kiriting', { kind: 'bad' }); $('id_lesson_time').focus(); return false; }
            if (!$('id_start_date').value) { UX.toast('Boshlanish sanasini tanlang', { kind: 'bad' }); $('id_start_date').focus(); return false; }
        }
        return true;
    }
    if (next) next.addEventListener('click', function () { if (validate(cur) && cur < 4) { cur++; render(); } });
    if (back) back.addEventListener('click', function () { if (cur > 1) { cur--; render(); } });
    render();
    var firstErr = form.querySelector('[aria-invalid=true]'); if (firstErr) firstErr.focus();
})();
