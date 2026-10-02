/* Sahifa chizilishidan oldin mavzuni o'rnatadi (miltillashsiz).
   Tanlov bo'lmasa — tizim sozlamasi (prefers-color-scheme). */
(function () {
    var theme = null;
    try { theme = localStorage.getItem('erp-theme'); } catch (e) { /* maxfiy rejim */ }
    if (theme !== 'light' && theme !== 'dark') {
        theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
})();
