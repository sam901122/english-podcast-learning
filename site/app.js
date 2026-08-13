const app = document.querySelector('#app');

const escapeHtml = (value = '') => value.replace(/[&<>'"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

const dateText = value => new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Taipei'
}).format(new Date(value));

async function loadEpisode(id) {
  app.innerHTML = '<p class="status">正在載入學習筆記⋯</p>';
  const response = await fetch(`data/episodes/${encodeURIComponent(id)}.json`);
  if (!response.ok) throw new Error('無法讀取這集內容');
  const episode = await response.json();
  app.innerHTML = `
    <article>
      <button class="back" type="button">← 所有集數</button>
      <p class="date">${dateText(episode.publishedAt)}</p>
      <h2>${escapeHtml(episode.title)}</h2>
      <a class="listen" href="${escapeHtml(episode.bbcUrl)}" target="_blank" rel="noopener">在 BBC 收聽 ↗</a>
      <section><h3>中文摘要</h3><p>${escapeHtml(episode.summaryZh)}</p></section>
      <section><h3>English summary</h3><p lang="en">${escapeHtml(episode.summaryEn)}</p></section>
      <section><h3>今日單字</h3><div class="cards">${episode.vocabulary.map(item => `
        <div class="card"><div><strong>${escapeHtml(item.word)}</strong><span>${escapeHtml(item.level)} · ${escapeHtml(item.partOfSpeech)}</span></div>
        <p>${escapeHtml(item.meaningZh)}</p><p class="definition" lang="en">${escapeHtml(item.definitionEn)}</p>
        <blockquote lang="en">${escapeHtml(item.example)}</blockquote></div>`).join('')}</div></section>
      <section><h3>實用片語</h3><div class="cards">${episode.phrases.map(item => `
        <div class="card"><strong>${escapeHtml(item.phrase)}</strong><p>${escapeHtml(item.meaningZh)}</p>
        <p class="definition" lang="en">${escapeHtml(item.definitionEn)}</p><blockquote lang="en">${escapeHtml(item.example)}</blockquote></div>`).join('')}</div></section>
    </article>`;
  document.querySelector('.back').addEventListener('click', loadIndex);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function loadIndex() {
  const response = await fetch('data/episodes.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('無法讀取集數列表');
  const episodes = await response.json();
  if (!episodes.length) {
    app.innerHTML = '<div class="empty"><h2>第一集準備中</h2><p>完成第一次自動更新後，學習筆記會出現在這裡。</p></div>';
    return;
  }
  app.innerHTML = `<div class="episode-list">${episodes.map(item => `
    <button class="episode" data-id="${escapeHtml(item.id)}" type="button">
      <span class="date">${dateText(item.publishedAt)}</span><strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.summaryZh)}</span><i>開始學習 →</i>
    </button>`).join('')}</div>`;
  document.querySelectorAll('.episode').forEach(button => button.addEventListener('click', () => {
    loadEpisode(button.dataset.id).catch(showError);
  }));
}

function showError(error) {
  app.innerHTML = `<p class="status error">${escapeHtml(error.message)}，請稍後再試。</p>`;
}

loadIndex().catch(showError);

