/* Umumiy interfeys: yon panel, foydalanuvchi menyusi, kun/tun rejimi,
   tasdiqlash (data-confirm) va qayta yuborishdan himoya (yuklanish holati). */
(function () {
    'use strict';
    var root = document.documentElement;
    var $ = function (id) { return document.getElementById(id); };

    /* ---- Yon panel (mobil) ---- */
    var sidebar = $('sidebar'), overlay = $('sidebarOverlay');
    var toggle = $('mobileToggle'), closeBtn = $('sidebarCloseBtn');
    function setSidebar(open) {
        if (!sidebar) return;
        sidebar.classList.toggle('active', open);
        if (overlay) overlay.classList.toggle('active', open);
        document.body.style.overflow = open ? 'hidden' : '';
        if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    if (toggle) toggle.addEventListener('click', function (e) { e.stopPropagation(); setSidebar(!sidebar.classList.contains('active')); });
    if (closeBtn) closeBtn.addEventListener('click', function () { setSidebar(false); });
    if (overlay) overlay.addEventListener('click', function () { setSidebar(false); });
    window.addEventListener('resize', function () { if (window.innerWidth > 1024) setSidebar(false); });

    /* ---- Foydalanuvchi menyusi ---- */
    var avatar = $('avatarBtn'), menu = $('dropdownMenu');
    function setMenu(open) {
        if (!menu) return;
        menu.classList.toggle('active', open);
        if (avatar) avatar.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    if (avatar && menu) {
        avatar.addEventListener('click', function (e) { e.stopPropagation(); setMenu(!menu.classList.contains('active')); });
        document.addEventListener('click', function (e) { if (!menu.contains(e.target)) setMenu(false); });
    }
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { setMenu(false); setSidebar(false); }
    });

    /* ---- Kun / tun rejimi ---- */
    var themeBtn = $('themeToggle');
    function paintThemeButton() {
        if (!themeBtn) return;
        var dark = root.getAttribute('data-theme') === 'dark';
        themeBtn.innerHTML = '<i class="fas fa-' + (dark ? 'sun' : 'moon') + '" aria-hidden="true"></i>';
        var label = dark ? 'Kun rejimiga o\'tish' : 'Tun rejimiga o\'tish';
        themeBtn.setAttribute('aria-label', label);
        themeBtn.title = label;
    }
    paintThemeButton();
    if (themeBtn) {
        themeBtn.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            try { localStorage.setItem('erp-theme', next); } catch (e) { /* ignore */ }
            paintThemeButton();
        });
    }

    /* ---- Brauzer confirm oynasi o'rniga markaziy ilova dialogi ---- */
    var confirmDialog = $('appConfirmDialog');
    var confirmMessage = $('appConfirmMessage');
    var confirmPending = null;
    function finishConfirm(result) {
        if (!confirmPending) return;
        var resolve = confirmPending;
        confirmPending = null;
        if (confirmDialog && confirmDialog.open) confirmDialog.close();
        resolve(result);
    }
    window.AppConfirm = function (message, opts) {
        opts = opts || {};
        if (!confirmDialog || !confirmMessage) return Promise.resolve(false);
        if (confirmPending) finishConfirm(false);
        $('appConfirmTitle').textContent = opts.title || 'Tasdiqlash';
        confirmMessage.textContent = message || '';
        $('appConfirmAccept').textContent = opts.ok || 'Tasdiqlash';
        $('appConfirmAccept').className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');
        return new Promise(function (resolve) {
            confirmPending = resolve;
            confirmDialog.showModal();
        });
    };
    var confirmAccept = $('appConfirmAccept'), confirmCancel = $('appConfirmCancel');
    if (confirmAccept) confirmAccept.addEventListener('click', function () { finishConfirm(true); });
    if (confirmCancel) confirmCancel.addEventListener('click', function () { finishConfirm(false); });
    if (confirmDialog) confirmDialog.addEventListener('cancel', function () { finishConfirm(false); });

    /* ---- Tasdiqlash: <form data-confirm="Savol?"> yoki <button data-confirm="..."> ---- */
    document.addEventListener('submit', function (e) {
        var form = e.target;
        var submitter = e.submitter;
        var msg = (submitter && submitter.getAttribute('data-confirm')) || form.getAttribute('data-confirm');
        if (msg && !form.__appConfirmPassed) {
            e.preventDefault();
            window.AppConfirm(msg, { title: (submitter && submitter.getAttribute('data-confirm-title')) || form.getAttribute('data-confirm-title') || 'Tasdiqlash',
                ok: (submitter && submitter.getAttribute('data-confirm-ok')) || form.getAttribute('data-confirm-ok') || 'Tasdiqlash',
                danger: (submitter && submitter.hasAttribute('data-danger')) || form.hasAttribute('data-danger') }).then(function (accepted) {
                if (!accepted) return;
                form.__appConfirmPassed = true;
                if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
                setTimeout(function () { form.__appConfirmPassed = false; }, 0);
            });
            return;
        }
        /* Qayta yuborishdan himoya + yuklanish holati */
        if (!e.defaultPrevented && !form.hasAttribute('data-no-lock')) {
            if (form.dataset.submitting === '1') { e.preventDefault(); return; }
            form.dataset.submitting = '1';
            var btn = submitter || form.querySelector('button[type="submit"], input[type="submit"]');
            if (btn) {
                btn.classList.add('is-loading');
                setTimeout(function () { /* sahifa yuklanmasa (xato) qayta ochish */
                    form.dataset.submitting = '0'; btn.classList.remove('is-loading');
                }, 15000);
            }
        }
    });

    /* ---- Jadval: tezkor qidiruv va saralash (<table data-enhance>) ---- */
    document.querySelectorAll('table[data-enhance]').forEach(function (table) {
        var tbody = table.tBodies[0];
        if (!tbody) return;
        var tools = document.createElement('div');
        tools.className = 'table-tools';
        tools.innerHTML = '<input type="search" placeholder="Jadvaldan qidirish..." aria-label="Jadvaldan qidirish">';
        var holder = table.closest('.table-container') || table;
        holder.parentNode.insertBefore(tools, holder);
        var input = tools.firstChild;
        input.addEventListener('input', function () {
            var q = input.value.trim().toLowerCase();
            Array.prototype.forEach.call(tbody.rows, function (row) {
                row.style.display = !q || row.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
            });
        });
        var heads = table.tHead ? table.tHead.rows[0].cells : [];
        Array.prototype.forEach.call(heads, function (th, idx) {
            if (!th.textContent.trim()) return;
            th.setAttribute('data-sortable', '');
            th.tabIndex = 0;
            function sort() {
                var asc = th.getAttribute('aria-sort') !== 'ascending';
                Array.prototype.forEach.call(heads, function (h) { h.removeAttribute('aria-sort'); });
                th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
                var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) { return r.cells.length > idx; });
                rows.sort(function (a, b) {
                    var x = a.cells[idx].textContent.trim(), y = b.cells[idx].textContent.trim();
                    var nx = parseFloat(x.replace(/[\s,]/g, '')), ny = parseFloat(y.replace(/[\s,]/g, ''));
                    var cmp = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : x.localeCompare(y, 'uz');
                    return asc ? cmp : -cmp;
                });
                rows.forEach(function (r) { tbody.appendChild(r); });
            }
            th.addEventListener('click', sort);
            th.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
        });
    });

    /* ---- Xabarlar (alert) yopish ---- */
    document.querySelectorAll('[data-dismiss-alert]').forEach(function (btn) {
        btn.addEventListener('click', function () { btn.closest('.alert').remove(); });
    });
})();
