const input = document.querySelector('#search-input');
const box = document.querySelector('#suggestions-box');
const status = document.querySelector('#search-status');
let timer, controller, sequence = 0;
function closeSuggestions() { box.replaceChildren(); box.hidden = true; }
input.addEventListener('input', () => {
  clearTimeout(timer); controller?.abort(); const current = ++sequence;
  closeSuggestions();
  if (input.value.trim().length < 2) return;
  timer = setTimeout(async () => {
    controller = new AbortController(); status.textContent = 'Поиск…';
    try {
      const response = await fetch('/api/search-suggestions/?q=' + encodeURIComponent(input.value.trim()), {signal: controller.signal});
      if (!response.ok) throw new Error('search');
      const data = await response.json();
      if (current !== sequence) return;
      box.replaceChildren();
      data.suggestions.forEach(item => {
        const a = document.createElement('a');
        a.href = item.url; a.textContent = item.designation + (item.manufacturer ? ' · ' + item.manufacturer : '') + (item.price ? ' · ' + item.price + ' ₽' : '');
        box.append(a);
      });
      box.hidden = !data.suggestions.length;
      status.textContent = data.suggestions.length ? 'Подсказки доступны под полем поиска.' : 'Подсказок нет. Нажмите Найти для полного поиска.';
    } catch (error) {
      if (error.name !== 'AbortError' && current === sequence) status.textContent = 'Подсказки недоступны. Используйте кнопку Найти.';
    }
  }, 250);
});
input.addEventListener('keydown', event => {
  if (event.key === 'ArrowDown' && !box.hidden) { event.preventDefault(); box.firstElementChild?.focus(); }
});
document.addEventListener('keydown', event => { if(event.key === 'Escape') { closeSuggestions(); input.focus(); } });
document.addEventListener('click', event => { if(!event.target.closest('#search-container')) { ++sequence; controller?.abort(); closeSuggestions(); } });
const categories = document.querySelector('.category-nav');
if (matchMedia('(max-width:767px)').matches) categories.open = false;
