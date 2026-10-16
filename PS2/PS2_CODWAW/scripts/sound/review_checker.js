'use strict';
const $ = id => document.getElementById(id);
const state = {levels: [], cache: new Map(), activeId: null, token: '', sequence: 0, saveAllActive: false, syncing: false, syncPreview: null, syncSequence: 0, importing: false, reviewing: false};
const languageNames = {en: '英语', ja: '日语', de: '德语', other: '未定 / 其他'};
let toastTimer, searchTimer, editTimer;
const active = () => state.cache.get(state.activeId);
const locked = () => state.importing || state.reviewing;
const selected = () => active()?.entries.find(row => row.filename === active().selected);
const valueOf = (level, row) => ({...row, ...(level.edits.get(row.filename) || {})});
const editable = row => row.kind === 'system' ? {translation: row.translation} : ({translation: row.translation, needs_review: row.needs_review, note: row.note,
  ...(row.requires_variant_review ? {reuse_approved: row.reuse_approved} : {})});
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function node(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text != null) el.textContent = text; return el; }
function toast(message, error = false) {
  $('toast').textContent = message; $('toast').className = error ? 'visible error' : 'visible';
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').className = '', error ? 6500 : 2600);
}
async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || `请求失败 (${response.status})`); error.status = response.status; throw error; }
  return result;
}
function dirtyCount() { return [...state.cache.values()].reduce((n, level) => n + level.edits.size, 0); }
function countsFor(info) {
  const level = state.cache.get(info.id);
  if (!level) return info.counts;
  const rows = level.entries.map(row => valueOf(level, row));
  return {...level.counts, translated: rows.filter(row => row.translation.trim()).length,
    reviewed: rows.filter(row => !row.needs_review).length};
}
function updateActions() {
  const count = dirtyCount(), level = active(), saving = [...state.cache.values()].some(item => item.saving);
  $('saveBtn').disabled = !level?.edits.size || level.saving || state.saveAllActive || state.syncing || locked();
  $('saveAllBtn').disabled = !count || saving || state.saveAllActive || state.syncing || locked();
  $('syncBtn').disabled = !state.syncPreview?.updates || count > 0 || saving || state.saveAllActive || state.syncing || locked();
  const system = level?.kind === 'system', readonly = !!selected()?.readonly;
  $('importBtn').classList.toggle('hidden', system);
  $('importBtn').disabled = system || !level || count > 0 || saving || state.saveAllActive || state.syncing || locked();
  $('importBtn').title = count ? '请先保存全部修改，再导入 JSON' : `导入到当前目录：${level?.label || '请先选择目录'}；保留已有内容，冲突列出供校对`;
  $('importBtn').textContent = state.importing ? '正在导入…' : '导入 ASR / 译文 JSON';
  $('reviewNextBtn').disabled = !selected() || saving || state.saveAllActive || state.syncing || locked();
  $('reviewNextBtn').textContent = state.reviewing ? '正在保存…' : system ? '保存并下一条' : '校对并下一句';
  $('reviewNextBtn').title = system ? '保存系统译文后跳到下一条（Ctrl+Enter）' : selected()?.text_only ? '标记已核对，保存后跳到下一句（Ctrl+Enter）' : '标记已听音校对，保存后跳到下一句（Ctrl+Enter）';
  for (const id of ['refreshBtn', 'collectionView', 'searchInput', 'languageFilter', 'systemGroupFilter', 'statusFilter', 'clearFilters']) $(id).disabled = locked();
  $('syncBtn').textContent = state.syncing ? '正在同步…' : '同步已校对译文到各关';
  $('exportBtn').disabled = !level?.edits.size;
  const saveLabel = system ? '保存系统译文 JSON' : level?.kind === 'level' ? '保存本关 JSON' : '保存当前 JSON';
  $('saveBtn').textContent = level?.saving ? '正在保存…' : level?.edits.size ? `${saveLabel} · ${level.edits.size} 条` : saveLabel;
  $('globalStatus').classList.toggle('dirty-text', !!count && !saving);
  $('globalStatus').textContent = state.importing ? '正在合并导入 JSON…' : saving || state.saveAllActive ? '正在保存修改…' : count ? `${count} 条修改尚未保存` : '所有修改已保存';
  for (const id of ['translation', 'note', 'reviewed', 'reuseApproved', 'revertBtn']) $(id).disabled = !!level?.saving || state.syncing || locked();
  if (readonly) {$('translation').disabled = true; $('revertBtn').disabled = true;}
  $('syncBar').classList.toggle('hidden', system || !state.syncPreview?.available);
  updateNavigation();
}
function visibleCollections() {
  const view = $('collectionView').value;
  return state.levels.filter(info => view === 'all' || (view === 'system' ? info.kind === 'system' : view === 'level' ? info.kind === 'level' : info.kind !== 'level'));
}
function renderLevels() {
  const fragment = document.createDocumentFragment();
  let previousKind = null;
  for (const info of visibleCollections()) {
    if (previousKind !== info.kind) {
      fragment.append(node('li', 'group-label', {system: '系统文本 · 直接保存统一译文', common: '通用语音 · 校对一次，跨关复用', story: '各关剧情 · 分关识别与校对', level: '完整关卡 · 最终字幕 JSON'}[info.kind] || '关卡'));
      previousKind = info.kind;
    }
    const count = countsFor(info), level = state.cache.get(info.id);
    const button = node('button', 'level-button' + (info.id === state.activeId ? ' active' : ''));
    button.type = 'button'; button.dataset.level = info.id; button.setAttribute('aria-current', info.id === state.activeId ? 'true' : 'false');
    const line = node('div', 'level-line'); line.append(node('span', 'level-name', info.label));
    if (level?.edits.size) line.append(node('span', 'level-dot', '●'));
    line.append(node('span', 'badge' + (count.asr || info.kind === 'system' ? ' green' : ''), info.error ? '读取异常' : info.kind === 'system' ? `${count.total} 条` : count.asr ? `${count.total} 句` : '待识别'));
    const meta = node('div', 'level-meta'); meta.append(node('span', '', `已译 ${count.translated} / ${count.total}`), node('span', '', info.kind === 'system' ? '支持手动换行' : `已校对 ${count.reviewed}`));
    const progress = node('div', 'progress'), bar = node('span'); bar.style.width = (count.total ? count.translated / count.total * 100 : 0) + '%'; progress.append(bar);
    button.append(line, meta, progress); const li = node('li'); li.append(button); fragment.append(li);
  }
  $('levelList').replaceChildren(fragment);
  $('levelCount').textContent = `${state.levels.filter(info => info.kind === 'level').length} 关`;
  const collections = visibleCollections(), textCount = collections.filter(info => info.kind === 'system').reduce((n, info) => n + info.counts.total, 0);
  $('totalCount').textContent = (textCount ? `${textCount} 条系统文本 · ` : '') + `${collections.reduce((n, info) => n + info.counts.audio, 0).toLocaleString()} 段音频`;
  $('rootLocation').textContent = $('collectionView').value === 'system' ? 'TEXT / 菜单与提示译文.json' : $('collectionView').value === 'level' ? 'SOUND / subtitles' : 'TEXT / SOUND';
  updateActions();
}
function filteredRows() {
  const level = active(); if (!level) return [];
  const language = $('languageFilter').value, status = $('statusFilter').value;
  const query = $('searchInput').value.trim().toLocaleLowerCase();
  return level.entries.filter(base => {
    const row = valueOf(level, base);
    if (level.kind !== 'system' && language !== 'all' && row.language !== language) return false;
    if (level.kind === 'system' && $('systemGroupFilter').value !== 'all' && !row.groups.includes($('systemGroupFilter').value)) return false;
    if (status === 'untranslated' && row.translation.trim()) return false;
    if (status === 'pending' && !row.needs_review) return false;
    if (status === 'reviewed' && row.needs_review) return false;
    if (status === 'no_asr' && (row.has_asr || row.text_only)) return false;
    if (status === 'text_only' && !row.text_only) return false;
    if (status === 'dirty' && !level.edits.has(row.filename)) return false;
    return !query || [row.filename, row.sound_name, row.sound_id, row.asr_text, row.embedded_english, row.translation, row.note,
      ...(row.references || []).map(ref => ref.file + ' ' + ref.key)]
      .some(text => String(text || '').toLocaleLowerCase().includes(query));
  });
}
function renderEntries(ensureSelection = false) {
  const level = active(), rows = filteredRows();
  if (level && ensureSelection && !rows.some(row => row.filename === level.selected)) {
    level.selected = rows[0]?.filename || null; renderEditor();
  }
  $('filterCount').textContent = `${rows.length} 条匹配`;
  $('entryCount').textContent = level ? `${level.entries.length} ${level.kind === 'system' ? '条' : '句'}` : '—';
  const fragment = document.createDocumentFragment();
  for (const base of rows) {
    const row = valueOf(level, base), button = node('button', 'entry-button' + (row.filename === level.selected ? ' active' : ''));
    button.type = 'button'; button.dataset.filename = row.filename; button.title = row.filename;
    const system = level.kind === 'system';
    const top = node('div', 'entry-top'); top.append(node('span', 'entry-index', system ? row.filename : '#' + String(row.index).padStart(4, '0')));
    top.append(node('span', 'badge blue', system ? row.readonly ? '保留英文' : `上限 ${row.max_units} 字` : languageNames[row.language]));
    if (row.text_only) top.append(node('span', 'badge yellow', '补录'));
    if (level.edits.has(row.filename)) top.append(node('span', 'entry-dirty', '●'));
    if (!system) top.append(node('span', 'badge' + (!row.needs_review ? ' green' : !row.translation ? ' yellow' : ''), !row.needs_review ? '已校对' : !row.translation ? '未译' : '待校对'));
    button.append(top, node('div', 'entry-snippet', row.translation || '尚无中文译文'),
      node('div', 'entry-original', row.text_only ? row.embedded_english : system || row.has_asr ? row.asr_text : row.asr_status === 'skipped_too_long' ? 'ASR 超长跳过 · 需补识别' : '尚无 ASR 原文 · ' + row.sound_name));
    const li = node('li'); li.append(button); fragment.append(li);
  }
  if (!rows.length) fragment.append(node('li', 'list-empty', level ? '没有符合筛选条件的条目' : '选择关卡后显示条目'));
  $('entryList').replaceChildren(fragment); updateNavigation();
}
function updateNavigation() {
  const rows = filteredRows(), current = selected(), index = rows.findIndex(row => row.filename === current?.filename);
  $('position').textContent = `${index < 0 ? '—' : index + 1} / ${rows.length}`;
  $('prevBtn').disabled = locked() || !rows.length || (index === 0);
  $('nextBtn').disabled = locked() || !rows.length || (index === rows.length - 1);
}
function lint(text, row) {
  if (row?.kind === 'system') {
    if (!text.trim()) return '系统译文不能为空。';
    if (/[\r\t\0]/.test(text)) return '系统译文允许回车换行，不能包含 Tab 或空字符。';
    if ([...text].some(char => char.codePointAt(0) > 0xffff || /[\uD800-\uDFFF]/.test(char))) return '当前字库不支持表情等四字节字符或无效字符。';
    if (row.readonly && text !== row.asr_text) return row.readonly_reason;
    if (text.length > row.max_units) return `超出 ${text.length - row.max_units} 字：此条最多 ${row.max_units} 字（含换行），请缩短。`;
    return '';
  }
  if (/[\r\n\t\0]/.test(text)) return '译文请保持单段文字，不能包含换行、Tab 或空字符。';
  if ([...text].some(char => char.codePointAt(0) > 0xffff)) return '当前游戏字库不支持四字节字符，请移除表情等特殊字符。';
  return '';
}
function updateEditorStatus() {
  const level = active(), base = selected(); if (!base) return;
  const row = valueOf(level, base), system = level.kind === 'system', warning = lint(row.translation, row);
  $('dirtyBadge').classList.toggle('hidden', !level.edits.has(row.filename));
  $('reviewBadge').textContent = row.text_only ? row.needs_review ? '待核对' : '已核对' : row.needs_review ? '待听音校对' : '已听音校对';
  $('reviewBadge').className = 'badge' + (row.needs_review ? '' : ' green');
  $('reviewBadge').classList.toggle('hidden', system);
  $('charCount').textContent = system ? `${row.translation.length} / ${row.max_units} 字（含换行）` : `${[...row.translation].length} 字`;
  $('lintMessage').textContent = warning; $('translation').classList.toggle('invalid', !!warning);
  const count = countsFor(level); $('currentProgress').textContent = `已译 ${count.translated} / ${count.total}` + (system ? '' : ` · 已校对 ${count.reviewed}`);
  updateActions();
}
function renderEditor() {
  const level = active(), base = selected();
  $('editor').classList.toggle('hidden', !base); $('emptyState').classList.toggle('hidden', !!base);
  if (!base) {
    $('audioPlayer').pause(); $('audioPlayer').removeAttribute('src'); $('audioPlayer').dataset.key = ''; $('audioPlayer').load();
    $('emptyState').replaceChildren(node('div', 'empty-icon', '♫'), node('strong', '', level ? '没有匹配的字幕' : '正在读取关卡'), node('span', '', level ? '调整右侧筛选条件后继续校对' : '正在载入音频清单与原文'));
    updateActions();
    return;
  }
  const row = valueOf(level, base);
  const system = level.kind === 'system';
  $('audioBox').classList.toggle('hidden', system);
  $('audioPlayer').classList.toggle('hidden', !!row.text_only);
  $('audioTools').classList.toggle('hidden', !!row.text_only);
  $('audioShortcut').classList.toggle('hidden', system || !!row.text_only);
  $('systemInfo').classList.toggle('hidden', !system);
  $('noteSection').classList.toggle('hidden', system);
  $('note').classList.toggle('hidden', system);
  $('reviewedLabel').classList.toggle('hidden', system);
  $('reviewedCaption').textContent = row.text_only ? '本条已核对' : '本句已听音校对';
  $('entryIcon').textContent = system || row.text_only ? '文' : '♫';
  $('translation').placeholder = system ? '在这里修改系统译文，按回车可强制换行' : row.text_only ? '结合游戏实际字幕，在这里修改中文译文' : '听取音频后，在这里修改中文译文';
  if (system) {
    $('systemRule').textContent = row.readonly_reason || `最多 ${row.max_units} 字；可直接按回车换行。多处共用时，保存会同时用于所有列出的位置。`;
    $('systemNote').textContent = row.note;
    const refs = row.references.map(ref => {const li = node('li'); li.append(node('code', '', ref.file + ' · ' + ref.key)); return li;});
    $('systemRefs').replaceChildren(...refs);
  }
  $('soundName').textContent = row.sound_name; $('fileName').textContent = row.filename;
  $('languageBadge').textContent = system ? '系统文本' : `${languageNames[row.language]} · ${row.language_marker}`;
  $('idBadge').textContent = row.sound_id || `#${row.index}`;
  $('duration').textContent = row.duration == null ? '' : `${Number(row.duration).toFixed(2)} 秒`;
  const skipped = row.asr_status === 'skipped_too_long';
  $('originalLabel').textContent = system ? '原文 · 游戏系统文本' : row.text_only ? '原文 · AM 补录文本' : '原文 · ASR 识别';
  $('originalStatus').textContent = row.text_only ? '无本地录音 · 非 ASR' : system || row.has_asr ? '' : skipped ? '超长跳过 · 需补识别' : '尚无 ASR 原文';
  $('originalText').textContent = row.text_only ? row.embedded_english : system || row.has_asr ? row.asr_text : skipped ? 'Whisper 跳过了这段超长音频，尚无有效识别结果。请听音校对或补做识别后导入。' : '本句尚无识别原文。可以先听音，之后通过上方“导入 ASR / 译文 JSON”合并识别结果。';
  $('originalText').classList.toggle('empty', !system && !row.text_only && !row.has_asr);
  $('embeddedWrap').classList.toggle('hidden', !!row.text_only || !row.embedded_english);
  $('embeddedText').textContent = row.embedded_english;
  $('translation').value = row.translation; $('note').value = row.note; $('reviewed').checked = !row.needs_review;
  $('reuseApproved').checked = row.reuse_approved;
  const isCommon = level.kind === 'common';
  $('variantWrap').classList.toggle('hidden', !isCommon);
  $('variantApprovalWrap').classList.toggle('hidden', !row.requires_variant_review);
  $('reuseInfo').textContent = isCommon ? `匹配 ${row.reuse_targets.length} 关 · ${row.audio_variants.length} 个音频版本` +
    (row.requires_variant_review ? '。差异较大，需确认各版本后同步。' : '。按完整声音名和 ID 同步。') : '';
  const variantSelect = $('variantSelect'); variantSelect.replaceChildren();
  const baseOption = node('option', '', '当前校对音频'); baseOption.value = JSON.stringify([level.id, row.filename]); variantSelect.append(baseOption);
  for (const variant of row.audio_variants) {
    const option = node('option', '', variant.level.replace(/_am$/, '.am') + ' · ' + variant.filename.split('__')[0]);
    option.value = JSON.stringify([variant.level, variant.filename]); variantSelect.append(option);
  }
  const player = $('audioPlayer'), key = `${level.id}/${row.filename}`;
  if (player.dataset.key !== key) {
    player.pause(); player.dataset.key = key;
    if (row.audio_available) player.src = `/audio/${encodeURIComponent(level.id)}/${encodeURIComponent(row.filename)}`;
    else player.removeAttribute('src');
    player.load(); player.playbackRate = Number($('playbackRate').value);
    $('audioError').classList.toggle('hidden', row.audio_available);
    $('audioError').textContent = row.text_only ? '本关音频银行无对应录音，请结合游戏实际显示的字幕核对。' : row.audio_available ? '' : '对应的 MP3 文件不存在。';
    if (row.audio_available && $('autoPlay').checked) playAudio();
  }
  $('replayBtn').disabled = !row.audio_available;
  updateEditorStatus(); updateNavigation();
}
function renderLevel() {
  const level = active();
  const system = level?.kind === 'system';
  $('prevBtn').textContent = system ? '← 上一条' : '← 上一句';
  $('nextBtn').textContent = system ? '下一条 →' : '下一句 →';
  $('audioShortcut').classList.toggle('hidden', system);
  $('nextShortcut').textContent = system ? '保存并下一条' : '校对并下一句';
  if (system) $('importReport').classList.add('hidden');
  $('languageFilter').classList.toggle('hidden', system);
  $('systemGroupFilter').classList.toggle('hidden', !system);
  for (const option of $('statusFilter').options) {
    option.hidden = option.disabled = system && ['pending', 'reviewed', 'no_asr', 'text_only'].includes(option.value);
    if (option.disabled && option.selected) $('statusFilter').value = 'all';
  }
  if (system) {
    const filter = $('systemGroupFilter'), previous = filter.value;
    const options = [{id: 'all', label: '全部系统文本'}, ...level.groups].map(group => {const option = node('option', '', group.label); option.value = group.id; return option;});
    filter.replaceChildren(...options); filter.value = options.some(option => option.value === previous) ? previous : 'all';
  }
  $('entryListTitle').textContent = system ? '系统文本条目' : '字幕条目';
  $('searchInput').placeholder = system ? '搜索原文、译文、ID 或使用位置' : '搜索原文、译文、文件名或备注';
  $('currentLevel').textContent = level ? `${level.label}  /  ${system ? '文字校对' : '字幕校对'}` : '正在读取关卡…';
  const notices = [];
  if (level) {
    if (system) notices.push('保存直接写回 TEXT/菜单与提示译文.json 的 zh。一键构建会读取已保存的修改，无需语音同步。');
    if (level.kind === 'common') notices.push('在这里统一校对通用台词。保存后，点击上方同步按钮复用到所有匹配关卡。');
    if (level.kind === 'story') notices.push('在这里逐条校对该关剧情。上方可合并导入 Colab 识别结果及译文 JSON，已有校对内容会保留。');
    const missing = level.entries.filter(row => !row.has_asr && !row.text_only).length;
    if (level.counts.text_only) notices.push(`另有 ${level.counts.text_only} 条 AM 补录文本，没有本地录音，可通过“AM补录（无录音）”筛选校对。`);
    if (!level.json_exists) notices.push('本关尚未导入识别 JSON。可以先听音，保存时只记录手动编辑的条目。');
    else if (missing && !system) notices.push(`${missing} 段音频尚无有效识别原文，可通过“待识别 / 超长跳过”筛选查看。`);
    if (level.unmatched_json_keys.length) notices.push(`${level.unmatched_json_keys.length} 个 JSON 条目未匹配音频，保存时会保留。`);
  }
  $('levelNotice').textContent = notices.join(' '); $('levelNotice').classList.toggle('hidden', !notices.length);
  $('saveLocation').textContent = level ? `${level.save_path || level.directory_hint + '/whisper_results.json'}（保存前自动备份）` : '';
  renderLevels(); renderEntries(true); renderEditor();
}
async function chooseLevel(id, reload = false) {
  if (locked()) return;
  const sequence = ++state.sequence;
  state.activeId = id; renderLevels();
  try {
    if (reload || !state.cache.has(id)) {
      $('audioPlayer').pause();
      if (!state.cache.has(id)) renderEditor();
      const data = await api('/api/level/' + encodeURIComponent(id));
      const prior = state.cache.get(id);
      data.edits = new Map(); data.saving = false; data.selected = prior?.selected || data.entries[0]?.filename || null;
      state.cache.set(id, data);
    }
    if (sequence === state.sequence) renderLevel();
  } catch (error) {
    if (sequence === state.sequence) {
      $('editor').classList.add('hidden'); $('emptyState').classList.remove('hidden');
      $('emptyState').replaceChildren(node('strong', '', '关卡读取失败'), node('span', '', error.message));
      toast(error.message, true);
    }
  }
}
function editCurrent(kind) {
  const level = active(), row = selected(); if (!row || row.readonly || level.saving || state.syncing || locked()) return;
  if (kind === 'translation') $('reviewed').checked = false;
  const change = level.kind === 'system' ? {translation: $('translation').value} : {translation: $('translation').value, needs_review: !$('reviewed').checked, note: $('note').value,
    ...(row.requires_variant_review ? {reuse_approved: $('reuseApproved').checked} : {})};
  if (same(change, editable(row))) level.edits.delete(row.filename); else level.edits.set(row.filename, change);
  updateEditorStatus();
  clearTimeout(editTimer); editTimer = setTimeout(() => { renderLevels(); renderEntries(); }, 120);
}
function selectEntry(filename) {
  const level = active(); if (!level || locked()) return;
  level.selected = filename; renderEditor(); renderEntries();
}
function navigate(direction) {
  const rows = filteredRows(), current = selected(); if (!rows.length) return;
  let index = rows.findIndex(row => row.filename === current?.filename);
  if (index < 0) index = direction > 0 ? rows.findIndex(row => row.index > (current?.index ?? -1)) : rows.findLastIndex(row => row.index < (current?.index ?? Infinity));
  else index += direction;
  if (index < 0 || index >= rows.length) return;
  selectEntry(rows[index].filename); $('entryList').querySelector('.active')?.scrollIntoView({block: 'nearest'});
}
async function playAudio(restart = false) {
  if (!selected()?.audio_available) return;
  if (restart) $('audioPlayer').currentTime = 0;
  try { await $('audioPlayer').play(); }
  catch (error) { if (error.name !== 'AbortError') toast('音频暂未播放，请点击播放器的播放按钮。', true); }
}
async function reviewAndNext() {
  if ($('reviewNextBtn').disabled) return;
  const level = active(), row = selected(), rows = filteredRows();
  const index = rows.findIndex(item => item.filename === row.filename);
  const next = index < 0 ? rows.find(item => item.index > row.index) : rows[index + 1];
  if (level.kind !== 'system') $('reviewed').checked = true;
  editCurrent(level.kind === 'system' ? 'translation' : 'reviewed');
  clearTimeout(editTimer);
  clearTimeout(searchTimer);
  state.reviewing = true; updateActions();
  let saved = false;
  try {
    await saveLevel(level.id, false, false);
    saved = true;
    level.selected = next?.filename || row.filename;
    toast(level.kind === 'system' ? (next ? '本条译文已保存' : '本条已保存，已到当前列表末尾') :
      next ? '本句已校对并保存' : '本句已保存，已到当前列表末尾');
  } catch (error) { toast(error.message, true); }
  finally {
    state.reviewing = false;
    if (saved) renderLevel(); else {renderLevels(); renderEntries(); renderEditor();}
    $('entryList').querySelector('.active')?.scrollIntoView({block: 'nearest'});
  }
}
async function importJsonFile(file) {
  if (!file || $('importBtn').disabled) return;
  const level = active();
  state.importing = true; clearTimeout(editTimer); clearTimeout(searchTimer); updateActions();
  $('importReport').classList.add('hidden');
  let written = false;
  try {
    const document = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
    const result = await api('/api/import', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': state.token},
      body: JSON.stringify({level: level.id, revision: level.revision, document})});
    written = true;
    const label = {asr_text: 'ASR 原文', translation: '译文', note: '备注'};
    $('importSummary').textContent = `${file.name} → ${level.label}：匹配 ${result.matched} 条，写入 ${result.saved} 条，保留 ${result.conflicts.length} 处已有内容。导入的译文需逐条校对。`;
    $('importConflicts').classList.toggle('hidden', !result.conflicts.length);
    $('importConflictText').textContent = result.conflicts.map(item => `${item.filename} · ${label[item.field]}\n现有：${item.existing || '（空白，已校对）'}\n导入：${item.incoming}`).join('\n\n');
    $('importReport').classList.remove('hidden');
    const data = await api('/api/level/' + encodeURIComponent(level.id));
    state.cache.set(level.id, {...data, edits: new Map(), saving: false, selected: level.selected});
    const info = state.levels.find(item => item.id === level.id);
    if (info) {info.counts = data.counts; info.json_exists = data.json_exists;}
    toast(`已合并到${level.label} · ${result.saved} 条`);
    await refreshSyncPreview();
  } catch (error) { toast((written ? '导入已完成，页面刷新失败，请点击重新读取：' : '导入失败：') + error.message, true); }
  finally { state.importing = false; $('importFile').value = ''; renderLevel(); }
}
async function saveLevel(id, announce = true, renderAfterSave = true) {
  const level = state.cache.get(id); if (!level?.edits.size || level.saving) return;
  const snapshot = Object.fromEntries(level.edits);
  for (const [name, change] of Object.entries(snapshot)) {
    const warning = lint(change.translation, level.entries.find(row => row.filename === name));
    if (warning) { throw new Error(`${name}：${warning}`); }
  }
  level.saving = true; updateActions();
  try {
    const result = await api('/api/save', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': state.token},
      body: JSON.stringify({level: id, revision: level.revision, edits: snapshot})});
    level.revision = result.revision; level.json_exists = true; level.counts = result.counts;
    for (const row of level.entries) if (snapshot[row.filename]) {
      Object.assign(row, result.edits?.[row.filename] || snapshot[row.filename], {has_record: true});
      if (same(level.edits.get(row.filename), snapshot[row.filename])) level.edits.delete(row.filename);
    }
    const info = state.levels.find(item => item.id === id); if (info) {info.counts = result.counts; info.json_exists = true;}
    if (announce) toast(`已保存 ${level.label} · ${result.saved} 条修改`);
  } finally {
    level.saving = false; renderLevels();
    if (state.activeId === id && renderAfterSave) { renderLevel(); }
    if (!state.saveAllActive) {
      if (renderAfterSave) await refreshSyncPreview(); else void refreshSyncPreview();
    }
  }
}
async function refreshSyncPreview() {
  const sequence = ++state.syncSequence;
  try {
    const preview = await api('/api/sync-preview');
    if (sequence !== state.syncSequence) return;
    state.syncPreview = preview; $('syncBar').classList.toggle('hidden', active()?.kind === 'system' || !preview.available);
    $('syncSummary').textContent = `可同步 ${preview.updates} 条 / ${Object.keys(preview.levels).length} 关 · 待校对 ${preview.pending_sources} 条` +
      (preview.variant_blocked ? ` · 版本待确认 ${preview.variant_blocked}` : '') + (preview.conflict_count ? ` · 译文冲突 ${preview.conflict_count}` : '');
    $('syncDetails').classList.toggle('hidden', !preview.variant_blocked && !preview.conflict_count);
    $('syncDetailText').textContent = [...preview.blocked.map(item => `${item.collection} / ${item.filename}：${item.reason}`),
      ...preview.conflicts.map(item => `${item.level} / ${item.filename}：${item.reason}\n现有：${item.existing}\n通用：${item.incoming}`)].join('\n');
    updateActions();
  } catch (error) { state.syncPreview = null; updateActions(); toast('同步预览失败：' + error.message, true); }
}
async function syncReviewed() {
  if (dirtyCount() || state.syncing || locked() || !state.syncPreview?.updates) return;
  state.syncing = true; updateActions();
  try {
    const result = await api('/api/sync', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': state.token},
      body: JSON.stringify({revision: state.syncPreview.revision})});
    for (const id of Object.keys(result.levels)) state.cache.delete(id);
    const response = await api('/api/levels'); state.levels = response.levels; state.token = response.token;
    if (state.activeId && !state.cache.has(state.activeId)) await chooseLevel(state.activeId, true);
    else renderLevels();
    toast(`已同步 ${result.saved} 条到 ${Object.keys(result.levels).length} 关` + (result.conflict_count ? `，保留 ${result.conflict_count} 条冲突译文` : ''));
  } catch (error) { toast(error.message, true); }
  finally { state.syncing = false; await refreshSyncPreview(); updateActions(); }
}
async function refresh() {
  if (state.syncing || locked() || state.saveAllActive || [...state.cache.values()].some(level => level.saving)) return toast('请等待保存完成。');
  if (active()?.edits.size && !confirm('本关有未保存修改。重新读取会丢弃本关的编辑；可以先取消并导出草稿。继续重新读取？')) return;
  try {
    const response = await api('/api/levels'); state.levels = response.levels; state.token = response.token;
    const id = state.levels.some(level => level.id === state.activeId) ? state.activeId : state.levels[0]?.id;
    if (id) await chooseLevel(id, true); else {state.activeId = null; renderLevel();}
    await refreshSyncPreview();
    toast('已重新读取音频与字幕 JSON');
  } catch (error) { toast(error.message, true); }
}
function exportDraft() {
  const level = active(); if (!level?.edits.size) return;
  const text = JSON.stringify({level: level.id, source_revision: level.revision, edits: Object.fromEntries(level.edits)}, null, 2) + '\n';
  const url = URL.createObjectURL(new Blob([text], {type: 'application/json;charset=utf-8'}));
  const link = node('a'); link.href = url; link.download = `${level.id}.review_draft.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); toast('编辑草稿已导出，尚未写入字幕文件。');
}
$('levelList').addEventListener('click', event => {const button = event.target.closest('[data-level]'); if (button) chooseLevel(button.dataset.level);});
$('entryList').addEventListener('click', event => {const button = event.target.closest('[data-filename]'); if (button) selectEntry(button.dataset.filename);});
for (const id of ['translation', 'note']) $(id).addEventListener('input', () => editCurrent(id));
$('reviewed').addEventListener('change', () => editCurrent('reviewed'));
$('reuseApproved').addEventListener('change', () => editCurrent('reuseApproved'));
$('collectionView').onchange = () => { const visible = visibleCollections(); renderLevels(); if (visible.length && !visible.some(info => info.id === state.activeId)) chooseLevel(visible[0].id); };
$('variantSelect').onchange = () => {
  const [level, filename] = JSON.parse($('variantSelect').value), player = $('audioPlayer');
  player.pause(); player.src = `/audio/${encodeURIComponent(level)}/${encodeURIComponent(filename)}`;
  player.dataset.key = ''; player.load(); player.playbackRate = Number($('playbackRate').value); playAudio();
};
$('searchInput').addEventListener('input', () => {clearTimeout(searchTimer); searchTimer = setTimeout(() => renderEntries(true), 120);});
for (const id of ['languageFilter', 'systemGroupFilter', 'statusFilter']) $(id).addEventListener('change', () => renderEntries(true));
$('clearFilters').onclick = () => { $('searchInput').value = ''; $('languageFilter').value = 'all'; $('systemGroupFilter').value = 'all'; $('statusFilter').value = 'all'; renderEntries(true); };
$('prevBtn').onclick = () => navigate(-1); $('nextBtn').onclick = () => navigate(1);
$('reviewNextBtn').onclick = reviewAndNext;
$('importBtn').onclick = () => $('importFile').click();
$('importFile').onchange = () => importJsonFile($('importFile').files[0]);
$('replayBtn').onclick = () => playAudio(true);
$('playbackRate').onchange = () => { $('audioPlayer').playbackRate = Number($('playbackRate').value); };
$('audioPlayer').onerror = () => { if (selected()?.audio_available) { $('audioError').textContent = '音频无法载入，请检查 MP3 文件或重新读取关卡。'; $('audioError').classList.remove('hidden'); } };
$('revertBtn').onclick = () => { const row = selected(); if (!row) return; active().edits.delete(row.filename); renderLevel(); };
$('saveBtn').onclick = () => saveLevel(state.activeId).catch(error => toast(error.message, true));
$('saveAllBtn').onclick = async () => {
  state.saveAllActive = true; updateActions();
  try { for (const [id, level] of state.cache) if (level.edits.size) await saveLevel(id, false); toast('所有修改已保存'); }
  catch (error) { toast(error.message, true); }
  finally { state.saveAllActive = false; await refreshSyncPreview(); updateActions(); }
};
$('refreshBtn').onclick = refresh; $('exportBtn').onclick = exportDraft;
$('syncBtn').onclick = syncReviewed;
window.addEventListener('beforeunload', event => { if (dirtyCount() || locked()) {event.preventDefault(); event.returnValue = '';} });
document.addEventListener('keydown', event => {
  if (event.isComposing) return;
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {event.preventDefault(); $('reviewNextBtn').click(); return;}
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault(); if (event.shiftKey) $('saveAllBtn').click(); else $('saveBtn').click(); return;
  }
  if (event.altKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {event.preventDefault(); navigate(event.key === 'ArrowLeft' ? -1 : 1); return;}
  if (event.code === 'Space' && !event.target.closest('input,textarea,select,button,audio,[contenteditable]')) {
    event.preventDefault(); if ($('audioPlayer').paused) playAudio(); else $('audioPlayer').pause();
  }
});
(async function init() {
  try {
    if (location.protocol === 'file:') throw new Error('请双击 SOUND/start_review_checker.bat 启动，浏览器才能读取音频并保存 JSON。');
    const response = await api('/api/levels'); state.levels = response.levels; state.token = response.token;
    if (!state.levels.some(info => info.kind !== 'level')) $('collectionView').value = 'level';
    renderLevels();
    if (state.levels.length) await chooseLevel(state.levels[0].id);
    else {$('emptyState').replaceChildren(node('strong', '', '没有找到关卡'), node('span', '', '请将关卡音频放在 SOUND/subtitles/<关卡>/mp3 中。'));}
    await refreshSyncPreview();
  } catch (error) {
    $('globalStatus').textContent = '读取失败'; $('globalStatus').classList.add('dirty-text');
    $('emptyState').replaceChildren(node('strong', '', '校对工具尚未连接'), node('span', '', error.message));
  }
})();
