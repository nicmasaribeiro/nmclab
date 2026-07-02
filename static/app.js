const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const editor = $('#lyricEditor');
const gutter = $('#lineGutter');
const coachMode = $('#coachMode');
const statusPill = $('#statusPill');
const liveStateMetric = $('#liveStateMetric');
const liveStateSmall = $('#liveStateSmall');
const cursorInfo = $('#cursorInfo');
const draftStats = $('#draftStats');
const autosaveInfo = $('#autosaveInfo');
const activeFixEl = $('#activeFix');
const fixQueueEl = $('#fixQueue');
const actionsEl = $('#editorActions');
const scoreRowEl = $('#scoreRow');
const beatStatusEl = $('#beatStatus');
const beatPanelEl = $('#beatPanel');
const beatDiagnosticsEl = $('#beatDiagnostics');
const rhymePanelEl = $('#rhymePanel');
const advancedRhymePanelEl = $('#advancedRhymePanel');
const rhymeTargetWordEl = $('#rhymeTargetWord');
const analyzeTargetRhymeBtn = $('#analyzeTargetRhyme');
const runAdvancedRhymeBtn = $('#runAdvancedRhyme');
const copyRhymeJsonBtn = $('#copyRhymeJson');
const jsonBlock = $('#jsonBlock');
const staticStatusEl = $('#staticBreakdownStatus');
const staticMetricsEl = $('#staticMetrics');
const staticOverviewEl = $('#staticOverview');
const staticLineBreakdownEl = $('#staticLineBreakdown');
const snapshotTheoryEl = $('#snapshotTheoryPanel');
const theoryFullEl = $('#theoryFullPanel');
const meterFullEl = $('#meterFullPanel');
const physicsFullEl = $('#physicsFullPanel');
const staticSnapshotSourceEl = $('#staticSnapshotSource');
const comparisonPanelEl = $('#comparisonPanel');
const sentenceInputEl = $('#sentenceInput');
const sentenceOutputEl = $('#sentenceOutput');
const sentenceMetricsEl = $('#sentenceMetrics');
const sentenceStatusEl = $('#sentenceSyncStatus');
const sentenceAutoSyncEl = $('#sentenceAutoSync');
const sentencePatternInputEl = $('#sentencePatternInput');
const sentencePatternOutputEl = $('#sentencePatternOutput');
const sentencePatternMetricsEl = $('#sentencePatternMetrics');
const sentencePatternStatusEl = $('#sentencePatternStatus');
const songRenderStatusEl = $('#songRenderStatus');
const songTtsStatusEl = $('#songTtsStatus');
const songOutputEl = $('#songOutput');
const scoreLabStatusEl = $('#scoreLabStatus');
const scoreGlobalPanelEl = $('#scoreGlobalPanel');
const scoreComparePanelEl = $('#scoreComparePanel');
const lyricDiffPanelEl = $('#lyricDiffPanel');
const scoreBaselineInputEl = $('#scoreBaselineInput');
const scoreEditedInputEl = $('#scoreEditedInput');
const liveRhymeStatusEl = $('#liveRhymeStatus');
const liveRhymeActiveEl = $('#liveRhymeActive');
const liveRhymeBanksEl = $('#liveRhymeBanks');
const liveRhymeSchemeEl = $('#liveRhymeScheme');
const liveRhymeAutoEl = $('#liveRhymeAuto');
const liveRhymeDiagnosticsEl = $('#liveRhymeDiagnostics');
const liveRhymeLineMapEl = $('#liveRhymeLineMap');
const highlightedWordPanelEl = $('#highlightedWordPanel');
const pythonAnywherePanelEl = $('#pythonAnywherePanel');
const analyzeHighlightedWordBtn = $('#analyzeHighlightedWord');
const selectedWordAutoEl = $('#selectedWordAuto');
const accountStateMetricEl = $('#accountStateMetric');
const accountStateSmallEl = $('#accountStateSmall');
const accountStatusEl = $('#accountStatus');
const authFormsEl = $('#authForms');
const accountWorkspaceEl = $('#accountWorkspace');
const loginFormEl = $('#loginForm');
const registerFormEl = $('#registerForm');
const loginEmailEl = $('#loginEmail');
const loginPasswordEl = $('#loginPassword');
const registerNameEl = $('#registerName');
const registerEmailEl = $('#registerEmail');
const registerPasswordEl = $('#registerPassword');
const rapTitleInputEl = $('#rapTitleInput');
const savedRapSearchEl = $('#savedRapSearch');
const savedRapsListEl = $('#savedRapsList');
const selectedRapInfoEl = $('#selectedRapInfo');

const state = {
  beatId: null,
  beatAnalysis: null,
  latest: null,
  jobId: null,
  sequence: 0,
  debounceTimer: null,
  pollTimer: null,
  activeLine: 1,
  lastLyricsSent: '',
  staticReport: null,
  staticSource: '',
  comparisonReport: null,
  sentenceTimer: null,
  sentenceSequence: 0,
  sentenceReport: null,
  sentencePatternReport: null,
  physicsReport: null,
  sentenceSourceRange: null,
  songReport: null,
  rhymeLab: null,
  scoreReport: null,
  editCompareReport: null,
  editCompareInputs: null,
  liveRhymeReport: null,
  liveRhymeSequence: 0,
  liveRhymeJobId: null,
  liveRhymeTimer: null,
  liveRhymePollTimer: null,
  lastLiveRhymeLyricsSent: '',
  lastLiveRhymeActiveLine: null,
  liveRhymeFailCount: 0,
  lastLiveRhymeRoutes: null,
  selectedWordReport: null,
  selectedWordSequence: 0,
  selectedWordTimer: null,
  selectedWordPollTimer: null,
  selectedWordJobId: null,
  selectedWordContextKey: '',
  selectedWordRange: null,
  currentUser: null,
  savedRaps: [],
  selectedRapId: null,
  selectedRap: null,
  selectedRapVersions: [],
  currentRapId: null,
  accountLoaded: false,
  charts: {},
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function showLiveUiError(message) {
  if (!liveRhymeDiagnosticsEl) return;
  liveRhymeDiagnosticsEl.className = 'live-rhyme-diagnostics';
  liveRhymeDiagnosticsEl.innerHTML = `<section class="live-rhyme-diagnostics-card error"><div><strong>UI error</strong><small>${escapeHtml(message || 'unknown')}</small></div></section>`;
}

window.addEventListener('error', (event) => {
  const message = event?.message || 'Script error';
  if (String(event?.filename || '').includes('app.js') || message.toLowerCase().includes('live')) showLiveUiError(message);
});
window.addEventListener('unhandledrejection', (event) => {
  const reason = event?.reason?.message || event?.reason || 'Unhandled promise rejection';
  showLiveUiError(reason);
});

function plural(n, word) {
  return `${n} ${word}${Number(n) === 1 ? '' : 's'}`;
}

function fmt(value, fallback = '0') {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return fallback;
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000);
  }
  return String(value);
}

function pctText(value) {
  if (value === null || value === undefined || value === '') return '0%';
  return `${fmt(value)}%`;
}

function countWords(text) {
  const matches = text.match(/[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*/g);
  return matches ? matches.length : 0;
}

function countLines(text) {
  if (!text) return 1;
  return text.split(/\r?\n/).length;
}

function activeLineNumber() {
  const start = editor.selectionStart || 0;
  return editor.value.slice(0, start).split(/\r?\n/).length;
}

function setStatus(kind, text, small = '') {
  statusPill.className = `status-pill ${kind || ''}`;
  statusPill.innerHTML = `<span></span>${escapeHtml(text)}`;
  liveStateMetric.textContent = String(text || 'IDLE').toUpperCase().slice(0, 12);
  liveStateSmall.textContent = small || (kind === 'running' ? 'background worker active' : 'waiting for edits');
}

function updateGutter() {
  const lines = countLines(editor.value);
  const numbers = Array.from({ length: lines }, (_, index) => index + 1).join('\n');
  gutter.textContent = numbers || '1';
}

function updateLocalStats() {
  state.activeLine = activeLineNumber();
  cursorInfo.textContent = `Line ${state.activeLine}`;
  draftStats.textContent = `${plural(countWords(editor.value), 'word')} · ${plural(countLines(editor.value), 'line')}`;
  updateGutter();
  try {
    localStorage.setItem('nmc_editing_lab_draft', editor.value);
    localStorage.setItem('nmc_editing_lab_mode', coachMode.value);
    autosaveInfo.textContent = 'Autosaved locally';
  } catch (_error) {
    autosaveInfo.textContent = 'Autosave unavailable';
  }
  markSnapshotStale();
}

function markSnapshotStale() {
  if (!state.staticReport || !staticStatusEl) return;
  if (editor.value !== state.staticSource) {
    staticStatusEl.className = 'fit-callout muted stale';
    staticStatusEl.textContent = 'Draft changed after this snapshot. Refresh the snapshot when you want a fixed report for the new text.';
  }
}

async function queueSuggestion(force = false) {
  const lyrics = editor.value;
  const wordCount = countWords(lyrics);
  updateLocalStats();
  if (!force && lyrics === state.lastLyricsSent && state.activeLine === activeLineNumber()) return;
  if (wordCount < 3) {
    state.latest = null;
    renderEmpty();
    setStatus('idle', 'Idle', 'type at least three words');
    return;
  }
  state.sequence += 1;
  const token = state.sequence;
  state.lastLyricsSent = lyrics;
  setStatus('running', 'Thinking', `line ${state.activeLine}`);
  try {
    const response = await fetch('/api/suggest-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lyrics,
        coach_mode: coachMode.value,
        active_line: state.activeLine,
        beat_id: state.beatId,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Suggestion job failed.');
    if (token !== state.sequence) return;
    state.jobId = payload.job_id;
    if (payload.status === 'complete' && payload.result) {
      state.latest = payload.result;
      setStatus('complete', 'Live', `updated ${payload.result.generated_at || ''}`);
      renderResult(payload.result);
      return;
    }
    if (payload.no_poll_required && payload.result) {
      state.latest = payload.result;
      renderResult(payload.result);
      setStatus('complete', 'Live', 'direct complete · no queue');
      return;
    }
    pollJob(payload.job_id, token);
  } catch (error) {
    setStatus('error', 'Error', error.message);
  }
}

async function pollJob(jobId, token) {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  try {
    const response = await fetch(`/api/job/${jobId}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Job lookup failed.');
    if (token !== state.sequence) return;
    if (payload.status === 'complete') {
      state.latest = payload.result;
      setStatus('complete', 'Live', `updated ${payload.result.generated_at || ''}`);
      renderResult(payload.result);
      return;
    }
    if (payload.status === 'error') throw new Error(payload.error || 'Analysis error.');
    setStatus('running', payload.status === 'queued' ? 'Direct' : 'Thinking', `job ${jobId.slice(0, 6)}`);
    state.pollTimer = setTimeout(() => pollJob(jobId, token), 420);
  } catch (error) {
    setStatus('error', 'Error', error.message);
  }
}

function scheduleSuggestion() {
  updateLocalStats();
  if (state.debounceTimer) clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(() => queueSuggestion(false), 700);
}

function renderEmpty() {
  activeFixEl.className = 'empty-state';
  activeFixEl.textContent = 'Start writing, then place your cursor on a line. The lab will show the best edit, word bank, and applyable patches for that line.';
  fixQueueEl.className = 'line-list empty-state';
  fixQueueEl.textContent = 'Suggestions will appear here after the first live analysis.';
  actionsEl.innerHTML = '';
  scoreRowEl.innerHTML = '';
  rhymePanelEl.className = 'empty-state';
  rhymePanelEl.textContent = 'Select a line or wait for live analysis.';
  if (advancedRhymePanelEl && !state.rhymeLab) {
    advancedRhymePanelEl.className = 'empty-state';
    advancedRhymePanelEl.textContent = 'Run the advanced rhyme pass to see scheme-level diagnostics and line-by-line rhyme repair.';
  }
  if (!state.liveRhymeReport) {
    renderLiveRhymeReport({ available: false, error: 'Start writing and place the cursor on a line. Active-line rhyme suggestions will appear here.' });
setLiveRhymeDiagnostics('ready');
  }
  if (snapshotTheoryEl && !state.staticReport) {
    snapshotTheoryEl.className = 'theory-panel empty-state';
    snapshotTheoryEl.textContent = 'Information-theoretic stats will appear after the first snapshot.';
  }
  if (theoryFullEl && !state.staticReport) {
    theoryFullEl.className = 'theory-panel empty-state';
    theoryFullEl.textContent = 'Generate a static snapshot to populate this view.';
  }
  if (comparisonPanelEl && !state.comparisonReport) {
    comparisonPanelEl.className = 'comparison-output empty-state';
    comparisonPanelEl.textContent = 'Generate a static snapshot or live analysis to populate rapper benchmark comparisons.';
  }
  if (physicsFullEl && !state.staticReport) {
    physicsFullEl.className = 'physics-output empty-state';
    physicsFullEl.textContent = 'Generate a static snapshot or live analysis to populate scansion physics.';
  }
  jsonBlock.textContent = '{}';
}

function priorityClass(priority) {
  return ['critical', 'high', 'medium', 'low'].includes(priority) ? priority : 'low';
}

function chips(words, cls = 'insert-chip') {
  if (!words || !words.length) return '<p class="muted tiny-text">No words for this bank yet.</p>';
  return words.map((word) => `<button type="button" class="chip ${cls}" data-word="${escapeHtml(word)}">${escapeHtml(word)}</button>`).join('');
}

function setLiveRhymeStatus(kind, text, small = '') {
  if (!liveRhymeStatusEl) return;
  liveRhymeStatusEl.className = `status-pill sentence-status ${kind || ''}`;
  liveRhymeStatusEl.innerHTML = `<span></span>${escapeHtml(text || 'Ready')}`;
  if (small && liveRhymeActiveEl && liveRhymeActiveEl.classList.contains('empty-state')) {
    liveRhymeActiveEl.textContent = small;
  }
}

function liveRhymeScoreClass(score) {
  const n = Number(score || 0);
  if (n >= 80) return 'elite';
  if (n >= 64) return 'strong';
  if (n >= 48) return 'mid';
  return 'weak';
}

function liveRhymeOptionChips(options = [], limit = 12) {
  if (!options.length) return '<p class="muted tiny-text">No ranked rhyme options yet.</p>';
  return `<div class="ranked-rhyme-chip-list">${options.slice(0, limit).map((row) => `
    <button type="button" class="ranked-rhyme-chip live-rhyme-swap-end ${escapeHtml(row.kind || 'texture')}" data-word="${escapeHtml(row.word || row.display || '')}" title="Replace active line ending · ${escapeHtml(row.kind || '')} · ${escapeHtml(row.score ?? 0)}">
      <b>${escapeHtml(row.display || row.word || '')}</b>
      <small>swap ending · ${escapeHtml(row.score ?? 0)} · ${escapeHtml(row.kind || '')}</small>
    </button>
  `).join('')}</div>`;
}

function liveRhymePatchesHtml(active = {}) {
  const patches = active.patches || [];
  if (!patches.length) return '<p class="muted tiny-text">No applyable rhyme patch yet. Try another landing word or add one more line.</p>';
  return `<div class="live-rhyme-patch-list">${patches.slice(0, 4).map((patch, index) => `
    <button type="button" class="patch-button apply-live-rhyme-patch" data-patch="${index}">
      <strong>${escapeHtml(patch.label || patch.operation || 'Apply rhyme patch')}</strong>
      <small>${escapeHtml(patch.why || '')}</small>
      <em>${escapeHtml(patch.replacement || '')}</em>
    </button>
  `).join('')}</div>`;
}

function liveRhymeSchemeHtml(report = {}) {
  const summary = report.summary || {};
  const scheme = report.scheme || {};
  const recs = scheme.recommendations || [];
  const ladders = report.family_ladders || [];
  return `
    <div class="live-rhyme-summary-grid">
      <article><span>Avg rhyme power</span><strong>${escapeHtml(summary.avg_rhyme_power ?? 0)}%</strong></article>
      <article><span>Rhyme families</span><strong>${escapeHtml(summary.unique_rhyme_families ?? 0)}</strong></article>
      <article><span>Weak lines</span><strong>${escapeHtml((summary.weak_rhyme_lines || []).length)}</strong></article>
      <article><span>Corpus overlap</span><strong>${escapeHtml(summary.corpus_rhyme_key_overlap_pct ?? 0)}%</strong></article>
    </div>
    ${recs.length ? `<section class="live-rhyme-card"><h4>Scheme repair moves</h4>${recs.slice(0, 4).map((rec) => `
      <div class="scheme-repair-row">
        <strong>${escapeHtml(rec.title || 'Repair move')}</strong>
        <p>${escapeHtml(rec.detail || '')}</p>
        ${(rec.line_numbers || []).length ? `<small>Lines ${(rec.line_numbers || []).slice(0, 8).map((n) => `<button type="button" class="line-link line-jump" data-line="${escapeHtml(n)}">${escapeHtml(n)}</button>`).join(' ')}</small>` : ''}
      </div>
    `).join('')}</section>` : ''}
    ${ladders.length ? `<section class="live-rhyme-card"><h4>Family ladders to try</h4>${ladders.slice(0, 3).map((ladder) => `
      <div class="family-ladder-mini">
        <strong>/${escapeHtml(ladder.key || ladder.rhyme_key || 'family')}/</strong>
        <p>${escapeHtml((ladder.words || ladder.options || ladder.suggestions || []).slice(0, 10).join(', ') || ladder.note || '')}</p>
      </div>
    `).join('')}</section>` : ''}
  `;
}


function liveActiveStaticRow() {
  return state.liveRhymeReport?.live_static_analysis?.active_line
    || state.liveRhymeReport?.active_report?.static_line_analysis
    || null;
}

function liveStaticMetricHtml(row = {}) {
  const metrics = row.metrics || {};
  const info = row.information || {};
  const meter = row.meter || {};
  const meterSummary = meter.summary || {};
  const physics = row.physics || {};
  const physicsDelta = physics.cadence_delta || {};
  const barScore = row.bar_score || {};
  const bar = row.breakdown?.bar_structure || {};
  return `
    <div class="live-static-metric-grid">
      ${barScore.overall !== undefined ? `<article><span>Bar score</span><strong>${escapeHtml(barScore.overall)}%</strong><small>${escapeHtml(barScore.grade?.letter || '')} · ${escapeHtml(barScore.grade?.label || '')}</small></article>` : ''}
      <article><span>Syllables</span><strong>${escapeHtml(metrics.syllables ?? 0)}</strong><small>${escapeHtml(metrics.words ?? 0)} words</small></article>
      <article><span>Rhyme</span><strong>/${escapeHtml(metrics.rhyme_key || '—')}/</strong><small>end ${escapeHtml(metrics.end_word || '—')}</small></article>
      <article><span>Info bits</span><strong>${escapeHtml(info.line_self_information_bits ?? 0)}</strong><small>${escapeHtml(info.bits_per_word ?? 0)} bits/word</small></article>
      ${meter.available ? `<article><span>Stress</span><strong>${escapeHtml(meterSummary.stress_ratio_pct ?? 0)}%</strong><small>${escapeHtml(meterSummary.dominant_meter || 'mixed')} · ${meterSummary.final_landing_stressed ? 'stressed landing' : 'soft landing'}</small></article>` : ''}
      ${physics.available ? `<article><span>Physics</span><strong>F ${escapeHtml(physics.force_pct ?? 0)}</strong><small>τ ${escapeHtml(physics.torsion_pct ?? 0)} · Ω ${escapeHtml(physics.spin_pct ?? 0)} · ΔC ${physicsDelta.available ? `${physicsDelta.delta_syllables > 0 ? '+' : ''}${escapeHtml(physicsDelta.delta_syllables)}` : 'open'}</small></article>` : ''}
      ${bar.available ? `<article><span>Beat/bar</span><strong>${escapeHtml(bar.assigned_bars || '—')}</strong><small>${escapeHtml(bar.time_window || bar.note || '')}</small></article>` : ''}
    </div>
  `;
}

function liveStaticRewriteHtml(row = {}) {
  const rewrites = row.rewrite_options || [];
  const patches = row.applyable_patches || [];
  const rewriteButtons = rewrites.slice(0, 4).map((rewrite, index) => `
    <article class="static-rewrite-card live-static-rewrite-card">
      <strong>${escapeHtml(rewrite.name || `Option ${index + 1}`)}</strong>
      <p>${escapeHtml(rewrite.text || '').replaceAll('\n', '<br>')}</p>
      <small>${escapeHtml(rewrite.syllables ?? '')} syllables · ${escapeHtml(rewrite.why || '')}</small>
      <button type="button" class="ghost tiny apply-live-static-rewrite" data-rewrite="${index}">Use rewrite</button>
    </article>
  `).join('');
  const patchButtons = patches.slice(0, 4).map((patch, index) => `
    <button type="button" class="patch-button apply-live-static-patch" data-patch="${index}">
      <strong>${escapeHtml(patch.label || `Patch ${index + 1}`)}</strong>
      <span>${escapeHtml(patch.why || '')}</span>
      <em>${escapeHtml(patch.replacement || '')}</em>
    </button>
  `).join('');
  if (!rewriteButtons && !patchButtons) return '<p class="muted tiny-text">No live rewrite generated for this line yet.</p>';
  return `<div class="static-rewrite-grid live-static-rewrite-grid">${rewriteButtons}</div><div class="patch-grid live-static-patches">${patchButtons}</div>`;
}

function liveNearbyStaticLinesHtml(lines = []) {
  if (!lines.length) return '';
  return `
    <div class="live-nearby-lines">
      ${lines.slice(0, 7).map((row) => {
        const score = row.bar_score?.overall;
        return `<button type="button" class="mini-line-item line-jump" data-line="${escapeHtml(row.line_number)}">
          <b>L${escapeHtml(row.line_number)}</b>
          <span>${escapeHtml(row.text || '').slice(0, 88)}${score !== undefined ? ` · ${escapeHtml(score)}%` : ''}</span>
        </button>`;
      }).join('')}
    </div>
  `;
}

function liveStaticLineAnalysisHtml(liveStatic = {}, activeReport = {}) {
  const row = liveStatic?.active_line || activeReport?.static_line_analysis || null;
  if (!row || !liveStatic?.available) {
    return `<section class="live-rhyme-card nested live-static-analysis muted"><h4>Static Snapshot line analysis</h4><p>${escapeHtml(liveStatic?.error || 'Static-style line diagnostics are not available for this live update yet.')}</p></section>`;
  }
  const metrics = row.metrics || {};
  const breakdown = row.breakdown || {};
  const bar = breakdown.bar_structure || {};
  const info = row.information || {};
  const meter = row.meter || {};
  const physics = row.physics || {};
  const barScore = row.bar_score || {};
  const overview = liveStatic.overview || {};
  return `
    <section class="live-rhyme-card nested live-static-analysis">
      <div class="live-static-head">
        <div>
          <p class="eyebrow">Static Snapshot elements live</p>
          <h4>Line ${escapeHtml(row.line_number || activeReport.line_number || '—')} · ${escapeHtml(row.role || 'line')}</h4>
          <small>${escapeHtml(row.section?.label || 'Section')} · ${escapeHtml(row.suggestion?.operation_label || 'Polish')}</small>
        </div>
        ${barScore.overall !== undefined ? `<div class="live-rhyme-score-badge ${liveRhymeScoreClass(barScore.overall)}"><strong>${escapeHtml(barScore.overall)}</strong><small>bar score</small></div>` : ''}
      </div>
      <blockquote class="rhyme-line live-static-rhyme-line">${rhymeHighlightedLineHtml(row.rhyme_highlight, row.text || activeReport.text || '')}</blockquote>
      ${rhymeLineMetaHtml(row.rhyme_highlight)}
      ${liveStaticMetricHtml(row)}
      <div class="live-static-read-first">
        <strong>What to do first</strong>
        <ol>${(row.suggestion?.action_steps || overview.actions || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
      </div>
      <details open>
        <summary>Line diagnosis: cadence, sound, content, rhyme</summary>
        <div class="static-breakdown-grid live-static-breakdown-grid">
          <section><h4>Cadence</h4><p>${escapeHtml(breakdown.cadence || '')}</p></section>
          <section><h4>Sound</h4><p>${escapeHtml(breakdown.sound || '')}</p></section>
          <section><h4>Content</h4><p>${escapeHtml(breakdown.content || '')}</p></section>
          <section><h4>Rhyme</h4><p>${escapeHtml(breakdown.rhyme || '')}</p></section>
          <section class="wide"><h4>Bar structure</h4><p>${escapeHtml(bar.note || '')}</p></section>
          <section class="wide"><h4>Information profile</h4><p>${escapeHtml(info.interpretation || '')}</p><p class="muted tiny-text">Rarest words: ${(info.rarest_words || []).map((item) => `${escapeHtml(item.word)} (${escapeHtml(item.bits)}b)`).join(', ') || '—'}</p></section>
          ${barScore.overall !== undefined ? `<section class="wide score-line-section"><h4>Bar score</h4><p><strong>${escapeHtml(barScore.overall)}%</strong> · ${escapeHtml(barScore.grade?.letter || '')} · ${escapeHtml(barScore.grade?.label || '')}</p><p>${escapeHtml((barScore.diagnosis?.issues || []).join('; '))}</p><ol>${(barScore.diagnosis?.advice || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></section>` : ''}
          ${row.comparison_guidance?.available ? `<section class="wide comparison-line-section"><h4>Reference benchmark</h4><p>${escapeHtml(row.comparison_guidance.note || '')}</p><p class="muted tiny-text">${escapeHtml(row.comparison_guidance.rhyme_note || '')}</p></section>` : ''}
        </div>
      </details>
      ${meter.available ? `<details open><summary>Meter / stress</summary>${meterMiniHtml(meter)}<ol>${(meter.suggestions || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></details>` : ''}
      ${physics.available ? `<details open><summary>Scansion Physics</summary>${physicsMiniHtml(physics)}</details>` : ''}
      <details open><summary>Advanced rhyme options</summary>${advancedRhymeReportHtml(row.advanced_rhyme || {})}</details>
      <details open><summary>Possible words</summary><div class="static-word-grid live-static-word-grid">${staticWordsHtml(row.possible_words || {})}</div></details>
      <details><summary>Rewrite options and applyable patches</summary>${liveStaticRewriteHtml(row)}</details>
      <details><summary>Revision checklist</summary><ul>${(row.suggestion?.checklist || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details>
      ${(liveStatic.nearby_lines || []).length ? `<details><summary>Nearby line context</summary>${liveNearbyStaticLinesHtml(liveStatic.nearby_lines || [])}</details>` : ''}
    </section>
  `;
}


function liveRhymeLineMapHtml(report = {}) {
  const lines = report.line_reports || [];
  if (!lines.length) return '<div class="empty-state compact-empty">Line rhyme map will appear after the first analysis.</div>';
  return `
    <section class="live-rhyme-card live-rhyme-map-card">
      <div class="viz-card-head"><h4>Line rhyme map</h4><small>Click a tile to jump to a line.</small></div>
      <div class="live-rhyme-line-map">
        ${lines.slice(0, 64).map((row) => {
          const score = Number(row.rhyme_power?.score || 0);
          return `<button type="button" class="live-rhyme-line-tile ${liveRhymeScoreClass(score)} ${row.active ? 'active' : ''} line-jump" data-line="${escapeHtml(row.line_number)}" title="${escapeHtml(row.text || '')}">
            <span>L${escapeHtml(row.line_number)}</span>
            <strong>${escapeHtml(row.end_word || '—')}</strong>
            <small>/${escapeHtml(row.rhyme_key || '—')}/ · ${escapeHtml(score)}</small>
          </button>`;
        }).join('')}
      </div>
    </section>
  `;
}

function liveRhymeDiagnosticsHtml(extra = {}) {
  const routes = state.lastLiveRhymeRoutes || {};
  const jobId = state.liveRhymeJobId || 'none';
  const active = state.lastLiveRhymeActiveLine || activeLineNumber();
  const routeText = routes.available ? 'routes ok' : 'routes not tested';
  return `
    <section class="live-rhyme-diagnostics-card">
      <div><strong>${escapeHtml(routeText)}</strong><small>active line ${escapeHtml(active)} · job ${escapeHtml(String(jobId).slice(0, 10))}</small></div>
      <div><span>${escapeHtml(extra.message || '')}</span><small>${escapeHtml(routes.now || '')}</small></div>
    </section>
  `;
}

function setLiveRhymeDiagnostics(message = '') {
  if (!liveRhymeDiagnosticsEl) return;
  liveRhymeDiagnosticsEl.className = 'live-rhyme-diagnostics';
  liveRhymeDiagnosticsEl.innerHTML = liveRhymeDiagnosticsHtml({ message });
}


async function safeJsonResponse(response, label = 'request') {
  const raw = await response.text();
  let payload = {};
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch (_error) {
    const snippet = raw.replace(/\s+/g, ' ').slice(0, 260);
    const paHint = /502|504|There was an error loading your PythonAnywhere web app|Traceback|ImportError|ModuleNotFoundError/i.test(snippet)
      ? ' · Check the PythonAnywhere error log and run the PythonAnywhere diagnostics button.'
      : '';
    throw new Error(`${label} returned non-JSON from ${response.url || 'route'}: ${snippet || response.status}${paHint}`);
  }
  if (!response.ok) {
    throw new Error(payload.error || payload.message || `${label} failed with HTTP ${response.status}`);
  }
  return payload;
}

function liveRhymeContextPayload(forceFull = false) {
  const original = editor.value || '';
  const lines = original.split(/\r?\n/);
  const activeOriginal = activeLineNumber();
  const maxChars = Math.min(Number(window.NMC_BOOTSTRAP?.maxLyricsChars || 30000), 2600);
  if (forceFull || original.length <= maxChars) {
    return {
      lyrics: original,
      active_line: activeOriginal,
      source_active_line: activeOriginal,
      context_offset_lines: 0,
      total_source_lines: lines.length,
      client_clipped: false,
    };
  }
  const radius = 6;
  const idx = Math.max(0, Math.min(lines.length - 1, activeOriginal - 1));
  let start = Math.max(0, idx - radius);
  let end = Math.min(lines.length, idx + radius + 1);
  let context = lines.slice(start, end).join('\n');
  while (context.length > maxChars && end - start > 12) {
    if (idx - start > end - idx - 1) start += 1;
    else end -= 1;
    context = lines.slice(start, end).join('\n');
  }
  return {
    lyrics: context,
    active_line: idx - start + 1,
    source_active_line: activeOriginal,
    context_offset_lines: start,
    total_source_lines: lines.length,
    client_clipped: true,
  };
}

function showLiveRhymeSoftFailure(message, title = 'Fallback') {
  setLiveRhymeStatus('warning', title);
  setLiveRhymeDiagnostics(message || 'using safe fallback');
}

function replaceLineEnding(lineNumber, word) {
  const line = Number(lineNumber || state.activeLine || activeLineNumber());
  const lines = editor.value.split(/\r?\n/);
  const index = Math.max(0, Math.min(lines.length - 1, line - 1));
  const replacement = String(word || '').trim();
  if (!replacement) return;
  const original = lines[index] || '';
  const patched = original.match(/[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*[^A-Za-z0-9]*$/)
    ? original.replace(/[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*([^A-Za-z0-9]*)$/, `${replacement}$1`)
    : `${original}${original && !/\s$/.test(original) ? ' ' : ''}${replacement}`;
  lines[index] = patched;
  editor.value = lines.join('\n');
  const before = lines.slice(0, index).join('\n');
  const pos = (before ? before.length + 1 : 0) + patched.length;
  editor.focus();
  editor.selectionStart = editor.selectionEnd = pos;
  handleEditorActivity();
}

function renderLiveRhymeReport(report = {}) {
  state.liveRhymeReport = report;
  if (!liveRhymeActiveEl || !liveRhymeSchemeEl) return;
  if (!report || !report.available) {
    liveRhymeActiveEl.className = 'live-rhyme-active empty-state';
    liveRhymeActiveEl.textContent = report?.error || 'Live rhyme suggestions will appear once the draft has at least three words.';
    liveRhymeSchemeEl.className = 'live-rhyme-scheme empty-state';
    liveRhymeSchemeEl.textContent = 'Draft-level rhyme scheme guidance will appear after the first live rhyme job.';
    if (liveRhymeBanksEl) liveRhymeBanksEl.innerHTML = '';
    if (liveRhymeLineMapEl) liveRhymeLineMapEl.innerHTML = '';
    setLiveRhymeDiagnostics(report?.error || 'waiting');
    return;
  }
  const active = report.active_report || {};
  const power = active.rhyme_power || {};
  const score = Number(power.score || 0);
  liveRhymeActiveEl.className = `live-rhyme-active live-rhyme-card ${liveRhymeScoreClass(score)}`;
  liveRhymeActiveEl.innerHTML = `
    <div class="live-rhyme-current-head">
      <div>
        <p class="eyebrow">Active line ${escapeHtml(active.line_number || report.active_line_number || '—')}</p>
        <h3>${escapeHtml(active.text || 'No active line detected.')}</h3>
      </div>
      <div class="live-rhyme-score-badge ${liveRhymeScoreClass(score)}"><strong>${escapeHtml(score)}</strong><small>${escapeHtml(power.label || 'score')}</small></div>
    </div>
    <div class="rhyme-meta-row">
      <span>landing: <b>${escapeHtml(active.end_word || '—')}</b></span>
      <span>family: <b>/${escapeHtml(active.rhyme_key || '—')}/</b></span>
      <span>${escapeHtml(active.chain_note || 'single line')}</span>
    </div>
    ${(active.actions || []).length ? `<section class="live-rhyme-card nested"><h4>Fix now</h4><ol>${(active.actions || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></section>` : ''}
    <section class="live-rhyme-card nested"><h4>Applyable rhyme patches</h4>${liveRhymePatchesHtml(active)}</section>
    <section class="live-rhyme-card nested"><h4>Ranked landing options</h4>${liveRhymeOptionChips(active.ranked_options || [])}</section>
    ${(active.blueprints || []).length ? `<section class="live-rhyme-card nested"><h4>Pattern blueprints</h4><ol>${(active.blueprints || []).slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></section>` : ''}
    ${liveStaticLineAnalysisHtml(report.live_static_analysis || {}, active)}
  `;
  if (liveRhymeBanksEl) {
    liveRhymeBanksEl.innerHTML = `<section class="live-rhyme-card"><h4>Active-line word banks</h4>${wordBankHtml(active.word_lists || {})}</section>`;
  }
  liveRhymeSchemeEl.className = 'live-rhyme-scheme';
  liveRhymeSchemeEl.innerHTML = liveRhymeSchemeHtml(report);
  if (liveRhymeLineMapEl) liveRhymeLineMapEl.innerHTML = liveRhymeLineMapHtml(report);
  setLiveRhymeDiagnostics(`updated ${report.generated_at || ''}`);
}

async function runLiveRhymeSync(lyrics, active, token, reason = '', context = null) {
  setLiveRhymeStatus('running', 'Sync');
  setLiveRhymeDiagnostics(reason ? `safe fallback after: ${reason}` : 'sync fallback');
  try {
    const body = context || liveRhymeContextPayload(false);
    const response = await fetch('/api/live-writer/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, coach_mode: coachMode.value, beat_id: state.beatId, request_id: token }),
    });
    const payload = await safeJsonResponse(response, 'Live rhyme sync');
    if (token !== state.liveRhymeSequence) return;
    state.liveRhymeReport = payload;
    setLiveRhymeStatus(payload.fallback_used ? 'warning' : 'complete', payload.fallback_used ? 'Fallback' : 'Rhymes');
    renderLiveRhymeReport(payload);
  } catch (error) {
    // Keep the writer usable. The sidecar should explain the issue without flashing a hard error.
    showLiveRhymeSoftFailure(error.message, 'Paused');
    if (!state.liveRhymeReport?.available) {
      renderLiveRhymeReport({ available: false, error: `Live rhyme paused: ${error.message}` });
    }
  }
}

async function queueLiveRhymeJob(force = false) {
  if (!liveRhymeStatusEl) return;
  if (!force && liveRhymeAutoEl && !liveRhymeAutoEl.checked) return;
  const context = liveRhymeContextPayload(false);
  const lyricsKey = `${context.lyrics}|${context.context_offset_lines}`;
  const active = context.source_active_line || activeLineNumber();
  if (!force && lyricsKey === state.lastLiveRhymeLyricsSent && active === state.lastLiveRhymeActiveLine) return;
  updateLocalStats();
  if (countWords(editor.value) < 3) {
    renderLiveRhymeReport({ available: false, error: 'Type at least three words to start the live rhyme sidecar.' });
    setLiveRhymeStatus('idle', 'Ready');
    return;
  }
  state.liveRhymeSequence += 1;
  const token = state.liveRhymeSequence;
  state.lastLiveRhymeLyricsSent = lyricsKey;
  state.lastLiveRhymeActiveLine = active;
  if (state.liveRhymePollTimer) clearTimeout(state.liveRhymePollTimer);
  setLiveRhymeStatus('running', 'Analyzing');
  setLiveRhymeDiagnostics(context.client_clipped ? 'queue-free direct live analysis with clipped local context' : 'queue-free direct live analysis');
  try {
    // Direct live mode: still asynchronous in the browser, but the server returns
    // the completed result in this response. This prevents PythonAnywhere/WSGI
    // deployments from getting stuck on queued jobs.
    const response = await fetch('/api/live-writer/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...context, coach_mode: coachMode.value, beat_id: state.beatId, request_id: token, direct_live: true }),
    });
    const payload = await safeJsonResponse(response, 'Live rhyme direct analysis');
    if (token !== state.liveRhymeSequence) return;
    state.liveRhymeJobId = payload.job_id || 'direct';
    const result = payload.result || (payload.available ? payload : null);
    if (!result) throw new Error(payload.error || `Live rhyme returned ${payload.status || 'no result'}.`);
    setLiveRhymeStatus(result.fallback_used ? 'warning' : 'complete', result.fallback_used ? 'Fallback' : 'Rhymes');
    setLiveRhymeDiagnostics(`direct complete · no queue${context.client_clipped ? ' · local context clipped' : ''}`);
    renderLiveRhymeReport(result);
  } catch (error) {
    state.liveRhymeFailCount += 1;
    await runLiveRhymeSync(context.lyrics, context.active_line, token, error.message, context);
  }
}

async function pollLiveRhymeJob(jobId, token, attempt = 0, context = null) {
  if (state.liveRhymePollTimer) clearTimeout(state.liveRhymePollTimer);
  try {
    const response = await fetch(`/api/live-rhyme/job/${jobId}`);
    const payload = await safeJsonResponse(response, 'Live rhyme poll');
    if (token !== state.liveRhymeSequence) return;
    if (payload.status === 'complete') {
      const result = payload.result || (payload.available ? payload : null);
      if (!result) throw new Error('Live rhyme job completed without a result payload.');
      setLiveRhymeStatus(result.fallback_used ? 'warning' : 'complete', result.fallback_used ? 'Fallback' : 'Rhymes');
      renderLiveRhymeReport(result);
      return;
    }
    if (payload.status === 'error') throw new Error(payload.error || 'Live rhyme analysis error.');
    setLiveRhymeStatus('running', payload.status === 'queued' ? 'Direct' : 'Thinking');
    setLiveRhymeDiagnostics(`${payload.status || 'running'} · poll ${attempt + 1}`);
    if (attempt >= 24) {
      await runLiveRhymeSync(context?.lyrics || editor.value, context?.active_line || activeLineNumber(), token, 'async job timed out', context || liveRhymeContextPayload(false));
      return;
    }
    state.liveRhymePollTimer = setTimeout(() => pollLiveRhymeJob(jobId, token, attempt + 1, context), 520);
  } catch (error) {
    state.liveRhymeFailCount += 1;
    await runLiveRhymeSync(context?.lyrics || editor.value, context?.active_line || activeLineNumber(), token, error.message, context || liveRhymeContextPayload(false));
  }
}

function scheduleLiveRhymeSuggestion() {
  if (!liveRhymeStatusEl) return;
  if (state.liveRhymeTimer) clearTimeout(state.liveRhymeTimer);
  state.liveRhymeTimer = setTimeout(() => queueLiveRhymeJob(false), 900);
}


const WORD_TOKEN_RE_SOURCE = "[A-Za-z0-9]+(?:['’\\-][A-Za-z0-9]+)*";
const WORD_TOKEN_RE_GLOBAL = new RegExp(WORD_TOKEN_RE_SOURCE, 'g');

function lineStartOffset(lineNumber) {
  const lines = (editor.value || '').split(/\r?\n/);
  const target = Math.max(1, Number(lineNumber || 1));
  let offset = 0;
  for (let i = 0; i < Math.min(target - 1, lines.length); i += 1) offset += lines[i].length + 1;
  return offset;
}

function tokenMatchesInRange(text, start, end) {
  const a = Math.max(0, Math.min(Number(start || 0), text.length));
  const b = Math.max(a, Math.min(Number(end || a), text.length));
  const fragment = text.slice(a, b);
  const matches = [];
  const localRe = new RegExp(WORD_TOKEN_RE_SOURCE, 'g');
  let match;
  while ((match = localRe.exec(fragment))) {
    const absStart = a + match.index;
    const absEnd = absStart + match[0].length;
    const center = (absStart + absEnd) / 2;
    matches.push({ word: match[0], start: absStart, end: absEnd, distance: Math.abs(center - ((a + b) / 2)) });
  }
  return matches;
}

function bestWordTokenInRange(text, start, end, cursor = start) {
  const matches = tokenMatchesInRange(text, start, end).map((m) => ({ ...m, distance: Math.abs(((m.start + m.end) / 2) - cursor) }));
  if (!matches.length) return null;
  matches.sort((x, y) => (x.distance - y.distance) || (y.word.length - x.word.length));
  return matches[0];
}

function phraseTokenInRange(text, start, end) {
  const matches = tokenMatchesInRange(text, start, end);
  if (matches.length < 2) return null;
  const first = matches[0];
  const last = matches[matches.length - 1];
  const phrase = text.slice(first.start, last.end).replace(/\s+/g, ' ').trim();
  if (!phrase || phrase.length > 140) return null;
  const lineNumber = text.slice(0, first.start).split(/\r?\n/).length;
  const lastLineNumber = text.slice(0, last.end).split(/\r?\n/).length;
  if (lineNumber !== lastLineNumber) return null;
  return { word: phrase, start: first.start, end: last.end, phrase: true, tokenCount: matches.length, distance: 0 };
}

function wordAtEditorCursor() {
  const text = editor.value || '';
  const rawStart = editor.selectionStart || 0;
  const rawEnd = editor.selectionEnd || rawStart;
  let token = null;
  if (rawEnd > rawStart) {
    token = phraseTokenInRange(text, rawStart, rawEnd) || bestWordTokenInRange(text, rawStart, rawEnd, (rawStart + rawEnd) / 2);
  }
  if (!token) {
    const left = text.slice(0, rawStart);
    const right = text.slice(rawStart);
    const leftMatch = left.match(new RegExp(`${WORD_TOKEN_RE_SOURCE}$`));
    const rightMatch = right.match(new RegExp(`^${WORD_TOKEN_RE_SOURCE}`));
    const leftPart = leftMatch ? leftMatch[0] : '';
    const rightPart = rightMatch ? rightMatch[0] : '';
    const combined = `${leftPart}${rightPart}`;
    if (combined) token = { word: combined, start: rawStart - leftPart.length, end: rawStart + rightPart.length, distance: 0, phrase: false, tokenCount: 1 };
  }
  const selStart = token ? token.start : rawStart;
  const selEnd = token ? token.end : rawEnd;
  const word = token ? token.word : '';
  const lineNumber = text.slice(0, selStart).split(/\r?\n/).length;
  const lineText = (text.split(/\r?\n/)[lineNumber - 1] || '').trim();
  return {
    word,
    lineNumber,
    lineText,
    start: selStart,
    end: selEnd,
    phrase: Boolean(token && token.phrase),
    tokenCount: token?.tokenCount || (word ? 1 : 0),
    selectedText: text.slice(selStart, selEnd),
    rawSelection: { start: rawStart, end: rawEnd, text: text.slice(rawStart, rawEnd) },
  };
}

function findWordRangeInEditorLine(word, lineNumber, preferredLineText = '') {
  const target = String(word || '').toLowerCase();
  if (!target) return null;
  const lines = (editor.value || '').split(/\r?\n/);
  const idx = Math.max(0, Math.min(lines.length - 1, Number(lineNumber || activeLineNumber()) - 1));
  const line = lines[idx] || '';
  const offset = lineStartOffset(idx + 1);
  const localRe = new RegExp(WORD_TOKEN_RE_SOURCE, 'g');
  const matches = [];
  let match;
  while ((match = localRe.exec(line))) {
    if (match[0].toLowerCase() === target) {
      matches.push({ word: match[0], start: offset + match.index, end: offset + match.index + match[0].length, lineNumber: idx + 1, lineText: line });
    }
  }
  if (matches.length) return matches[0];
  if (preferredLineText) {
    const pref = String(preferredLineText).toLowerCase();
    const pos = pref.indexOf(target);
    if (pos >= 0 && pos < line.length) {
      return { word, start: offset + pos, end: offset + pos + String(word).length, lineNumber: idx + 1, lineText: line };
    }
  }
  return null;
}

function renderHighlightedWordReport(report = {}) {
  if (!highlightedWordPanelEl) return;
  state.selectedWordReport = report;
  if (!report || !report.available) {
    highlightedWordPanelEl.className = 'highlighted-word-panel empty-state compact-empty';
    highlightedWordPanelEl.textContent = report?.error || 'Highlight or double-click a word or phrase in the editor to fetch similar rhymes asynchronously.';
    return;
  }
  const summary = report.summary || {};
  const ranked = report.ranked || [];
  const ladder = report.rhyme_ladder || [];
  const wordLists = report.word_lists || {};
  const isPhrase = Boolean(report.phrase_mode || report.selected_phrase);
  const displayTarget = report.selected_phrase || report.target_word || report.selected_word || '';
  const chips = (items = [], cls = '') => items.slice(0, 14).map((item) => {
    const word = typeof item === 'string' ? item : (item.word || item.phrase || item.display || '');
    if (!word) return '';
    const kind = typeof item === 'string' ? '' : (item.kind || item.category || '');
    const score = typeof item === 'string' ? '' : (item.score ?? '');
    const label = kind || score !== '' ? `<small>${escapeHtml(kind)}${score !== '' ? ` · ${escapeHtml(score)}` : ''}</small>` : '';
    return `<button type="button" class="selected-rhyme-chip ${cls} ${escapeHtml(String(kind).replace(/\s+/g, '-'))}" data-word="${escapeHtml(word)}"><span>${escapeHtml(word)}</span>${label}</button>`;
  }).join('');
  highlightedWordPanelEl.className = 'highlighted-word-panel live-rhyme-card';
  highlightedWordPanelEl.innerHTML = `
    <div class="highlighted-word-head">
      <div>
        <p class="eyebrow">${isPhrase ? 'Highlighted phrase' : 'Highlighted word'}</p>
        <h3>${escapeHtml(displayTarget || '—')}</h3>
        ${isPhrase ? `<p class="muted tiny-text">phrase landing: <b>${escapeHtml(report.target_word || '—')}</b></p>` : ''}
      </div>
      <div class="live-rhyme-score-badge ${liveRhymeScoreClass(summary.best_score || 0)}"><strong>${escapeHtml(summary.best_score || 0)}</strong><small>${escapeHtml(summary.best_kind || 'rhyme')}</small></div>
    </div>
    <p class="muted tiny-text">/${escapeHtml(summary.rhyme_key || '—')}/ · ${escapeHtml(summary.phones || '')} · ${escapeHtml(summary.syllables || 0)} syll · ${report.broad_family_mode ? 'broad family mode' : report.strict_filtering ? 'strict phonetic filter on' : `stress ${escapeHtml(summary.stress_signature || '—')}`} · ${escapeHtml(report.generated_at || '')}</p>
    ${report.instruction ? `<div class="fit-callout tiny-text">${escapeHtml(report.instruction)}</div>` : ''}
    <div class="highlighted-word-actions">
      <button type="button" class="ghost tiny" id="replaceHighlightedWithBest">Replace with best</button>
      <button type="button" class="ghost tiny" id="copyHighlightedWordJson">Copy rhyme JSON</button>
    </div>
    <section class="selected-word-bank"><h4>${isPhrase ? 'Best phrase rhymes' : 'Best similar rhymes'}</h4><div class="chip-row">${chips(ranked, isPhrase ? 'ranked phrase' : 'ranked')}</div></section>
    ${isPhrase && (wordLists.pattern_preserving_phrases || []).length ? `<section class="selected-word-bank"><h4>Preserve phrase frame</h4><div class="chip-row">${chips(wordLists.pattern_preserving_phrases || [], 'phrase-preserve')}</div></section>` : ''}
    ${isPhrase && (wordLists.suggestive_phrase_families || []).length ? `<section class="selected-word-bank"><h4>Suggestive phrase families</h4><div class="chip-row">${chips(wordLists.suggestive_phrase_families || [], 'phrase-family')}</div></section>` : ''}
    <section class="selected-word-bank"><h4>Clean family / end rhymes</h4><div class="chip-row">${chips(wordLists.end_rhymes || [])}</div></section>
    ${(wordLists.style_slants || []).length ? `<section class="selected-word-bank"><h4>Corpus style slants</h4><div class="chip-row">${chips(wordLists.style_slants || [], 'style-slant')}</div></section>` : ''}
    ${(wordLists.broad_family || []).length ? `<section class="selected-word-bank"><h4>Broad rap family</h4><div class="chip-row">${chips(wordLists.broad_family || [], 'broad-family')}</div></section>` : ''}
    <section class="selected-word-bank"><h4>Slant + near rhymes</h4><div class="chip-row">${chips([...(wordLists.slant_rhymes || []), ...(wordLists.near_rhymes || [])], 'slant')}</div></section>
    <section class="selected-word-bank"><h4>Multi-syllable landings</h4><div class="chip-row">${chips(wordLists.multi_syllable_endings || [], 'phrase')}</div></section>
    ${report.classification_legend ? `<details><summary>Rhyme classification guide</summary><ul>${(report.classification_legend || []).map((row) => `<li><b>${escapeHtml(row.kind || '')}</b>: ${escapeHtml(row.meaning || '')}</li>`).join('')}</ul></details>` : ''}
    ${ladder.length ? `<details><summary>Rhyme pattern ladder</summary>${ladder.slice(0,5).map((row) => `<div class="rhyme-ladder-step"><strong>${escapeHtml(row.stage || '')}</strong><small>${escapeHtml(row.use_when || '')}</small><div class="chip-row">${chips(row.options || [])}</div></div>`).join('')}</details>` : ''}
  `;
}

function selectedWordPayload(infoOverride = null) {
  const info = infoOverride || wordAtEditorCursor();
  state.selectedWordRange = {
    start: info.start,
    end: info.end,
    word: info.word,
    line_number: info.lineNumber,
    line_text: info.lineText,
    selected_text: info.selectedText,
    phrase: Boolean(info.phrase),
    token_count: info.tokenCount || 1,
  };
  const context = liveRhymeContextPayload(false);
  return {
    word: info.word,
    selected_word: info.word,
    highlighted_word: info.word,
    selected_text: info.selectedText,
    selected_phrase: info.phrase ? info.word : '',
    phrase: info.phrase ? info.word : '',
    phrase_mode: Boolean(info.phrase),
    lyrics: editor.value,
    context_lyrics: context.lyrics,
    line_text: info.lineText,
    active_line: info.lineNumber,
    coach_mode: coachMode.value,
    selection_start: info.start,
    selection_end: info.end,
    selection_range: state.selectedWordRange,
    raw_selection: info.rawSelection || null,
    source_active_line: info.lineNumber,
    context_offset_lines: context.context_offset_lines || 0,
    total_source_lines: context.total_source_lines || countLines(editor.value),
  };
}

async function runSelectedWordRhymeSync(token, reason = '', explicitInfo = null) {
  const payloadBody = selectedWordPayload(explicitInfo);
  if (!payloadBody.word || payloadBody.word.length < 2) {
    renderHighlightedWordReport({ available: false, error: 'Highlight a word or phrase, or place the cursor inside a word first.' });
    return;
  }
  highlightedWordPanelEl.className = 'highlighted-word-panel live-rhyme-card loading';
  try {
    const response = await fetch('/api/live-writer/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payloadBody, request_id: token, reason }),
    });
    const payload = await safeJsonResponse(response, 'Selected-word rhyme sync');
    if (token !== state.selectedWordSequence) return;
    renderHighlightedWordReport(payload);
  } catch (error) {
    renderHighlightedWordReport({ available: false, error: error.message });
  }
}

async function pollSelectedWordRhymeJob(jobId, token, attempt = 0) {
  if (state.selectedWordPollTimer) clearTimeout(state.selectedWordPollTimer);
  try {
    const response = await fetch(`/api/rhyme-word/job/${jobId}`);
    const payload = await safeJsonResponse(response, 'Selected-word rhyme poll');
    if (token !== state.selectedWordSequence) return;
    if (payload.status === 'complete') {
      const result = payload.result || (payload.available ? payload : null);
      if (!result) throw new Error('Selected-word job completed without a result payload.');
      renderHighlightedWordReport(result);
      return;
    }
    if (payload.status === 'error') throw new Error(payload.error || 'Selected-word rhyme analysis error.');
    highlightedWordPanelEl.className = 'highlighted-word-panel live-rhyme-card loading';
    highlightedWordPanelEl.innerHTML = `<p class="muted tiny-text">Analyzing highlighted word asynchronously… ${escapeHtml(payload.status || 'running')} · poll ${escapeHtml(attempt + 1)}</p>`;
    if (attempt >= 18) {
      await runSelectedWordRhymeSync(token, 'async selected-word job timed out');
      return;
    }
    state.selectedWordPollTimer = setTimeout(() => pollSelectedWordRhymeJob(jobId, token, attempt + 1), 300);
  } catch (error) {
    await runSelectedWordRhymeSync(token, error.message);
  }
}

async function queueSelectedWordRhyme(force = false, explicitInfo = null) {
  if (!highlightedWordPanelEl) return;
  const payloadBody = selectedWordPayload(explicitInfo);
  if (!payloadBody.word || payloadBody.word.length < 2) {
    if (force) renderHighlightedWordReport({ available: false, error: 'Highlight a word or phrase, or place the cursor inside a word first.' });
    return;
  }
  const contextKey = `${payloadBody.word}|${payloadBody.active_line}|${payloadBody.selection_start}|${payloadBody.selection_end}|${payloadBody.line_text}`;
  if (!force && contextKey === state.selectedWordContextKey) return;
  state.selectedWordContextKey = contextKey;
  state.selectedWordSequence += 1;
  const token = state.selectedWordSequence;
  if (state.selectedWordPollTimer) clearTimeout(state.selectedWordPollTimer);
  highlightedWordPanelEl.className = 'highlighted-word-panel live-rhyme-card loading';
  highlightedWordPanelEl.innerHTML = `<p class="eyebrow">Highlighted word</p><h3>${escapeHtml(payloadBody.word)}</h3><p class="muted tiny-text">${payloadBody.phrase_mode ? 'Analyzing phrase rhymes' : 'Analyzing similar rhymes'} for line ${escapeHtml(payloadBody.active_line)}…</p>`;
  try {
    const response = await fetch('/api/live-writer/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payloadBody, request_id: token, direct_live: true }),
    });
    const payload = await safeJsonResponse(response, 'Selected-word direct rhyme route');
    if (token !== state.selectedWordSequence) return;
    state.selectedWordJobId = payload.job_id || 'direct-word';
    const result = payload.result || (payload.available ? payload : null);
    if (!result) throw new Error(payload.error || `Selected-word rhyme returned ${payload.status || 'no result'}.`);
    renderHighlightedWordReport(result);
  } catch (error) {
    await runSelectedWordRhymeSync(token, error.message, explicitInfo);
  }
}

function analyzeExplicitHighlightedWord(word, lineNumber = null, lineText = '') {
  const clean = String(word || '').match(new RegExp(WORD_TOKEN_RE_SOURCE));
  const target = clean ? clean[0] : '';
  if (!target) return;
  const located = findWordRangeInEditorLine(target, lineNumber || activeLineNumber(), lineText);
  const info = located || {
    word: target,
    lineNumber: Number(lineNumber || activeLineNumber()),
    lineText: lineText || (editor.value.split(/\r?\n/)[activeLineNumber() - 1] || ''),
    start: editor.selectionStart || 0,
    end: editor.selectionEnd || editor.selectionStart || 0,
    selectedText: target,
    rawSelection: null,
  };
  if (located) {
    editor.focus();
    editor.selectionStart = located.start;
    editor.selectionEnd = located.end;
  }
  queueSelectedWordRhyme(true, info);
}

function scheduleSelectedWordRhyme(force = false) {
  if (!force && selectedWordAutoEl && !selectedWordAutoEl.checked) return;
  if (state.selectedWordTimer) clearTimeout(state.selectedWordTimer);
  state.selectedWordTimer = setTimeout(() => queueSelectedWordRhyme(force), force ? 0 : 520);
}

function replaceSelectedWord(newWord) {
  const word = String(newWord || '').trim();
  if (!word) return;
  let range = state.selectedWordRange || wordAtEditorCursor();
  let start = Math.max(0, Number(range.start || 0));
  let end = Math.max(start, Number(range.end || start));
  const current = editor.value.slice(start, end);
  const isPhraseRange = Boolean(range.phrase || /\s/.test(String(range.word || range.selected_text || '')));
  if (!isPhraseRange && (!current || (range.word && current.toLowerCase() !== String(range.word).toLowerCase()))) {
    const found = findWordRangeInEditorLine(range.word || current || word, range.line_number || activeLineNumber(), range.line_text || '');
    if (found) {
      range = found;
      start = found.start;
      end = found.end;
    }
  }
  const before = editor.value.slice(0, start);
  const after = editor.value.slice(end);
  const needsLeft = before && /[A-Za-z0-9]$/.test(before) ? ' ' : '';
  const needsRight = after && /^[A-Za-z0-9]/.test(after) ? ' ' : '';
  editor.value = `${before}${needsLeft}${word}${needsRight}${after}`;
  const pos = before.length + needsLeft.length + word.length;
  editor.focus();
  editor.selectionStart = Math.max(0, before.length + needsLeft.length);
  editor.selectionEnd = pos;
  state.selectedWordRange = { start: editor.selectionStart, end: editor.selectionEnd, word, line_number: range.line_number || activeLineNumber(), line_text: (editor.value.split(/\r?\n/)[(range.line_number || activeLineNumber()) - 1] || '') };
  handleEditorActivity();
  scheduleSelectedWordRhyme(true);
}

function handleEditorActivity() {
  updateLocalStats();
  // The same-template writer should stay lightweight. Full live coaching is manual;
  // rhyme sidecar remains asynchronous while typing.
  scheduleLiveRhymeSuggestion();
}


function wordBankHtml(bank = {}) {
  const groups = [
    ['End rhymes', bank.end_rhymes],
    ['Near rhymes', bank.near_rhymes],
    ['Slant rhymes', bank.slant_rhymes],
    ['Assonance', bank.assonance_words],
    ['Consonance', bank.consonance_words],
    ['Stress matched', bank.stress_matched],
    ['Multi-syllable endings', bank.multi_syllable_endings],
    ['Internal echoes', bank.internal_echoes],
    ['Signature words', bank.signature_words],
    ['Images', bank.images],
    ['Verbs', bank.verbs],
    ['Punch words', bank.punch_words],
    ['Cut words', bank.cut_words],
  ];  return groups.map(([title, words]) => `
    <section class="bank-group">
      <h4>${escapeHtml(title)}</h4>
      <div class="chips">${chips(words || [])}</div>
    </section>
  `).join('');
}


function rhymeHighlightedLineHtml(highlight, fallbackText = '') {
  const tokens = highlight && Array.isArray(highlight.tokens) ? highlight.tokens : [];
  if (!tokens.length) return escapeHtml(fallbackText);
  return tokens.map((token) => {
    const text = escapeHtml(token.text || '');
    if (!token.highlight) return text;
    const cls = Number(token.rhyme_class || highlight.line_rhyme_class || 0);
    const role = String(token.role || 'rhyme').replace(/[^a-z0-9-]/gi, '').toLowerCase() || 'rhyme';
    const title = token.title || `${token.rhyme_key || highlight.line_rhyme_key || ''} rhyme family`;
    return `<span class="rh-token rh-fam-${cls || 1} rh-role-${role}" title="${escapeHtml(title)}" data-rhyme-key="${escapeHtml(token.rhyme_key || '')}" data-word="${escapeHtml(token.text || '')}" data-line="${escapeHtml(highlight.line_number || token.line_number || '')}">${text}</span>`;
  }).join('');
}

function rhymeLineMetaHtml(highlight = {}) {
  if (!highlight || !highlight.line_rhyme_key) return '';
  const cls = Number(highlight.line_rhyme_class || 1);
  const familyLines = highlight.line_family_lines || [];
  const repeated = Number(highlight.line_family_count || 0) > 1;
  return `
    <div class="rhyme-meta-row">
      <span class="rhyme-family-chip rh-fam-${cls}" data-rhyme-key="${escapeHtml(highlight.line_rhyme_key)}"><b>${escapeHtml(highlight.line_rhyme_letter || '—')}</b> /${escapeHtml(highlight.line_rhyme_key)}/</span>
      <span>${escapeHtml(highlight.end_word || 'end')} landing</span>
      <span>${escapeHtml(highlight.highlighted_word_count || 0)} highlighted word(s)</span>
      ${repeated ? `<span>also lines ${familyLines.slice(0, 8).map((n) => escapeHtml(n)).join(', ')}</span>` : '<span>single-use ending</span>'}
    </div>
  `;
}

function rhymeLegendHtml(rhymeData = {}, limit = 18) {
  const families = rhymeData.families || [];
  if (!families.length) return '<p class="muted tiny-text">No rhyme families detected yet.</p>';
  const visible = families.slice(0, limit);
  return `
    <section class="rhyme-legend-panel">
      <div class="rhyme-legend-head">
        <strong>Rhyme highlight key</strong>
        <span>${escapeHtml(rhymeData.summary?.unique_families || families.length)} families · ${escapeHtml(rhymeData.summary?.repeated_families || 0)} repeated</span>
      </div>
      <p class="muted tiny-text">${escapeHtml(rhymeData.summary?.instruction || 'Matching colors show shared rhyme families.')}</p>
      <div class="rhyme-legend">
        ${visible.map((family) => `
          <button type="button" class="rhyme-family-chip rh-fam-${Number(family.class || 1)}" data-rhyme-key="${escapeHtml(family.key)}" title="Lines ${(family.line_numbers || []).join(', ')}">
            <b>${escapeHtml(family.letter || '—')}</b>
            <span>/${escapeHtml(family.key || '—')}/</span>
            <em>${escapeHtml((family.end_words || []).slice(0, 5).join(', ') || '—')}</em>
            <small>${escapeHtml(family.count || 0)} line${Number(family.count) === 1 ? '' : 's'}</small>
          </button>
        `).join('')}
      </div>
    </section>
  `;
}

function rhymeScoreClass(score) {
  const value = Number(score || 0);
  if (value >= 82) return 'hot';
  if (value >= 66) return 'warm';
  if (value >= 48) return 'cool';
  return 'soft';
}

function advancedRhymeOptionsHtml(rows = [], limit = 8) {
  if (!rows || !rows.length) return '<p class="muted tiny-text">No scored options in this category yet.</p>';
  return `
    <div class="advanced-rhyme-options">
      ${rows.slice(0, limit).map((row) => `
        <button type="button" class="advanced-rhyme-option insert-chip ${rhymeScoreClass(row.score)}" data-word="${escapeHtml(row.word || row.phrase || '')}" title="${escapeHtml((row.reasons || []).join('; '))}">
          <strong>${escapeHtml(row.word || row.phrase || '—')}</strong>
          <span>${escapeHtml(row.kind || 'rhyme')} · ${escapeHtml(row.score ?? 0)}</span>
          <small>/${escapeHtml(row.rhyme_key || '—')}/ · ${escapeHtml(row.syllables ?? '—')}σ</small>
        </button>
      `).join('')}
    </div>
  `;
}

function rhymeLadderHtml(ladder = []) {
  if (!ladder || !ladder.length) return '';
  return `
    <div class="rhyme-ladder-grid">
      ${ladder.slice(0, 4).map((stage) => `
        <article class="rhyme-ladder-stage">
          <h4>${escapeHtml(stage.stage || 'Rhyme stage')}</h4>
          <p>${escapeHtml(stage.use_when || '')}</p>
          <div class="chips">${chips((stage.options || []).slice(0, 8))}</div>
        </article>
      `).join('')}
    </div>
  `;
}

function advancedRhymeReportHtml(report = {}) {
  if (!report || !report.available) return '<div class="empty-state">Advanced rhyme report is not available for this line yet.</div>';
  const wordReport = report.word_report || {};
  const summary = wordReport.summary || {};
  const power = report.rhyme_power || {};
  const actions = report.actions || [];
  return `
    <section class="advanced-rhyme-card">
      <div class="advanced-rhyme-head">
        <div>
          <p class="eyebrow">Advanced rhyme engine</p>
          <h3>${escapeHtml(report.end_word || summary.target_word || 'landing')} <span>/${escapeHtml(report.rhyme_key || summary.rhyme_key || '—')}/</span></h3>
        </div>
        <div class="rhyme-power ${rhymeScoreClass(power.score)}">
          <strong>${escapeHtml(power.score ?? 0)}%</strong>
          <span>${escapeHtml(power.label || 'rhyme power')}</span>
        </div>
      </div>
      <div class="metric-pills compact">
        <span>${escapeHtml(summary.engine || 'rhyme engine')}</span>
        <span>${escapeHtml(summary.candidate_count ?? 0)} candidates</span>
        <span>best ${escapeHtml(summary.best_score ?? 0)} · ${escapeHtml(summary.best_kind || '—')}</span>
        <span>stress ${escapeHtml(summary.stress_signature || '—')}</span>
        <span>${escapeHtml(report.chain_note || 'chain open')}</span>
      </div>
      ${actions.length ? `<ol class="advanced-action-list">${actions.slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>` : ''}
      <div class="advanced-rhyme-columns">
        <section><h4>Perfect / family</h4>${advancedRhymeOptionsHtml(wordReport.perfect_or_family || [], 8)}</section>
        <section><h4>Slant turns</h4>${advancedRhymeOptionsHtml(wordReport.slant || [], 8)}</section>
        <section><h4>Assonance</h4>${advancedRhymeOptionsHtml(wordReport.assonance || [], 8)}</section>
        <section><h4>Consonance</h4>${advancedRhymeOptionsHtml(wordReport.consonance || [], 8)}</section>
        <section class="wide"><h4>Multi-syllable endings</h4>${advancedRhymeOptionsHtml(wordReport.multi_syllable || [], 10)}</section>
      </div>
      ${rhymeLadderHtml(report.rhyme_ladder || wordReport.rhyme_ladder || [])}
    </section>
  `;
}

function rhymeLabSummaryHtml(lab = {}) {
  if (!lab || !lab.available) return '';
  const summary = lab.summary || {};
  const recs = lab.scheme?.recommendations || [];
  const ladders = lab.family_ladders || [];
  return `
    <section class="rhyme-lab-summary">
      <div class="beat-summary-grid compact">
        <article class="metric-card"><span>Rhyme power</span><strong>${escapeHtml(summary.avg_rhyme_power ?? 0)}%</strong><small>avg line landing</small></article>
        <article class="metric-card"><span>Families</span><strong>${escapeHtml(summary.unique_rhyme_families ?? 0)}</strong><small>${escapeHtml(summary.repeated_rhyme_families ?? 0)} repeated</small></article>
        <article class="metric-card"><span>Rhyme entropy</span><strong>${escapeHtml(summary.rhyme_entropy_bits ?? 0)}</strong><small>${escapeHtml(summary.rhyme_perplexity ?? 0)} perplexity</small></article>
        <article class="metric-card"><span>Corpus overlap</span><strong>${escapeHtml(summary.corpus_rhyme_key_overlap_pct ?? 0)}%</strong><small>rhyme-key DNA</small></article>
      </div>
      ${recs.length ? `<div class="advanced-scheme-recs">${recs.slice(0, 4).map((rec) => `
        <article>
          <strong>${escapeHtml(rec.title || 'Scheme note')}</strong>
          <p>${escapeHtml(rec.detail || '')}</p>
          ${(rec.line_numbers || []).length ? `<small>Lines ${(rec.line_numbers || []).slice(0, 10).map((n) => escapeHtml(n)).join(', ')}</small>` : ''}
        </article>
      `).join('')}</div>` : ''}
      ${ladders.length ? `<details><summary>Family ladders for the draft</summary><div class="family-ladder-list">${ladders.slice(0, 5).map((ladder) => `
        <article>
          <h4>/${escapeHtml(ladder.rhyme_key || '—')}/ · ${escapeHtml(ladder.count || 0)} line(s)</h4>
          <p class="muted tiny-text">Current: ${(ladder.current_end_words || []).map((w) => escapeHtml(w)).join(', ') || '—'}</p>
          <div class="chips">${chips([...(ladder.direct_options || []), ...(ladder.slant_options || []), ...(ladder.multi_syllable_options || [])].slice(0, 14))}</div>
        </article>
      `).join('')}</div></details>` : ''}
    </section>
  `;
}

function advancedRhymeLineTableHtml(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No line-level rhyme repairs yet.</p>';
  return `
    <div class="table-wrap compact-table"><table>
      <thead><tr><th>Line</th><th>Landing</th><th>Power</th><th>Actions</th><th>Fast options</th></tr></thead>
      <tbody>${rows.slice(0, 80).map((row) => {
        const lists = row.word_lists || {};
        const options = [...(lists.end_rhymes || []), ...(lists.slant_rhymes || []), ...(lists.multi_syllable_endings || [])].slice(0, 8);
        return `
          <tr>
            <td><button type="button" class="line-jump ghost tiny" data-line="${escapeHtml(row.line_number)}">${escapeHtml(row.line_number)}</button></td>
            <td><strong>${escapeHtml(row.end_word || '')}</strong><small> /${escapeHtml(row.rhyme_key || '—')}/</small></td>
            <td>${escapeHtml(row.rhyme_power?.score ?? 0)}%</td>
            <td>${escapeHtml((row.actions || []).slice(0, 2).join(' '))}</td>
            <td><div class="chips mini-chips">${chips(options)}</div></td>
          </tr>
        `;
      }).join('')}</tbody>
    </table></div>
  `;
}

function renderAdvancedRhymePanel(data = {}) {
  if (!advancedRhymePanelEl) return;
  if (!data || !data.available) {
    advancedRhymePanelEl.className = 'empty-state';
    advancedRhymePanelEl.textContent = data?.error || 'Run the advanced rhyme pass to populate this panel.';
    return;
  }
  advancedRhymePanelEl.className = 'advanced-rhyme-panel';
  if (data.report_type === 'advanced_rhyme_suggestion_lab') {
    advancedRhymePanelEl.innerHTML = `
      ${rhymeLabSummaryHtml(data)}
      <h3>Active-line deep report</h3>
      ${advancedRhymeReportHtml(data.active_report || {})}
      <h3>Line-by-line repair table</h3>
      ${advancedRhymeLineTableHtml(data.line_reports || [])}
    `;
  } else {
    const wordWrapper = {
      available: true,
      end_word: data.target_word,
      rhyme_key: data.summary?.rhyme_key,
      rhyme_power: { score: data.summary?.best_score || 0, label: 'word target' },
      actions: data.blueprints || [],
      word_report: data,
      rhyme_ladder: data.rhyme_ladder || [],
    };
    advancedRhymePanelEl.innerHTML = advancedRhymeReportHtml(wordWrapper);
  }
}

async function runAdvancedRhymeLab() {
  const lyrics = editor.value;
  if (countWords(lyrics) < 3) {
    renderAdvancedRhymePanel({ available: false, error: 'Paste at least three words before running the rhyme lab.' });
    return;
  }
  switchTab('rhyme');
  advancedRhymePanelEl.className = 'empty-state';
  advancedRhymePanelEl.textContent = 'Running advanced rhyme analysis...';
  try {
    const response = await fetch('/api/rhyme/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lyrics, coach_mode: coachMode.value, active_line: state.activeLine }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Rhyme lab failed.');
    state.rhymeLab = payload;
    renderAdvancedRhymePanel(payload);
    jsonBlock.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    renderAdvancedRhymePanel({ available: false, error: error.message });
  }
}

async function analyzeTargetRhyme() {
  let word = (rhymeTargetWordEl?.value || '').trim();
  if (!word && state.latest?.active_fix?.metrics?.end_word) word = state.latest.active_fix.metrics.end_word;
  if (!word) {
    renderAdvancedRhymePanel({ available: false, error: 'Enter a target word or put your cursor on a lyric line.' });
    return;
  }
  switchTab('rhyme');
  advancedRhymePanelEl.className = 'empty-state';
  advancedRhymePanelEl.textContent = `Analyzing rhymes for “${word}”...`;
  try {
    const response = await fetch('/api/rhyme/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word, line_text: state.latest?.active_fix?.text || '', coach_mode: coachMode.value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Word rhyme analysis failed.');
    state.rhymeLab = payload;
    renderAdvancedRhymePanel(payload);
    jsonBlock.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    renderAdvancedRhymePanel({ available: false, error: error.message });
  }
}

async function copyRhymeJson() {
  const data = state.rhymeLab || state.latest?.rhyme_lab || {};
  try {
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    if (advancedRhymePanelEl) advancedRhymePanelEl.insertAdjacentHTML('afterbegin', '<div class="fit-callout success">Copied rhyme JSON.</div>');
  } catch (_error) {
    if (jsonBlock) jsonBlock.textContent = JSON.stringify(data, null, 2);
  }
}

function snapshotRhymeLinesHtml(report) {
  const rows = report?.line_breakdown || [];
  if (!rows.length) return '<div class="empty-state">No editable lyric lines found in this snapshot.</div>';
  return rows.map((row) => `
    <div class="snapshot-rhyme-line" data-line="${escapeHtml(row.line_number)}">
      <button type="button" class="snapshot-line-no line-jump" data-line="${escapeHtml(row.line_number)}">${escapeHtml(row.line_number)}</button>
      <div class="snapshot-line-body">
        <div class="rhyme-line">${rhymeHighlightedLineHtml(row.rhyme_highlight, row.text || '')}</div>
        ${rhymeLineMetaHtml(row.rhyme_highlight)}
      </div>
    </div>
  `).join('');
}

function patchButtons(fix) {
  const patches = fix.patches || [];
  if (!patches.length) return '<p class="muted tiny-text">No direct patch generated for this line.</p>';
  return patches.map((patch, index) => `
    <button type="button" class="patch-button apply-patch" data-line="${fix.line_number}" data-patch="${index}">
      <strong>${escapeHtml(patch.label)}</strong>
      <span>${escapeHtml(patch.why)}</span>
    </button>
  `).join('');
}

function variantButtons(fix) {
  const variants = fix.rewrite_variants || [];
  if (!variants.length) return '';
  return variants.map((variant, index) => `
    <article class="variant-card">
      <div>
        <strong>${escapeHtml(variant.name)}</strong>
        <small>${escapeHtml(variant.syllables)} syllables</small>
      </div>
      <p>${escapeHtml(variant.text).replaceAll('\n', '<br>')}</p>
      <button type="button" class="ghost tiny apply-variant" data-line="${fix.line_number}" data-variant="${index}">Use this</button>
    </article>
  `).join('');
}

function activeFixHtml(fix) {
  if (!fix) return '<div class="empty-state">No active lyric line found.</div>';
  const priority = priorityClass(fix.priority);
  const metrics = fix.metrics || {};
  const meter = fix.meter || {};
  const meterSummary = meter.summary || {};
  const physics = fix.physics || {};
  const barScore = fix.bar_score || {};
  const beat = fix.beat_guidance || {};
  const beatLine = beat.assigned_bars ? `<span>Bars ${escapeHtml(beat.assigned_bars)} · ${escapeHtml(beat.time_window || '')}</span>` : '<span>No beat map for this line</span>';
  return `
    <article class="active-fix-card ${priority}">
      <div class="fix-head">
        <div>
          <small>Line ${fix.line_number} · ${escapeHtml(fix.operation_label)}</small>
          <h3>${rhymeHighlightedLineHtml(fix.rhyme_highlight, fix.text)}</h3>
        </div>
        <b>${fix.severity}</b>
      </div>
      ${rhymeLineMetaHtml(fix.rhyme_highlight)}
      <p class="diagnosis">${escapeHtml(fix.diagnosis)}</p>
      ${comparisonGuidanceHtml(fix.comparison_guidance)}
      <div class="metric-pills">
        <span>${escapeHtml(fix.syllable_status)}</span>
        ${barScore.available !== false && barScore.overall !== undefined ? `<span>bar score ${escapeHtml(barScore.overall)}%</span>` : ''}
        <span>${escapeHtml(metrics.syllables ?? 0)} syllables</span>
        <span>rhyme: ${escapeHtml(metrics.rhyme_key || '—')}</span>
        ${meter.available ? `<span>${escapeHtml(meterSummary.dominant_meter || 'mixed meter')}</span><span>${escapeHtml(meterSummary.stress_ratio_pct ?? 0)}% stress</span>` : ''}
        ${physics.available ? `<span>F ${escapeHtml(physics.force_pct ?? 0)}%</span><span>τ ${escapeHtml(physics.torsion_pct ?? 0)}%</span><span>Ω ${escapeHtml(physics.spin_pct ?? 0)}%</span>` : ''}
        ${beatLine}
      </div>
      ${meter.available ? `<h4>Meter / stress</h4>${meterMiniHtml(meter)}` : ''}
      ${physics.available ? `<h4>Scansion physics</h4>${physicsMiniHtml(physics)}` : ''}
      <div class="moves-list">
        ${(fix.specific_moves || []).slice(0, 5).map((move) => `<p>${escapeHtml(move)}</p>`).join('')}
      </div>
      <h4>Applyable patches</h4>
      <div class="patch-grid">${patchButtons(fix)}</div>
      <h4>Rewrite options</h4>
      <div class="variants">${variantButtons(fix)}</div>
      <h4>Possible words</h4>
      <div class="word-bank-grid">${wordBankHtml(fix.word_banks)}</div>
    </article>
  `;
}

function lineCardHtml(fix) {
  const priority = priorityClass(fix.priority);
  const text = `${fix.text} ${(fix.issues || []).map((i) => i.message).join(' ')} ${Object.values(fix.word_banks || {}).flat().join(' ')}`.toLowerCase();
  const beat = fix.beat_guidance || {};
  const meter = fix.meter || {};
  const meterSummary = meter.summary || {};
  const physics = fix.physics || {};
  const beatBadge = beat.assigned_bars ? `<span class="badge beat">bars ${escapeHtml(beat.assigned_bars)}</span>` : '';
  return `
    <article class="line-card ${priority}" data-search="${escapeHtml(text)}" data-line="${fix.line_number}">
      <div class="line-card-head">
        <button type="button" class="line-jump" data-line="${fix.line_number}">Line ${fix.line_number}</button>
        <div class="badges">
          <span class="badge ${priority}">${escapeHtml(fix.priority)}</span>
          <span class="badge">${escapeHtml(fix.operation_label)}</span>
          ${meter.available ? `<span class="badge meter">${escapeHtml(meterSummary.dominant_meter || 'meter')}</span>` : ''}
          ${physics.available ? `<span class="badge physics">F${escapeHtml(physics.force_pct ?? 0)} τ${escapeHtml(physics.torsion_pct ?? 0)}</span>` : ''}
          ${beatBadge}
        </div>
      </div>
      <blockquote>${rhymeHighlightedLineHtml(fix.rhyme_highlight, fix.text)}</blockquote>
      ${rhymeLineMetaHtml(fix.rhyme_highlight)}
      <p>${escapeHtml(fix.diagnosis)}</p>
      ${meter.available ? `<code class="meter-code mini">${escapeHtml(meter.pattern?.glyphs || '')}</code>` : ''}
      ${physics.available ? `<code class="meter-code mini physics-code">F ${escapeHtml(physics.force_pct ?? 0)}% · τ ${escapeHtml(physics.torsion_pct ?? 0)}% · Ω ${escapeHtml(physics.spin_pct ?? 0)}% · ΔC ${escapeHtml(physics.cadence_delta?.delta_syllables ?? 0)}</code>` : ''}
      ${comparisonGuidanceHtml(fix.comparison_guidance, true)}
      <div class="card-actions">
        ${(fix.patches || []).slice(0, 2).map((patch, index) => `
          <button type="button" class="ghost tiny apply-patch" data-line="${fix.line_number}" data-patch="${index}">${escapeHtml(patch.label)}</button>
        `).join('')}
        <button type="button" class="ghost tiny inspect-line" data-line="${fix.line_number}">Inspect</button>
      </div>
    </article>
  `;
}

function renderScore(result) {
  const score = result.editor_score || {};
  const rapScore = result.rap_score || result.score_report || {};
  scoreRowEl.innerHTML = `
    <article class="metric-card score"><span>System score</span><strong>${rapScore.overall ?? score.overall ?? 0}%</strong><small>${escapeHtml(rapScore.grade?.letter || '')} ${escapeHtml(rapScore.grade?.label || 'whole rap')}</small></article>
    <article class="metric-card"><span>Editor score</span><strong>${score.overall ?? 0}%</strong><small>style + beat + fix load</small></article>
    <article class="metric-card"><span>Style match</span><strong>${score.style_match ?? 0}%</strong><small>corpus DNA</small></article>
    <article class="metric-card"><span>Beat fit</span><strong>${score.beat_fit ?? 0}%</strong><small>${result.beat_alignment?.available ? 'uploaded beat' : 'no beat loaded'}</small></article>
    <article class="metric-card"><span>Closest ref</span><strong>${escapeHtml(result.comparison?.best_match?.score ?? 0)}%</strong><small>${escapeHtml(result.comparison?.best_match?.name || 'no reference')}</small></article>
    <article class="metric-card"><span>High fixes</span><strong>${score.critical_or_high_cards ?? 0}</strong><small>critical/high cards</small></article>
  `;
}

function renderActions(result) {
  const actions = result.editor_actions || [];
  actionsEl.innerHTML = actions.map((action) => `
    <article class="action-card">
      <strong>${escapeHtml(action.title)}</strong>
      <p>${escapeHtml(action.detail)}</p>
      ${(action.line_numbers || []).length ? `<small>Lines: ${(action.line_numbers || []).map((n) => `<button type="button" class="line-link line-jump" data-line="${n}">${n}</button>`).join(' ')}</small>` : ''}
    </article>
  `).join('');
}

function renderFixQueue(result) {
  const list = result.fix_queue || [];
  if (!list.length) {
    fixQueueEl.className = 'line-list empty-state';
    fixQueueEl.textContent = 'No line suggestions yet.';
    return;
  }
  fixQueueEl.className = 'line-list';
  fixQueueEl.innerHTML = `<div class="live-rhyme-legend">${rhymeLegendHtml(result.rhyme_highlights)}</div>` + list.map(lineCardHtml).join('');
}


function attemptsHtml(attempts = []) {
  if (!attempts.length) return '<span class="muted">No decoder attempts reported.</span>';
  return `<div class="diagnostic-attempts">${attempts.map((attempt) => `
    <div class="diagnostic-attempt ${attempt.ok ? 'ok' : 'bad'}">
      <strong>${escapeHtml(attempt.backend || 'backend')}</strong>
      <span>${attempt.ok ? 'OK' : 'failed'}</span>
      <small>${escapeHtml(attempt.message || '')}</small>
    </div>
  `).join('')}</div>`;
}

function renderBeatDiagnostics(data = {}) {
  if (!beatDiagnosticsEl) return;
  const status = data.backend_status || data;
  const diagnostics = data.audio_diagnostics || data;
  const attempts = diagnostics.attempts || diagnostics?.audio_diagnostics?.attempts || [];
  const ffmpeg = status.ffmpeg || {};
  const librosa = status.librosa || {};
  const soundfile = status.soundfile || {};
  const warnings = diagnostics.warnings || [];
  beatDiagnosticsEl.className = 'diagnostic-panel';
  beatDiagnosticsEl.innerHTML = `
    <div class="beat-summary-grid compact-grid">
      <article class="metric-card"><span>Selected decoder</span><strong>${escapeHtml(diagnostics.backend || diagnostics.selected_backend || '—')}</strong><small>${escapeHtml(diagnostics.sample_rate || '')} Hz</small></article>
      <article class="metric-card"><span>librosa</span><strong>${librosa.available ? 'OK' : 'NO'}</strong><small>${escapeHtml(librosa.version || librosa.error || '')}</small></article>
      <article class="metric-card"><span>soundfile</span><strong>${soundfile.available ? 'OK' : 'NO'}</strong><small>${escapeHtml(soundfile.version || soundfile.error || '')}</small></article>
      <article class="metric-card"><span>ffmpeg</span><strong>${ffmpeg.available ? 'OK' : 'NO'}</strong><small>${escapeHtml(ffmpeg.path || ffmpeg.error || 'not found')}</small></article>
    </div>
    ${warnings.length ? `<div class="fit-callout muted">${warnings.map(escapeHtml).join('<br>')}</div>` : ''}
    ${attemptsHtml(attempts)}
  `;
}

async function runBeatDiagnostics() {
  if (!beatDiagnosticsEl) return;
  beatDiagnosticsEl.className = 'diagnostic-panel empty-state';
  beatDiagnosticsEl.textContent = 'Checking server audio decoder stack...';
  try {
    const response = await fetch('/api/beat/diagnostics');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Beat diagnostics failed.');
    renderBeatDiagnostics(payload);
  } catch (error) {
    beatDiagnosticsEl.className = 'diagnostic-panel empty-state error-box';
    beatDiagnosticsEl.textContent = error.message;
  }
}


function renderUploadedBeatPanel(beat = {}) {
  if (!beatPanelEl) return;
  if (!beat.available) {
    beatPanelEl.className = 'empty-state error-box';
    beatPanelEl.textContent = beat.error || 'Beat analysis failed.';
    return;
  }
  const energyBars = (beat.energy_bars || []).slice(0, 96).map((bar) => `
    <div class="energy-bar ${escapeHtml(bar.label)}" style="height:${Math.max(8, Number(bar.energy || 0))}%" title="Bar ${bar.bar}: ${bar.energy}%"></div>
  `).join('');
  const windows = (beat.four_bar_windows || []).slice(0, 10).map((row) => `
    <tr><td>${escapeHtml(row.bars)}</td><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.energy)}%</td><td>${escapeHtml(row.time)}</td></tr>
  `).join('');
  const sections = (beat.section_suggestions || []).slice(0, 5).map((item) => `
    <li><strong>${escapeHtml(item.section)}</strong> · ${escapeHtml(item.bars)} · ${escapeHtml(item.reason || '')}</li>
  `).join('');
  beatPanelEl.className = '';
  beatPanelEl.innerHTML = `
    <div class="beat-summary-grid">
      <article class="metric-card"><span>Detected BPM</span><strong>${escapeHtml(beat.detected_bpm)}</strong><small>${escapeHtml(beat.beat_stability)}% stability</small></article>
      <article class="metric-card"><span>Rap grid</span><strong>${escapeHtml(beat.rap_grid_bpm)}</strong><small>${escapeHtml(beat.bar_duration_seconds)} sec/bar</small></article>
      <article class="metric-card"><span>Beat bars</span><strong>${escapeHtml(beat.estimated_bar_count)}</strong><small>${escapeHtml(beat.duration_label)}</small></article>
      <article class="metric-card"><span>Decoder</span><strong>${escapeHtml(beat.load_method || 'unknown')}</strong><small>${escapeHtml(beat.beat_method || '')}</small></article>
    </div>
    <div class="fit-callout muted">${escapeHtml(beat.grid_note || 'Beat grid ready. Add lyrics or refresh live analysis for line-by-line bar advice.')}</div>
    <div class="energy-map">${energyBars}</div>
    ${sections ? `<ul class="section-list">${sections}</ul>` : ''}
    ${windows ? `<div class="table-wrap"><table><thead><tr><th>Bars</th><th>Zone</th><th>Energy</th><th>Time</th></tr></thead><tbody>${windows}</tbody></table></div>` : ''}
  `;
}

function renderBeatPanel(result) {
  const beat = result.beat_analysis || {};
  const alignment = result.beat_alignment || {};
  if (!beat.available || !alignment.available) {
    beatPanelEl.className = 'empty-state';
    beatPanelEl.textContent = 'Upload a beat to unlock bar-by-bar structure coaching.';
    return;
  }
  const energyBars = (beat.energy_bars || []).slice(0, 64).map((bar) => `
    <div class="energy-bar ${escapeHtml(bar.label)}" style="height:${Math.max(8, Number(bar.energy || 0))}%" title="Bar ${bar.bar}: ${bar.energy}%"></div>
  `).join('');
  const perLine = (alignment.per_line || []).slice(0, 24).map((row) => `
    <tr>
      <td>${row.line_number}</td>
      <td>${escapeHtml(row.assigned_bars)}</td>
      <td>${escapeHtml(row.density_label)}</td>
      <td>${escapeHtml(row.syllables)} / ${escapeHtml((row.target_syllables_per_bar || []).join('-'))}</td>
      <td>${escapeHtml(row.time_window)}</td>
    </tr>
  `).join('');
  beatPanelEl.className = '';
  beatPanelEl.innerHTML = `
    <div class="beat-summary-grid">
      <article class="metric-card"><span>Detected BPM</span><strong>${escapeHtml(beat.detected_bpm)}</strong><small>${escapeHtml(beat.beat_stability)}% stability</small></article>
      <article class="metric-card"><span>Rap grid</span><strong>${escapeHtml(beat.rap_grid_bpm)}</strong><small>${escapeHtml(beat.bar_duration_seconds)} sec/bar</small></article>
      <article class="metric-card"><span>Beat bars</span><strong>${escapeHtml(beat.estimated_bar_count)}</strong><small>${escapeHtml(beat.duration_label)}</small></article>
      <article class="metric-card"><span>Lyrics need</span><strong>${escapeHtml(alignment.bars_needed_by_lyrics)}</strong><small>${escapeHtml(alignment.recommended_pocket)} pocket</small></article>
    </div>
    <div class="fit-callout">${escapeHtml(alignment.fit_status || '')}</div>
    <div class="energy-map">${energyBars}</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Line</th><th>Bars</th><th>Density</th><th>Syllables</th><th>Time</th></tr></thead>
        <tbody>${perLine}</tbody>
      </table>
    </div>
  `;
}

function renderRhymePanel(result) {
  const fix = result.active_fix;
  if (!fix) {
    rhymePanelEl.className = 'empty-state';
    rhymePanelEl.textContent = 'Select a line or wait for live analysis.';
    return;
  }
  const rhymeLab = result.rhyme_lab || {};
  const activeAdvanced = fix.advanced_rhyme || rhymeLab.active_report || {};
  rhymePanelEl.className = '';
  rhymePanelEl.innerHTML = `
    ${rhymeLegendHtml(result.rhyme_highlights, 14)}
    ${rhymeLabSummaryHtml(rhymeLab)}
    <div class="section-head compact mini-head">
      <div>
        <p class="eyebrow">Active rhyme line · line ${fix.line_number}</p>
        <h3 class="rhyme-line">${rhymeHighlightedLineHtml(fix.rhyme_highlight, fix.text)}</h3>
        ${rhymeLineMetaHtml(fix.rhyme_highlight)}
      </div>
    </div>
    ${advancedRhymeReportHtml(activeAdvanced)}
    <details open class="rhyme-word-bank-details">
      <summary>Rhyme word banks</summary>
      <div class="word-bank-grid wide">${wordBankHtml(fix.word_banks)}</div>
    </details>
  `;
  if (result.rhyme_lab && advancedRhymePanelEl) {
    state.rhymeLab = result.rhyme_lab;
    renderAdvancedRhymePanel(result.rhyme_lab);
  }
}

function switchTab(target) {
  $$('.tab').forEach((item) => item.classList.toggle('active', item.dataset.tab === target));
  $$('.tab-panel').forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${target}`));
}


function comparisonGuidanceHtml(guidance = {}, compact = false) {
  if (!guidance || !guidance.available) return '';
  const moves = guidance.benchmark_moves || [];
  return `
    <div class="comparison-guidance ${compact ? 'compact' : ''}">
      <strong>${escapeHtml(guidance.reference_name || 'Reference')} · ${escapeHtml(guidance.reference_score ?? 0)}%</strong>
      <p>${escapeHtml(guidance.note || '')}</p>
      ${compact ? '' : `<small>${escapeHtml(guidance.rhyme_note || '')}</small>`}
      ${!compact && moves.length ? `<ul>${moves.slice(0, 3).map((move) => `<li>${escapeHtml(move)}</li>`).join('')}</ul>` : ''}
    </div>
  `;
}

function comparisonMiniHtml(comparison = {}) {
  if (!comparison || !comparison.available) return '<div class="empty-state">No rapper benchmark comparison available.</div>';
  const best = comparison.best_match || {};
  const recs = comparison.recommendations || [];
  return `
    <article class="comparison-mini-card">
      <div>
        <span>Closest rapper benchmark</span>
        <strong>${escapeHtml(best.name || '—')} · ${escapeHtml(best.score ?? 0)}%</strong>
        <small>${escapeHtml(comparison.interpretation || '')}</small>
      </div>
      <ol>${recs.slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </article>
  `;
}

function comparisonDeltaRows(rows = []) {
  if (!rows.length) return '';
  return rows.slice(0, 6).map((row) => {
    const delta = Number(row.delta || 0);
    const sign = delta > 0 ? '+' : '';
    return `
      <div class="comparison-delta-row">
        <span>${escapeHtml(row.label || row.key)}</span>
        <strong>${escapeHtml(row.input)} / ${escapeHtml(row.reference)}</strong>
        <em>${sign}${escapeHtml(row.delta)} ${escapeHtml(row.unit || '')}</em>
      </div>
    `;
  }).join('');
}

function comparisonProfileCard(profile = {}, index = 0) {
  const comps = profile.components || {};
  const topKeys = (profile.top_rhyme_keys || []).slice(0, 6).map((row) => `/${escapeHtml(row.key)}/`).join(' ');
  return `
    <article class="comparison-profile-card ${index === 0 ? 'best' : ''}">
      <div class="comparison-card-head">
        <div>
          <small>${index === 0 ? 'Closest reference' : 'Reference profile'}</small>
          <h3>${escapeHtml(profile.name || 'Reference')}</h3>
        </div>
        <strong>${escapeHtml(profile.score ?? 0)}%</strong>
      </div>
      <p class="muted tiny-text">${escapeHtml((profile.notes || []).join(' · '))}</p>
      <div class="comparison-component-grid">
        <span>Cadence ${escapeHtml(comps.cadence_distribution_fit ?? 0)}%</span>
        <span>Internal ${escapeHtml(comps.internal_rhyme_fit ?? 0)}%</span>
        <span>Rhyme entropy ${escapeHtml(comps.rhyme_entropy_fit ?? 0)}%</span>
        <span>Rhyme overlap ${escapeHtml(comps.rhyme_key_overlap ?? 0)}%</span>
      </div>
      <div class="comparison-deltas">${comparisonDeltaRows(profile.deltas || [])}</div>
      ${topKeys ? `<p class="muted tiny-text">Top reference rhyme keys: ${topKeys}</p>` : ''}
      <ol>${(profile.advice || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </article>
  `;
}

function renderComparisonPanel(comparison = {}) {
  if (!comparisonPanelEl) return;
  state.comparisonReport = comparison || null;
  if (!comparison || !comparison.available) {
    comparisonPanelEl.className = 'comparison-output empty-state';
    comparisonPanelEl.textContent = comparison?.message || 'Generate a static snapshot or live analysis to populate rapper benchmark comparisons.';
    return;
  }
  const input = comparison.input_signature || {};
  comparisonPanelEl.className = 'comparison-output';
  comparisonPanelEl.innerHTML = `
    <div class="comparison-summary-grid">
      <article class="metric-card score"><span>Best reference</span><strong>${escapeHtml(comparison.best_match?.score ?? 0)}%</strong><small>${escapeHtml(comparison.best_match?.name || '—')}</small></article>
      <article class="metric-card"><span>Input avg syll</span><strong>${escapeHtml(input.avg_syllables ?? 0)}</strong><small>${escapeHtml(input.median_syllables ?? 0)} median</small></article>
      <article class="metric-card"><span>Input rhyme entropy</span><strong>${escapeHtml(input.rhyme_entropy_bits ?? 0)}</strong><small>${escapeHtml(input.rhyme_perplexity ?? 0)} perplexity</small></article>
      <article class="metric-card"><span>Internal-rhyme lines</span><strong>${escapeHtml(input.internal_rhyme_line_pct ?? 0)}%</strong><small>draft density</small></article>
    </div>
    <div class="fit-callout">${escapeHtml(comparison.interpretation || '')}</div>
    <div class="comparison-recommendations">
      <h3>What to change first</h3>
      <ol>${(comparison.recommendations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </div>
    <div class="comparison-card-grid">${(comparison.closest_profiles || []).slice(0, 6).map(comparisonProfileCard).join('')}</div>
    <p class="muted tiny-text">Policy: ${escapeHtml(comparison.metadata?.copyright_handling || 'derived_profile_only_no_raw_lyrics')}</p>
  `;
}

function staticMetricCards(report) {
  const summary = report.summary || {};
  const counts = report.overview?.counts || {};
  const theory = report.information_theory?.overview || {};
  const meter = report.meter_report?.summary || {};
  const physics = report.physics_report?.summary || {};
  const systemScore = report.score_report || {};
  staticMetricsEl.innerHTML = `
    <article class="metric-card score"><span>System score</span><strong>${systemScore.overall ?? 0}%</strong><small>${escapeHtml(systemScore.grade?.letter || '')} · ${escapeHtml(systemScore.grade?.label || '')}</small></article>
    <article class="metric-card"><span>Snapshot lines</span><strong>${summary.lines ?? 0}</strong><small>${summary.words ?? 0} words analyzed</small></article>
    <article class="metric-card"><span>Rhyme entropy</span><strong>${fmt(theory.rhyme_entropy_bits ?? 0)}</strong><small>${fmt(theory.rhyme_perplexity ?? 0)} effective rhyme families</small></article>
    <article class="metric-card"><span>Line surprise</span><strong>${fmt(theory.avg_line_self_information_bits ?? 0)}</strong><small>avg bits per line</small></article>
    <article class="metric-card"><span>Bar entropy</span><strong>${fmt(theory.bar_load_entropy_bits ?? 0)}</strong><small>bar-load variety</small></article>
    <article class="metric-card"><span>Verse entropy</span><strong>${fmt(theory.verse_section_entropy_bits ?? 0)}</strong><small>section-length variety</small></article>
    <article class="metric-card"><span>Stress density</span><strong>${escapeHtml(meter.avg_stress_ratio_pct ?? 0)}%</strong><small>${escapeHtml(meter.stress_consistency_pct ?? 0)}% consistency</small></article>
    <article class="metric-card"><span>Dominant meter</span><strong>${escapeHtml(meter.dominant_meter || 'mixed')}</strong><small>${escapeHtml(meter.dominant_meter_share_pct ?? 0)}% of lines</small></article>
    <article class="metric-card"><span>Force F</span><strong>${escapeHtml(physics.avg_force_pct ?? 0)}%</strong><small>avg accent impact</small></article>
    <article class="metric-card"><span>Torsion τ</span><strong>${escapeHtml(physics.avg_torsion_pct ?? 0)}%</strong><small>avg off-grid twist</small></article>
    <article class="metric-card"><span>Spin Ω</span><strong>${escapeHtml(physics.avg_spin_pct ?? 0)}%</strong><small>avg sound-loop motion</small></article>
    <article class="metric-card"><span>Compression</span><strong>${fmt(theory.compression_ratio ?? 0)}</strong><small>tokens per unique token</small></article>
    <article class="metric-card"><span>Style match</span><strong>${summary.style_match ?? 0}%</strong><small>against corpus DNA</small></article>
    <article class="metric-card"><span>Closest ref</span><strong>${escapeHtml(report.comparison?.best_match?.score ?? 0)}%</strong><small>${escapeHtml(report.comparison?.best_match?.name || 'no reference')}</small></article>
    <article class="metric-card"><span>High priority</span><strong>${counts.critical_or_high ?? 0}</strong><small>critical/high line cards</small></article>
  `;
}

function staticOverviewHtml(report) {
  const overview = report.overview || {};
  const interpretations = report.information_theory?.interpretations || [];
  const meter = report.meter_report || {};
  const physics = report.physics_report || {};
  staticOverviewEl.innerHTML = `
    ${snapshotVisualGuideHtml(report)}
    <article class="static-overview-card">
      <h3>${escapeHtml(overview.headline || 'Static report ready.')}</h3>
      <ol>${(overview.actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join('')}</ol>
      ${interpretations.length ? `
        <h4>Information-theoretic reading</h4>
        <ul>${interpretations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
      ` : ''}
    </article>
    ${meter.available ? `<article class="static-overview-card meter-overview-card"><h3>Meter / stress snapshot</h3><ol>${(meter.recommendations || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></article>` : ''}
    ${physics.available ? `<article class="static-overview-card physics-overview-card"><h3>Scansion physics snapshot</h3><p>${escapeHtml(physics.summary?.reading || '')}</p><ol>${(physics.priority_actions || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></article>` : ''}
    ${report.score_report?.available ? `<article class="static-overview-card score-overview-card"><h3>System-wide score</h3><p>${escapeHtml(report.score_report.headline || '')}</p><ol>${(report.score_report.global_actions || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></article>` : ''}
    ${comparisonMiniHtml(report.comparison)}
    ${rhymeLegendHtml(report.rhyme_highlights)}
  `;
}


function miniDistribution(rows = [], labelKey = 'key') {
  if (!rows.length) return '<p class="muted tiny-text">No distribution data yet.</p>';
  return rows.slice(0, 10).map((row) => `
    <div class="distribution-row">
      <span>${escapeHtml(row[labelKey] ?? row.key ?? '—')}</span>
      <strong>${escapeHtml(row.count ?? '')}</strong>
      <em>${escapeHtml(row.pct ?? '')}% · ${escapeHtml(row.self_information_bits ?? '')} bits</em>
    </div>
  `).join('');
}

function theoryLineRows(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No line information rows yet.</p>';
  return rows.slice(0, 8).map((row) => `
    <article class="theory-line-row">
      <div><strong>Line ${escapeHtml(row.line_number)}</strong><span>${escapeHtml(row.line_self_information_bits)} bits · ${escapeHtml(row.bits_per_word)} bits/word · rhyme surprise ${escapeHtml(row.rhyme_surprise_bits)}</span></div>
      <p>${escapeHtml(row.text || '')}</p>
      <small>${escapeHtml(row.interpretation || '')}</small>
    </article>
  `).join('');
}

function theorySectionTable(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No sections detected.</p>';
  const body = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.label)}</td>
      <td>${escapeHtml(row.line_count)}</td>
      <td>${escapeHtml(row.avg_syllables)}</td>
      <td>${escapeHtml(row.lexical_entropy_bits)}</td>
      <td>${escapeHtml(row.rhyme_entropy_bits)}</td>
      <td>${escapeHtml(row.cadence_entropy_bits)}</td>
      <td>${escapeHtml(row.notes)}</td>
    </tr>
  `).join('');
  return `
    <div class="table-wrap theory-table-wrap">
      <table>
        <thead><tr><th>Section</th><th>Lines</th><th>Avg syll</th><th>Lex bits</th><th>Rhyme bits</th><th>Cadence bits</th><th>Reading</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function theoryBarRows(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No bar rows yet.</p>';
  return rows.slice(0, 12).map((row) => `
    <div class="bar-theory-row">
      <strong>Line ${escapeHtml(row.line_number)}</strong>
      <span>${escapeHtml(row.assigned_bars || '—')}</span>
      <em>${escapeHtml(row.syllables_per_beat)} syll/beat · ${escapeHtml(row.density_label)}</em>
    </div>
  `).join('');
}

function renderInformationTheory(report) {
  const theory = report.information_theory || {};
  const overview = theory.overview || {};
  const rhymes = theory.rhymes || {};
  const lines = theory.lines || {};
  const bars = theory.bars || {};
  const verses = theory.verses || {};
  const html = `
    <div class="theory-grid">
      <article class="theory-card spotlight">
        <span>Token entropy</span>
        <strong>${fmt(overview.token_entropy_bits)}</strong>
        <small>${fmt(overview.token_perplexity)} effective content-word choices</small>
      </article>
      <article class="theory-card">
        <span>Rhyme entropy</span>
        <strong>${fmt(rhymes.rhyme_key_entropy_bits)}</strong>
        <small>${fmt(rhymes.rhyme_key_perplexity)} effective rhyme families · ${pctText(rhymes.rhyme_key_normalized_entropy)} normalized</small>
      </article>
      <article class="theory-card">
        <span>Rhyme reuse</span>
        <strong>${pctText(rhymes.rhyme_reuse_ratio_pct)}</strong>
        <small>${fmt(rhymes.unique_rhyme_families)} unique rhyme families</small>
      </article>
      <article class="theory-card">
        <span>Rhyme transitions</span>
        <strong>${fmt(rhymes.transition_entropy_bits)}</strong>
        <small>${fmt(rhymes.transition_perplexity)} effective transitions</small>
      </article>
      <article class="theory-card">
        <span>Line-length entropy</span>
        <strong>${fmt(lines.syllable_entropy_bits)}</strong>
        <small>${fmt(lines.syllable_perplexity)} effective cadence bins</small>
      </article>
      <article class="theory-card">
        <span>Avg line surprise</span>
        <strong>${fmt(overview.avg_line_self_information_bits)}</strong>
        <small>bits per editable line</small>
      </article>
      <article class="theory-card">
        <span>Bar-load entropy</span>
        <strong>${fmt(bars.bar_load_entropy_bits)}</strong>
        <small>${fmt(bars.bar_load_perplexity)} effective bar-density bins</small>
      </article>
      <article class="theory-card">
        <span>Sections</span>
        <strong>${fmt(verses.section_count)}</strong>
        <small>${fmt(verses.verse_count)} verse(s) · ${fmt(verses.hook_count)} hook/chorus section(s)</small>
      </article>
    </div>

    <div class="theory-detail-grid">
      <article class="theory-detail-card">
        <h3>Rhyme-family distribution</h3>
        <p class="muted">High entropy means many endings; low entropy means a few repeated rhyme families dominate.</p>
        ${miniDistribution(rhymes.top_families || [])}
      </article>
      <article class="theory-detail-card">
        <h3>Rhyme transitions</h3>
        <p class="muted">Adjacent-line rhyme moves. Useful for seeing whether the scheme loops or constantly turns.</p>
        ${miniDistribution(rhymes.top_transitions || [])}
      </article>
      <article class="theory-detail-card wide">
        <h3>Most informative lines</h3>
        <p class="muted">These lines carry the most local self-information because they use rarer words and/or rare rhyme landings.</p>
        ${theoryLineRows(lines.most_informative_lines || [])}
      </article>
      <article class="theory-detail-card">
        <h3>Bar-density distribution</h3>
        <p class="muted">${escapeHtml(bars.assumption || '')}</p>
        ${miniDistribution(bars.density_distribution || [])}
      </article>
      <article class="theory-detail-card">
        <h3>Bar pressure rows</h3>
        <p class="muted">Dense/open rows are the first place to adjust bar structure.</p>
        ${theoryBarRows((bars.overloaded_lines || []).concat(bars.open_lines || []))}
      </article>
      <article class="theory-detail-card wide">
        <h3>Verse / section entropy table</h3>
        ${theorySectionTable(verses.section_rows || [])}
      </article>
    </div>
  `;
  if (snapshotTheoryEl) {
    snapshotTheoryEl.className = 'theory-panel';
    snapshotTheoryEl.innerHTML = html;
  }
  if (theoryFullEl) {
    theoryFullEl.className = 'theory-panel';
    theoryFullEl.innerHTML = html;
  }
}


function meterSyllableStripHtml(meter = {}) {
  const units = meter.syllables || [];
  if (!meter.available || !units.length) return '<p class="muted tiny-text">No stress syllables detected.</p>';
  return `
    <div class="meter-syllable-strip" title="●/´ = stressed, ○/˘ = weak">
      ${units.map((unit) => `
        <span class="stress-syll ${unit.stressed ? 'strong' : 'weak'}" title="${escapeHtml(unit.word || '')} · syllable ${escapeHtml(unit.syllable_in_word || '')} · ${unit.stressed ? 'stressed' : 'weak'}">
          <b>${escapeHtml(unit.glyph || (unit.stressed ? '●' : '○'))}</b>
          <em>${escapeHtml(unit.syllable_label || unit.word || '')}</em>
        </span>
      `).join('')}
    </div>
  `;
}

function meterWordScansionHtml(meter = {}) {
  const words = meter.words || [];
  if (!meter.available || !words.length) return '<p class="muted tiny-text">No word stresses detected.</p>';
  return `
    <div class="meter-word-row">
      ${words.map((word) => `
        <span class="meter-word ${word.is_content_stressed ? 'anchor' : word.is_function_word ? 'pickup' : ''}" title="${escapeHtml(word.source || 'heuristic')} · ${escapeHtml(word.syllables || 0)} syllable(s)">
          <strong>${escapeHtml(word.word || '')}</strong>
          <em>${escapeHtml(word.glyphs || '')}</em>
        </span>
      `).join('')}
    </div>
  `;
}

function meterPulseGridHtml(meter = {}) {
  const grid = meter.pulse_grid || {};
  const beats = grid.beats || [];
  if (!grid.available || !beats.length) return '<p class="muted tiny-text">No pulse grid available.</p>';
  return `
    <div class="meter-pulse-card">
      <div class="meter-pulse-grid">
        ${beats.map((beat) => `
          <article>
            <strong>Beat ${escapeHtml(beat.beat)}</strong>
            <span>${escapeHtml(beat.pattern || '—')}</span>
            <small>${escapeHtml(beat.stress_count || 0)} stress / ${escapeHtml(beat.syllable_count || 0)} syll</small>
          </article>
        `).join('')}
      </div>
      <p class="muted tiny-text">${escapeHtml(grid.reading || '')}</p>
    </div>
  `;
}

function meterMiniHtml(meter = {}) {
  if (!meter || !meter.available) return '<p class="muted tiny-text">Meter not available.</p>';
  const summary = meter.summary || {};
  const pattern = meter.pattern || {};
  return `
    <div class="meter-mini">
      <div class="metric-pills">
        <span>${escapeHtml(summary.dominant_meter || 'mixed')}</span>
        <span>${escapeHtml(summary.stress_ratio_pct ?? 0)}% stress density</span>
        <span>${escapeHtml(summary.meter_confidence_pct ?? 0)}% meter confidence</span>
        <span>${escapeHtml(summary.longest_weak_run ?? 0)} longest weak run</span>
        <span>${summary.final_landing_stressed ? 'stressed landing' : 'soft landing'}</span>
      </div>
      <code class="meter-code">${escapeHtml(pattern.glyphs || pattern.scansion || '')}</code>
      ${meterWordScansionHtml(meter)}
    </div>
  `;
}

function sentenceMeterHtml(meter = {}) {
  if (!meter || !meter.available) return '<article class="sentence-detail-card"><h4>Meter / stress</h4><p class="muted">No meter result available.</p></article>';
  const summary = meter.summary || {};
  const pattern = meter.pattern || {};
  const dominant = meter.feet?.dominant || {};
  const suggestions = meter.suggestions || [];
  return `
    <article class="sentence-detail-card meter-card">
      <h4>Sentence meter / stresses</h4>
      <div class="meter-headline">
        <strong>${escapeHtml(summary.dominant_meter || 'mixed meter')}</strong>
        <span>${escapeHtml(summary.stressed_syllables ?? 0)} stressed / ${escapeHtml(summary.syllables ?? 0)} syllables</span>
        <span>${escapeHtml(summary.stress_ratio_pct ?? 0)}% stress density</span>
        <span>${escapeHtml(meter.source || 'heuristic')}</span>
      </div>
      <code class="meter-code">${escapeHtml(pattern.scansion || pattern.glyphs || '')}</code>
      ${meterSyllableStripHtml(meter)}
      ${meterWordScansionHtml(meter)}
      ${meterPulseGridHtml(meter)}
      <div class="meter-foot-note">
        <b>${escapeHtml(dominant.name || 'mixed')}</b>
        <span>${escapeHtml(dominant.pattern || '—')} · ${escapeHtml(dominant.confidence_pct ?? 0)}% confidence · ${escapeHtml(dominant.grouping || 'mixed')} grouping</span>
      </div>
      <ol class="meter-suggestions">${suggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </article>
  `;
}

function meterDistributionHtml(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No meter distribution yet.</p>';
  return rows.slice(0, 10).map((row) => `
    <div class="distribution-row">
      <span>${escapeHtml(row.meter || row.name || row.pattern || 'mixed')}</span>
      <strong>${escapeHtml(row.count ?? '')}</strong>
      <em>${escapeHtml(row.pct ?? '')}%</em>
    </div>
  `).join('');
}

function meterProblemRowsHtml(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No problem rows detected for this category.</p>';
  return rows.slice(0, 8).map((row) => `
    <article class="meter-line-row">
      <div><strong>Line ${escapeHtml(row.line_number)}</strong><span>${escapeHtml(row.dominant_meter || 'mixed')} · ${escapeHtml(row.stress_ratio_pct ?? 0)}% stress · ${escapeHtml(row.syllables ?? 0)} syll</span></div>
      <code>${escapeHtml(row.pattern || '')}</code>
      <p>${escapeHtml(row.text || '')}</p>
      <small>${escapeHtml(row.suggestion || '')}</small>
    </article>
  `).join('');
}

function meterLineRowsHtml(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No meter rows yet.</p>';
  return rows.slice(0, 40).map((row) => `
    <article class="meter-line-row">
      <div>
        <button type="button" class="line-jump" data-line="${escapeHtml(row.line_number)}">Line ${escapeHtml(row.line_number)}</button>
        <span>${escapeHtml(row.dominant_meter || 'mixed')} · ${escapeHtml(row.meter_confidence_pct ?? 0)}% confidence · ${escapeHtml(row.final_landing_stressed ? 'stressed landing' : 'soft landing')}</span>
      </div>
      <code>${escapeHtml(row.pattern || '')}</code>
      <p>${escapeHtml(row.text || '')}</p>
      <small>${escapeHtml(row.suggestion || '')}</small>
    </article>
  `).join('');
}

function renderMeterPanel(report = {}) {
  if (!meterFullEl) return;
  const meter = report.meter_report || report.meter || {};
  if (!meter || !meter.available) {
    meterFullEl.className = 'meter-panel empty-state';
    meterFullEl.textContent = 'Generate a static snapshot or live analysis to populate meter and stress analysis.';
    return;
  }
  const summary = meter.summary || {};
  const problems = meter.problem_rows || {};
  meterFullEl.className = 'meter-panel';
  meterFullEl.innerHTML = `
    <div class="meter-summary-grid">
      <article class="metric-card score"><span>Dominant meter</span><strong>${escapeHtml(summary.dominant_meter || 'mixed')}</strong><small>${escapeHtml(summary.dominant_meter_share_pct ?? 0)}% of lines</small></article>
      <article class="metric-card"><span>Stress density</span><strong>${escapeHtml(summary.avg_stress_ratio_pct ?? 0)}%</strong><small>${escapeHtml(summary.stress_consistency_pct ?? 0)}% consistency</small></article>
      <article class="metric-card"><span>Landing stress</span><strong>${escapeHtml(summary.final_landing_stressed_pct ?? 0)}%</strong><small>line endings carrying stress</small></article>
      <article class="metric-card"><span>Pocket issues</span><strong>${escapeHtml((summary.lines_over_pocket || 0) + (summary.lines_under_pocket || 0))}</strong><small>${escapeHtml(summary.lines_over_pocket || 0)} over · ${escapeHtml(summary.lines_under_pocket || 0)} under</small></article>
    </div>
    <article class="static-overview-card meter-overview-card">
      <h3>Meter/stress reading</h3>
      <ol>${(meter.recommendations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </article>
    <div class="theory-detail-grid meter-detail-grid">
      <article class="theory-detail-card">
        <h3>Meter distribution</h3>
        ${meterDistributionHtml(meter.meter_distribution || [])}
      </article>
      <article class="theory-detail-card">
        <h3>Foot pattern distribution</h3>
        ${meterDistributionHtml((meter.foot_pattern_distribution || []).map((row) => ({...row, meter: `${row.name || 'mixed'} (${row.pattern || '—'})`}))) }
      </article>
      <article class="theory-detail-card wide">
        <h3>Long weak runs</h3>
        ${meterProblemRowsHtml(problems.long_weak_runs || [])}
      </article>
      <article class="theory-detail-card wide">
        <h3>Stress clusters</h3>
        ${meterProblemRowsHtml(problems.stress_clusters || [])}
      </article>
      <article class="theory-detail-card wide">
        <h3>Line-by-line meter map</h3>
        ${meterLineRowsHtml(meter.lines || [])}
      </article>
    </div>
  `;
}



function physicsSymbolLegendHtml(legend = []) {
  if (!legend.length) return '<p class="muted tiny-text">No symbol legend available.</p>';
  return `<div class="physics-symbol-grid">${legend.map((item) => `
    <article class="physics-symbol-card">
      <strong>${escapeHtml(item.symbol || '')}</strong>
      <span>${escapeHtml(item.name || '')}</span>
      <small>${escapeHtml(item.meaning || '')}</small>
    </article>
  `).join('')}</div>`;
}

function physicsMetricCards(report = {}) {
  const summary = report.summary || {};
  return `
    <div class="physics-metric-grid">
      <article class="metric-card score"><span>Average force F</span><strong>${escapeHtml(summary.avg_force_pct ?? 0)}%</strong><small>accent impact</small></article>
      <article class="metric-card"><span>Average torsion τ</span><strong>${escapeHtml(summary.avg_torsion_pct ?? 0)}%</strong><small>off-grid stress twist</small></article>
      <article class="metric-card"><span>Average spin Ω</span><strong>${escapeHtml(summary.avg_spin_pct ?? 0)}%</strong><small>phonetic loop motion</small></article>
      <article class="metric-card"><span>Cadence shifts ΔC</span><strong>${escapeHtml(summary.cadence_shift_count ?? 0)}</strong><small>${escapeHtml(summary.avg_cadence_delta_abs ?? 0)} avg absolute delta</small></article>
      <article class="metric-card"><span>Compression sequences</span><strong>${escapeHtml(summary.compression_sequence_count ?? 0)}</strong><small>long → short release shapes</small></article>
    </div>
  `;
}

function physicsPhaseUnitsHtml(units = [], limit = 32) {
  if (!units.length) return '<p class="muted tiny-text">No syllable phase units available.</p>';
  return `
    <div class="physics-phase-strip">
      ${units.slice(0, limit).map((unit) => `
        <span class="phase-unit ${unit.stressed ? 'stressed' : 'weak'} ${String(unit.theta_slot || '').includes('off') ? 'offgrid' : ''}" title="σ${escapeHtml(unit.sigma)} · θ ${escapeHtml(unit.theta_grid)} · F ${escapeHtml(unit.F)} · τ ${escapeHtml(unit.tau)} · ${escapeHtml(unit.word || '')}">
          <b>${escapeHtml(unit.theta_grid || '')}</b>
          <em>${escapeHtml(unit.glyph || '')}</em>
          <small>${escapeHtml(unit.syllable_label || unit.word || '')}</small>
        </span>
      `).join('')}
    </div>
  `;
}

function physicsMiniHtml(physics = {}) {
  if (!physics || !physics.available) return '<p class="muted tiny-text">Scansion physics unavailable.</p>';
  const delta = physics.cadence_delta || {};
  return `
    <div class="physics-mini-card">
      <div class="metric-pills physics-pills">
        <span>F ${escapeHtml(physics.force_pct ?? 0)}%</span>
        <span>τ ${escapeHtml(physics.torsion_pct ?? 0)}%</span>
        <span>Ω ${escapeHtml(physics.spin_pct ?? 0)}%</span>
        <span>ΔC ${delta.available ? `${escapeHtml(delta.delta_syllables > 0 ? '+' : '')}${escapeHtml(delta.delta_syllables)}` : 'open'}</span>
        <span>γ /${escapeHtml(physics.rhyme_key || '—')}/</span>
        <span>β ${escapeHtml(physics.assigned_bars || '—')}</span>
      </div>
      <p>${escapeHtml(physics.physics_reading || '')}</p>
      ${physicsPhaseUnitsHtml(physics.phase_units || [], 24)}
      <ol>${(physics.actions || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
    </div>
  `;
}

function physicsSequencesHtml(sequences = []) {
  if (!sequences.length) return '<p class="muted tiny-text">No compression sequences detected yet.</p>';
  return sequences.slice(0, 8).map((seq) => `
    <article class="physics-sequence-card">
      <strong>${escapeHtml(seq.label || 'sequence')}</strong>
      <span>Lines ${(seq.line_numbers || []).map(escapeHtml).join(' → ')}</span>
      <code>${(seq.syllable_shape || []).map(escapeHtml).join(' → ')} syllables</code>
      <p>${escapeHtml(seq.reading || '')}</p>
    </article>
  `).join('');
}

function physicsSkeletonPairsHtml(data = {}) {
  const pairs = data.top_pairs || [];
  const notebook = data.notebook_test_pairs || [];
  const pairHtml = pairs.slice(0, 8).map((row) => `
    <article class="skeleton-pair-card">
      <div><strong>Lines ${escapeHtml(row.line_a)} / ${escapeHtml(row.line_b)}</strong><span>${escapeHtml(row.match?.score ?? 0)}% · ${escapeHtml(row.match?.label || '')}</span></div>
      <p>${escapeHtml(row.text_a || '')}</p>
      <p>${escapeHtml(row.text_b || '')}</p>
      <small>${escapeHtml(row.match?.reading || '')}</small>
    </article>
  `).join('') || '<p class="muted tiny-text">No strong skeleton pairs detected yet.</p>';
  const notebookHtml = notebook.slice(0, 4).map((row) => `
    <article class="skeleton-pair-card notebook-test">
      <div><strong>${escapeHtml(row.match?.score ?? 0)}%</strong><span>${escapeHtml(row.match?.label || '')}</span></div>
      <p>${escapeHtml(row.left?.text || '')}</p>
      <p>${escapeHtml(row.right?.text || '')}</p>
      <small>${escapeHtml(row.match?.reading || '')}</small>
    </article>
  `).join('');
  return `
    <div class="skeleton-section">
      <h3>Phonetic skeleton matches</h3>
      <p class="muted">${escapeHtml(data.interpretation || 'Skeleton matching compares consonants, vowels, stress, and rhyme family.')}</p>
      <div class="skeleton-pair-grid">${pairHtml}</div>
      <h4>Notebook test phrase matrix</h4>
      <div class="skeleton-pair-grid compact">${notebookHtml}</div>
    </div>
  `;
}

function physicsLineRowsHtml(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No line physics rows yet.</p>';
  return rows.slice(0, 40).map((row) => {
    const delta = row.cadence_delta || {};
    return `
      <article class="physics-line-row">
        <div>
          <button type="button" class="line-jump" data-line="${escapeHtml(row.line_number)}">Line ${escapeHtml(row.line_number)}</button>
          <span>F ${escapeHtml(row.force_pct ?? 0)}% · τ ${escapeHtml(row.torsion_pct ?? 0)}% · Ω ${escapeHtml(row.spin_pct ?? 0)}% · ${escapeHtml(delta.label || 'opening')}</span>
        </div>
        <blockquote>${escapeHtml(row.text || '')}</blockquote>
        <code>θ ${escapeHtml(row.phase_grid?.unit_grid || '')}</code>
        <code>${escapeHtml(row.phase_grid?.stress_glyphs || '')}</code>
        <small>${escapeHtml(delta.reading || row.physics_reading || '')}</small>
      </article>
    `;
  }).join('');
}

function renderPhysicsPanel(report = {}) {
  if (!physicsFullEl) return;
  const physics = report.physics_report || report.physics || report;
  if (!physics || !physics.available) {
    physicsFullEl.className = 'physics-output empty-state';
    physicsFullEl.textContent = physics?.error || 'Generate a static snapshot or live analysis to populate scansion physics.';
    return;
  }
  state.physicsReport = physics;
  const summary = physics.summary || {};
  const ref = physics.notebook_reference || {};
  physicsFullEl.className = 'physics-output';
  physicsFullEl.innerHTML = `
    ${physicsMetricCards(physics)}
    <article class="static-overview-card physics-overview-card">
      <h3>${escapeHtml(physics.model_name || 'Scansion Physics')}</h3>
      <p>${escapeHtml(summary.reading || '')}</p>
      <ol>${(physics.priority_actions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
      <p class="muted tiny-text">Pipeline: ${(ref.pipeline || []).map(escapeHtml).join(' → ')}</p>
    </article>
    <div class="theory-detail-grid physics-detail-grid">
      <article class="theory-detail-card wide">
        <h3>Symbol system</h3>
        ${physicsSymbolLegendHtml(physics.symbol_legend || [])}
      </article>
      <article class="theory-detail-card wide">
        <h3>Compression / release sequences</h3>
        ${physicsSequencesHtml(physics.compression_sequences || [])}
      </article>
      <article class="theory-detail-card wide">
        ${physicsSkeletonPairsHtml(physics.phonetic_skeletons || {})}
      </article>
      <article class="theory-detail-card wide">
        <h3>Line-by-line phase map</h3>
        ${physicsLineRowsHtml(physics.line_physics || [])}
      </article>
    </div>
  `;
}

function sentencePhysicsHtml(physics = {}) {
  if (!physics || !physics.available) return '';
  const line = physics.line || {};
  return `
    <article class="sentence-detail-card physics-sentence-card">
      <h4>Scansion Physics</h4>
      <p>${escapeHtml(physics.reading || line.physics_reading || '')}</p>
      ${physicsMiniHtml(line)}
      <details>
        <summary>Symbol legend</summary>
        ${physicsSymbolLegendHtml(physics.symbol_legend || [])}
      </details>
    </article>
  `;
}



async function runScansionPhysics() {
  const lyrics = editor.value;
  updateLocalStats();
  if (countWords(lyrics) < 3) {
    switchTab('physics');
    renderPhysicsPanel({ available: false, error: 'Type or import at least three words before running Scansion Physics.' });
    return;
  }
  switchTab('physics');
  if (physicsFullEl) {
    physicsFullEl.className = 'physics-output empty-state';
    physicsFullEl.textContent = 'Running notebook Scansion Physics...';
  }
  try {
    const response = await fetch('/api/physics/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lyrics, coach_mode: coachMode.value, beat_id: state.beatId }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Scansion Physics failed.');
    state.physicsReport = payload;
    renderPhysicsPanel(payload);
    if (jsonBlock) jsonBlock.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    renderPhysicsPanel({ available: false, error: error.message });
  }
}

function staticWordsHtml(words = {}) {
  const groups = [
    ['End rhymes', words.end_rhymes],
    ['Near rhymes', words.near_rhymes],
    ['Slant rhymes', words.slant_rhymes],
    ['Assonance', words.assonance_words],
    ['Consonance', words.consonance_words],
    ['Stress matched', words.stress_matched],
    ['Multi-syllable endings', words.multi_syllable_endings],
    ['Internal echoes', words.internal_echoes],
    ['Signature words', words.signature_words],
    ['Images', words.images],
    ['Verbs', words.verbs],
    ['Punch words', words.punch_words],
    ['Cut words', words.cut_words],
  ];  return groups.map(([title, list]) => `
    <section class="static-bank-group">
      <h4>${escapeHtml(title)}</h4>
      <div class="chips">${chips(list || [])}</div>
    </section>
  `).join('');
}

function staticRewriteHtml(row) {
  const rewrites = row.rewrite_options || [];
  const patches = row.applyable_patches || [];
  const rewriteButtons = rewrites.slice(0, 3).map((rewrite, index) => `
    <article class="static-rewrite-card">
      <strong>${escapeHtml(rewrite.name || `Option ${index + 1}`)}</strong>
      <p>${escapeHtml(rewrite.text || '').replaceAll('\n', '<br>')}</p>
      <small>${escapeHtml(rewrite.syllables ?? '')} syllables · ${escapeHtml(rewrite.why || '')}</small>
      <button type="button" class="ghost tiny apply-static-rewrite" data-line="${row.line_number}" data-rewrite="${index}">Use rewrite</button>
    </article>
  `).join('');
  const patchButtonsHtml = patches.slice(0, 3).map((patch, index) => `
    <button type="button" class="patch-button apply-static-patch" data-line="${row.line_number}" data-patch="${index}">
      <strong>${escapeHtml(patch.label || `Patch ${index + 1}`)}</strong>
      <span>${escapeHtml(patch.why || '')}</span>
    </button>
  `).join('');
  if (!rewriteButtons && !patchButtonsHtml) return '<p class="muted tiny-text">No direct rewrite generated for this line.</p>';
  return `
    <div class="static-rewrite-grid">${rewriteButtons}</div>
    <div class="patch-grid static-patches">${patchButtonsHtml}</div>
  `;
}

function staticLineCardHtml(row) {
  const priority = priorityClass(row.suggestion?.priority);
  const metrics = row.metrics || {};
  const breakdown = row.breakdown || {};
  const bar = breakdown.bar_structure || {};
  const wordsForSearch = Object.values(row.possible_words || {}).flat().join(' ');
  const info = row.information || {};
  const meter = row.meter || {};
  const meterSummary = meter.summary || {};
  const physics = row.physics || {};
  const barScore = row.bar_score || {};
  const physicsDelta = physics.cadence_delta || {};
  const searchText = `${row.text} ${row.section?.label || ''} ${row.role || ''} ${row.suggestion?.diagnosis || ''} ${wordsForSearch} ${info.interpretation || ''} ${meterSummary.dominant_meter || ''} ${(meter.suggestions || []).join(' ')} ${physics.physics_reading || ''} ${(physics.actions || []).join(' ')}`.toLowerCase();
  return `
    <article class="static-line-card ${priority}" data-line="${row.line_number}" data-search="${escapeHtml(searchText)}">
      <div class="static-line-head">
        <div>
          <button type="button" class="line-jump" data-line="${row.line_number}">Line ${row.line_number}</button>
          <span class="badge">${escapeHtml(row.section?.label || 'Section')}</span>
          <span class="badge">${escapeHtml(row.role || 'line')}</span>
        </div>
        <div class="badges">
          <span class="badge ${priority}">${escapeHtml(row.suggestion?.priority || 'low')}</span>
          ${barScore.available !== false && barScore.overall !== undefined ? `<span class="badge score-badge">Score ${escapeHtml(barScore.overall)}%</span>` : ''}
          <span class="badge">${escapeHtml(row.suggestion?.operation_label || 'Polish')}</span>
        </div>
      </div>
      <blockquote class="rhyme-line">${rhymeHighlightedLineHtml(row.rhyme_highlight, row.text || '')}</blockquote>
      ${rhymeLineMetaHtml(row.rhyme_highlight)}
      <div class="metric-pills">
        ${barScore.available !== false && barScore.overall !== undefined ? `<span>bar score ${escapeHtml(barScore.overall)}%</span>` : ''}
        <span>${escapeHtml(metrics.syllables ?? 0)} syllables</span>
        <span>${escapeHtml(metrics.words ?? 0)} words</span>
        <span>end: ${escapeHtml(metrics.end_word || '—')}</span>
        <span>rhyme: ${escapeHtml(metrics.rhyme_key || '—')}</span>
        <span>${escapeHtml(info.line_self_information_bits ?? 0)} info bits</span>
        <span>${escapeHtml(info.bits_per_word ?? 0)} bits/word</span>
        <span>rhyme surprise ${escapeHtml(info.rhyme_surprise_bits ?? 0)}</span>
        ${meter.available ? `<span>${escapeHtml(meterSummary.dominant_meter || 'mixed meter')}</span><span>${escapeHtml(meterSummary.stress_ratio_pct ?? 0)}% stress</span><span>${meterSummary.final_landing_stressed ? 'stressed landing' : 'soft landing'}</span>` : ''}
        ${physics.available ? `<span>F ${escapeHtml(physics.force_pct ?? 0)}%</span><span>τ ${escapeHtml(physics.torsion_pct ?? 0)}%</span><span>Ω ${escapeHtml(physics.spin_pct ?? 0)}%</span><span>ΔC ${physicsDelta.available ? `${physicsDelta.delta_syllables > 0 ? '+' : ''}${escapeHtml(physicsDelta.delta_syllables)}` : 'open'}</span>` : ''}
        ${bar.available ? `<span>bars ${escapeHtml(bar.assigned_bars)} · ${escapeHtml(bar.time_window || '')}</span>` : ''}
      </div>
      <div class="static-breakdown-grid">
        <section><h4>Cadence</h4><p>${escapeHtml(breakdown.cadence || '')}</p></section>
        <section><h4>Sound</h4><p>${escapeHtml(breakdown.sound || '')}</p></section>
        <section><h4>Content</h4><p>${escapeHtml(breakdown.content || '')}</p></section>
        <section><h4>Rhyme</h4><p>${escapeHtml(breakdown.rhyme || '')}</p></section>
        ${meter.available ? `<section class="wide meter-static-section"><h4>Meter / stress</h4>${meterMiniHtml(meter)}<ol>${(meter.suggestions || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></section>` : ''}
        ${physics.available ? `<section class="wide physics-static-section"><h4>Scansion physics</h4>${physicsMiniHtml(physics)}</section>` : ''}
        <section class="wide"><h4>Bar structure</h4><p>${escapeHtml(bar.note || '')}</p></section>
        <section class="wide"><h4>Information profile</h4><p>${escapeHtml(info.interpretation || '')}</p><p class="muted tiny-text">Rarest words: ${(info.rarest_words || []).map((item) => `${escapeHtml(item.word)} (${escapeHtml(item.bits)}b)`).join(', ') || '—'}</p></section>
        ${barScore.overall !== undefined ? `<section class="wide score-line-section"><h4>Bar score</h4><p><strong>${escapeHtml(barScore.overall)}%</strong> · ${escapeHtml(barScore.grade?.letter || '')} · ${escapeHtml(barScore.grade?.label || '')}</p><p>${escapeHtml((barScore.diagnosis?.issues || []).join('; '))}</p><ol>${(barScore.diagnosis?.advice || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></section>` : ''}
        ${row.comparison_guidance?.available ? `<section class="wide comparison-line-section"><h4>Reference benchmark</h4><p>${escapeHtml(row.comparison_guidance.note || '')}</p><p class="muted tiny-text">${escapeHtml(row.comparison_guidance.rhyme_note || '')}</p></section>` : ''}
      </div>
      <div class="static-suggestion-box">
        <h4>Suggestion</h4>
        <p>${escapeHtml(row.suggestion?.diagnosis || '')}</p>
        <ol>${(row.suggestion?.action_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join('')}</ol>
      </div>
      <details open>
        <summary>Advanced rhyme options</summary>
        ${advancedRhymeReportHtml(row.advanced_rhyme || {})}
      </details>
      <details open>
        <summary>Possible words</summary>
        <div class="static-word-grid">${staticWordsHtml(row.possible_words || {})}</div>
      </details>
      <details>
        <summary>Rewrite options and patches</summary>
        ${staticRewriteHtml(row)}
      </details>
      <details>
        <summary>Checklist</summary>
        <ul>${(row.suggestion?.checklist || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
      </details>
    </article>
  `;
}

function renderStaticReport(report) {
  state.staticReport = report;
  state.staticSource = editor.value;
  staticStatusEl.className = 'fit-callout';
  staticStatusEl.textContent = report.overview?.headline || 'Static report generated.';
  if (staticSnapshotSourceEl) {
    staticSnapshotSourceEl.className = 'snapshot-source highlighted-source';
    staticSnapshotSourceEl.innerHTML = `
      <strong>Rhyme-highlighted snapshot source</strong>
      <small>Matching colors show rhyme families. Underlined words are end-rhyme landings; dashed highlights are internal echoes.</small>
      ${rhymeLegendHtml(report.rhyme_highlights)}
      <div class="highlighted-lyrics">${snapshotRhymeLinesHtml(report)}</div>
    `;
  }
  staticMetricCards(report);
  staticOverviewHtml(report);
  renderSnapshotCharts(report);
  renderInformationTheory(report);
  renderMeterPanel(report);
  renderPhysicsPanel(report);
  renderComparisonPanel(report.comparison);
  if (report.score_report?.available) renderScoreReport(report.score_report);
  jsonBlock.textContent = JSON.stringify(report, null, 2);
  const rows = report.line_breakdown || [];
  if (!rows.length) {
    staticLineBreakdownEl.className = 'static-line-list empty-state';
    staticLineBreakdownEl.textContent = 'No editable lyric lines found.';
    return;
  }
  staticLineBreakdownEl.className = 'static-line-list';
  staticLineBreakdownEl.innerHTML = rows.map(staticLineCardHtml).join('');
}

async function generateStaticBreakdown(full = false) {
  const lyrics = editor.value;
  updateLocalStats();
  if (countWords(lyrics) < 3) {
    staticStatusEl.className = 'fit-callout muted';
    staticStatusEl.textContent = 'Type or import at least three words before generating a static report.';
    switchTab('snapshot');
    return;
  }
  staticStatusEl.className = 'fit-callout';
  staticStatusEl.textContent = full ? 'Generating full deep snapshot. This can take longer on hosted apps...' : 'Generating fast hosted-safe snapshot...';
  switchTab('snapshot');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), full ? 90000 : 25000);
  try {
    const response = await fetch(full ? '/api/snapshot/full' : '/api/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        lyrics,
        coach_mode: coachMode.value,
        beat_id: state.beatId,
        full,
      }),
    });
    const payload = await safeJsonResponse(response, full ? 'Full snapshot' : 'Fast snapshot');
    renderStaticReport(payload);
    if (payload.fast_snapshot || payload.truncated) {
      staticStatusEl.className = 'fit-callout';
      staticStatusEl.textContent = `${payload.overview?.headline || 'Fast snapshot loaded.'} ${payload.truncation_note || ''}`;
    }
  } catch (error) {
    staticStatusEl.className = 'fit-callout muted';
    staticStatusEl.textContent = error.name === 'AbortError'
      ? 'Snapshot request timed out. Use Refresh fast snapshot, or reduce the draft length before running Full deep snapshot.'
      : error.message;
  } finally {
    clearTimeout(timeout);
  }
}

function staticReportToText(report) {
  if (!report) return 'No static report generated yet.';
  const lines = [];
  lines.push('NMC Static Line Breakdown');
  lines.push(`Mode: ${report.mode_label || report.mode || ''}`);
  lines.push(report.overview?.headline || '');
  (report.overview?.actions || []).forEach((action, index) => lines.push(`${index + 1}. ${action}`));
  const theory = report.information_theory || {};
  if (theory.overview) {
    lines.push('');
    lines.push('INFORMATION THEORY SNAPSHOT');
    lines.push(`Token entropy: ${theory.overview.token_entropy_bits ?? 0} bits`);
    lines.push(`Rhyme entropy: ${theory.overview.rhyme_entropy_bits ?? 0} bits`);
    lines.push(`Line-length entropy: ${theory.overview.line_length_entropy_bits ?? 0} bits`);
    lines.push(`Bar-load entropy: ${theory.overview.bar_load_entropy_bits ?? 0} bits`);
    lines.push(`Compression ratio: ${theory.overview.compression_ratio ?? 0}`);
    (theory.interpretations || []).forEach((note) => lines.push(`- ${note}`));
  }
  if (report.physics_report?.available) {
    lines.push('');
    lines.push('SCANSION PHYSICS SNAPSHOT');
    lines.push(`Average F: ${report.physics_report.summary?.avg_force_pct ?? 0}%`);
    lines.push(`Average τ: ${report.physics_report.summary?.avg_torsion_pct ?? 0}%`);
    lines.push(`Average Ω: ${report.physics_report.summary?.avg_spin_pct ?? 0}%`);
    (report.physics_report.priority_actions || []).forEach((note) => lines.push(`- ${note}`));
  }
  if (report.meter_report?.available) {
    lines.push('');
    lines.push('METER / STRESS SNAPSHOT');
    lines.push(`Dominant meter: ${report.meter_report.summary?.dominant_meter || 'mixed'}`);
    lines.push(`Avg stress density: ${report.meter_report.summary?.avg_stress_ratio_pct ?? 0}%`);
    lines.push(`Landing stress: ${report.meter_report.summary?.final_landing_stressed_pct ?? 0}%`);
    (report.meter_report.recommendations || []).forEach((note) => lines.push(`- ${note}`));
  }
  if (report.comparison?.available) {
    lines.push('');
    lines.push('REFERENCE BENCHMARK COMPARISON');
    lines.push(`Closest reference: ${report.comparison.best_match?.name || '—'} (${report.comparison.best_match?.score ?? 0}%)`);
    (report.comparison.recommendations || []).forEach((note) => lines.push(`- ${note}`));
  }
  lines.push('');
  (report.line_breakdown || []).forEach((row) => {
    lines.push(`LINE ${row.line_number} — ${row.section?.label || 'Section'} — ${row.suggestion?.operation_label || 'Polish'}`);
    lines.push(row.text || '');
    lines.push(`Metrics: ${row.metrics?.syllables ?? 0} syllables, ${row.metrics?.words ?? 0} words, end=${row.metrics?.end_word || '—'}, rhyme=${row.metrics?.rhyme_key || '—'}`);
    if (row.information) lines.push(`Information: ${row.information.line_self_information_bits ?? 0} bits, ${row.information.bits_per_word ?? 0} bits/word, rhyme surprise=${row.information.rhyme_surprise_bits ?? 0} bits`);
    if (row.physics?.available) {
      lines.push(`Physics: F=${row.physics.force_pct ?? 0}%, τ=${row.physics.torsion_pct ?? 0}%, Ω=${row.physics.spin_pct ?? 0}%, ΔC=${row.physics.cadence_delta?.delta_syllables ?? 0}`);
      (row.physics.actions || []).slice(0, 3).forEach((note) => lines.push(`- ${note}`));
    }
    if (row.physics?.available) {
      lines.push(`Scansion Physics: F=${row.physics.symbols?.F ?? 0}, τ=${row.physics.symbols?.['τ'] ?? 0}, Ω=${row.physics.symbols?.['Ω'] ?? 0}, ΔC=${row.physics.cadence_delta?.motion_label || 'start'}`);
      (row.physics.suggestions || []).slice(0, 3).forEach((note) => lines.push(`- ${note}`));
    }
    if (row.meter?.available) {
      lines.push(`Meter: ${row.meter.summary?.dominant_meter || 'mixed'}, stress=${row.meter.summary?.stress_ratio_pct ?? 0}%, landing=${row.meter.summary?.final_landing_stressed ? 'stressed' : 'soft'}`);
      lines.push(`Stress pattern: ${row.meter.pattern?.glyphs || ''}`);
      (row.meter.suggestions || []).slice(0, 3).forEach((note) => lines.push(`- ${note}`));
    }
    lines.push(`Cadence: ${row.breakdown?.cadence || ''}`);
    lines.push(`Rhyme: ${row.breakdown?.rhyme || ''}`);
    lines.push(`Suggestion: ${row.suggestion?.diagnosis || ''}`);
    (row.suggestion?.action_steps || []).forEach((step) => lines.push(`- ${step}`));
    const words = row.possible_words || {};
    const compactWords = Object.entries(words)
      .filter(([, value]) => Array.isArray(value) && value.length)
      .map(([key, value]) => `${key}: ${value.slice(0, 8).join(', ')}`)
      .join(' | ');
    if (compactWords) lines.push(`Possible words: ${compactWords}`);
    if ((row.rewrite_options || [])[0]) lines.push(`Rewrite seed: ${row.rewrite_options[0].text}`);
    lines.push('');
  });
  return lines.join('\n');
}

function findStaticRow(lineNumber) {
  const report = state.staticReport;
  if (!report) return null;
  return (report.line_breakdown || []).find((row) => Number(row.line_number) === Number(lineNumber)) || null;
}

// ---------------------------------------------------------------------------
// Synchronous one-sentence lab
// ---------------------------------------------------------------------------

function activeSentenceFromEditor() {
  const text = editor.value || '';
  const cursor = editor.selectionStart || 0;
  const spans = [];
  const re = /[^.!?;\n]+(?:[.!?;]+|$)/g;
  let match;
  while ((match = re.exec(text)) !== null) {
    const sentence = (match[0] || '').trim();
    if (sentence) spans.push({ start: match.index, end: match.index + match[0].length, sentence });
  }
  if (!spans.length) {
    const lines = text.split(/\r?\n/);
    let pos = 0;
    for (const line of lines) {
      const start = pos;
      const end = pos + line.length;
      if (start <= cursor && cursor <= end) return { start, end, sentence: line.trim() };
      pos = end + 1;
    }
    return { start: 0, end: text.length, sentence: text.trim() };
  }
  for (const span of spans) {
    if (span.start <= cursor && cursor <= span.end) return span;
  }
  const before = spans.filter((span) => span.start <= cursor);
  return before.length ? before[before.length - 1] : spans[0];
}

function setSentenceStatus(kind, text, small = '') {
  if (!sentenceStatusEl) return;
  sentenceStatusEl.className = `status-pill sentence-status ${kind || ''}`;
  sentenceStatusEl.innerHTML = `<span></span>${escapeHtml(text || 'Ready')}`;
  if (small && $('#sentenceHelper')) {
    $('#sentenceHelper').textContent = small;
  }
}

function sentenceChips(words, cls = 'sentence-word-chip') {
  if (!words || !words.length) return '<p class="muted tiny-text">No words in this bank yet.</p>';
  return words.map((word) => `<button type="button" class="chip ${cls}" data-word="${escapeHtml(word)}">${escapeHtml(word)}</button>`).join('');
}

function sentenceWordBanksHtml(bank = {}) {
  const groups = [
    ['End rhymes', bank.end_rhymes],
    ['Near rhymes', bank.near_rhymes],
    ['Slant rhymes', bank.slant_rhymes],
    ['Assonance', bank.assonance_words],
    ['Consonance', bank.consonance_words],
    ['Stress matched', bank.stress_matched],
    ['Multi-syllable endings', bank.multi_syllable_endings],
    ['Internal echoes', bank.internal_echoes],
    ['Signature words', bank.signature_words],
    ['Images', bank.images],
    ['Verbs', bank.verbs],
    ['Punch words', bank.punch_words],
    ['Cut words', bank.cut_words],
  ];
  return groups.map(([title, words]) => `
    <section class="sentence-bank-group">
      <h4>${escapeHtml(title)}</h4>
      <div class="chips">${sentenceChips(words || [])}</div>
    </section>
  `).join('');
}

function sentenceMetricsHtml(report) {
  if (!sentenceMetricsEl) return;
  if (!report || !report.available) {
    sentenceMetricsEl.innerHTML = '';
    return;
  }
  const m = report.metrics || {};
  const scores = report.scores || {};
  const bar = report.bar_plan || {};
  const info = report.information || {};
  sentenceMetricsEl.innerHTML = `
    <article class="metric-card score"><span>Sentence fit</span><strong>${escapeHtml(scores.overall ?? 0)}%</strong><small>${escapeHtml(scores.reading || '')}</small></article>
    <article class="metric-card"><span>Syllables</span><strong>${escapeHtml(m.syllables ?? 0)}</strong><small>target ${(bar.target_syllables_per_bar || []).join('–') || '—'}</small></article>
    <article class="metric-card"><span>End rhyme</span><strong>/${escapeHtml(m.rhyme_key || '—')}/</strong><small>${escapeHtml(m.end_word || 'no end word')}</small></article>
    <article class="metric-card"><span>Internal sound</span><strong>${escapeHtml(m.internal_rhyme_groups ?? 0)}</strong><small>${escapeHtml(m.alliteration_groups ?? 0)} alliteration group(s)</small></article>
    <article class="metric-card"><span>Bar span</span><strong>${escapeHtml(bar.estimated_bar_span ?? 1)}</strong><small>${escapeHtml(bar.primary_action || 'one-bar check')}</small></article>
    <article class="metric-card"><span>Corpus bits</span><strong>${escapeHtml(info.bits_per_content_word ?? 0)}</strong><small>bits/content word</small></article>
    <article class="metric-card"><span>Physics</span><strong>F ${escapeHtml(m.force_pct ?? 0)}%</strong><small>τ ${escapeHtml(m.torsion_pct ?? 0)}% · Ω ${escapeHtml(m.spin_pct ?? 0)}%</small></article>
    <article class="metric-card"><span>Closest ref</span><strong>${escapeHtml(report.comparison_guidance?.reference_score ?? 0)}%</strong><small>${escapeHtml(report.comparison_guidance?.reference_name || '—')}</small></article>
  `;
}

function sentenceScoreBarsHtml(scores = {}) {
  const rows = [
    ['Cadence fit', scores.cadence_fit],
    ['Rhyme landing', scores.rhyme_landing],
    ['Internal sound', scores.internal_sound],
    ['Image balance', scores.image_balance],
    ['Reference fit', scores.reference_fit],
  ];
  return `
    <div class="sentence-score-bars">
      ${rows.map(([label, value]) => `
        <div class="sentence-score-bar">
          <span>${escapeHtml(label)}</span>
          <div><i style="width:${Math.max(0, Math.min(100, Number(value || 0)))}%"></i></div>
          <strong>${escapeHtml(value ?? 0)}%</strong>
        </div>
      `).join('')}
    </div>
  `;
}

function sentenceClausesHtml(clauses = []) {
  if (!clauses.length) return '<p class="muted tiny-text">No clause split detected.</p>';
  return `
    <div class="sentence-clause-grid">
      ${clauses.map((clause) => `
        <article>
          <strong>Clause ${escapeHtml(clause.index)}</strong>
          <p>${escapeHtml(clause.text)}</p>
          <small>${escapeHtml(clause.syllables)} syllables · end ${escapeHtml(clause.end_word || '—')} /${escapeHtml(clause.rhyme_key || '—')}/</small>
          ${clause.meter?.available ? `<code class="meter-code mini">${escapeHtml(clause.meter.pattern?.glyphs || '')}</code>` : ''}
        </article>
      `).join('')}
    </div>
  `;
}

function sentenceRewriteHtml(report) {
  const rewrites = report.rewrite_options || [];
  const patches = report.applyable_patches || [];
  const rewriteHtml = rewrites.map((rewrite, index) => `
    <article class="sentence-rewrite-card">
      <div><strong>${escapeHtml(rewrite.name || `Rewrite ${index + 1}`)}</strong><small>${escapeHtml(rewrite.syllables ?? '')} syllables</small></div>
      <p>${escapeHtml(rewrite.text || '').replaceAll('\n', '<br>')}</p>
      <small>${escapeHtml(rewrite.why || '')}</small>
      <button type="button" class="ghost tiny sentence-use-rewrite" data-index="${index}">Use in sentence box</button>
    </article>
  `).join('');
  const patchHtml = patches.slice(0, 3).map((patch, index) => `
    <button type="button" class="patch-button sentence-use-patch" data-index="${index}">
      <strong>${escapeHtml(patch.label || `Patch ${index + 1}`)}</strong>
      <span>${escapeHtml(patch.why || '')}</span>
    </button>
  `).join('');
  if (!rewriteHtml && !patchHtml) return '<p class="muted tiny-text">No direct rewrite generated yet.</p>';
  return `<div class="sentence-rewrite-grid">${rewriteHtml}</div><div class="patch-grid sentence-patch-grid">${patchHtml}</div>`;
}

function sentenceInformationHtml(info = {}) {
  const rare = info.rarest_words || [];
  return `
    <div class="sentence-info-card">
      <h4>Corpus information profile</h4>
      <p>${escapeHtml(info.interpretation || '')}</p>
      <div class="metric-pills">
        <span>${escapeHtml(info.profile_overlap_pct ?? 0)}% corpus overlap</span>
        <span>${escapeHtml(info.signature_overlap_pct ?? 0)}% signature overlap</span>
        <span>${escapeHtml(info.sentence_self_information_bits ?? 0)} total bits</span>
        <span>${escapeHtml(info.rhyme_surprise_bits_vs_corpus ?? 0)} rhyme bits</span>
      </div>
      <p class="muted tiny-text">Rarest words: ${rare.map((row) => `${escapeHtml(row.word)} (${escapeHtml(row.self_information_bits)}b)`).join(', ') || '—'}</p>
    </div>
  `;
}

function sentenceBarPlanHtml(plan = {}) {
  const split = plan.split_plan || {};
  const beat = plan.beat_guidance || {};
  return `
    <div class="sentence-bar-card">
      <h4>Bar-structure feedback</h4>
      <p>${escapeHtml(plan.instruction || '')}</p>
      <div class="metric-pills">
        <span>${escapeHtml(plan.basis || 'corpus')}</span>
        <span>${(plan.target_syllables_per_bar || []).join('–') || '—'} syll/bar target</span>
        <span>${escapeHtml(plan.estimated_bar_span ?? 1)} estimated bar(s)</span>
        ${beat.assigned_bars ? `<span>assigned bars ${escapeHtml(beat.assigned_bars)}</span>` : ''}
        ${beat.time_window ? `<span>${escapeHtml(beat.time_window)}</span>` : ''}
      </div>
      ${split.available ? `
        <div class="split-preview">
          <strong>Suggested split after word ${escapeHtml(split.split_after_word)}</strong>
          <pre>${escapeHtml(split.formatted_split || '')}</pre>
          <small>${escapeHtml(split.first_half_syllables)} syllables / ${escapeHtml(split.second_half_syllables)} syllables</small>
        </div>
      ` : `<p class="muted tiny-text">${escapeHtml(split.reason || 'No split needed.')}</p>`}
    </div>
  `;
}

function renderSentenceReport(report) {
  state.sentenceReport = report;
  if (!sentenceOutputEl) return;
  if (!report || !report.available) {
    sentenceMetricsHtml(null);
    sentenceOutputEl.className = 'sentence-output empty-state';
    sentenceOutputEl.textContent = report?.error || 'Sentence-level feedback will appear here.';
    return;
  }
  sentenceMetricsHtml(report);
  sentenceOutputEl.className = 'sentence-output';
  const issues = report.suggestion?.issues || [];
  const moves = report.next_actions || [];
  const compare = report.comparison_guidance || {};
  sentenceOutputEl.innerHTML = `
    <article class="sentence-main-card">
      <div class="sentence-main-head">
        <div>
          <small>${escapeHtml(report.mode_label || report.mode || '')}</small>
          <h3>${escapeHtml(report.headline || 'Sentence analyzed')}</h3>
        </div>
        <strong>${escapeHtml(report.scores?.overall ?? 0)}%</strong>
      </div>
      <blockquote class="rhyme-line sentence-highlight-line">${rhymeHighlightedLineHtml(report.rhyme_highlight, report.sentence)}</blockquote>
      ${rhymeLineMetaHtml(report.rhyme_highlight)}
      <p class="diagnosis">${escapeHtml(report.diagnosis || '')}</p>
      ${sentenceScoreBarsHtml(report.scores || {})}
      <div class="sentence-fix-columns">
        <section>
          <h4>Fix now</h4>
          <ol>${moves.map((move) => `<li>${escapeHtml(move)}</li>`).join('')}</ol>
        </section>
        <section>
          <h4>Detected issues</h4>
          <ul>${issues.map((issue) => `<li><b>${escapeHtml(issue.type || 'issue')}</b>: ${escapeHtml(issue.message || '')}</li>`).join('') || '<li>No major issue detected.</li>'}</ul>
        </section>
      </div>
    </article>
    <article class="sentence-detail-card">
      <h4>Clauses / breath units</h4>
      ${sentenceClausesHtml(report.clauses || [])}
    </article>
    ${sentenceMeterHtml(report.meter || {})}
    ${sentencePhysicsHtml(report.physics || {})}
    <article class="sentence-detail-card">
      <h4>Advanced rhyme options</h4>
      ${advancedRhymeReportHtml(report.advanced_rhyme || {})}
    </article>
    ${sentenceBarPlanHtml(report.bar_plan || {})}
    ${sentenceInformationHtml(report.information || {})}
    ${compare.available ? `
      <article class="sentence-detail-card comparison-line-section">
        <h4>Reference benchmark</h4>
        <p>${escapeHtml(compare.note || '')}</p>
        <p class="muted tiny-text">${escapeHtml(compare.rhyme_note || '')}</p>
      </article>
    ` : ''}
    <article class="sentence-detail-card">
      <h4>Possible words</h4>
      <div class="sentence-word-grid">${sentenceWordBanksHtml(report.possible_words || {})}</div>
    </article>
    <article class="sentence-detail-card">
      <h4>Rewrite options and direct patches</h4>
      ${sentenceRewriteHtml(report)}
    </article>
    <details>
      <summary>Sentence JSON</summary>
      <pre class="sentence-json-block">${escapeHtml(JSON.stringify(report, null, 2))}</pre>
    </details>
  `;
  jsonBlock.textContent = JSON.stringify(report, null, 2);
}

async function analyzeSentenceNow(force = false) {
  if (!sentenceInputEl) return;
  const sentence = (sentenceInputEl.value || '').trim();
  if (!sentence) {
    renderSentenceReport({ available: false, error: 'Type one sentence or pull the active sentence from the editor.' });
    setSentenceStatus('idle', 'Ready', 'Type one sentence or pull the active sentence from the editor.');
    return;
  }
  if (!force && state.sentenceReport?.sentence === sentence && state.sentenceReport?.mode === coachMode.value) return;
  state.sentenceSequence += 1;
  const token = state.sentenceSequence;
  setSentenceStatus('running', 'Syncing', 'Running direct one-sentence analysis now.');
  try {
    const response = await fetch('/api/sentence/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sentence,
        lyrics: editor.value,
        cursor_index: editor.selectionStart || 0,
        coach_mode: coachMode.value,
        beat_id: state.beatId,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Sentence analysis failed.');
    if (token !== state.sentenceSequence) return;
    renderSentenceReport(payload);
    setSentenceStatus('complete', 'Synced', payload.headline || 'Sentence feedback ready.');
  } catch (error) {
    renderSentenceReport({ available: false, error: error.message });
    setSentenceStatus('error', 'Error', error.message);
  }
}

function scheduleSentenceAnalysis() {
  if (!sentenceAutoSyncEl?.checked) return;
  if (state.sentenceTimer) clearTimeout(state.sentenceTimer);
  state.sentenceTimer = setTimeout(() => analyzeSentenceNow(false), 360);
}

function pullActiveSentenceToLab() {
  const active = activeSentenceFromEditor();
  state.sentenceSourceRange = active;
  if (sentenceInputEl) sentenceInputEl.value = active.sentence || '';
  switchTab('sentence');
  analyzeSentenceNow(true);
}

function applySentenceToEditor() {
  if (!sentenceInputEl) return;
  const replacement = sentenceInputEl.value || '';
  if (!replacement.trim()) return;
  let range = state.sentenceSourceRange;
  if (!range || range.start === undefined || range.end === undefined) range = activeSentenceFromEditor();
  const before = editor.value.slice(0, range.start);
  const after = editor.value.slice(range.end);
  editor.value = `${before}${replacement}${after}`;
  const pos = before.length + replacement.length;
  editor.focus();
  editor.selectionStart = editor.selectionEnd = pos;
  updateLocalStats();
  queueSuggestion(true);
  markSnapshotStale();
}


// ---------------------------------------------------------------------------
// Sentence rhyme-pattern comparison lab
// ---------------------------------------------------------------------------

function setSentencePatternStatus(kind, text, small = '') {
  if (!sentencePatternStatusEl) return;
  sentencePatternStatusEl.className = `status-pill sentence-status ${kind || ''}`;
  sentencePatternStatusEl.innerHTML = `<span></span>${escapeHtml(text || 'Ready')}`;
  if (small && sentencePatternOutputEl?.classList.contains('empty-state')) sentencePatternOutputEl.textContent = small;
}

function editorLinesForPattern(limit = 12) {
  return (editor.value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^\s*(?:\/\/\s*)?(intro|verse|chorus|hook|bridge|outro|refrain)\b/i.test(line))
    .slice(0, limit)
    .join('\n');
}

function loadEditorSentencePatterns() {
  if (!sentencePatternInputEl) return;
  const lines = editorLinesForPattern(16);
  sentencePatternInputEl.value = lines;
  switchTab('sentence-patterns');
  if (lines) compareSentencePatternsNow();
}

function addActiveSentencePattern() {
  if (!sentencePatternInputEl) return;
  const active = activeSentenceFromEditor();
  const current = sentencePatternInputEl.value.trim();
  sentencePatternInputEl.value = current ? `${current}\n${active.sentence || ''}` : (active.sentence || '');
  switchTab('sentence-patterns');
  compareSentencePatternsNow();
}

function patternMetricCards(report = {}) {
  const s = report.summary || {};
  if (!sentencePatternMetricsEl) return;
  sentencePatternMetricsEl.innerHTML = `
    <article class="metric-card score"><span>Avg pattern</span><strong>${escapeHtml(s.avg_pattern_strength ?? 0)}%</strong><small>rhyme architecture strength</small></article>
    <article class="metric-card"><span>Sentences</span><strong>${escapeHtml(s.sentences ?? 0)}</strong><small>compared side by side</small></article>
    <article class="metric-card"><span>Best pair</span><strong>${escapeHtml(s.best_pair_score ?? 0)}%</strong><small>strongest structure match</small></article>
    <article class="metric-card"><span>Internal density</span><strong>${escapeHtml(s.avg_internal_rhyme_density_pct ?? 0)}%</strong><small>avg internal echo weight</small></article>
    <article class="metric-card"><span>Strongest</span><strong>${escapeHtml(s.strongest_sentence_score ?? 0)}%</strong><small>sentence ${escapeHtml(s.strongest_sentence_index || '—')}</small></article>
    <article class="metric-card"><span>Weakest</span><strong>${escapeHtml(s.weakest_sentence_score ?? 0)}%</strong><small>sentence ${escapeHtml(s.weakest_sentence_index || '—')}</small></article>
  `;
}

function patternTokensHtml(tokens = []) {
  if (!tokens.length) return '<p class="muted tiny-text">No token map.</p>';
  return `<div class="pattern-token-stream">${tokens.map((token) => `
    <span class="pattern-token ${escapeHtml(token.role || '')}" data-rhyme-key="${escapeHtml(token.rhyme_key || '')}" title="/${escapeHtml(token.rhyme_key || '—')}/ · ${escapeHtml(token.stress_signature || '')}">
      ${escapeHtml(token.word || '')}<small>${escapeHtml(token.rhyme_key || '—')}</small>
    </span>
  `).join('')}</div>`;
}

function patternFamiliesHtml(families = []) {
  if (!families.length) return '<p class="muted tiny-text">No repeated internal rhyme family detected.</p>';
  return `<div class="pattern-family-list">${families.map((row) => `
    <span class="rhyme-family-chip" data-rhyme-key="${escapeHtml(row.key || '')}">/${escapeHtml(row.key || '')}/ <em>${escapeHtml((row.words || []).join(', '))}</em></span>
  `).join('')}</div>`;
}

function patternRewriteCards(sig = {}) {
  const rewrites = sig.rewrite_suggestions || [];
  if (!rewrites.length) return '<p class="muted tiny-text">No direct rewrite suggestion for this sentence yet.</p>';
  return `<div class="pattern-rewrite-list">${rewrites.map((row, index) => `
    <button type="button" class="pattern-rewrite-card pattern-use-rewrite" data-sentence-index="${escapeHtml(sig.index)}" data-rewrite-index="${index}">
      <strong>${escapeHtml(row.label || 'Use rewrite')}</strong>
      <span>${escapeHtml(row.text || '')}</span>
      <small>${escapeHtml(row.why || '')} ${row.delta_syllables ? `· Δ syll ${escapeHtml(row.delta_syllables)}` : ''}</small>
    </button>
  `).join('')}</div>`;
}

function sentencePatternCard(sig = {}) {
  const summary = sig.summary || {};
  const role = sig.compare_role || 'middle_pattern';
  const diagnosis = sig.diagnosis || [];
  const tail = sig.tail_pattern || [];
  return `
    <article class="sentence-pattern-card ${escapeHtml(role)}" data-sentence-index="${escapeHtml(sig.index)}">
      <div class="pattern-card-head">
        <div>
          <small>Sentence ${escapeHtml(sig.index)} · ${escapeHtml(role.replaceAll('_', ' '))}</small>
          <h3>${escapeHtml(sig.sentence || '')}</h3>
        </div>
        <b>${escapeHtml(summary.pattern_strength ?? 0)}%</b>
      </div>
      <div class="pattern-badges">
        <span>end /${escapeHtml(summary.end_rhyme_key || '—')}/</span>
        <span>${escapeHtml(summary.syllables ?? 0)} syllables</span>
        <span>${escapeHtml(summary.rhyme_density_pct ?? 0)}% internal density</span>
        <span>scheme ${escapeHtml(summary.compact_scheme || '—')}</span>
      </div>
      ${patternTokensHtml(sig.tokens || [])}
      <div class="pattern-card-grid">
        <section><h4>Repeated families</h4>${patternFamiliesHtml(sig.repeated_families || [])}</section>
        <section><h4>Tail pattern</h4><p class="muted tiny-text">${tail.map((row) => `${escapeHtml(row.word)} /${escapeHtml(row.rhyme_key || '—')}/ ${escapeHtml(row.stress_signature || '')}`).join(' → ') || '—'}</p></section>
        <section><h4>Diagnosis</h4><ol>${diagnosis.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ol></section>
        <section><h4>Rewrite options</h4>${patternRewriteCards(sig)}</section>
      </div>
    </article>
  `;
}

function pairMatrixHtml(report = {}) {
  const count = Number(report.summary?.sentences || 0);
  const pairs = report.pairwise || [];
  if (count < 2) return '<p class="muted tiny-text">Add at least two sentences to see pairwise comparison.</p>';
  const lookup = new Map();
  pairs.forEach((pair) => {
    lookup.set(`${pair.left_index}-${pair.right_index}`, pair);
    lookup.set(`${pair.right_index}-${pair.left_index}`, pair);
  });
  const rows = [];
  for (let i = 1; i <= count; i += 1) {
    const cells = [];
    for (let j = 1; j <= count; j += 1) {
      if (i === j) {
        cells.push(`<td class="pair-self">S${i}</td>`);
      } else {
        const pair = lookup.get(`${i}-${j}`) || {};
        const score = Number(pair.score || 0);
        cells.push(`<td class="pair-score ${scoreTone(score)}" title="${escapeHtml(pair.relationship || '')}"><strong>${escapeHtml(score)}</strong><small>${escapeHtml((pair.relationship || '').slice(0, 18))}</small></td>`);
      }
    }
    rows.push(`<tr><th>S${i}</th>${cells.join('')}</tr>`);
  }
  const head = Array.from({ length: count }, (_, idx) => `<th>S${idx + 1}</th>`).join('');
  return `<div class="table-wrap compact-table pair-matrix-wrap"><table class="pair-matrix"><thead><tr><th></th>${head}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

function bestPairsHtml(pairs = []) {
  if (!pairs.length) return '<p class="muted tiny-text">No pair report yet.</p>';
  return `<div class="best-pair-list">${pairs.slice(0, 6).map((pair) => `
    <article class="best-pair-card">
      <div><strong>S${escapeHtml(pair.left_index)} ↔ S${escapeHtml(pair.right_index)}</strong><span>${escapeHtml(pair.relationship || '')}</span></div>
      <b>${escapeHtml(pair.score ?? 0)}%</b>
      <small>end ${escapeHtml(pair.end_rhyme_similarity ?? 0)} · tail ${escapeHtml(pair.tail_stress_match_pct ?? 0)} · shared ${(pair.shared_rhyme_keys || []).map((k) => `/${escapeHtml(k)}/`).join(' ') || '—'}</small>
      <ol>${(pair.reasons || []).slice(0, 3).map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ol>
    </article>
  `).join('')}</div>`;
}

function patternBlueprintsHtml(blueprints = []) {
  if (!blueprints.length) return '<p class="muted tiny-text">No pattern blueprints available.</p>';
  return `<div class="pattern-blueprint-grid">${blueprints.slice(0, 6).map((bp) => `
    <article class="pattern-blueprint-card">
      <small>${escapeHtml(bp.scheme || '')}</small>
      <h3>${escapeHtml(bp.name || 'Pattern')}</h3>
      <p>${escapeHtml(bp.structure || '')}</p>
      <em>${escapeHtml(bp.use_when || '')}</em>
      <ol>${(bp.steps || []).slice(0, 5).map((step) => `<li>${escapeHtml(step)}</li>`).join('')}</ol>
      ${(bp.word_bank || []).length ? `<div class="chips">${(bp.word_bank || []).slice(0, 12).map((word) => `<button type="button" class="chip insert-chip" data-word="${escapeHtml(word)}">${escapeHtml(word)}</button>`).join('')}</div>` : ''}
    </article>
  `).join('')}</div>`;
}

function renderSentencePatternChart(report = {}) {
  const rows = report.sentences || [];
  const labels = rows.map((row) => `S${row.index}`);
  const strength = rows.map((row) => clampPct(row.summary?.pattern_strength));
  const density = rows.map((row) => clampPct(row.summary?.rhyme_density_pct));
  if (!labels.length) return false;
  return makeChart('sentencePatternStrengthChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        type: 'bar',
        label: 'Pattern strength',
        data: strength,
        backgroundColor: strength.map(scoreColor),
        borderWidth: 0,
      }, {
        type: 'line',
        label: 'Internal density',
        data: density,
        borderColor: 'rgba(217,251,82,0.95)',
        backgroundColor: 'rgba(217,251,82,0.16)',
        tension: 0.32,
        pointRadius: 3,
      }],
    },
    options: sharedChartOptions(),
  });
}

function renderSentencePatternReport(report = {}) {
  state.sentencePatternReport = report;
  if (!sentencePatternOutputEl) return;
  if (!report || !report.available) {
    sentencePatternMetricsEl.innerHTML = '';
    sentencePatternOutputEl.className = 'sentence-pattern-output empty-state';
    sentencePatternOutputEl.textContent = report?.error || 'Sentence pattern comparison will appear here.';
    return;
  }
  patternMetricCards(report);
  sentencePatternOutputEl.className = 'sentence-pattern-output';
  sentencePatternOutputEl.innerHTML = `
    <section class="pattern-overview-grid">
      <article class="viz-card action-card-primary">
        <h3>How to use this</h3>
        <p class="muted">Treat the strongest sentence as a rhyme-shape donor. Transfer its internal echo positions or end family to the weakest sentence, then compare again.</p>
        <ol>${(report.recommendations || []).map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ol>
      </article>
      <article class="viz-card wide chart-card">
        <div class="viz-card-head"><h3>Sentence pattern strength</h3><small>Bar = structure strength, line = internal density.</small></div>
        ${chartCanvasHtml('sentencePatternStrengthChart', simpleTrendSvg((report.sentences || []).map((row) => row.summary?.pattern_strength)))}
      </article>
    </section>
    <section class="pattern-section"><h3>Pairwise rhyme-structure matrix</h3>${pairMatrixHtml(report)}</section>
    <section class="pattern-section"><h3>Best sentence pairs</h3>${bestPairsHtml(report.best_pairs || [])}</section>
    <section class="pattern-section"><h3>Suggested rhyme patterns</h3>${patternBlueprintsHtml(report.pattern_blueprints || [])}</section>
    <section class="pattern-section"><h3>Sentence-by-sentence structure</h3><div class="sentence-pattern-card-list">${(report.sentences || []).map(sentencePatternCard).join('')}</div></section>
  `;
  renderSentencePatternChart(report);
  jsonBlock.textContent = JSON.stringify(report, null, 2);
}

async function compareSentencePatternsNow() {
  if (!sentencePatternInputEl) return;
  const text = (sentencePatternInputEl.value || '').trim();
  if (!text) {
    switchTab('sentence-patterns');
    renderSentencePatternReport({ available: false, error: 'Type two or more sentences, or load lines from the editor.' });
    setSentencePatternStatus('idle', 'Ready', 'Type two or more sentences, or load lines from the editor.');
    return;
  }
  switchTab('sentence-patterns');
  setSentencePatternStatus('running', 'Comparing', 'Building sentence rhyme-pattern report.');
  try {
    const response = await fetch('/api/sentence/compare-patterns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, coach_mode: coachMode.value, max_sentences: 16 }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Sentence pattern comparison failed.');
    renderSentencePatternReport(payload);
    setSentencePatternStatus('complete', 'Ready', `${payload.summary?.sentences || 0} sentences compared.`);
  } catch (error) {
    renderSentencePatternReport({ available: false, error: error.message });
    setSentencePatternStatus('error', 'Error', error.message);
  }
}

function applySentencePatternRewrite(sentenceIndex, rewriteIndex) {
  const report = state.sentencePatternReport;
  const sig = (report?.sentences || []).find((row) => Number(row.index) === Number(sentenceIndex));
  const rewrite = sig?.rewrite_suggestions?.[Number(rewriteIndex)];
  if (!rewrite || !sentencePatternInputEl) return;
  const lines = (sentencePatternInputEl.value || '').split(/\r?\n/);
  let seen = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (!lines[i].trim()) continue;
    seen += 1;
    if (seen === Number(sentenceIndex)) {
      lines[i] = rewrite.text || lines[i];
      break;
    }
  }
  sentencePatternInputEl.value = lines.join('\n');
  compareSentencePatternsNow();
}


function renderResult(result) {
  activeFixEl.className = '';
  activeFixEl.innerHTML = activeFixHtml(result.active_fix);
  renderScore(result);
  renderActions(result);
  renderFixQueue(result);
  renderBeatPanel(result);
  renderRhymePanel(result);
  renderMeterPanel(result);
  renderPhysicsPanel(result);
  renderComparisonPanel(result.comparison);
  if (result.rap_score?.available) renderScoreReport(result.rap_score);
  jsonBlock.textContent = JSON.stringify(result, null, 2);
}

function findFix(lineNumber) {
  const result = state.latest;
  if (!result) return null;
  return (result.line_fixes || []).find((fix) => Number(fix.line_number) === Number(lineNumber)) || null;
}

function replaceLine(lineNumber, replacement) {
  const lines = editor.value.split(/\r?\n/);
  const index = Math.max(0, Number(lineNumber) - 1);
  if (index >= lines.length) return;
  const replacementLines = String(replacement).split('\n');
  lines.splice(index, 1, ...replacementLines);
  editor.value = lines.join('\n');
  const before = lines.slice(0, index).join('\n');
  const cursor = before.length + (before ? 1 : 0) + replacementLines.join('\n').length;
  editor.focus();
  editor.selectionStart = editor.selectionEnd = cursor;
  updateLocalStats();
  queueSuggestion(true);
  queueLiveRhymeJob(true);
}

function jumpToLine(lineNumber) {
  const lines = editor.value.split(/\r?\n/);
  const target = Math.max(1, Math.min(Number(lineNumber), lines.length));
  let pos = 0;
  for (let i = 0; i < target - 1; i += 1) pos += lines[i].length + 1;
  editor.focus();
  editor.selectionStart = editor.selectionEnd = pos;
  state.activeLine = target;
  updateLocalStats();
  queueSuggestion(true);
  queueLiveRhymeJob(true);
}

function insertAtCursor(word) {
  const start = editor.selectionStart || 0;
  const end = editor.selectionEnd || start;
  const before = editor.value.slice(0, start);
  const after = editor.value.slice(end);
  const needsLeft = before && !/\s$/.test(before) ? ' ' : '';
  const needsRight = after && !/^\s/.test(after) ? ' ' : '';
  editor.value = `${before}${needsLeft}${word}${needsRight}${after}`;
  const pos = before.length + needsLeft.length + String(word).length + needsRight.length;
  editor.focus();
  editor.selectionStart = editor.selectionEnd = pos;
  updateLocalStats();
  scheduleSuggestion();
  scheduleLiveRhymeSuggestion();
}

async function uploadBeat(file) {
  if (!file) return;
  setStatus('running', 'Beat', 'analyzing upload');
  beatStatusEl.innerHTML = `<strong>Analyzing ${escapeHtml(file.name)}...</strong><span>This may take a moment for long MP3/M4A files.</span>`;
  const form = new FormData();
  form.append('beat_file', file);
  try {
    const response = await fetch('/api/beat/upload', { method: 'POST', body: form });
    const payload = await response.json();
    if (!response.ok) {
      const uploadError = new Error(payload.error || payload.message || 'Beat upload failed.');
      uploadError.payload = payload;
      throw uploadError;
    }
    state.beatId = payload.beat_id;
    state.beatAnalysis = payload;
    renderBeatDiagnostics(payload);
    renderUploadedBeatPanel(payload);
    beatStatusEl.innerHTML = `
      <strong>${escapeHtml(payload.filename || file.name)}</strong>
      <span>${escapeHtml(payload.rap_grid_bpm)} BPM rap grid · ${escapeHtml(payload.estimated_bar_count)} bars · ${escapeHtml(payload.duration_label)} · decoder ${escapeHtml(payload.load_method || 'unknown')}</span>
    `;
    setStatus('complete', 'Beat loaded', `${payload.rap_grid_bpm} BPM grid`);
    queueSuggestion(true);
  } catch (error) {
    state.beatId = null;
    if (error.payload) {
      renderBeatDiagnostics(error.payload);
      renderUploadedBeatPanel(error.payload);
    }
    beatStatusEl.innerHTML = `<strong>Beat analysis failed.</strong><span>${escapeHtml(error.message)}</span>`;
    setStatus('error', 'Beat error', error.message);
  }
}


async function importLyrics(file) {
  if (!file) return;
  const form = new FormData();
  form.append('lyrics_file', file);
  setStatus('running', 'Importing', file.name);
  try {
    const response = await fetch('/api/import-lyrics', { method: 'POST', body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Import failed.');
    editor.value = payload.lyrics || '';
    updateLocalStats();
    setStatus('complete', 'Imported', `${payload.lines} lines`);
    queueSuggestion(true);
    queueLiveRhymeJob(true);
    generateStaticBreakdown();
  } catch (error) {
    setStatus('error', 'Import error', error.message);
  }
}

function downloadDraft() {
  const blob = new Blob([editor.value], { type: 'text/plain;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'nmc_rap_draft.txt';
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
}

function loadSample() {
  editor.value = window.NMC_BOOTSTRAP.sampleLyrics || '';
  updateLocalStats();
  queueSuggestion(true);
  generateStaticBreakdown();
}


// ---------------------------------------------------------------------------
// Song Render Lab: lyrics + beat -> rough mixed WAV
// ---------------------------------------------------------------------------

function setSongStatus(kind, text, small = '') {
  if (!songRenderStatusEl) return;
  songRenderStatusEl.className = `status-pill song-status ${kind || ''}`;
  songRenderStatusEl.innerHTML = `<span></span>${escapeHtml(text || 'Ready')}`;
  if (small && songOutputEl && songOutputEl.classList.contains('empty-state')) {
    songOutputEl.textContent = small;
  }
}

function renderTtsStatus(tts = {}) {
  if (!songTtsStatusEl) return;
  const real = Boolean(tts.real_tts_available || tts.auto_will_render_speech);
  const bits = [];
  if (tts.espeak_available) bits.push('espeak available');
  if (tts.mac_say_available) bits.push('macOS say available');
  if (!bits.length) bits.push('no real speech backend detected');
  const advice = real
    ? 'Auto should render spoken TTS. Use Test speech voice before a full mix.'
    : 'Auto will stop with an error instead of making buzz. For hosted beta, deploy with Docker/espeak-ng; on Mac, select macOS system say and run locally.';
  songTtsStatusEl.innerHTML = `<strong>${real ? 'Speech TTS ready' : 'Speech TTS missing'}</strong><p>${escapeHtml(bits.join(' · '))}. ${escapeHtml(advice)}</p>`;
  songTtsStatusEl.classList.toggle('warning-strong', !real);
}


function numberInputValue(id, fallback) {
  const el = $(id);
  const value = Number(el?.value);
  return Number.isFinite(value) ? value : fallback;
}

function songPayload() {
  return {
    lyrics: editor.value || '',
    beat_id: state.beatId,
    tts_backend: $('#songVoiceEngine')?.value || 'auto',
    voice_preset: $('#songVoicePreset')?.value || 'neutral',
    rap_intensity: $('#songRapIntensity')?.value || 'balanced',
    start_bar: numberInputValue('#songStartBar', 0),
    intro_bars: numberInputValue('#songStartBar', 0),
    tail_bars: numberInputValue('#songTailBars', 2),
    outro_bars: numberInputValue('#songTailBars', 2),
    beat_gain_db: numberInputValue('#songBeatGain', -4),
    vocal_gain_db: numberInputValue('#songVocalGain', -1),
    ducking: numberInputValue('#songDucking', 0.18),
    loop_beat: Boolean($('#songLoopBeat')?.checked),
    title: 'nmc_song_render',
  };
}

function songTimingRowsHtml(lines = [], limit = 32) {
  if (!lines.length) return '<p class="muted tiny-text">No timing rows yet.</p>';
  return `
    <div class="table-wrap song-table-wrap">
      <table>
        <thead><tr><th>Line</th><th>Bars</th><th>Time</th><th>Syl/bar</th><th>Action</th></tr></thead>
        <tbody>
          ${lines.slice(0, limit).map((row) => `
            <tr>
              <td>${escapeHtml(row.render_line_number || row.line_number || '—')}</td>
              <td>${escapeHtml(row.bar_start || '—')}-${escapeHtml(row.bar_end || row.bar_start || '—')}</td>
              <td>${escapeHtml(row.start_time || fmt(row.start_seconds, '0'))} → ${escapeHtml(row.end_time || fmt(row.end_seconds, '0'))}</td>
              <td>${escapeHtml(row.syllables_per_bar ?? '—')}</td>
              <td>${escapeHtml(row.performance_action || row.instruction || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderSongOutput(data = {}, mode = 'render') {
  state.songReport = data;
  if (!songOutputEl) return;
  if (!data.available && data.error) {
    const warnings = data.warnings || [];
    const tts = data.tts_status || {};
    songOutputEl.className = 'song-output';
    songOutputEl.innerHTML = `
      <div class="fit-callout warning-strong">
        <strong>Render stopped</strong>
        <p>${escapeHtml(data.error)}</p>
        ${warnings.length ? warnings.map((note) => `<p>${escapeHtml(note)}</p>`).join('') : ''}
        ${tts && Object.keys(tts).length ? `<p><strong>TTS status:</strong> ${escapeHtml(tts.espeak_available ? 'espeak available' : 'espeak missing')} · ${escapeHtml(tts.mac_say_available ? 'macOS say available' : 'macOS say missing')}</p>` : ''}
      </div>
    `;
    jsonBlock.textContent = JSON.stringify(data, null, 2);
    return;
  }
  const plan = data.alignment_plan || data;
  const summary = data.summary || plan.summary || {};
  const warnings = data.warnings || plan.warnings || [];
  const suggestions = data.suggestions || plan.density_summary || [];
  const lines = plan.lines || data.lines || [];
  const audioUrl = data.audio_url || data.download_urls?.mix || '';
  const vocalUrl = data.vocal_stem_url || data.download_urls?.vocal_stem || '';
  const timingUrl = data.timing_json_url || data.download_urls?.timing_json || '';
  const downloadLinks = data.download_urls ? `
    <div class="song-downloads">
      ${audioUrl ? `<a class="button-link" href="${escapeHtml(audioUrl)}" download>Download mix WAV</a>` : ''}
      ${vocalUrl ? `<a class="button-link ghost-link-button" href="${escapeHtml(vocalUrl)}" download>Download vocal stem</a>` : ''}
      ${timingUrl ? `<a class="button-link ghost-link-button" href="${escapeHtml(timingUrl)}" download>Download timing JSON</a>` : ''}
    </div>
  ` : '';
  songOutputEl.className = 'song-output';
  songOutputEl.innerHTML = `
    <div class="song-result-head">
      <div>
        <p class="eyebrow">${mode === 'timing' ? 'Timing preview' : mode === 'voice-test' ? 'TTS voice test' : 'Rendered rough song'}</p>
        <h3>${escapeHtml(data.filename || 'Song timing plan')}</h3>
        <small>${escapeHtml(data.duration_label || plan.estimated_vocal_time || '')} · ${escapeHtml(data.rendered_line_count || summary.rendered_line_count || lines.length || 0)} voiced line(s)</small>
      </div>
      <div class="metric-pills">
        <span>${escapeHtml(data.vocal_engine?.voice_label || $('#songVoicePreset')?.selectedOptions?.[0]?.textContent || 'voice preset')}</span>
        <span>${escapeHtml(data.vocal_engine?.rap_intensity_label || plan.rap_intensity_label || 'balanced')}</span>
        <span>${escapeHtml(data.beat_looped ? 'beat looped' : 'beat not looped')}</span>
      </div>
    </div>
    ${audioUrl ? `<audio class="song-audio" controls src="${escapeHtml(audioUrl)}"></audio>` : ''}
    ${vocalUrl ? `<div class="stem-preview"><small>Vocal stem preview</small><audio class="song-audio" controls src="${escapeHtml(vocalUrl)}"></audio></div>` : ''}
    ${downloadLinks}
    <div class="beat-summary-grid song-summary-grid">
      <article class="metric-card"><span>Rap grid</span><strong>${escapeHtml(plan.rap_grid_bpm || summary.rap_grid_bpm || '—')}</strong><small>BPM</small></article>
      <article class="metric-card"><span>Bars needed</span><strong>${escapeHtml(plan.bars_needed || summary.bars_needed || '—')}</strong><small>${escapeHtml(plan.beat_bars || '—')} beat bars</small></article>
      <article class="metric-card"><span>Target density</span><strong>${escapeHtml(plan.target_syllables_per_bar || summary.target_syllables_per_bar || '—')}</strong><small>syllables/bar</small></article>
      <article class="metric-card"><span>TTS</span><strong>${escapeHtml(data.vocal_engine?.requested_backend || $('#songVoiceEngine')?.value || 'auto')}</strong><small>${escapeHtml((data.vocal_engine?.methods_used || []).slice(0, 1).join('') || 'timing only')}</small></article>
      <article class="metric-card"><span>Vocal signal</span><strong>${escapeHtml(data.vocal_diagnostics?.has_vocal_signal === false ? 'none' : data.vocal_diagnostics?.peak ?? '—')}</strong><small>peak level</small></article>
    </div>
    ${warnings.length ? `<div class="fit-callout muted"><strong>Warnings</strong>${warnings.map((note) => `<p>${escapeHtml(note)}</p>`).join('')}</div>` : ''}
    ${suggestions.length ? `<div class="fit-callout"><strong>Song structure suggestions</strong>${suggestions.map((note) => `<p>${escapeHtml(note)}</p>`).join('')}</div>` : ''}
    ${songTimingRowsHtml(lines)}
  `;
  jsonBlock.textContent = JSON.stringify(data, null, 2);
}

async function buildSongTiming() {
  const lyrics = editor.value || '';
  if (countWords(lyrics) < 3) {
    setSongStatus('error', 'Need lyrics', 'Type or import lyrics first.');
    switchTab('song');
    return;
  }
  if (!state.beatId) {
    setSongStatus('error', 'Need beat', 'Upload a beat before previewing song timing.');
    switchTab('song');
    return;
  }
  setSongStatus('running', 'Planning', 'building bar-by-bar vocal timing');
  switchTab('song');
  try {
    const response = await fetch('/api/song/timing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(songPayload()),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Song timing failed.');
    setSongStatus('complete', 'Planned', `${payload.bars_needed || 0} bars`);
    renderSongOutput(payload, 'timing');
  } catch (error) {
    setSongStatus('error', 'Timing error', error.message);
    renderSongOutput({ available: false, error: error.message });
  }
}

async function renderSongNow() {
  const lyrics = editor.value || '';
  if (countWords(lyrics) < 3) {
    setSongStatus('error', 'Need lyrics', 'Type or import lyrics first.');
    switchTab('song');
    return;
  }
  if (!state.beatId) {
    setSongStatus('error', 'Need beat', 'Upload a beat before rendering a song.');
    switchTab('song');
    return;
  }
  setSongStatus('running', 'Rendering', 'generating TTS vocals and mixing with beat');
  switchTab('song');
  try {
    const response = await fetch('/api/song/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(songPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      setSongStatus('error', 'Render stopped', payload.error || 'Song render failed.');
      renderSongOutput(payload, 'render');
      return;
    }
    setSongStatus('complete', 'Rendered', payload.duration_label || 'WAV ready');
    renderSongOutput(payload, 'render');
  } catch (error) {
    setSongStatus('error', 'Render error', error.message);
    renderSongOutput({ available: false, error: error.message });
  }
}

async function testSongVoice() {
  const lyrics = editor.value || '';
  const firstLine = lyrics.split(/\n+/).map((line) => line.trim()).find((line) => countWords(line) >= 3) || 'Every sentence I am inventing has resonance on the beat.';
  setSongStatus('running', 'Testing voice', 'checking the selected speech backend');
  switchTab('song');
  try {
    const response = await fetch('/api/song/test-voice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...songPayload(), text: firstLine }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setSongStatus('error', 'Voice missing', payload.error || 'Voice test failed.');
      renderSongOutput(payload, 'voice-test');
      return;
    }
    setSongStatus('complete', 'Voice ready', payload.duration_seconds ? `${payload.duration_seconds}s sample` : 'sample ready');
    renderSongOutput(payload, 'voice-test');
  } catch (error) {
    setSongStatus('error', 'Voice test error', error.message);
    renderSongOutput({ available: false, error: error.message }, 'voice-test');
  }
}



function clampPct(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function scoreTone(value) {
  const n = clampPct(value);
  if (n >= 85) return 'elite';
  if (n >= 72) return 'strong';
  if (n >= 58) return 'mid';
  return 'weak';
}


function chartCanvasHtml(id, fallbackHtml = '<div class="chart-empty">Chart data will render here.</div>') {
  return `
    <div class="chart-shell" data-chart-id="${escapeHtml(id)}">
      <canvas id="${escapeHtml(id)}" aria-label="${escapeHtml(id)} visualization"></canvas>
      <div class="chart-fallback">${fallbackHtml}</div>
    </div>
  `;
}

function destroyChart(id) {
  if (state.charts && state.charts[id]) {
    try { state.charts[id].destroy(); } catch (_error) {}
    delete state.charts[id];
  }
}

function makeChart(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas || !window.Chart) return false;
  destroyChart(id);
  const shell = canvas.closest('.chart-shell');
  if (shell) shell.classList.add('chart-ready');
  state.charts[id] = new Chart(canvas, config);
  return true;
}

function scoreColor(value) {
  const n = Number(value || 0);
  if (n >= 85) return 'rgba(149,255,186,0.78)';
  if (n >= 72) return 'rgba(154,164,255,0.75)';
  if (n >= 58) return 'rgba(255,211,106,0.78)';
  return 'rgba(255,129,129,0.78)';
}

function deltaColor(value) {
  const n = Number(value || 0);
  if (n > 0) return 'rgba(130,255,208,0.78)';
  if (n < 0) return 'rgba(255,129,129,0.80)';
  return 'rgba(174,184,214,0.48)';
}

function sharedChartOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#dfe6ff', boxWidth: 12, usePointStyle: true } },
      tooltip: { intersect: false, mode: 'index' },
    },
    scales: {
      x: { ticks: { color: '#aeb8d6', maxRotation: 0, autoSkip: true }, grid: { color: 'rgba(255,255,255,0.08)' } },
      y: { ticks: { color: '#aeb8d6' }, grid: { color: 'rgba(255,255,255,0.08)' }, suggestedMin: 0, suggestedMax: 100 },
    },
    ...extra,
  };
}

function renderComponentRadarChart(id, rows = []) {
  const labels = rows.slice(0, 6).map((row) => row.label || row.key || 'metric');
  const data = rows.slice(0, 6).map((row) => clampPct(row.score));
  if (!labels.length) return false;
  return makeChart(id, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Component strength',
        data,
        fill: true,
        backgroundColor: 'rgba(149,255,186,0.20)',
        borderColor: 'rgba(149,255,186,0.95)',
        pointBackgroundColor: 'rgba(217,251,82,0.95)',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          suggestedMin: 0,
          suggestedMax: 100,
          angleLines: { color: 'rgba(255,255,255,0.12)' },
          grid: { color: 'rgba(255,255,255,0.12)' },
          pointLabels: { color: '#dfe6ff', font: { size: 11 } },
          ticks: { display: false },
        },
      },
    },
  });
}

function renderBarTimelineChart(id, rows = [], label = 'Bar score') {
  const visible = rows.slice(0, 96);
  const labels = visible.map((row, idx) => `L${row.line_number || idx + 1}`);
  const scores = visible.map((row) => clampPct(row.overall));
  if (!scores.length) return false;
  return makeChart(id, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        type: 'bar',
        label,
        data: scores,
        backgroundColor: scores.map(scoreColor),
        borderWidth: 0,
      }, {
        type: 'line',
        label: 'Trend',
        data: scores,
        borderColor: 'rgba(217,251,82,0.95)',
        backgroundColor: 'rgba(217,251,82,0.18)',
        tension: 0.32,
        pointRadius: 2,
      }],
    },
    options: sharedChartOptions(),
  });
}

function renderDeltaTimelineChart(id, rows = []) {
  const visible = rows.slice(0, 96);
  const labels = visible.map((row, idx) => `B${row.bar_index ?? idx + 1}`);
  const deltas = visible.map((row) => Number(row.delta || 0));
  if (!deltas.length) return false;
  return makeChart(id, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Edit delta by bar',
        data: deltas,
        backgroundColor: deltas.map(deltaColor),
        borderWidth: 0,
      }],
    },
    options: sharedChartOptions({
      scales: {
        x: { ticks: { color: '#aeb8d6', maxRotation: 0, autoSkip: true }, grid: { color: 'rgba(255,255,255,0.08)' } },
        y: { ticks: { color: '#aeb8d6' }, grid: { color: 'rgba(255,255,255,0.08)' } },
      },
    }),
  });
}

function renderSnapshotCharts(report = {}) {
  const score = report.score_report || {};
  renderComponentRadarChart('snapshotComponentRadarChart', score.component_rows || []);
  renderBarTimelineChart('snapshotBarTimelineChart', score.bar_scores || [], 'Snapshot bar score');
}

function renderScoreCharts(report = {}) {
  renderComponentRadarChart('scoreComponentRadarChart', report.component_rows || []);
  renderBarTimelineChart('scoreBarTimelineChart', report.bar_scores || [], 'Bar score');
}

function renderCompareCharts(report = {}) {
  renderDeltaTimelineChart('compareDeltaTimelineChart', report.changed_bars || []);
}

function scoreGaugeHtml(value, label = 'Score', sub = '') {
  const pct = clampPct(value);
  return `
    <div class="viz-gauge ${scoreTone(pct)}" style="--pct:${pct};">
      <div class="viz-gauge-ring"><div class="viz-gauge-core"><strong>${escapeHtml(fmt(pct))}%</strong><small>${escapeHtml(label)}</small></div></div>
      ${sub ? `<p class="muted tiny-text">${escapeHtml(sub)}</p>` : ''}
    </div>
  `;
}

function simpleTrendSvg(values = [], width = 260, height = 90) {
  const nums = values.map((v) => Number(v)).filter((v) => Number.isFinite(v));
  if (!nums.length) return '<div class="chart-empty">No chart data.</div>';
  const min = Math.min(...nums, 0);
  const max = Math.max(...nums, 100);
  const range = Math.max(1, max - min);
  const points = nums.map((value, idx) => {
    const x = nums.length === 1 ? width / 2 : (idx / (nums.length - 1)) * (width - 18) + 9;
    const y = height - (((value - min) / range) * (height - 18) + 9);
    return `${Math.round(x)},${Math.round(y)}`;
  }).join(' ');
  const area = `9,${height - 9} ${points} ${width - 9},${height - 9}`;
  return `
    <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="trend chart">
      <polyline class="trend-line" fill="none" points="${points}"></polyline>
      <polygon class="trend-area" points="${area}"></polygon>
    </svg>
  `;
}

function componentRadarSvg(rows = []) {
  const items = rows.slice(0, 6);
  if (!items.length) return '<div class="chart-empty">No component shape yet.</div>';
  const cx = 110;
  const cy = 110;
  const radius = 78;
  const levels = [0.25, 0.5, 0.75, 1.0];
  const axis = items.map((row, idx) => {
    const angle = ((Math.PI * 2) / items.length) * idx - Math.PI / 2;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    const lx = cx + Math.cos(angle) * (radius + 22);
    const ly = cy + Math.sin(angle) * (radius + 22);
    return { row, angle, x, y, lx, ly };
  });
  const polygon = axis.map((item) => {
    const score = clampPct(item.row.score) / 100;
    const x = cx + Math.cos(item.angle) * radius * score;
    const y = cy + Math.sin(item.angle) * radius * score;
    return `${Math.round(x)},${Math.round(y)}`;
  }).join(' ');
  const rings = levels.map((level) => {
    const pts = axis.map((item) => {
      const x = cx + Math.cos(item.angle) * radius * level;
      const y = cy + Math.sin(item.angle) * radius * level;
      return `${Math.round(x)},${Math.round(y)}`;
    }).join(' ');
    return `<polygon class="radar-ring" points="${pts}"></polygon>`;
  }).join('');
  const lines = axis.map((item) => `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${item.x}" y2="${item.y}"></line>`).join('');
  const labels = axis.map((item) => `<text class="radar-label" x="${item.lx}" y="${item.ly}">${escapeHtml(item.row.label || item.row.key || 'metric')}</text>`).join('');
  return `
    <div class="radar-wrap">
      <svg class="radar-svg" viewBox="0 0 220 220" role="img" aria-label="score component radar">
        ${rings}
        ${lines}
        <polygon class="radar-shape" points="${polygon}"></polygon>
        ${labels}
      </svg>
    </div>
  `;
}

function barHeatMapHtml(rows = [], options = {}) {
  const limit = options.limit || 48;
  const showDelta = Boolean(options.showDelta);
  const cells = rows.slice(0, limit).map((row, idx) => {
    const value = Number(showDelta ? row.delta : row.overall);
    const tone = showDelta ? (value > 0 ? 'gain' : value < 0 ? 'loss' : 'flat') : scoreTone(value);
    const label = showDelta ? `${value > 0 ? '+' : ''}${fmt(value)}` : `${fmt(value)}%`;
    const lineNo = row.line_number || row.bar_index || idx + 1;
    const text = showDelta ? (row.edited_text || row.original_text || '') : (row.text || '');
    return `
      <button type="button" class="heat-cell ${tone} ${showDelta ? 'delta-cell' : ''} ${row.line_number ? 'line-jump' : ''}" ${row.line_number ? `data-line="${escapeHtml(row.line_number)}"` : ''} title="${escapeHtml(text)}">
        <small>${escapeHtml(lineNo)}</small>
        <strong>${escapeHtml(label)}</strong>
      </button>
    `;
  }).join('');
  return `<div class="heatmap-grid">${cells || '<div class="chart-empty">No bar map available.</div>'}</div>`;
}

function priorityListHtml(actions = [], fallback = 'No priority actions yet.') {
  if (!actions.length) return `<p class="muted tiny-text">${escapeHtml(fallback)}</p>`;
  return `<ol class="priority-list">${actions.slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>`;
}

function lineMiniList(title, rows = [], mode = 'score') {
  if (!rows.length) return `
    <article class="viz-card"><h4>${escapeHtml(title)}</h4><p class="muted tiny-text">No line list available.</p></article>
  `;
  return `
    <article class="viz-card">
      <h4>${escapeHtml(title)}</h4>
      <div class="mini-line-list">${rows.slice(0, 4).map((row) => `
        <button type="button" class="mini-line-item ${row.line_number ? 'line-jump' : ''}" ${row.line_number ? `data-line="${escapeHtml(row.line_number)}"` : ''}>
          <b>${mode === 'delta' ? `${Number(row.delta || 0) > 0 ? '+' : ''}${escapeHtml(fmt(row.delta || 0))}` : `${escapeHtml(fmt(row.overall || 0))}%`}</b>
          <span>${row.line_number ? `Line ${escapeHtml(row.line_number)} · ` : ''}${escapeHtml((row.text || row.edited_text || row.original_text || '').slice(0, 64))}</span>
        </button>`).join('')}</div>
    </article>
  `;
}

function snapshotVisualGuideHtml(report = {}) {
  const score = report.score_report || {};
  const lines = score.bar_scores || [];
  const comps = score.component_rows || [];
  const overview = report.overview || {};
  const theory = report.information_theory?.overview || {};
  return `
    <div class="viz-grid snapshot-viz-grid">
      <article class="viz-card action-card-primary">
        <h3>Use this snapshot</h3>
        <p class="muted">Start with the weakest bars, fix the top revision actions, then protect the strongest lines so good edits survive the rewrite.</p>
        ${priorityListHtml((overview.actions || []).concat(score.global_actions || []), 'Refresh the snapshot after making edits.')}
      </article>
      <article class="viz-card">
        <h3>Rap fingerprint</h3>
        <div class="viz-two-up">
          ${scoreGaugeHtml(score.overall || 0, 'overall', score.grade?.label || '')}
          <div>
            ${chartCanvasHtml('snapshotComponentRadarChart', componentRadarSvg(comps))}
            <p class="muted tiny-text">Entropy ${escapeHtml(fmt(theory.token_entropy_bits || 0))} bits · compression ${escapeHtml(fmt(theory.compression_ratio || 0))}</p>
          </div>
        </div>
      </article>
      <article class="viz-card wide">
        <div class="viz-card-head"><h3>Line health map</h3><small>Click a tile to jump to that line in the editor.</small></div>
        ${barHeatMapHtml(lines)}
      </article>
      <article class="viz-card wide chart-card">
        <div class="viz-card-head"><h3>Bar-by-bar timeline</h3><small>True Chart.js bar + trend visualization.</small></div>
        ${chartCanvasHtml('snapshotBarTimelineChart', simpleTrendSvg(lines.map((row) => row.overall)))}
      </article>
      ${lineMiniList('Keep these lines', score.strongest_bars || [])}
      ${lineMiniList('Fix these first', score.weakest_bars || [])}
    </div>
  `;
}

function scoreInsightGridHtml(report = {}) {
  const bars = report.bar_scores || [];
  const components = report.component_rows || [];
  return `
    <div class="viz-grid score-viz-grid">
      <article class="viz-card">
        <h3>At a glance</h3>
        <div class="viz-two-up">
          ${scoreGaugeHtml(report.overall || 0, 'system', report.grade?.label || '')}
          <div>
            ${chartCanvasHtml('scoreComponentRadarChart', componentRadarSvg(components))}
          </div>
        </div>
      </article>
      <article class="viz-card">
        <h3>How to use the score</h3>
        <p class="muted">Use the overall score to judge the whole draft, but make decisions with the bar map below. Fix low bars first, then rescore.</p>
        ${priorityListHtml(report.global_actions || [], 'No global actions reported.')}
      </article>
      <article class="viz-card wide">
        <div class="viz-card-head"><h3>Bar score map</h3><small>Weak bars cluster visually. Click any line tile to inspect it.</small></div>
        ${barHeatMapHtml(bars)}
      </article>
      <article class="viz-card wide chart-card">
        <div class="viz-card-head"><h3>Bar-by-bar timeline</h3><small>Line scores with trend overlay.</small></div>
        ${chartCanvasHtml('scoreBarTimelineChart', simpleTrendSvg(bars.map((row) => row.overall)))}
      </article>
      ${lineMiniList('Strongest bars', report.strongest_bars || [])}
      ${lineMiniList('Weakest bars', report.weakest_bars || [])}
    </div>
  `;
}

function compareInsightGridHtml(report = {}) {
  const summary = report.summary || {};
  const changed = report.changed_bars || [];
  const actions = [];
  if (summary.delta > 0) actions.push(`Keep the edit direction: the draft improved by ${summary.delta} points overall.`);
  if (summary.delta < 0) actions.push(`Be careful: the edit reduced the total score by ${Math.abs(summary.delta)} points.`);
  if (summary.improved_bars) actions.push(`${summary.improved_bars} bars improved — keep the strongest edit ideas from those lines.`);
  if (summary.weakened_bars) actions.push(`${summary.weakened_bars} bars weakened — revisit those lines before adopting the edit.`);
  return `
    <div class="viz-grid compare-viz-grid">
      <article class="viz-card action-card-primary">
        <h3>Edit verdict</h3>
        <p class="muted">${escapeHtml(summary.recommendation || summary.verdict || 'Compare two drafts to see what truly improved.')}</p>
        ${priorityListHtml(actions, 'Run a comparison after changing a few lines.')}
      </article>
      <article class="viz-card">
        <h3>Delta overview</h3>
        <div class="viz-two-up">
          ${scoreGaugeHtml(clampPct(50 + Number(summary.delta || 0)), 'delta view', `${summary.delta > 0 ? '+' : ''}${escapeHtml(fmt(summary.delta || 0))} net`)}
          <div class="delta-stat-stack">
            <div><strong>${escapeHtml(summary.original_score ?? 0)}%</strong><small>original</small></div>
            <div><strong>${escapeHtml(summary.edited_score ?? 0)}%</strong><small>edited</small></div>
            <div><strong>${escapeHtml(summary.changed_bars ?? 0)}</strong><small>bars changed</small></div>
          </div>
        </div>
      </article>
      <article class="viz-card wide">
        <div class="viz-card-head"><h3>Change map</h3><small>Green = improved bar, red = weakened bar, gray = flat.</small></div>
        ${barHeatMapHtml(changed, { showDelta: true })}
      </article>
      <article class="viz-card wide chart-card">
        <div class="viz-card-head"><h3>Before/after delta timeline</h3><small>True Chart.js visualization of edit gains and losses.</small></div>
        ${chartCanvasHtml('compareDeltaTimelineChart', '<div class="chart-empty">Compare edits to render the delta chart.</div>')}
      </article>
      ${lineMiniList('Best gains', report.top_gains || [], 'delta')}
      ${lineMiniList('Bars to rework', report.top_losses || [], 'delta')}
    </div>
  `;
}



// System-wide score and edit comparison
function scoreGradeHtml(grade = {}) {
  return `<span class="score-grade">${escapeHtml(grade.letter || '—')}</span><small>${escapeHtml(grade.label || '')}</small>`;
}

function scoreComponentBars(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No component rows available.</p>';
  return `<div class="score-component-list">${rows.map((row) => `
    <div class="score-component-row">
      <div><strong>${escapeHtml(row.label || row.key)}</strong><small>${escapeHtml(row.description || '')}</small></div>
      <div class="score-bar-wrap"><span class="score-bar"><i style="width:${Math.max(0, Math.min(100, Number(row.score || 0)))}%"></i></span></div>
      <b>${escapeHtml(row.score ?? 0)}%</b>
    </div>
  `).join('')}</div>`;
}

function scoreMiniDelta(value) {
  const n = Number(value || 0);
  const cls = n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
  return `<span class="delta ${cls}">${n > 0 ? '+' : ''}${escapeHtml(n)}</span>`;
}

function scoreDigestCards(report = {}) {
  const summary = report.bar_summary || {};
  const best = (report.strongest_bars || [])[0] || {};
  const weak = (report.weakest_bars || [])[0] || {};
  return `
    <div class="score-row score-lab-cards">
      <article class="metric-card score"><span>System score</span><strong>${escapeHtml(report.overall ?? 0)}%</strong>${scoreGradeHtml(report.grade || {})}</article>
      <article class="metric-card"><span>Bars scored</span><strong>${escapeHtml(summary.lines_scored ?? 0)}</strong><small>${escapeHtml(summary.bars_estimated ?? 0)} estimated bars</small></article>
      <article class="metric-card"><span>Avg bar score</span><strong>${escapeHtml(summary.avg_bar_score ?? 0)}%</strong><small>min ${escapeHtml(summary.min_bar_score ?? 0)} · max ${escapeHtml(summary.max_bar_score ?? 0)}</small></article>
      <article class="metric-card"><span>Weakest bar</span><strong>${escapeHtml(weak.overall ?? 0)}%</strong><small>line ${escapeHtml(weak.line_number || '—')}</small></article>
      <article class="metric-card"><span>Strongest bar</span><strong>${escapeHtml(best.overall ?? 0)}%</strong><small>line ${escapeHtml(best.line_number || '—')}</small></article>
    </div>
  `;
}

function barScoreTable(rows = [], limit = 80) {
  if (!rows.length) return '<p class="muted tiny-text">No bar scores available.</p>';
  const body = rows.slice(0, limit).map((row) => {
    const comps = row.component_scores || {};
    const weakest = (row.diagnosis?.weakest_components || []).map((item) => `${item.key}:${item.score}`).join(', ');
    return `
      <tr>
        <td>${escapeHtml(row.assigned_bars || row.bar_index || '—')}</td>
        <td><button type="button" class="line-link line-jump" data-line="${escapeHtml(row.line_number || '')}">${escapeHtml(row.line_number || '—')}</button></td>
        <td><strong>${escapeHtml(row.overall ?? 0)}%</strong><br><small>${escapeHtml(row.grade?.letter || '')} · ${escapeHtml(row.grade?.label || '')}</small></td>
        <td>${escapeHtml(comps.rhyme_power ?? 0)}</td>
        <td>${escapeHtml(comps.cadence_fit ?? 0)}</td>
        <td>${escapeHtml(comps.bar_fit ?? 0)}</td>
        <td>${escapeHtml(comps.meter_stress ?? 0)}</td>
        <td>${escapeHtml(comps.scansion_physics ?? 0)}</td>
        <td>${escapeHtml(comps.content_clarity ?? 0)}</td>
        <td><span class="bar-score-text">${escapeHtml(row.text || '')}</span><br><small>${escapeHtml((row.diagnosis?.issues || []).join('; '))}</small><br><small class="muted">Weakest: ${escapeHtml(weakest || '—')}</small></td>
      </tr>
    `;
  }).join('');
  return `
    <div class="table-wrap score-table-wrap">
      <table class="score-table">
        <thead><tr><th>β bars</th><th>Line</th><th>Total</th><th>Rhyme</th><th>Cadence</th><th>Bar</th><th>Meter</th><th>Physics</th><th>Clarity</th><th>Diagnosis</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function sectionScoreTable(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No section scores available.</p>';
  return `
    <div class="table-wrap compact-table"><table>
      <thead><tr><th>Section</th><th>Lines</th><th>Bars</th><th>Score</th><th>Weak lines</th><th>Reading</th></tr></thead>
      <tbody>${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.label || 'Section')}</td>
          <td>${escapeHtml(row.line_count ?? 0)}</td>
          <td>${escapeHtml(row.bar_count ?? 0)}</td>
          <td><strong>${escapeHtml(row.overall ?? 0)}%</strong> <small>${escapeHtml(row.grade?.letter || '')}</small></td>
          <td>${(row.weak_lines || []).map((n) => `<button type="button" class="line-link line-jump" data-line="${escapeHtml(n)}">${escapeHtml(n)}</button>`).join(' ') || '—'}</td>
          <td>${escapeHtml(row.reading || '')}</td>
        </tr>
      `).join('')}</tbody>
    </table></div>
  `;
}

function renderScoreReport(report, container = scoreGlobalPanelEl) {
  if (!container) return;
  state.scoreReport = report;
  if (!report || !report.available) {
    container.className = 'score-lab-output empty-state';
    container.textContent = report?.error || 'No score report available.';
    return;
  }
  container.className = 'score-lab-output';
  container.innerHTML = `
    <section class="score-report-block">
      <h3>${escapeHtml(report.headline || 'Score report ready.')}</h3>
      ${scoreDigestCards(report)}
      ${scoreInsightGridHtml(report)}
      <div class="score-layout-grid">
        <article class="score-panel-card">
          <h4>Component score formula</h4>
          ${scoreComponentBars(report.component_rows || [])}
        </article>
        <article class="score-panel-card">
          <h4>Global revision actions</h4>
          <ol>${(report.global_actions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
        </article>
      </div>
      <details open>
        <summary>Section scores</summary>
        ${sectionScoreTable(report.section_scores || [])}
      </details>
      <details open>
        <summary>All bar scores</summary>
        ${barScoreTable(report.bar_scores || [])}
      </details>
    </section>
  `;
  renderScoreCharts(report);
}

async function scoreCurrentRap() {
  const lyrics = editor.value;
  updateLocalStats();
  if (countWords(lyrics) < 3) {
    if (scoreLabStatusEl) {
      scoreLabStatusEl.className = 'fit-callout muted';
      scoreLabStatusEl.textContent = 'Type or import at least three words before scoring.';
    }
    switchTab('score');
    return;
  }
  if (scoreLabStatusEl) {
    scoreLabStatusEl.className = 'fit-callout';
    scoreLabStatusEl.textContent = 'Scoring full rap and all bars...';
  }
  switchTab('score');
  try {
    const response = await fetch('/api/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lyrics, coach_mode: coachMode.value, beat_id: state.beatId }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Score failed.');
    if (scoreLabStatusEl) {
      scoreLabStatusEl.className = 'fit-callout';
      scoreLabStatusEl.textContent = payload.headline || 'Score report ready.';
    }
    renderScoreReport(payload);
    jsonBlock.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    if (scoreLabStatusEl) {
      scoreLabStatusEl.className = 'fit-callout muted';
      scoreLabStatusEl.textContent = error.message;
    }
  }
}

function captureScoreBaseline() {
  if (!scoreBaselineInputEl) return;
  scoreBaselineInputEl.value = editor.value;
  try { localStorage.setItem('nmc_score_baseline', scoreBaselineInputEl.value); } catch (_error) {}
  if (scoreLabStatusEl) {
    scoreLabStatusEl.className = 'fit-callout';
    scoreLabStatusEl.textContent = 'Current editor draft captured as baseline.';
  }
  switchTab('score');
}

function loadCurrentIntoEditedBox() {
  if (!scoreEditedInputEl) return;
  scoreEditedInputEl.value = editor.value;
  try { localStorage.setItem('nmc_score_edited_box', scoreEditedInputEl.value); } catch (_error) {}
  switchTab('score');
}

function editComparePayload(useEditorAsEdited = false) {
  const original = scoreBaselineInputEl?.value || '';
  const editedBox = scoreEditedInputEl?.value || '';
  return {
    original_lyrics: original,
    edited_lyrics: useEditorAsEdited ? editor.value : (editedBox || editor.value),
    coach_mode: coachMode.value,
    beat_id: state.beatId,
  };
}

function compareSummaryCards(report = {}) {
  const s = report.summary || {};
  return `
    <div class="score-row score-lab-cards">
      <article class="metric-card score"><span>Edit delta</span><strong>${scoreMiniDelta(s.delta || 0)}</strong><small>${escapeHtml(s.verdict || '')}</small></article>
      <article class="metric-card"><span>Original</span><strong>${escapeHtml(s.original_score ?? 0)}%</strong>${scoreGradeHtml(s.original_grade || {})}</article>
      <article class="metric-card"><span>Edited</span><strong>${escapeHtml(s.edited_score ?? 0)}%</strong>${scoreGradeHtml(s.edited_grade || {})}</article>
      <article class="metric-card"><span>Changed bars</span><strong>${escapeHtml(s.changed_bars ?? 0)}</strong><small>${escapeHtml(s.improved_bars ?? 0)} up · ${escapeHtml(s.weakened_bars ?? 0)} down</small></article>
    </div>
  `;
}

function componentDeltaTable(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No component deltas available.</p>';
  return `<div class="table-wrap compact-table"><table>
    <thead><tr><th>Component</th><th>Original</th><th>Edited</th><th>Δ</th><th>Verdict</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td>${escapeHtml(row.label || row.key)}</td>
      <td>${escapeHtml(row.original ?? 0)}%</td>
      <td>${escapeHtml(row.edited ?? 0)}%</td>
      <td>${scoreMiniDelta(row.delta || 0)}</td>
      <td>${escapeHtml(row.verdict || '')}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function barDeltaTable(rows = []) {
  if (!rows.length) return '<p class="muted tiny-text">No changed bars detected.</p>';
  return `<div class="table-wrap score-table-wrap"><table class="score-table">
    <thead><tr><th>Bar</th><th>Δ</th><th>Old</th><th>New</th><th>Main gain/loss</th><th>Advice</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td>${escapeHtml(row.bar_index ?? '')}<br><small>${escapeHtml(row.status || '')}</small></td>
      <td>${scoreMiniDelta(row.delta || 0)}<br><small>${escapeHtml(row.original_score ?? 0)} → ${escapeHtml(row.edited_score ?? 0)}</small></td>
      <td>${escapeHtml(row.original_text || '')}</td>
      <td>${escapeHtml(row.edited_text || '')}</td>
      <td><small>gain: ${escapeHtml(row.main_gain?.label || '—')} ${scoreMiniDelta(row.main_gain?.delta || 0)}</small><br><small>loss: ${escapeHtml(row.main_loss?.label || '—')} ${scoreMiniDelta(row.main_loss?.delta || 0)}</small></td>
      <td><ol>${(row.edited_advice || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol></td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function renderEditCompare(report) {
  state.editCompareReport = report;
  if (!scoreComparePanelEl) return;
  if (!report || !report.available) {
    scoreComparePanelEl.className = 'score-compare-output empty-state';
    scoreComparePanelEl.textContent = report?.error || 'No comparison available.';
    return;
  }
  scoreComparePanelEl.className = 'score-compare-output';
  renderLyricDiff(state.editCompareInputs?.original || scoreBaselineInputEl?.value || '', state.editCompareInputs?.edited || scoreEditedInputEl?.value || editor.value, report);
  scoreComparePanelEl.innerHTML = `
    <section class="score-report-block compare-report-block">
      <h3>${escapeHtml(report.summary?.recommendation || 'Comparison ready.')}</h3>
      ${compareSummaryCards(report)}
      ${compareInsightGridHtml(report)}
      <div class="score-layout-grid">
        <article class="score-panel-card"><h4>Component deltas</h4>${componentDeltaTable(report.component_deltas || [])}</article>
        <article class="score-panel-card"><h4>Top gains</h4>${barDeltaTable(report.top_gains || [])}</article>
      </div>
      <details open><summary>Top losses / bars to rework</summary>${barDeltaTable(report.top_losses || [])}</details>
      <details><summary>All changed bars</summary>${barDeltaTable(report.changed_bars || [])}</details>
    </section>
  `;
  renderCompareCharts(report);
  jsonBlock.textContent = JSON.stringify(report, null, 2);
}

async function compareEdits(useEditorAsEdited = false) {
  switchTab('score');
  if (scoreLabStatusEl) {
    scoreLabStatusEl.className = 'fit-callout';
    scoreLabStatusEl.textContent = 'Comparing the baseline against the edit...';
  }
  try {
    const payload = editComparePayload(useEditorAsEdited);
    state.editCompareInputs = { original: payload.original_lyrics || '', edited: payload.edited_lyrics || '' };
    const response = await fetch('/api/score/compare-edits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Edit comparison failed.');
    if (scoreLabStatusEl) {
      scoreLabStatusEl.className = 'fit-callout';
      scoreLabStatusEl.textContent = result.summary?.recommendation || 'Edit comparison ready.';
    }
    renderEditCompare(result);
  } catch (error) {
    if (scoreLabStatusEl) {
      scoreLabStatusEl.className = 'fit-callout muted';
      scoreLabStatusEl.textContent = error.message;
    }
  }
}


function lineStatusClass(before, after) {
  if (!before && after) return 'added';
  if (before && !after) return 'deleted';
  if (before === after) return 'same';
  return 'changed';
}

function tokenizeDiffText(text) {
  return String(text || '').match(/[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[^\sA-Za-z0-9]+/g) || [];
}

function wordDiffHtml(before, after, side = 'after') {
  const a = tokenizeDiffText(before);
  const b = tokenizeDiffText(after);
  const rows = Array.from({ length: a.length + 1 }, () => Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      rows[i][j] = a[i] === b[j] ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  const out = [];
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      out.push(`<span class="diff-word keep">${escapeHtml(a[i])}</span>`);
      i += 1;
      j += 1;
    } else if (j < b.length && (i >= a.length || rows[i][j + 1] >= rows[i + 1][j])) {
      if (side === 'after') out.push(`<span class="diff-word added">${escapeHtml(b[j])}</span>`);
      j += 1;
    } else if (i < a.length) {
      if (side === 'before') out.push(`<span class="diff-word deleted">${escapeHtml(a[i])}</span>`);
      i += 1;
    }
  }
  return out.join(' ');
}

function renderLyricDiff(original = '', edited = '', report = {}) {
  if (!lyricDiffPanelEl) return;
  const beforeLines = String(original || '').split(/\r?\n/);
  const afterLines = String(edited || '').split(/\r?\n/);
  const max = Math.max(beforeLines.length, afterLines.length);
  if (!String(original || '').trim() || !String(edited || '').trim()) {
    lyricDiffPanelEl.className = 'lyric-diff-panel empty-state';
    lyricDiffPanelEl.textContent = 'Capture a baseline and compare an edit to see the highlighted before/after lyric diff.';
    return;
  }
  let added = 0;
  let deleted = 0;
  let changed = 0;
  const rows = [];
  for (let idx = 0; idx < max; idx += 1) {
    const before = beforeLines[idx] || '';
    const after = afterLines[idx] || '';
    const status = lineStatusClass(before, after);
    if (status === 'added') added += 1;
    if (status === 'deleted') deleted += 1;
    if (status === 'changed') changed += 1;
    if (status === 'same' && idx > 160) continue;
    rows.push(`
      <article class="diff-row ${status}">
        <div class="diff-line-number">${idx + 1}<small>${status}</small></div>
        <div class="diff-cell before"><strong>Before</strong><p>${status === 'changed' ? wordDiffHtml(before, after, 'before') : escapeHtml(before || '—')}</p></div>
        <div class="diff-cell after"><strong>After</strong><p>${status === 'changed' ? wordDiffHtml(before, after, 'after') : escapeHtml(after || '—')}</p></div>
      </article>
    `);
  }
  const summary = report.summary || {};
  lyricDiffPanelEl.className = 'lyric-diff-panel';
  lyricDiffPanelEl.innerHTML = `
    <div class="diff-head">
      <div><p class="eyebrow">Highlighted lyric diff</p><h3>Before / after edit view</h3></div>
      <div class="diff-stats">
        <span>${changed} changed</span>
        <span>${added} added</span>
        <span>${deleted} deleted</span>
        ${summary.delta !== undefined ? `<span class="delta ${Number(summary.delta || 0) >= 0 ? 'positive' : 'negative'}">${Number(summary.delta || 0) > 0 ? '+' : ''}${escapeHtml(summary.delta)} score</span>` : ''}
      </div>
    </div>
    <p class="muted tiny-text">Use this like a revision audit: green words were added, red words were removed, and unchanged words stay neutral.</p>
    <div class="diff-list">${rows.join('')}</div>
  `;
}

function reportPayload(kind) {
  if (kind === 'compare') {
    return { ...editComparePayload(false), kind };
  }
  return { kind, lyrics: editor.value, coach_mode: coachMode.value, beat_id: state.beatId };
}

function filenameFromDisposition(disposition, fallback) {
  const match = String(disposition || '').match(/filename="?([^";]+)"?/i);
  return match ? match[1] : fallback;
}

async function downloadServerReport(kind, format) {
  const endpoint = `/api/report/${format}`;
  const payload = reportPayload(kind);
  const statusEl = kind === 'snapshot' ? staticStatusEl : scoreLabStatusEl;
  if (kind !== 'compare' && countWords(payload.lyrics || '') < 3) {
    if (statusEl) {
      statusEl.className = 'fit-callout muted';
      statusEl.textContent = 'Type or import at least three words before downloading a report.';
    }
    return;
  }
  if (kind === 'compare' && (!String(payload.original_lyrics || '').trim() || !String(payload.edited_lyrics || '').trim())) {
    if (statusEl) {
      statusEl.className = 'fit-callout muted';
      statusEl.textContent = 'Capture or paste both versions before downloading an edit comparison.';
    }
    return;
  }
  if (statusEl) {
    statusEl.className = 'fit-callout';
    statusEl.textContent = `Preparing ${kind} ${format.toUpperCase()} report...`;
  }
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let message = `Report download failed (${response.status}).`;
      try {
        const errorPayload = await response.json();
        message = errorPayload.error || errorPayload.detail || message;
      } catch (_error) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get('Content-Disposition'), `nmc_${kind}_report.${format}`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (statusEl) statusEl.textContent = `${format.toUpperCase()} report downloaded.`;
  } catch (error) {
    if (statusEl) {
      statusEl.className = 'fit-callout muted';
      statusEl.textContent = error.message;
    }
  }
}

function loadScoreBaselineFromStorage() {
  try {
    const baseline = localStorage.getItem('nmc_score_baseline') || '';
    const edited = localStorage.getItem('nmc_score_edited_box') || '';
    if (scoreBaselineInputEl && baseline) scoreBaselineInputEl.value = baseline;
    if (scoreEditedInputEl && edited) scoreEditedInputEl.value = edited;
  } catch (_error) {}
}

scoreBaselineInputEl?.addEventListener('input', () => {
  try { localStorage.setItem('nmc_score_baseline', scoreBaselineInputEl.value); } catch (_error) {}
  state.editCompareInputs = { original: scoreBaselineInputEl.value, edited: scoreEditedInputEl?.value || editor.value };
  if (state.editCompareReport?.available) renderLyricDiff(scoreBaselineInputEl.value, scoreEditedInputEl?.value || editor.value, state.editCompareReport);
});
scoreEditedInputEl?.addEventListener('input', () => {
  try { localStorage.setItem('nmc_score_edited_box', scoreEditedInputEl.value); } catch (_error) {}
  state.editCompareInputs = { original: scoreBaselineInputEl?.value || '', edited: scoreEditedInputEl.value };
  if (state.editCompareReport?.available) renderLyricDiff(scoreBaselineInputEl?.value || '', scoreEditedInputEl.value, state.editCompareReport);
});


// Account + saved rap library
function accountSetStatus(message, kind = 'muted') {
  if (!accountStatusEl) return;
  accountStatusEl.className = kind === 'ok' ? 'fit-callout' : 'fit-callout muted';
  accountStatusEl.textContent = message || '';
}

function updateAccountChrome() {
  const user = state.currentUser;
  if (accountStateMetricEl) accountStateMetricEl.textContent = user ? 'Saved' : 'Guest';
  if (accountStateSmallEl) accountStateSmallEl.textContent = user ? `${user.display_name || user.email}` : 'login to save raps';
  if (authFormsEl) authFormsEl.classList.toggle('hidden', Boolean(user));
  if (accountWorkspaceEl) accountWorkspaceEl.classList.toggle('hidden', !user);
  if (user) {
    accountSetStatus(`Logged in as ${user.display_name || user.email}. You can save and load raps from this server.`, 'ok');
  } else {
    accountSetStatus('Guest mode: local browser autosave is available, but server saves require login.', 'muted');
  }
}

function guessRapTitle() {
  if (rapTitleInputEl && rapTitleInputEl.value.trim()) return rapTitleInputEl.value.trim();
  const firstLine = (editor.value || '').split(/\r?\n/).map((line) => line.trim()).find((line) => line && !line.startsWith('//')) || '';
  return firstLine.slice(0, 70) || 'Untitled rap';
}

async function accountFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  let data = null;
  try { data = await response.json(); } catch (_error) { data = { error: await response.text() }; }
  if (!response.ok) throw new Error(data?.error || `Request failed: ${response.status}`);
  return data;
}

async function loadAccountState() {
  if (!accountStatusEl && !accountStateMetricEl) return;
  try {
    const data = await accountFetch('/api/auth/me');
    state.currentUser = data.user || null;
    state.accountLoaded = true;
    updateAccountChrome();
    if (state.currentUser) await loadSavedRaps(false);
  } catch (error) {
    state.currentUser = null;
    updateAccountChrome();
    accountSetStatus(error.message || 'Could not check account state.', 'muted');
  }
}


function getRapTagsInput() { return $('#rapTagsInput'); }
function getRapNotesInput() { return $('#rapNotesInput'); }
function getRapPinnedInput() { return $('#rapPinnedInput'); }
function getRapArchivedInput() { return $('#rapArchivedInput'); }
function getSavedRapSort() { return $('#savedRapSort'); }
function getSavedRapIncludeArchived() { return $('#savedRapIncludeArchived'); }
function getSavedRapStatsEl() { return $('#savedRapStats'); }
function getSavedRapVersionsEl() { return $('#savedRapVersions'); }

function parseTagInput(value) {
  return String(value || '')
    .split(/[,#\n]+/)
    .map((item) => item.trim().toLowerCase().replace(/[^a-z0-9_\- ]+/g, '').replace(/\s+/g, '-').replace(/^-+|-+$/g, ''))
    .filter(Boolean)
    .filter((item, index, arr) => arr.indexOf(item) === index)
    .slice(0, 12);
}

function formatTagInput(tags = []) {
  return (Array.isArray(tags) ? tags : []).join(', ');
}

function savedRapStatsHtml(stats = {}) {
  const tags = (stats.top_tags || []).slice(0, 10);
  return `
    <div class="saved-suite-grid">
      <article class="metric-card score"><span>Saved raps</span><strong>${escapeHtml(stats.rap_count ?? 0)}</strong><small>${escapeHtml(stats.active_count ?? 0)} active · ${escapeHtml(stats.archived_count ?? 0)} archived</small></article>
      <article class="metric-card"><span>Versions</span><strong>${escapeHtml(stats.version_count ?? 0)}</strong><small>restore points</small></article>
      <article class="metric-card"><span>Total words</span><strong>${escapeHtml(stats.total_words ?? 0)}</strong><small>${escapeHtml(stats.total_lines ?? 0)} lines</small></article>
      <article class="metric-card"><span>Avg length</span><strong>${escapeHtml(stats.avg_words ?? 0)}</strong><small>words per rap</small></article>
    </div>
    ${tags.length ? `<div class="saved-tag-cloud">${tags.map((row) => `<button type="button" class="chip saved-tag-filter" data-tag="${escapeHtml(row.tag)}">#${escapeHtml(row.tag)} <small>${escapeHtml(row.count)}</small></button>`).join('')}</div>` : ''}
  `;
}

async function loadSavedRapStats() {
  if (!state.currentUser) return;
  const statsEl = getSavedRapStatsEl();
  if (!statsEl) return;
  try {
    const data = await accountFetch('/api/raps/stats');
    statsEl.className = 'saved-suite-stats';
    statsEl.innerHTML = savedRapStatsHtml(data.stats || {});
  } catch (error) {
    statsEl.className = 'saved-suite-stats empty-state';
    statsEl.textContent = error.message || 'Could not load library stats.';
  }
}

function savedRapCardHtml(rap = {}) {
  const selected = state.selectedRapId === rap.id;
  const tags = (rap.tags || []).slice(0, 4).map((tag) => `<span>#${escapeHtml(tag)}</span>`).join('');
  const score = rap.last_score !== null && rap.last_score !== undefined ? `${escapeHtml(fmt(rap.last_score))}%` : '—';
  return `
    <button type="button" class="saved-rap-card enhanced ${selected ? 'active' : ''} ${rap.archived ? 'archived' : ''}" data-rap-id="${escapeHtml(rap.id)}">
      <div class="saved-card-head">
        <strong>${rap.pinned ? '📌 ' : ''}${escapeHtml(rap.title || 'Untitled rap')}</strong>
        <b>${score}</b>
      </div>
      <span>${escapeHtml(rap.word_count ?? 0)} words · ${escapeHtml(rap.line_count ?? 0)} lines · ${escapeHtml(rap.version_count ?? 0)} versions</span>
      <small>Updated ${escapeHtml(rap.updated_at || '')}${rap.archived ? ' · archived' : ''}</small>
      <em>${escapeHtml(rap.preview || 'No preview yet.')}</em>
      ${tags ? `<div class="saved-card-tags">${tags}</div>` : ''}
    </button>
  `;
}

function renderSavedRaps() {
  if (!savedRapsListEl) return;
  if (!state.currentUser) {
    savedRapsListEl.className = 'saved-raps-list empty-state';
    savedRapsListEl.textContent = 'Login to see saved raps.';
    return;
  }
  const rows = state.savedRaps || [];
  if (!rows.length) {
    savedRapsListEl.className = 'saved-raps-list empty-state';
    savedRapsListEl.textContent = 'No saved raps match this view. Clear the search/filter or save the current draft.';
    return;
  }
  savedRapsListEl.className = 'saved-raps-list';
  savedRapsListEl.innerHTML = rows.map(savedRapCardHtml).join('');
}

function populateRapForm(rap = {}) {
  if (rapTitleInputEl) rapTitleInputEl.value = rap.title || '';
  const tagsEl = getRapTagsInput();
  if (tagsEl) tagsEl.value = formatTagInput(rap.tags || []);
  const notesEl = getRapNotesInput();
  if (notesEl) notesEl.value = rap.notes || '';
  const pinnedEl = getRapPinnedInput();
  if (pinnedEl) pinnedEl.checked = Boolean(rap.pinned);
  const archivedEl = getRapArchivedInput();
  if (archivedEl) archivedEl.checked = Boolean(rap.archived);
}

function selectedRapBadges(rap = {}) {
  const tags = (rap.tags || []).map((tag) => `<span class="badge">#${escapeHtml(tag)}</span>`).join('');
  const flags = `${rap.pinned ? '<span class="badge">Pinned</span>' : ''}${rap.archived ? '<span class="badge">Archived</span>' : ''}`;
  return `<div class="badges">${flags}${tags}</div>`;
}

function renderSelectedRapInfo(rap = null) {
  if (!selectedRapInfoEl) return;
  if (!rap) {
    selectedRapInfoEl.className = 'empty-state';
    selectedRapInfoEl.textContent = 'Select a saved rap to load, update, duplicate, compare, archive, or restore an older version.';
    return;
  }
  state.selectedRap = rap;
  selectedRapInfoEl.className = 'selected-rap-info enhanced';
  selectedRapInfoEl.innerHTML = `
    <h3>${escapeHtml(rap.title || 'Untitled rap')}</h3>
    ${selectedRapBadges(rap)}
    <p class="muted">${escapeHtml(rap.word_count ?? 0)} words · ${escapeHtml(rap.line_count ?? 0)} lines · score ${escapeHtml(rap.last_score ?? '—')} · mode ${escapeHtml(rap.coach_mode || 'match')}</p>
    <p class="muted tiny-text">Created ${escapeHtml(rap.created_at || '')}<br>Updated ${escapeHtml(rap.updated_at || '')}<br>Versions ${escapeHtml(rap.version_count ?? 0)}</p>
    ${rap.notes ? `<div class="fit-callout muted"><strong>Notes</strong><p>${escapeHtml(rap.notes)}</p></div>` : ''}
    <pre>${escapeHtml(rap.preview || '')}</pre>
  `;
}

function renderSavedRapVersions(versions = []) {
  const versionsEl = getSavedRapVersionsEl();
  if (!versionsEl) return;
  if (!state.selectedRapId) {
    versionsEl.className = 'saved-versions-panel empty-state';
    versionsEl.textContent = 'Version history will appear after selecting a rap.';
    return;
  }
  if (!versions.length) {
    versionsEl.className = 'saved-versions-panel empty-state';
    versionsEl.textContent = 'No versions yet. Save a checkpoint to create a restore point.';
    return;
  }
  versionsEl.className = 'saved-versions-panel';
  versionsEl.innerHTML = `
    <div class="section-head compact mini-head">
      <div><p class="eyebrow">Version history</p><h2>Restore points</h2></div>
      <button type="button" class="ghost" id="reloadSavedRapVersions">Reload versions</button>
    </div>
    <div class="version-list">
      ${versions.map((version) => `
        <article class="version-card" data-version-id="${escapeHtml(version.id)}">
          <div>
            <strong>v${escapeHtml(version.version_number)} · ${escapeHtml(version.title || 'Untitled rap')}</strong>
            <small>${escapeHtml(version.created_at || '')} · ${escapeHtml(version.word_count ?? 0)} words · ${escapeHtml(version.line_count ?? 0)} lines</small>
            <p>${escapeHtml(version.change_note || 'Saved checkpoint')}</p>
          </div>
          <div class="version-actions">
            <button type="button" class="tiny ghost load-version" data-version-id="${escapeHtml(version.id)}">Preview/load</button>
            <button type="button" class="tiny restore-version" data-version-id="${escapeHtml(version.id)}">Restore</button>
          </div>
        </article>
      `).join('')}
    </div>
  `;
}

async function loadSavedRapVersions(showStatus = false) {
  if (!state.currentUser || !state.selectedRapId) return;
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/versions`);
    state.selectedRapVersions = data.versions || [];
    renderSavedRapVersions(state.selectedRapVersions);
    if (showStatus) accountSetStatus(`Loaded ${state.selectedRapVersions.length} versions.`, 'ok');
  } catch (error) {
    const versionsEl = getSavedRapVersionsEl();
    if (versionsEl) {
      versionsEl.className = 'saved-versions-panel empty-state';
      versionsEl.textContent = error.message || 'Could not load versions.';
    }
  }
}

async function loadSavedRaps(showStatus = true) {
  if (!state.currentUser) return;
  if (showStatus) accountSetStatus('Loading saved raps...', 'muted');
  const q = savedRapSearchEl?.value || '';
  const sort = getSavedRapSort()?.value || 'updated_desc';
  const includeArchived = getSavedRapIncludeArchived()?.checked ? '1' : '0';
  const data = await accountFetch(`/api/raps?q=${encodeURIComponent(q)}&limit=150&sort=${encodeURIComponent(sort)}&include_archived=${includeArchived}`);
  state.savedRaps = data.raps || [];
  renderSavedRaps();
  await loadSavedRapStats();
  if (showStatus) accountSetStatus(`Loaded ${state.savedRaps.length} saved rap${state.savedRaps.length === 1 ? '' : 's'}.`, 'ok');
}

async function loginAccount(event) {
  event.preventDefault();
  try {
    accountSetStatus('Logging in...', 'muted');
    const data = await accountFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: loginEmailEl?.value || '', password: loginPasswordEl?.value || '' }),
    });
    state.currentUser = data.user || null;
    updateAccountChrome();
    await loadSavedRaps(false);
    accountSetStatus('Login successful. Your saved rap library is ready.', 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function registerAccount(event) {
  event.preventDefault();
  try {
    accountSetStatus('Creating account...', 'muted');
    const data = await accountFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        display_name: registerNameEl?.value || '',
        email: registerEmailEl?.value || '',
        password: registerPasswordEl?.value || '',
      }),
    });
    state.currentUser = data.user || null;
    updateAccountChrome();
    await loadSavedRaps(false);
    accountSetStatus('Account created. You can save this rap now.', 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function logoutAccount() {
  try { await accountFetch('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) }); } catch (_error) {}
  state.currentUser = null;
  state.savedRaps = [];
  state.selectedRapId = null;
  state.currentRapId = null;
  state.selectedRap = null;
  state.selectedRapVersions = [];
  updateAccountChrome();
  renderSavedRaps();
  renderSelectedRapInfo(null);
  renderSavedRapVersions([]);
}

function savePayloadFromEditor({ checkpoint = false } = {}) {
  const snapshotScore = state.scoreReport?.overall ?? state.staticReport?.score_report?.overall ?? null;
  const compactSnapshot = state.staticReport ? {
    generated_at: new Date().toISOString(),
    summary: state.staticReport.overview?.headline || state.staticReport.summary || '',
    score: state.staticReport.score_report?.overall ?? null,
    actions: (state.staticReport.overview?.actions || []).slice(0, 6),
  } : null;
  return {
    title: guessRapTitle(),
    lyrics: editor.value || '',
    coach_mode: coachMode?.value || 'match',
    tags: parseTagInput(getRapTagsInput()?.value || ''),
    notes: getRapNotesInput()?.value || '',
    pinned: Boolean(getRapPinnedInput()?.checked),
    archived: Boolean(getRapArchivedInput()?.checked),
    last_score: snapshotScore,
    last_snapshot: compactSnapshot,
    save_version: true,
    change_note: checkpoint ? 'Manual checkpoint' : 'Saved from editor',
    metadata: {
      saved_from: 'full_lab_editor',
      beat_id: state.beatId || null,
      app_version: window.NMC_BOOTSTRAP?.version || '',
      word_count: countWords(editor.value || ''),
      line_count: countLines(editor.value || ''),
    },
  };
}

async function saveRap({ updateExisting = false } = {}) {
  if (!state.currentUser) {
    switchTab('account');
    accountSetStatus('Login or create an account before saving raps to the server.', 'muted');
    return;
  }
  const payload = savePayloadFromEditor();
  try {
    accountSetStatus(updateExisting ? 'Updating saved rap...' : 'Saving rap...', 'muted');
    const existingId = state.currentRapId || state.selectedRapId;
    const url = updateExisting && existingId ? `/api/raps/${encodeURIComponent(existingId)}` : '/api/raps';
    const method = updateExisting && existingId ? 'PATCH' : 'POST';
    const data = await accountFetch(url, { method, body: JSON.stringify(payload) });
    const rap = data.rap;
    state.currentRapId = rap.id;
    state.selectedRapId = rap.id;
    populateRapForm(rap);
    await loadSavedRaps(false);
    renderSelectedRapInfo(rap);
    await loadSavedRapVersions(false);
    accountSetStatus(`${method === 'POST' ? 'Saved' : 'Updated'} “${rap.title}”. Version history updated.`, 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function saveVersionCheckpoint() {
  if (!state.currentUser) {
    switchTab('account');
    accountSetStatus('Login first, then save a checkpoint.', 'muted');
    return;
  }
  const existingId = state.currentRapId || state.selectedRapId;
  if (!existingId) {
    await saveRap({ updateExisting: false });
    return;
  }
  try {
    accountSetStatus('Saving checkpoint...', 'muted');
    const payload = savePayloadFromEditor({ checkpoint: true });
    payload.change_note = 'Manual checkpoint before next revision';
    const data = await accountFetch(`/api/raps/${encodeURIComponent(existingId)}`, { method: 'PATCH', body: JSON.stringify(payload) });
    renderSelectedRapInfo(data.rap);
    await loadSavedRaps(false);
    await loadSavedRapVersions(false);
    accountSetStatus('Checkpoint saved. You can restore it later from Version history.', 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function selectSavedRap(rapId, loadFull = false) {
  if (!rapId || !state.currentUser) return;
  state.selectedRapId = rapId;
  renderSavedRaps();
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(rapId)}`);
    const rap = data.rap;
    populateRapForm(rap);
    renderSelectedRapInfo(rap);
    await loadSavedRapVersions(false);
    if (loadFull) loadRapIntoEditor(rap);
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

function loadRapIntoEditor(rap) {
  if (!rap) return;
  editor.value = rap.lyrics || '';
  state.currentRapId = rap.id;
  state.selectedRapId = rap.id;
  state.selectedRap = rap;
  populateRapForm(rap);
  if (coachMode && rap.coach_mode && Array.from(coachMode.options).some((opt) => opt.value === rap.coach_mode)) coachMode.value = rap.coach_mode;
  try { localStorage.setItem('nmc_editing_lab_draft', editor.value); } catch (_error) {}
  updateLocalStats();
  updateGutter();
  switchTab('editor');
  setStatus('complete', 'Loaded', `loaded ${rap.title || 'saved rap'}`);
  queueLiveRhymeJob(true);
}

async function loadSelectedRapIntoEditor() {
  if (!state.selectedRapId) {
    accountSetStatus('Select a saved rap first.', 'muted');
    return;
  }
  const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}`);
  loadRapIntoEditor(data.rap);
}

async function duplicateSelectedRap() {
  if (!state.selectedRapId) {
    accountSetStatus('Select a saved rap first.', 'muted');
    return;
  }
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/duplicate`, { method: 'POST', body: JSON.stringify({}) });
    state.selectedRapId = data.rap.id;
    state.currentRapId = data.rap.id;
    await loadSavedRaps(false);
    populateRapForm(data.rap);
    renderSelectedRapInfo(data.rap);
    await loadSavedRapVersions(false);
    accountSetStatus(`Duplicated “${data.rap.title}”.`, 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function togglePinSelectedRap() {
  if (!state.selectedRapId) return accountSetStatus('Select a saved rap first.', 'muted');
  const current = state.selectedRap || state.savedRaps.find((row) => row.id === state.selectedRapId) || {};
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/pin`, { method: 'POST', body: JSON.stringify({ pinned: !current.pinned }) });
    populateRapForm(data.rap);
    renderSelectedRapInfo(data.rap);
    await loadSavedRaps(false);
    accountSetStatus(data.rap.pinned ? 'Pinned rap.' : 'Unpinned rap.', 'ok');
  } catch (error) { accountSetStatus(error.message, 'muted'); }
}

async function toggleArchiveSelectedRap() {
  if (!state.selectedRapId) return accountSetStatus('Select a saved rap first.', 'muted');
  const current = state.selectedRap || state.savedRaps.find((row) => row.id === state.selectedRapId) || {};
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/archive`, { method: 'POST', body: JSON.stringify({ archived: !current.archived }) });
    populateRapForm(data.rap);
    renderSelectedRapInfo(data.rap);
    await loadSavedRaps(false);
    accountSetStatus(data.rap.archived ? 'Archived rap. Enable “include archived” to show it in the list.' : 'Unarchived rap.', 'ok');
  } catch (error) { accountSetStatus(error.message, 'muted'); }
}

async function deleteSelectedRap() {
  if (!state.selectedRapId) {
    accountSetStatus('Select a saved rap first.', 'muted');
    return;
  }
  const rap = state.savedRaps.find((row) => row.id === state.selectedRapId) || state.selectedRap;
  if (!confirm(`Delete “${rap?.title || 'this saved rap'}”? This removes it from the library.`)) return;
  try {
    await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}`, { method: 'DELETE' });
    if (state.currentRapId === state.selectedRapId) state.currentRapId = null;
    state.selectedRapId = null;
    state.selectedRap = null;
    await loadSavedRaps(false);
    renderSelectedRapInfo(null);
    renderSavedRapVersions([]);
    accountSetStatus('Saved rap deleted.', 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function loadVersionIntoEditor(versionId) {
  if (!state.selectedRapId || !versionId) return;
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/versions/${encodeURIComponent(versionId)}`);
    const version = data.version;
    editor.value = version.lyrics || '';
    if (rapTitleInputEl) rapTitleInputEl.value = version.title || '';
    if (coachMode && version.coach_mode && Array.from(coachMode.options).some((opt) => opt.value === version.coach_mode)) coachMode.value = version.coach_mode;
    updateLocalStats();
    switchTab('editor');
    accountSetStatus(`Loaded version ${version.version_number} into the editor. Press Update selected to restore permanently.`, 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function restoreVersion(versionId) {
  if (!state.selectedRapId || !versionId) return;
  if (!confirm('Restore this version as the current saved rap? A new checkpoint will be created.')) return;
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}/versions/${encodeURIComponent(versionId)}/restore`, { method: 'POST', body: JSON.stringify({}) });
    populateRapForm(data.rap);
    renderSelectedRapInfo(data.rap);
    loadRapIntoEditor(data.rap);
    await loadSavedRaps(false);
    await loadSavedRapVersions(false);
    accountSetStatus('Version restored and loaded into the editor.', 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function compareSelectedRapToEditor() {
  if (!state.selectedRapId) return accountSetStatus('Select a saved rap first.', 'muted');
  try {
    const data = await accountFetch(`/api/raps/${encodeURIComponent(state.selectedRapId)}`);
    if (scoreBaselineInputEl) scoreBaselineInputEl.value = data.rap.lyrics || '';
    if (scoreEditedInputEl) scoreEditedInputEl.value = editor.value || '';
    switchTab('score');
    await compareEdits(false);
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

async function exportRapsJson() {
  try {
    const data = await accountFetch('/api/raps/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `nmc-saved-raps-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 500);
    accountSetStatus('Exported saved rap library JSON.', 'ok');
  } catch (error) { accountSetStatus(error.message, 'muted'); }
}

async function importRapsJson(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const data = await accountFetch('/api/raps/import', { method: 'POST', body: JSON.stringify(payload) });
    await loadSavedRaps(false);
    accountSetStatus(`Imported ${data.created_count || 0} raps. Skipped ${data.skipped_count || 0}.`, 'ok');
  } catch (error) {
    accountSetStatus(error.message || 'Import failed.', 'muted');
  }
}

async function accountDiagnostics() {
  try {
    const data = await accountFetch('/api/account/diagnostics');
    accountSetStatus(`Account DB ready. Users: ${data.database?.users ?? 0}. Saved raps: ${data.database?.raps ?? 0}. Versions: ${data.database?.versions ?? 0}. DB: ${data.database?.path || 'default'}`, 'ok');
  } catch (error) {
    accountSetStatus(error.message, 'muted');
  }
}

// Tabs
$$('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    switchTab(tab.dataset.tab);
  });
});

// Editor events
editor.addEventListener('input', handleEditorActivity);
editor.addEventListener('keyup', handleEditorActivity);
editor.addEventListener('mouseup', () => scheduleSelectedWordRhyme(false));
editor.addEventListener('select', () => scheduleSelectedWordRhyme(false));
editor.addEventListener('dblclick', () => scheduleSelectedWordRhyme(true));
editor.addEventListener('click', () => { handleEditorActivity(); scheduleSelectedWordRhyme(false); });
document.addEventListener('selectionchange', () => {
  if (document.activeElement === editor && editor.selectionStart !== editor.selectionEnd) scheduleSelectedWordRhyme(false);
});
editor.addEventListener('scroll', () => { gutter.scrollTop = editor.scrollTop; });
coachMode.addEventListener('change', () => { queueLiveRhymeJob(true); });
$('#analyzeNow').addEventListener('click', () => { queueLiveRhymeJob(true); });
$('#staticBreakdownNow').addEventListener('click', () => generateStaticBreakdown(false));
$('#generateStaticBreakdown').addEventListener('click', () => generateStaticBreakdown(false));
$('#generateFullSnapshot')?.addEventListener('click', () => generateStaticBreakdown(true));
$('#refreshLine').addEventListener('click', () => queueLiveRhymeJob(true));
$('#downloadDraft').addEventListener('click', downloadDraft);
$('#loadSampleTop').addEventListener('click', loadSample);
$('#snapshotNowTop')?.addEventListener('click', () => generateStaticBreakdown(false));
$('#openEditorTop')?.addEventListener('click', () => switchTab('editor'));
$('#runLiveRhymeNow')?.addEventListener('click', () => queueLiveRhymeJob(true));
$('#runLiveRhymeSync')?.addEventListener('click', () => {
  state.liveRhymeSequence += 1;
  const token = state.liveRhymeSequence;
  const context = liveRhymeContextPayload(false);
  state.lastLiveRhymeLyricsSent = `${context.lyrics}|${context.context_offset_lines}`;
  state.lastLiveRhymeActiveLine = context.source_active_line || activeLineNumber();
  runLiveRhymeSync(context.lyrics, context.active_line, token, 'manual sync', context);
});
$('#testLiveRhymeRoutes')?.addEventListener('click', testLiveRhymeRoutes);
$('#testPythonAnywhere')?.addEventListener('click', testPythonAnywhereDiagnostics);
analyzeHighlightedWordBtn?.addEventListener('click', () => queueSelectedWordRhyme(true));
$('#openSentenceTop')?.addEventListener('click', () => { switchTab('sentence'); pullActiveSentenceToLab(); });
$('#openSentencePatternsTop')?.addEventListener('click', () => { switchTab('sentence-patterns'); if (!sentencePatternInputEl?.value.trim()) loadEditorSentencePatterns(); });
$('#openPhysicsTop')?.addEventListener('click', () => switchTab('physics'));
$('#openLiveTop')?.addEventListener('click', () => switchTab('live'));
$('#openSongTop')?.addEventListener('click', () => switchTab('song'));
$('#refreshTheorySnapshot')?.addEventListener('click', () => generateStaticBreakdown(false));
$('#refreshComparisonSnapshot')?.addEventListener('click', () => generateStaticBreakdown(false));
$('#physicsRefreshSnapshot')?.addEventListener('click', runScansionPhysics);
$('#copyPhysicsJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.physicsReport || {}, null, 2));
    $('#copyPhysicsJson').textContent = 'Copied';
    setTimeout(() => { $('#copyPhysicsJson').textContent = 'Copy physics JSON'; }, 900);
  } catch (_error) {
    $('#copyPhysicsJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copyPhysicsJson').textContent = 'Copy physics JSON'; }, 900);
  }
});
$('#lyricsFile').addEventListener('change', (event) => importLyrics(event.target.files[0]));
$('#beatFile').addEventListener('change', (event) => uploadBeat(event.target.files[0]));
$('#songBeatFile')?.addEventListener('change', (event) => uploadBeat(event.target.files[0]));
$('#runBeatDiagnostics')?.addEventListener('click', runBeatDiagnostics);
$('#buildSongTiming')?.addEventListener('click', buildSongTiming);
$('#renderSongNow')?.addEventListener('click', renderSongNow);
$('#testSongVoice')?.addEventListener('click', testSongVoice);
$('#copySongJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.songReport || {}, null, 2));
    $('#copySongJson').textContent = 'Copied';
    setTimeout(() => { $('#copySongJson').textContent = 'Copy render JSON'; }, 900);
  } catch (_error) {
    $('#copySongJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copySongJson').textContent = 'Copy render JSON'; }, 900);
  }
});
$('#analyzeSentenceNow')?.addEventListener('click', () => analyzeSentenceNow(true));
$('#pullActiveSentence')?.addEventListener('click', pullActiveSentenceToLab);
$('#applySentenceToEditor')?.addEventListener('click', applySentenceToEditor);
sentenceInputEl?.addEventListener('input', scheduleSentenceAnalysis);
coachMode?.addEventListener('change', () => {
  if ($('#tab-sentence')?.classList.contains('active')) analyzeSentenceNow(true);
  if ($('#tab-sentence-patterns')?.classList.contains('active') && sentencePatternInputEl?.value.trim()) compareSentencePatternsNow();
});
$('#compareSentencePatterns')?.addEventListener('click', compareSentencePatternsNow);
$('#loadEditorSentencePatterns')?.addEventListener('click', loadEditorSentencePatterns);
$('#loadActiveSentencePattern')?.addEventListener('click', addActiveSentencePattern);
$('#copySentencePatternJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.sentencePatternReport || {}, null, 2));
    $('#copySentencePatternJson').textContent = 'Copied';
    setTimeout(() => { $('#copySentencePatternJson').textContent = 'Copy pattern JSON'; }, 900);
  } catch (_error) {
    $('#copySentencePatternJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copySentencePatternJson').textContent = 'Copy pattern JSON'; }, 900);
  }
});

$('#copySentenceJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.sentenceReport || {}, null, 2));
    $('#copySentenceJson').textContent = 'Copied';
    setTimeout(() => { $('#copySentenceJson').textContent = 'Copy JSON'; }, 900);
  } catch (_error) {
    $('#copySentenceJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copySentenceJson').textContent = 'Copy JSON'; }, 900);
  }
});

$('#lineFilter').addEventListener('input', (event) => {
  const needle = event.target.value.trim().toLowerCase();
  $$('.line-card').forEach((card) => {
    const hay = card.dataset.search || card.textContent.toLowerCase();
    card.style.display = hay.includes(needle) ? '' : 'none';
  });
});

$('#staticLineFilter').addEventListener('input', (event) => {
  const needle = event.target.value.trim().toLowerCase();
  $$('.static-line-card').forEach((card) => {
    const hay = card.dataset.search || card.textContent.toLowerCase();
    card.style.display = hay.includes(needle) ? '' : 'none';
  });
});

$('#copyJson').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(jsonBlock.textContent || '{}');
    $('#copyJson').textContent = 'Copied';
    setTimeout(() => { $('#copyJson').textContent = 'Copy JSON'; }, 900);
  } catch (_error) {
    $('#copyJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copyJson').textContent = 'Copy JSON'; }, 900);
  }
});

$('#copyStaticReport').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(staticReportToText(state.staticReport));
    $('#copyStaticReport').textContent = 'Copied';
    setTimeout(() => { $('#copyStaticReport').textContent = 'Copy report'; }, 900);
  } catch (_error) {
    $('#copyStaticReport').textContent = 'Copy failed';
    setTimeout(() => { $('#copyStaticReport').textContent = 'Copy report'; }, 900);
  }
});


async function sendBetaFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#feedbackStatus');
  const messageEl = $('#feedbackMessage');
  const message = (messageEl?.value || '').trim();
  if (!message) {
    if (status) status.textContent = 'Write a short note before sending feedback.';
    return;
  }
  const includeDraft = $('#feedbackIncludeDraft')?.checked;
  const payload = {
    kind: $('#feedbackKind')?.value || 'general',
    rating: $('#feedbackRating')?.value || '',
    email: $('#feedbackEmail')?.value || '',
    message,
    page: location.pathname + location.hash,
    draft_excerpt: includeDraft ? (editor.value || '').slice(0, 1500) : '',
  };
  if (status) {
    status.textContent = 'Sending feedback...';
    status.className = 'muted';
  }
  try {
    const response = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Feedback failed.');
    if (status) {
      status.textContent = `Feedback sent. ID: ${data.feedback_id}`;
      status.className = 'fit-callout';
    }
    form.reset();
  } catch (error) {
    if (status) {
      status.textContent = error.message;
      status.className = 'fit-callout muted';
    }
  }
}

async function checkBetaHealth() {
  const status = $('#betaHealthStatus');
  if (status) {
    status.textContent = 'Checking /healthz and /readyz...';
    status.className = 'fit-callout muted';
  }
  try {
    const [healthRes, readyRes] = await Promise.all([fetch('/healthz'), fetch('/readyz')]);
    const health = await healthRes.json();
    const ready = await readyRes.json();
    if (!healthRes.ok || !readyRes.ok) throw new Error('Health or readiness check failed.');
    if (status) {
      status.textContent = `${health.app || 'App'} ${health.version || ''} is healthy. Corpus lines: ${ready.corpus_lines ?? 0}. Jobs: ${ready.jobs_in_memory ?? 0}. Beats: ${ready.beats_in_memory ?? 0}.`;
      status.className = 'fit-callout';
    }
  } catch (error) {
    if (status) {
      status.textContent = error.message;
      status.className = 'fit-callout muted';
    }
  }
}


async function testLiveRhymeRoutes() {
  setLiveRhymeStatus('running', 'Routes');
  setLiveRhymeDiagnostics('checking route manifest');
  try {
    const [routesResponse, healthResponse] = await Promise.all([fetch('/api/live-rhyme/routes'), fetch('/api/live-rhyme/health')]);
    const payload = await safeJsonResponse(routesResponse, 'Live rhyme routes');
    const health = await safeJsonResponse(healthResponse, 'Live rhyme health');
    payload.health_result = health;
    state.lastLiveRhymeRoutes = payload;
    setLiveRhymeStatus('complete', 'Routes OK');
    setLiveRhymeDiagnostics('direct live routes available; polling is not required');
    if (liveRhymeDiagnosticsEl) {
      liveRhymeDiagnosticsEl.innerHTML += `<pre class="route-manifest">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
    }
  } catch (error) {
    setLiveRhymeStatus('error', 'Route error');
    setLiveRhymeDiagnostics(error.message);
  }
}

async function testPythonAnywhereDiagnostics() {
  if (!pythonAnywherePanelEl) return;
  pythonAnywherePanelEl.className = 'pythonanywhere-panel live-rhyme-card loading';
  pythonAnywherePanelEl.innerHTML = '<p class="muted tiny-text">Checking PythonAnywhere deployment mode…</p>';
  try {
    const response = await fetch('/api/pythonanywhere/diagnostics');
    const payload = await safeJsonResponse(response, 'PythonAnywhere diagnostics');
    const imports = payload.imports || {};
    const importRows = Object.entries(imports).map(([name, info]) => `
      <div class="pa-import-row ${info.available ? 'ok' : 'warn'}"><strong>${escapeHtml(name)}</strong><small>${info.available ? `ok ${escapeHtml(info.version || '')}` : escapeHtml(info.error || 'missing')}</small></div>
    `).join('');
    pythonAnywherePanelEl.className = 'pythonanywhere-panel live-rhyme-card';
    pythonAnywherePanelEl.innerHTML = `
      <div class="pa-head"><div><p class="eyebrow">PythonAnywhere check</p><h3>${payload.pythonanywhere_compat ? 'Compatibility mode active' : 'Compatibility route active'}</h3></div><span>${escapeHtml(payload.executor || 'engine')}</span></div>
      <div class="rhyme-meta-row">
        <span>async mode: <b>${escapeHtml(payload.async_job_mode || 'direct')}</b></span>
        <span>live inline: <b>${escapeHtml(payload.live_rhyme_inline_jobs)}</b></span>
        <span>python: <b>${escapeHtml(payload.python || '—')}</b></span>
      </div>
      <div class="pa-import-grid">${importRows}</div>
      <ol>${(payload.advice || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>
      <details><summary>Raw diagnostics</summary><pre class="route-manifest">${escapeHtml(JSON.stringify(payload, null, 2))}</pre></details>
    `;
    setLiveRhymeDiagnostics('PythonAnywhere diagnostics loaded');
  } catch (error) {
    pythonAnywherePanelEl.className = 'pythonanywhere-panel live-rhyme-card error';
    pythonAnywherePanelEl.innerHTML = `<strong>PythonAnywhere diagnostics failed</strong><p>${escapeHtml(error.message)}</p>`;
    setLiveRhymeDiagnostics(error.message);
  }
}

document.addEventListener('click', (event) => {
  const legendButton = event.target.closest('.rhyme-legend-item, .rhyme-family-chip');
  if (legendButton && legendButton.dataset.rhymeKey) {
    const key = legendButton.dataset.rhymeKey || '';
    const current = document.body.dataset.rhymeFocus || '';
    const next = current === key ? '' : key;
    document.body.dataset.rhymeFocus = next;
    document.body.classList.toggle('rhyme-focus-on', Boolean(next));
    $$('.rhyme-word, .rh-token').forEach((word) => word.classList.toggle('focus-match', Boolean(next) && word.dataset.rhymeKey === next));
    $$('.rhyme-legend-item, .rhyme-family-chip').forEach((item) => item.classList.toggle('active', Boolean(next) && item.dataset.rhymeKey === next));
    return;
  }

  const rhymeToken = event.target.closest('.rh-token, .rhyme-word');
  if (rhymeToken && !event.target.closest('.rhyme-family-chip, .rhyme-legend-item')) {
    const word = rhymeToken.dataset.word || rhymeToken.textContent.trim();
    const lineNumber = Number(rhymeToken.dataset.line || rhymeToken.closest('[data-line]')?.dataset.line || activeLineNumber());
    const lineText = rhymeToken.closest('.rhyme-line, blockquote, h3, .highlight-line')?.textContent || '';
    analyzeExplicitHighlightedWord(word, lineNumber, lineText);
    switchTab('editor');
    return;
  }

  const patchButton = event.target.closest('.apply-patch');
  if (patchButton) {
    const fix = findFix(patchButton.dataset.line);
    const patch = fix && fix.patches ? fix.patches[Number(patchButton.dataset.patch)] : null;
    if (patch) replaceLine(fix.line_number, patch.replacement);
    return;
  }

  const variantButton = event.target.closest('.apply-variant');
  if (variantButton) {
    const fix = findFix(variantButton.dataset.line);
    const variant = fix && fix.rewrite_variants ? fix.rewrite_variants[Number(variantButton.dataset.variant)] : null;
    if (variant) replaceLine(fix.line_number, variant.text);
    return;
  }

  const liveRhymePatchButton = event.target.closest('.apply-live-rhyme-patch');
  if (liveRhymePatchButton) {
    const active = state.liveRhymeReport?.active_report || {};
    const patch = (active.patches || [])[Number(liveRhymePatchButton.dataset.patch)];
    if (patch && active.line_number) replaceLine(active.line_number, patch.replacement);
    return;
  }

  const sentenceRewriteButton = event.target.closest('.sentence-use-rewrite');
  if (sentenceRewriteButton) {
    const rewrite = state.sentenceReport?.rewrite_options?.[Number(sentenceRewriteButton.dataset.index)];
    if (rewrite && sentenceInputEl) {
      sentenceInputEl.value = rewrite.text || '';
      analyzeSentenceNow(true);
    }
    return;
  }

  const sentencePatchButton = event.target.closest('.sentence-use-patch');
  if (sentencePatchButton) {
    const patch = state.sentenceReport?.applyable_patches?.[Number(sentencePatchButton.dataset.index)];
    if (patch && sentenceInputEl) {
      sentenceInputEl.value = patch.replacement || '';
      analyzeSentenceNow(true);
    }
    return;
  }

  const patternRewriteButton = event.target.closest('.pattern-use-rewrite');
  if (patternRewriteButton) {
    applySentencePatternRewrite(patternRewriteButton.dataset.sentenceIndex, patternRewriteButton.dataset.rewriteIndex);
    return;
  }

  const sentenceWordButton = event.target.closest('.sentence-word-chip');
  if (sentenceWordButton && sentenceInputEl) {
    const word = sentenceWordButton.dataset.word || sentenceWordButton.textContent.trim();
    const start = sentenceInputEl.selectionStart || sentenceInputEl.value.length;
    const end = sentenceInputEl.selectionEnd || start;
    const before = sentenceInputEl.value.slice(0, start);
    const after = sentenceInputEl.value.slice(end);
    const needsLeft = before && !/\s$/.test(before) ? ' ' : '';
    const needsRight = after && !/^\s/.test(after) ? ' ' : '';
    sentenceInputEl.value = `${before}${needsLeft}${word}${needsRight}${after}`;
    const pos = before.length + needsLeft.length + String(word).length + needsRight.length;
    sentenceInputEl.focus();
    sentenceInputEl.selectionStart = sentenceInputEl.selectionEnd = pos;
    scheduleSentenceAnalysis();
    return;
  }

  const liveSwap = event.target.closest('.live-rhyme-swap-end');
  if (liveSwap) {
    const active = state.liveRhymeReport?.active_report || {};
    replaceLineEnding(active.line_number || state.activeLine, liveSwap.dataset.word || liveSwap.textContent.trim());
    return;
  }

  const selectedRhymeChip = event.target.closest('.selected-rhyme-chip');
  if (selectedRhymeChip) {
    replaceSelectedWord(selectedRhymeChip.dataset.word || selectedRhymeChip.textContent.trim());
    return;
  }

  const selectedBest = event.target.closest('#replaceHighlightedWithBest');
  if (selectedBest) {
    const best = (state.selectedWordReport?.ranked || [])[0];
    replaceSelectedWord(best?.word || best?.phrase || '');
    return;
  }

  const copyWordJson = event.target.closest('#copyHighlightedWordJson');
  if (copyWordJson) {
    navigator.clipboard?.writeText(JSON.stringify(state.selectedWordReport || {}, null, 2));
    copyWordJson.textContent = 'Copied';
    setTimeout(() => { copyWordJson.textContent = 'Copy rhyme JSON'; }, 900);
    return;
  }

  const chip = event.target.closest('.insert-chip');
  if (chip) {
    insertAtCursor(chip.dataset.word || chip.textContent.trim());
    return;
  }

  const liveStaticPatchButton = event.target.closest('.apply-live-static-patch');
  if (liveStaticPatchButton) {
    const row = liveActiveStaticRow();
    const patch = row && row.applyable_patches ? row.applyable_patches[Number(liveStaticPatchButton.dataset.patch)] : null;
    if (row && patch) replaceLine(row.line_number, patch.replacement);
    return;
  }

  const liveStaticRewriteButton = event.target.closest('.apply-live-static-rewrite');
  if (liveStaticRewriteButton) {
    const row = liveActiveStaticRow();
    const rewrite = row && row.rewrite_options ? row.rewrite_options[Number(liveStaticRewriteButton.dataset.rewrite)] : null;
    if (row && rewrite) replaceLine(row.line_number, rewrite.text);
    return;
  }

  const staticPatchButton = event.target.closest('.apply-static-patch');
  if (staticPatchButton) {
    const row = findStaticRow(staticPatchButton.dataset.line);
    const patch = row && row.applyable_patches ? row.applyable_patches[Number(staticPatchButton.dataset.patch)] : null;
    if (patch) replaceLine(row.line_number, patch.replacement);
    return;
  }

  const staticRewriteButton = event.target.closest('.apply-static-rewrite');
  if (staticRewriteButton) {
    const row = findStaticRow(staticRewriteButton.dataset.line);
    const rewrite = row && row.rewrite_options ? row.rewrite_options[Number(staticRewriteButton.dataset.rewrite)] : null;
    if (rewrite) replaceLine(row.line_number, rewrite.text);
    return;
  }

  const lineJump = event.target.closest('.line-jump, .inspect-line');
  if (lineJump) {
    jumpToLine(lineJump.dataset.line);
  }
});


const feedbackForm = $('#feedbackForm');
if (feedbackForm) feedbackForm.addEventListener('submit', sendBetaFeedback);
$('#checkHealth')?.addEventListener('click', checkBetaHealth);
runAdvancedRhymeBtn?.addEventListener('click', runAdvancedRhymeLab);
analyzeTargetRhymeBtn?.addEventListener('click', analyzeTargetRhyme);
copyRhymeJsonBtn?.addEventListener('click', copyRhymeJson);
$('#copyLiveRhymeJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.liveRhymeReport || {}, null, 2));
    $('#copyLiveRhymeJson').textContent = 'Copied';
    setTimeout(() => { $('#copyLiveRhymeJson').textContent = 'Copy JSON'; }, 900);
  } catch (_error) {
    $('#copyLiveRhymeJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copyLiveRhymeJson').textContent = 'Copy JSON'; }, 900);
  }
});
rhymeTargetWordEl?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') analyzeTargetRhyme();
});
$('#scoreCurrentRap')?.addEventListener('click', scoreCurrentRap);
$('#captureScoreBaseline')?.addEventListener('click', captureScoreBaseline);
$('#compareCurrentToBaseline')?.addEventListener('click', () => compareEdits(true));
$('#loadCurrentIntoEdited')?.addEventListener('click', loadCurrentIntoEditedBox);
$('#compareEditedBox')?.addEventListener('click', () => compareEdits(false));
$('#copyCompareJson')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.editCompareReport || {}, null, 2));
    $('#copyCompareJson').textContent = 'Copied';
    setTimeout(() => { $('#copyCompareJson').textContent = 'Copy compare JSON'; }, 900);
  } catch (_error) {
    $('#copyCompareJson').textContent = 'Copy failed';
    setTimeout(() => { $('#copyCompareJson').textContent = 'Copy compare JSON'; }, 900);
  }
});


$('#downloadSnapshotPdf')?.addEventListener('click', () => downloadServerReport('snapshot', 'pdf'));
$('#downloadSnapshotCsv')?.addEventListener('click', () => downloadServerReport('snapshot', 'csv'));
$('#downloadScorePdf')?.addEventListener('click', () => downloadServerReport('score', 'pdf'));
$('#downloadScoreCsv')?.addEventListener('click', () => downloadServerReport('score', 'csv'));
$('#downloadComparePdf')?.addEventListener('click', () => downloadServerReport('compare', 'pdf'));
$('#downloadCompareCsv')?.addEventListener('click', () => downloadServerReport('compare', 'csv'));


$('#openAccountTop')?.addEventListener('click', () => switchTab('account'));
$('#openSavedRapsFromEditor')?.addEventListener('click', () => switchTab('account'));
$('#quickSaveRap')?.addEventListener('click', () => saveRap({ updateExisting: Boolean(state.currentRapId) }));
$('#refreshAccountState')?.addEventListener('click', loadAccountState);
$('#accountDiagnostics')?.addEventListener('click', accountDiagnostics);
loginFormEl?.addEventListener('submit', loginAccount);
registerFormEl?.addEventListener('submit', registerAccount);
$('#logoutAccount')?.addEventListener('click', logoutAccount);
$('#saveRapAsNew')?.addEventListener('click', () => saveRap({ updateExisting: false }));
$('#updateSavedRap')?.addEventListener('click', () => saveRap({ updateExisting: true }));
$('#saveVersionCheckpoint')?.addEventListener('click', saveVersionCheckpoint);
$('#reloadSavedRaps')?.addEventListener('click', () => loadSavedRaps(true));
$('#loadSelectedRap')?.addEventListener('click', loadSelectedRapIntoEditor);
$('#compareSelectedRap')?.addEventListener('click', compareSelectedRapToEditor);
$('#duplicateSelectedRap')?.addEventListener('click', duplicateSelectedRap);
$('#togglePinSelectedRap')?.addEventListener('click', togglePinSelectedRap);
$('#toggleArchiveSelectedRap')?.addEventListener('click', toggleArchiveSelectedRap);
$('#deleteSelectedRap')?.addEventListener('click', deleteSelectedRap);
$('#exportRapsJson')?.addEventListener('click', exportRapsJson);
$('#importRapsJson')?.addEventListener('change', (event) => importRapsJson(event.target.files?.[0]));
$('#savedRapSort')?.addEventListener('change', () => loadSavedRaps(false));
$('#savedRapIncludeArchived')?.addEventListener('change', () => loadSavedRaps(false));
savedRapSearchEl?.addEventListener('input', () => {
  clearTimeout(state.savedRapSearchTimer);
  state.savedRapSearchTimer = setTimeout(() => loadSavedRaps(false), 250);
});
savedRapsListEl?.addEventListener('click', (event) => {
  const tag = event.target.closest('.saved-tag-filter');
  if (tag && savedRapSearchEl) {
    savedRapSearchEl.value = tag.dataset.tag || '';
    loadSavedRaps(false);
    return;
  }
  const card = event.target.closest('.saved-rap-card');
  if (!card) return;
  selectSavedRap(card.dataset.rapId, false);
});
savedRapsListEl?.addEventListener('dblclick', (event) => {
  const card = event.target.closest('.saved-rap-card');
  if (!card) return;
  selectSavedRap(card.dataset.rapId, true);
});
getSavedRapStatsEl()?.addEventListener('click', (event) => {
  const tag = event.target.closest('.saved-tag-filter');
  if (!tag || !savedRapSearchEl) return;
  savedRapSearchEl.value = tag.dataset.tag || '';
  loadSavedRaps(false);
});
getSavedRapVersionsEl()?.addEventListener('click', (event) => {
  if (event.target.closest('#reloadSavedRapVersions')) {
    loadSavedRapVersions(true);
    return;
  }
  const loadButton = event.target.closest('.load-version');
  if (loadButton) {
    loadVersionIntoEditor(loadButton.dataset.versionId);
    return;
  }
  const restoreButton = event.target.closest('.restore-version');
  if (restoreButton) restoreVersion(restoreButton.dataset.versionId);
});

// Bootstrap
try {
  const saved = localStorage.getItem('nmc_editing_lab_draft') || '';
  const savedMode = localStorage.getItem('nmc_editing_lab_mode');
  if (saved) editor.value = saved;
  if (savedMode && Array.from(coachMode.options).some((opt) => opt.value === savedMode)) coachMode.value = savedMode;
} catch (_error) {
  // Local storage is optional.
}
loadScoreBaselineFromStorage();
updateLocalStats();
renderTtsStatus(window.NMC_BOOTSTRAP?.tts || {});
renderEmpty();
loadAccountState();
renderSentenceReport({ available: false, error: 'Sentence-level feedback will appear here.' });
renderHighlightedWordReport({ available: false, error: 'Highlight or double-click a word in the editor to fetch similar rhymes asynchronously.' });
renderLiveRhymeReport({ available: false, error: 'Start writing and place the cursor on a line. Active-line rhyme suggestions will appear here.' });
renderSentencePatternReport({ available: false, error: 'Sentence pattern comparison will appear here.' });
setStatus('idle', 'Idle', 'waiting for edits');
setLiveRhymeDiagnostics('ready · highlight a word or keep typing');
if (/pythonanywhere\.com$/i.test(location.hostname)) { setTimeout(testPythonAnywhereDiagnostics, 700); }
if (countWords(editor.value) >= 3) {
  generateStaticBreakdown();
  queueLiveRhymeJob(true);
}
