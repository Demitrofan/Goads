// «Просмотрено»: какие объявления человек уже открывал. Хранится только в этом браузере
// (входа на сайте нет). Страница объявления: <body data-viewed-id="rent-123">,
// карточка в списке: <div class="card" data-viewed-id="rent-123">.
(function () {
    var KEY = 'viewed', MAX = 3000;

    function load() {
        try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
    }

    function mark(id) {
        var v = load();
        v[id] = Date.now();
        var keys = Object.keys(v);
        if (keys.length > MAX) {   // забываем самые старые
            keys.sort(function (a, b) { return v[a] - v[b]; })
                .slice(0, keys.length - MAX).forEach(function (k) { delete v[k]; });
        }
        try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {}
    }

    var page = document.body.dataset.viewedId;
    if (page) mark(page);

    var cards = document.querySelectorAll('.card[data-viewed-id]');
    function paint() {
        var v = load();
        cards.forEach(function (c) { c.classList.toggle('viewed', !!v[c.dataset.viewedId]); });
    }
    cards.forEach(function (c) {
        // любая ссылка карточки (фото, «Подробнее», «Telegram») — объявление просмотрено
        c.addEventListener('click', function (e) {
            if (e.target.closest('a')) { mark(c.dataset.viewedId); c.classList.add('viewed'); }
        });
    });
    paint();
    // вернулись кнопкой «Назад» — страница из памяти браузера, пометки обновить
    window.addEventListener('pageshow', function (e) { if (e.persisted) paint(); });
})();
