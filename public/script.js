async function main(){
  try{
    const res = await fetch('./rates.json', {cache: 'no-cache'});
    const text = await res.text();
    let data;
    try{ data = JSON.parse(text); } catch(e){ data = []; }
    render(data);

    const now = new Date();
    document.getElementById('stamp').textContent = now.toLocaleString('ru-RU');
    const dset = bestDate(data);
    document.getElementById('updated').textContent = dset ? ('на дату: ' + dset) : 'нет данных';
  }catch(e){
    console.error(e);
    document.getElementById('updated').textContent = 'ошибка загрузки';
  }
}

function bestDate(all){
  const dates = Array.from(new Set(all.map(x => x.date))).sort();
  return dates.length ? dates[dates.length - 1] : null;
}

function render(all){
  const tbody = document.getElementById('tbody');
  const ccys = ['USD','EUR','RUB'];
  const rows = all.map(b => {
    const by = Object.fromEntries(b.rates.map(r => [r.ccy, r]));
    const cells = ccys.map(c => by[c] ? `${fmt(by[c].buy)} / ${fmt(by[c].sell)}` : '—').join('</td><td>');
    const src = b.source_url ? `<a href="${b.source_url}" target="_blank" rel="noopener">сайт</a>` : '—';
    return `<tr>
      <td class="bank">${escapeHtml(b.bank)}</td>
      <td>${cells}</td>
      <td>${escapeHtml(b.date || '—')}</td>
      <td class="src">${src}</td>
    </tr>`;
  }).join('');
  tbody.innerHTML = rows || `<tr><td colspan="6">Данных нет</td></tr>`;
}

function fmt(x){
  if (x == null || isNaN(x)) return '—';
  return Number(x).toLocaleString('ru-RU', {maximumFractionDigits: 2});
}

function escapeHtml(str){
  return (str || '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
}

main();
