/* O'quvchi formasi: qadamlar (yangi o'quvchi), chegirma bo'limi, birinchi xatoga fokus. */
(function () {
    'use strict';
    var form = document.getElementById('sForm');
    if (!form) return;
    var edit = form.dataset.edit === '1';
    var steps = Array.prototype.slice.call(form.querySelectorAll('[data-step]'));
    var cur = parseInt(form.dataset.openStep || '1', 10);
    var next = document.getElementById('sNext'), back = document.getElementById('sBack'), save = document.getElementById('sSave');
    function render() {
        if (edit) return;
        steps.forEach(function (s) { s.hidden = parseInt(s.dataset.step, 10) !== cur; });
        document.getElementById('sStepTxt').textContent = 'Qadam ' + cur + '/3';
        document.getElementById('sBar').style.width = (cur / 3 * 100) + '%';
        back.hidden = cur === 1; next.hidden = cur === 3;
        next.innerHTML = cur === 1 ? "Qo'shimcha ma'lumot kiritish <i class=\"fa-solid fa-arrow-right\"></i>" : 'Keyingi <i class="fa-solid fa-arrow-right"></i>';
        save.textContent = cur === 3 ? 'Saqlash' : 'Hozir saqlash';
        window.scrollTo(0, 0);
    }
    if (next) next.addEventListener('click', function () { if (cur < 3) { cur++; render(); } });
    if (back) back.addEventListener('click', function () { if (cur > 1) { cur--; render(); } });
    render();

    var has = document.getElementById('id_has_discount'), box = document.getElementById('discBox');
    if (has) has.addEventListener('change', function () { box.hidden = !has.checked; });

    /* Bo'sh ism bilan yuborishni darhol maydonda ko'rsatish */
    form.addEventListener('submit', function (e) {
        var name = document.getElementById('id_full_name');
        if (!name.value.trim()) {
            e.preventDefault(); e.stopImmediatePropagation();
            cur = 1; render();
            document.getElementById('e_name').textContent = "Ism va familiyani kiriting. Masalan: Ali Valiyev";
            name.setAttribute('aria-invalid', 'true'); name.focus();
        }
    }, true);

    var firstErr = form.querySelector('[aria-invalid=true]');
    if (firstErr) firstErr.focus();

    /* Ota-ona raqami bo'yicha aka-uka/opa-singillar (mavjud API) */
    var pp = document.getElementById('id_parent_phone'), sib = document.getElementById('siblings'), t = null;
    if (pp) pp.addEventListener('input', function () {
        clearTimeout(t);
        t = setTimeout(function () {
            var d = pp.value.replace(/\D/g, '');
            if (d.length < 9) { sib.hidden = true; return; }
            fetch('/students/api/check-parent-phone/?phone=' + encodeURIComponent(d), { credentials: 'same-origin' })
                .then(function (r) { return r.json(); }).then(function (data) {
                    if (data.siblings && data.siblings.length) { sib.textContent = "Bu raqam bilan ro'yxatdan o'tgan farzandlar: " + data.siblings.join(', '); sib.hidden = false; }
                    else sib.hidden = true;
                }).catch(function () { sib.hidden = true; });
        }, 400);
    });
})();
