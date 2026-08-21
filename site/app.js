const app = document.querySelector('#app');
let selectedStudyLevel = 'advanced';

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

const copyIcon = `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <rect x="9" y="9" width="11" height="11" rx="2"></rect>
    <path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"></path>
  </svg>`;

const copiedIcon = `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="m5 12 4 4L19 6"></path>
  </svg>`;

const speech = 'speechSynthesis' in window ? window.speechSynthesis : null;
let availableVoices = [];
let activeUtterance = null;

function refreshVoices() {
  availableVoices = speech ? speech.getVoices() : [];
}

if (speech) {
  refreshVoices();
  speech.addEventListener('voiceschanged', refreshVoices);
}

function speakText(text = '') {
  if (!speech || !text.trim()) return;
  const startSpeaking = () => {
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = speech.getVoices();
    if (voices.length) availableVoices = voices;
    const englishVoice = availableVoices.find(voice => voice.lang.toLowerCase() === 'en-us')
      || availableVoices.find(voice => voice.lang.toLowerCase().startsWith('en'));
    activeUtterance = utterance;
    utterance.lang = 'en-US';
    utterance.rate = 0.6;
    utterance.volume = 1;
    if (englishVoice) utterance.voice = englishVoice;
    utterance.onend = utterance.onerror = () => {
      if (activeUtterance === utterance) activeUtterance = null;
    };
    speech.speak(utterance);
    if (speech.paused) speech.resume();
  };

  if (speech.speaking || speech.pending) {
    speech.cancel();
    window.setTimeout(startSpeaking, 100);
  } else {
    startSpeaking();
  }
}

function bindSpeakButtons(root = app) {
  root.querySelectorAll('.speak-word:not(.copy-word)').forEach(button => {
    button.addEventListener('click', () => speakText(button.dataset.speak));
  });
}

function bindCopyButtons(root = app) {
  root.querySelectorAll('.copy-word').forEach(button => {
    button.addEventListener('click', async () => {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.innerHTML = copiedIcon;
      button.classList.add('copied');
      button.setAttribute('aria-label', `${button.dataset.copy} 已複製`);
      window.setTimeout(() => {
        button.innerHTML = copyIcon;
        button.classList.remove('copied');
        button.setAttribute('aria-label', `複製 ${button.dataset.copy}`);
      }, 1500);
    });
  });
}

function renderStudySet(studySet = {}) {
  const vocabulary = studySet.vocabulary || [];
  const phrases = studySet.phrases || [];
  return `
    <section><h3>今日單字</h3><div class="cards">${vocabulary.map(item => `
      <div class="card"><div class="word-row"><strong>${escapeHtml(item.word)}</strong><button class="speak-word" type="button" data-speak="${escapeHtml(item.word)}" aria-label="Pronounce ${escapeHtml(item.word)}">${speakerIcon}</button><button class="speak-word copy-word" type="button" data-copy="${escapeHtml(item.word)}" aria-label="複製 ${escapeHtml(item.word)}">${copyIcon}</button><span>${escapeHtml(item.level)} · ${escapeHtml(item.partOfSpeech)}</span></div>
      <p class="phonetic" lang="en">${escapeHtml(item.kkPhonetic || '')}</p>
      <p>${escapeHtml(item.meaningZh)}</p>
      <blockquote lang="en">${highlightTerm(item.example, item.highlight || item.word)}</blockquote></div>`).join('')}</div></section>
    ${phrases.length ? `<section><h3>實用片語</h3><div class="cards">${phrases.map(item => `
      <div class="card"><div class="phrase-row"><strong>${escapeHtml(item.phrase)}</strong><button class="speak-word" type="button" data-speak="${escapeHtml(item.phrase)}" aria-label="Pronounce ${escapeHtml(item.phrase)}">${speakerIcon}</button></div><p>${escapeHtml(item.meaningZh)}</p>
      <blockquote lang="en">${highlightTerm(item.example, item.highlight || item.phrase)}</blockquote></div>`).join('')}</div></section>` : ''}`;
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
  const hasNewStudySets = Boolean(episode.studySets?.practical && episode.studySets?.topic);
  const studyLevelOptions = hasNewStudySets ? [
    { id: 'practical', label: '實用' },
    { id: 'advanced', label: '進階' },
    { id: 'topic', label: '主題' }
  ] : [
    { id: 'basic', label: '初級' },
    { id: 'intermediate', label: '中級' },
    { id: 'advanced', label: '高級' }
  ];
  app.innerHTML = `
    <article>
      <button class="back" type="button">← 所有集數</button>
      <p class="date">${dateText(episode.publishedAt)}</p>
      <h2>${escapeHtml(episode.title)}</h2>
      <div class="listen-links">
        <a class="listen" href="${escapeHtml(episode.bbcUrl)}" target="_blank" rel="noopener">在 BBC 收聽 ↗</a>
        ${episode.spotifyUrl ? `<a class="listen" href="${escapeHtml(episode.spotifyUrl)}" target="_blank" rel="noopener">在 Spotify 收聽 ↗</a>` : ''}
      </div>
      <section><h3>中文摘要</h3><p>${escapeHtml(episode.summaryZh)}</p></section>
      <section><h3>English summary</h3><p lang="en">${escapeHtml(episode.summaryEn)}</p></section>
      <div class="study-toolbar">
        <h3>${hasNewStudySets ? '學習分類' : '學習難度'}</h3>
        <div class="level-switch" role="group" aria-label="${hasNewStudySets ? '選擇學習分類' : '選擇學習難度'}">
          ${studyLevelOptions.map(option => `<button type="button" data-study-level="${option.id}" aria-pressed="${option.id === selectedStudyLevel}">${option.label}</button>`).join('')}
        </div>
      </div>
      <div class="study-content"></div>
      <nav class="day-nav" aria-label="單集日期導覽">
        <button type="button" data-episode-id="${previousEpisode ? escapeHtml(previousEpisode.id) : ''}" ${previousEpisode ? '' : 'disabled'}>← Previous Day</button>
        <button type="button" data-episode-id="${nextEpisode ? escapeHtml(nextEpisode.id) : ''}" ${nextEpisode ? '' : 'disabled'}>Next Day →</button>
      </nav>
    </article>`;
  app.querySelector('.back').addEventListener('click', loadIndex);
  app.querySelectorAll('.day-nav button:not(:disabled)').forEach(button => {
    button.addEventListener('click', () => loadEpisode(button.dataset.episodeId).catch(showError));
  });
  const legacyStudySet = {
    vocabulary: episode.vocabulary || [],
    phrases: episode.phrases || []
  };
  const studySets = episode.studySets || {
    basic: legacyStudySet,
    intermediate: legacyStudySet,
    advanced: legacyStudySet
  };
  const studyContent = app.querySelector('.study-content');
  const levelButtons = app.querySelectorAll('.level-switch button');
  const showStudyLevel = studyLevel => {
    selectedStudyLevel = studyLevel;
    studyContent.innerHTML = renderStudySet(studySets[studyLevel] || legacyStudySet);
    levelButtons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.studyLevel === studyLevel));
    });
    bindSpeakButtons(studyContent);
    bindCopyButtons(studyContent);
  };
  levelButtons.forEach(button => {
    button.addEventListener('click', () => showStudyLevel(button.dataset.studyLevel));
  });
  showStudyLevel(selectedStudyLevel);
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
