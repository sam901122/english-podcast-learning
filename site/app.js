const app = document.querySelector('#app');

const escapeHtml = (value = '') => value.replace(/[&<>'"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

const highlightTerm = (sentence = '', term = '') => {
  if (!term) return escapeHtml(sentence);
  const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`(^|[^A-Za-z])(${escapedTerm})(?=$|[^A-Za-z])`, 'gi');
  let html = '';
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(sentence)) !== null) {
    const wordStart = match.index + match[1].length;
    html += escapeHtml(sentence.slice(lastIndex, wordStart));
    html += `<mark class="target-word">${escapeHtml(match[2])}</mark>`;
    lastIndex = wordStart + match[2].length;
  }

  return html + escapeHtml(sentence.slice(lastIndex));
};

const dateText = value => new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Taipei'
}).format(new Date(value));

const speakerIcon = `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M11 5 6 9H3v6h3l5 4V5Z"></path>
    <path d="M15.5 8.5a5 5 0 0 1 0 7"></path>
    <path d="M18.5 5.5a9 9 0 0 1 0 13"></path>
  </svg>`;

function speakText(text = '') {
  if (!('speechSynthesis' in window) || !text.trim()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  utterance.rate = 0.6;
  window.speechSynthesis.speak(utterance);
}

async function loadEpisode(id) {
  app.innerHTML = '<p class="status">正在載入學習筆記⋯</p>';
  const [episodeResponse, indexResponse] = await Promise.all([
    fetch(`data/episodes/${encodeURIComponent(id)}.json`),
    fetch('data/episodes.json', { cache: 'no-store' })
  ]);
  if (!episodeResponse.ok) throw new Error('無法讀取這集內容');
  const episode = await episodeResponse.json();
  const episodes = indexResponse.ok ? await indexResponse.json() : [];
  const episodeIndex = episodes.findIndex(item => item.id === id);
  const previousEpisode = episodeIndex >= 0 ? episodes[episodeIndex + 1] : null;
  const nextEpisode = episodeIndex > 0 ? episodes[episodeIndex - 1] : null;
  app.innerHTML = `
    <article>
      <button class="back" type="button">← 所有集數</button>
      <p class="date">${dateText(episode.publishedAt)}</p>
      <h2>${escapeHtml(episode.title)}</h2>
      <a class="listen" href="${escapeHtml(episode.bbcUrl)}" target="_blank" rel="noopener">在 BBC 收聽 ↗</a>
      <section><h3>中文摘要</h3><p>${escapeHtml(episode.summaryZh)}</p></section>
      <section><h3>English summary</h3><p lang="en">${escapeHtml(episode.summaryEn)}</p></section>
      <section><h3>今日單字</h3><div class="cards">${episode.vocabulary.map(item => `
        <div class="card"><div class="word-row"><strong>${escapeHtml(item.word)}</strong><button class="speak-word" type="button" data-speak="${escapeHtml(item.word)}" aria-label="Pronounce ${escapeHtml(item.word)}">${speakerIcon}</button><span>${escapeHtml(item.level)} · ${escapeHtml(item.partOfSpeech)}</span></div>
        <p class="phonetic" lang="en">${escapeHtml(item.kkPhonetic || '')}</p>
        <p>${escapeHtml(item.meaningZh)}</p>
        <blockquote lang="en">${highlightTerm(item.example, item.word)}</blockquote></div>`).join('')}</div></section>
      <section><h3>實用片語</h3><div class="cards">${episode.phrases.map(item => `
        <div class="card"><strong>${escapeHtml(item.phrase)}</strong><p>${escapeHtml(item.meaningZh)}</p>
        <blockquote lang="en">${highlightTerm(item.example, item.phrase)}</blockquote></div>`).join('')}</div></section>
      <nav class="day-nav" aria-label="單集日期導覽">
        <button type="button" data-episode-id="${previousEpisode ? escapeHtml(previousEpisode.id) : ''}" ${previousEpisode ? '' : 'disabled'}>← Previous Day</button>
        <button type="button" data-episode-id="${nextEpisode ? escapeHtml(nextEpisode.id) : ''}" ${nextEpisode ? '' : 'disabled'}>Next Day →</button>
      </nav>
    </article>`;
  document.querySelector('.back').addEventListener('click', loadIndex);
  document.querySelectorAll('.day-nav button:not(:disabled)').forEach(button => {
    button.addEventListener('click', () => loadEpisode(button.dataset.episodeId).catch(showError));
  });
  document.querySelectorAll('.speak-word').forEach(button => {
    button.addEventListener('click', () => speakText(button.dataset.speak));
  });
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

async function loadLatest() {
  const response = await fetch('data/episodes.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('無法讀取集數列表');
  const episodes = await response.json();
  if (!episodes.length) return loadIndex();
  return loadEpisode(episodes[0].id);
}

function showError(error) {
  app.innerHTML = `<p class="status error">${escapeHtml(error.message)}，請稍後再試。</p>`;
}

loadLatest().catch(showError);
