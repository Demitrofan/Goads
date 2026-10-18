// Общий скрипт страниц со списком объявлений (жильё, байки):
// мгновенные фильтры, переключатель валют, сортировка.
// Ждёт window.SITE = {rates, currency} из шаблона.

// Компьютер: фильтры применяются сразу. На телефоне — по кнопке «Показать»,
// иначе свёрнутая панель фильтров закрывалась бы после каждой галочки.
(function () {
    const form = document.getElementById('filters');
    if (!form || window.matchMedia('(max-width: 767.98px)').matches) return;
    let timer;
    const submit = () => { clearTimeout(timer); form.requestSubmit(); };
    form.addEventListener('change', e => {
        if (e.target.matches('input[type=checkbox], input[type=radio], select')) submit();
    });
    // Цена и слова: ждём секунду после последнего нажатия клавиши
    form.addEventListener('input', e => {
        if (e.target.matches('input[type=number], input[type=text]')) {
            clearTimeout(timer);
            timer = setTimeout(submit, 1000);
        }
    });
    // Сохраняем прокрутку меню, чтобы после обновления страницы оно не прыгало наверх
    const sidebar = document.querySelector('.filters-sidebar');
    try {
        const y = sessionStorage.getItem('filtersScroll');
        if (y) sidebar.scrollTop = +y;
        form.addEventListener('submit', () => sessionStorage.setItem('filtersScroll', sidebar.scrollTop));
    } catch (e) {}
})();

// Валюта: цены в фильтре пересчитываются, чтобы диапазон остался тем же
document.querySelectorAll('.cur-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const url = new URL(window.location.href);
        const rates = window.SITE.rates;
        const from = window.SITE.currency, to = btn.dataset.cur;
        ['price_from', 'price_to'].forEach(name => {
            const v = url.searchParams.get(name);
            if (v) url.searchParams.set(name, Math.round(v / rates[from] * rates[to]));
        });
        url.searchParams.set('cur', to);
        url.searchParams.delete('page');
        window.location.href = url.toString();
    });
});

// Сортировка: меняем только sort, остальные фильтры сохраняются
document.querySelectorAll('.sort-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const url = new URL(window.location.href);
        url.searchParams.set('sort', btn.dataset.sort);
        url.searchParams.delete('page');
        window.location.href = url.toString();
    });
});

// Город → район (Армения, Грузия): в меню районов только районы выбранного города,
// у города без районов меню районов скрыто. Смена города сбрасывает чужой район.
(() => {
    const city = document.getElementById('city-select');
    const village = document.getElementById('village-select');
    if (!city || !village) return;
    const apply = () => {
        let shown = 0;
        for (const opt of village.options) {
            if (!opt.value) continue;
            const ok = !city.value || opt.dataset.city === city.value;
            opt.hidden = !ok;
            if (ok) shown++;
            else if (opt.selected) village.value = '';
        }
        document.getElementById('village-block').hidden = shown === 0;
    };
    city.addEventListener('change', apply);   // раньше общего обработчика формы, который её отправит
    apply();
})();
