const app = document.querySelector('#app');

const escapeHtml = (value = '') => value.replace(/[&<>'"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

const CEFR_ORDER = { A2: 0, B1: 1, B2: 2, C1: 3, C2: 4 };
const STUDY_LEVEL_OPTIONS = [
  { id: 'basic', label: '初級' },
  { id: 'intermediate', label: '中級' },
  { id: 'advanced', label: '高級' }
];
let selectedStudyLevel = 'advanced';
let episodeIndexPromise;

const renderExample = item => {
  if (!item.exampleParts?.length) return escapeHtml(item.example || '');
  return item.exampleParts.map(part => part.highlight
    ? `<mark class="target-word">${escapeHtml(part.text)}</mark>`
    : escapeHtml(part.text)).join('');
};

const sortByCefr = items => [...items].sort((left, right) =>
  (CEFR_ORDER[left.level] ?? 99) - (CEFR_ORDER[right.level] ?? 99));

const legacyStudySets = episode => {
  const studySets = Object.fromEntries(STUDY_LEVEL_OPTIONS.map(option => [
    option.id, { vocabulary: [], phrases: [] }
  ]));
  (episode.vocabulary || []).forEach(item => {
    const studyLevel = ['A2', 'B1'].includes(item.level)
      ? 'basic' : item.level === 'B2' ? 'intermediate' : 'advanced';
    studySets[studyLevel].vocabulary.push(item);
  });
  (episode.phrases || []).forEach(item => {
    const studyLevel = ['A2', 'B1'].includes(item.level)
      ? 'basic' : item.level === 'B2' ? 'intermediate' : 'advanced';
    studySets[studyLevel].phrases.push(item);
  });
  return studySets;
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

app.addEventListener('click', event => {
  const button = event.target.closest('.speak-word');
  if (button) speakText(button.dataset.speak);
});

async function getEpisodeIndex() {
  if (!episodeIndexPromise) {
    episodeIndexPromise = fetch('data/episodes.json', { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('無法讀取集數列表');
      return response.json();
    });
  }
  return episodeIndexPromise;
}

function renderStudySet(studySet = {}) {
  const vocabulary = sortByCefr(studySet.vocabulary || []);
  const phrases = sortByCefr(studySet.phrases || []);
  const vocabularyCards = vocabulary.length ? vocabulary.map(item => `
    <div class="card"><div class="word-row"><strong>${escapeHtml(item.word)}</strong><button class="speak-word" type="button" data-speak="${escapeHtml(item.word)}" aria-label="Pronounce ${escapeHtml(item.word)}">${speakerIcon}</button><span>${escapeHtml(item.level)} · ${escapeHtml(item.partOfSpeech)}</span></div>
    <p class="phonetic" lang="en">${escapeHtml(item.kkPhonetic || '')}</p>
    <p>${escapeHtml(item.meaningZh)}</p>
    <blockquote lang="en">${renderExample(item)}</blockquote></div>`).join('')
    : '<p class="status">尚無單字內容</p>';
  const phraseCards = phrases.length ? phrases.map(item => `
    <div class="card"><div class="phrase-row"><strong>${escapeHtml(item.phrase)}</strong><button class="speak-word" type="button" data-speak="${escapeHtml(item.phrase)}" aria-label="Pronounce ${escapeHtml(item.phrase)}">${speakerIcon}</button>${item.level ? `<span>${escapeHtml(item.level)}</span>` : ''}</div><p>${escapeHtml(item.meaningZh)}</p>
    <blockquote lang="en">${renderExample(item)}</blockquote></div>`).join('')
    : '<p class="status">尚無片語內容</p>';
  return `
    <section><h3>今日單字</h3><div class="cards">${vocabularyCards}</div></section>
    <section><h3>實用片語</h3><div class="cards">${phraseCards}</div></section>`;
}

async function loadEpisode(id) {
  app.innerHTML = '<p class="status">正在載入學習筆記⋯</p>';
  const [episodeResponse, episodes] = await Promise.all([
    fetch(`data/episodes/${encodeURIComponent(id)}.json`),
    getEpisodeIndex()
  ]);
  if (!episodeResponse.ok) throw new Error('無法讀取這集內容');
  const episode = await episodeResponse.json();
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
      <div class="study-toolbar">
        <h3>學習難度</h3>
        <div class="level-switch" role="group" aria-label="選擇學習難度">
          ${STUDY_LEVEL_OPTIONS.map(option => `<button type="button" data-study-level="${option.id}" aria-pressed="${option.id === selectedStudyLevel}">${option.label}</button>`).join('')}
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
  const studySets = episode.studySets || legacyStudySets(episode);
  const studyContent = app.querySelector('.study-content');
  const levelButtons = app.querySelectorAll('.level-switch button');
  const showStudyLevel = studyLevel => {
    selectedStudyLevel = studyLevel;
    studyContent.innerHTML = renderStudySet(studySets[studyLevel]);
    levelButtons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.studyLevel === studyLevel));
    });
  };
  levelButtons.forEach(button => {
    button.addEventListener('click', () => showStudyLevel(button.dataset.studyLevel));
  });
  showStudyLevel(selectedStudyLevel);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function loadIndex() {
  const episodes = await getEpisodeIndex();
  if (!episodes.length) {
    app.innerHTML = '<div class="empty"><h2>第一集準備中</h2><p>完成第一次自動更新後，學習筆記會出現在這裡。</p></div>';
    return;
  }
  app.innerHTML = `<div class="episode-list">${episodes.map(item => `
    <button class="episode" data-id="${escapeHtml(item.id)}" type="button">
      <span class="date">${dateText(item.publishedAt)}</span><strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.summaryZh)}</span><i>開始學習 →</i>
    </button>`).join('')}</div>`;
  app.querySelectorAll('.episode').forEach(button => button.addEventListener('click', () => {
    loadEpisode(button.dataset.id).catch(showError);
  }));
}

async function loadLatest() {
  const episodes = await getEpisodeIndex();
  if (!episodes.length) return loadIndex();
  return loadEpisode(episodes[0].id);
}

function showError(error) {
  app.innerHTML = `<p class="status error">${escapeHtml(error.message)}，請稍後再試。</p>`;
}

loadLatest().catch(showError);
