const state = {
  catalog: null,
  selectionId: null,
  meta: null,
  network: null,
  events: [],
  frame: null,
  index: 0,
  playing: false,
  timer: null,
  zoom: 1,
  panX: 0,
  panY: 0,
  selectedVehicleId: null,
  dragPointerId: null,
  dragX: 0,
  dragY: 0,
  dragMoved: false,
};

const canvas = document.querySelector('#map');
const ctx = canvas.getContext('2d');
const timeline = document.querySelector('#timeline');
const playButton = document.querySelector('#play');
const speedSelect = document.querySelector('#speed');
const experimentSelect = document.querySelector('#experiment-select');
const caseSelect = document.querySelector('#case-select');
const seedSelect = document.querySelector('#seed-select');

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

function apiURL(path, parameters = {}) {
  const query = new URLSearchParams(parameters);
  if (state.selectionId !== null) query.set('selection', state.selectionId);
  return `${path}?${query}`;
}

function caseLabel(value) {
  const match = String(value).match(/^eval(\d+)$/i);
  return match ? `Eval.${match[1]}` : value;
}

function setOptions(select, entries, valueOf, labelOf, selectedValue) {
  select.innerHTML = '';
  for (const entry of entries) {
    const option = document.createElement('option');
    option.value = String(valueOf(entry));
    option.textContent = labelOf(entry);
    option.selected = option.value === String(selectedValue);
    select.append(option);
  }
  select.disabled = entries.length <= 1;
}

function uniqueBy(items, keyOf) {
  return [...new Map(items.map(item => [String(keyOf(item)), item])).values()];
}

function experimentEntries(experimentId = experimentSelect.value) {
  return state.catalog.entries.filter(entry => entry.experiment_id === experimentId);
}

function refreshCaseAndSeed(preferredCase, preferredSeed) {
  const entries = experimentEntries();
  const cases = uniqueBy(entries, entry => entry.case).sort((left, right) =>
    String(left.case).localeCompare(String(right.case), undefined, { numeric: true }));
  const selectedCase = cases.some(entry => entry.case === preferredCase)
    ? preferredCase : cases[0].case;
  setOptions(caseSelect, cases, entry => entry.case,
    entry => caseLabel(entry.case), selectedCase);
  const seeds = entries.filter(entry => entry.case === selectedCase).sort((left, right) =>
    Number(left.seed) - Number(right.seed));
  const selectedSeed = seeds.some(entry => String(entry.seed) === String(preferredSeed))
    ? preferredSeed : seeds[0].seed;
  setOptions(seedSelect, seeds, entry => entry.seed,
    entry => `Seed ${entry.seed}`, selectedSeed);
}

function selectedCatalogEntry() {
  return state.catalog.entries.find(entry =>
    entry.experiment_id === experimentSelect.value
    && entry.case === caseSelect.value
    && String(entry.seed) === seedSelect.value);
}

function closestFrameIndex(time) {
  const times = state.meta.times;
  let low = 0;
  let high = times.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (times[middle] < time) low = middle + 1;
    else high = middle;
  }
  if (low > 0 && Math.abs(times[low - 1] - time) < Math.abs(times[low] - time)) return low - 1;
  return low;
}

function eventsAt(time) {
  return state.events.filter(event => Math.abs(Number(event.sim_time) - time) < 0.051);
}

function nearbyEvents(time) {
  return state.events.filter(event => Math.abs(Number(event.sim_time) - time) <= 3);
}

function eventLabel(event) {
  if (event.accept === true) return '承諾';
  if (event.accept === false) return '拒否';
  if (event.event === 'suppressed') return '重複判定省略';
  return event.event;
}

function eventReason(event) {
  if (event.reason === 'decision_locked') return '判断済みのため省略';
  return event.reason || event.event || '';
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}

function transform() {
  const [minX, minY, maxX, maxY] = state.network.bounds;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const pad = 42;
  const scale = Math.min((width - pad * 2) / (maxX - minX), (height - pad * 2) / (maxY - minY)) * state.zoom;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  return {
    scale,
    point(x, y) {
      return [width / 2 + (x - cx) * scale + state.panX,
              height / 2 - (y - cy) * scale + state.panY];
    },
  };
}

function drawNetwork(view) {
  ctx.lineCap = 'round';
  for (const lane of state.network.lanes) {
    if (lane.shape.length < 2) continue;
    ctx.beginPath();
    lane.shape.forEach(([x, y], index) => {
      const [px, py] = view.point(x, y);
      if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.lineWidth = Math.max(2, lane.width * view.scale);
    ctx.strokeStyle = lane.internal ? '#263746' : '#1b2a38';
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.strokeStyle = lane.internal ? '#536779' : '#435668';
    ctx.stroke();
  }
}

function drawAnnotationLabel(text, x, y, color) {
  ctx.save();
  ctx.font = '700 11px -apple-system, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  const width = ctx.measureText(text).width + 12;
  ctx.fillStyle = 'rgba(8, 16, 25, .9)';
  ctx.fillRect(x - width / 2, y - 18, width, 17);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y - 4);
  ctx.restore();
}

function drawMergeZone(annotation, view) {
  const [startX, laneY] = view.point(annotation.start_x, annotation.y);
  const [endX] = view.point(annotation.end_x, annotation.y);
  const laneWidth = Math.max(8, Number(annotation.width_m || 3.2) * view.scale);
  const left = Math.min(startX, endX);
  const width = Math.abs(endX - startX);

  ctx.save();
  ctx.fillStyle = 'rgba(73, 210, 255, .13)';
  ctx.fillRect(left, laneY - laneWidth / 2, width, laneWidth);
  ctx.strokeStyle = 'rgba(89, 219, 255, .9)';
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 5]);
  for (const x of [startX, endX]) {
    ctx.beginPath();
    ctx.moveTo(x, laneY - laneWidth * .8);
    ctx.lineTo(x, laneY + laneWidth * .8);
    ctx.stroke();
  }
  ctx.restore();

  drawAnnotationLabel(annotation.start_label, startX, laneY - laneWidth, '#69dcff');
  drawAnnotationLabel(annotation.end_label, endX, laneY + laneWidth + 25, '#69dcff');
}

function drawObstacle(annotation, view) {
  const [x, y] = view.point(annotation.x, annotation.y);
  const length = Math.max(12, Number(annotation.length_m || 5) * view.scale);
  const width = Math.max(8, Number(annotation.width_m || 1.8) * view.scale);
  const angle = Number(annotation.angle_deg || 0) * Math.PI / 180;

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = '#e7edf3';
  ctx.strokeStyle = '#ff5c68';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.roundRect(-width / 2, -length / 2, width, length, 2);
  ctx.fill();
  ctx.stroke();
  ctx.strokeStyle = '#ff5c68';
  ctx.lineWidth = 2;
  for (let offset = -length / 2 + 3; offset < length / 2; offset += 7) {
    ctx.beginPath();
    ctx.moveTo(-width / 2, offset);
    ctx.lineTo(width / 2, Math.min(length / 2, offset + width));
    ctx.stroke();
  }
  ctx.restore();

  const position = Number.isFinite(Number(annotation.lane_position_m))
    ? ` · 車線位置 ${Number(annotation.lane_position_m).toFixed(0)} m` : '';
  drawAnnotationLabel(`${annotation.label}${position}`, x, y - Math.max(width, length) / 2 - 4, '#ff7b84');
}

function drawScenarioAnnotations(view) {
  for (const annotation of state.network.annotations || []) {
    if (annotation.kind === 'merge_zone') drawMergeZone(annotation, view);
    if (annotation.kind === 'obstacle') drawObstacle(annotation, view);
  }
}

function signalState(vehicle) {
  if (vehicle.signal_state) return vehicle.signal_state;
  const bits = Number(vehicle.signals || 0);
  return {
    right_blinker: Boolean(bits & 1), left_blinker: Boolean(bits & 2),
    emergency_blinker: Boolean(bits & 4), brake_light: Boolean(bits & 8),
  };
}

function drawLeaderLines(view, currentEvents) {
  const vehicles = new Map(state.frame.vehicles.map(vehicle => [String(vehicle.vehicle_id), vehicle]));
  const relatedIds = new Set(currentEvents.flatMap(event => [String(event.sender_id), String(event.receiver_id)]));
  for (const vehicle of state.frame.vehicles) {
    if (!vehicle.leader_id) continue;
    const leader = vehicles.get(String(vehicle.leader_id));
    if (!leader) continue;
    const [x1, y1] = view.point(Number(vehicle.x), Number(vehicle.y));
    const [x2, y2] = view.point(Number(leader.x), Number(leader.y));
    ctx.save();
    ctx.globalAlpha = currentEvents.length && !relatedIds.has(String(vehicle.vehicle_id)) ? .1 : .34;
    ctx.strokeStyle = '#9db1c5';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }
}

function drawVehicle(vehicle, view, currentEvents) {
  const [x, y] = view.point(Number(vehicle.x), Number(vehicle.y));
  const angle = Number(vehicle.angle_deg ?? 0) * Math.PI / 180;
  const length = Math.max(8, Number(vehicle.length_m ?? 5) * view.scale);
  const width = Math.max(5, Number(vehicle.width_m ?? 1.8) * view.scale);
  const sender = currentEvents.some(event => String(event.sender_id) === String(vehicle.vehicle_id));
  const receiver = currentEvents.some(event => String(event.receiver_id) === String(vehicle.vehicle_id));
  const related = currentEvents.length === 0 || sender || receiver;
  const stopped = Number(vehicle.speed_mps) < 0.1;
  const signals = signalState(vehicle);
  const blinkerPhase = Math.floor(Number(state.frame.sim_time) * 2) % 2 === 0;

  ctx.save();
  ctx.globalAlpha = related ? 1 : 0.18;
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = String(vehicle.vehicle_group).toLowerCase().includes('bus') ? '#f2ae4a' : '#4fa3ff';
  ctx.strokeStyle = '#07111c';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(-width / 2, 0, width, length, Math.min(3, width / 3));
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = 'rgba(230,244,255,.75)';
  ctx.fillRect(-width * .34, length * .14, width * .68, Math.max(1, length * .12));

  const lampRadius = Math.max(1.7, width * .12);
  if (signals.brake_light) {
    ctx.fillStyle = '#ff3048';
    ctx.shadowColor = '#ff3048';
    ctx.shadowBlur = 7;
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(side * width * .32, length * .88, lampRadius, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.shadowBlur = 0;
  if (blinkerPhase && (signals.left_blinker || signals.right_blinker || signals.emergency_blinker)) {
    ctx.fillStyle = '#ffbd3e';
    ctx.shadowColor = '#ffbd3e';
    ctx.shadowBlur = 8;
    const sides = signals.emergency_blinker ? [-1, 1] : [signals.left_blinker ? -1 : 1];
    for (const side of sides) {
      for (const longitudinal of [length * .12, length * .88]) {
        ctx.beginPath();
        ctx.arc(side * width * .43, longitudinal, lampRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.restore();

  for (const [active, color, offset] of [[stopped, '#ff4f5f', 5], [sender, '#ff67b3', 9], [receiver, '#a879ff', 13]]) {
    if (!active) continue;
    ctx.beginPath();
    ctx.arc(x, y + length / 2, Math.max(width, length / 2) + offset, 0, Math.PI * 2);
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = color;
    ctx.stroke();
  }
  ctx.globalAlpha = related ? 1 : 0.32;
  ctx.fillStyle = '#f5f8fc';
  ctx.font = `${String(vehicle.vehicle_id) === state.selectedVehicleId ? '800' : '600'} 11px -apple-system, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(vehicle.vehicle_id, x, y - 7);
  ctx.globalAlpha = 1;
}

function draw() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = '#081019';
  ctx.fillRect(0, 0, width, height);
  if (!state.network || !state.frame) return;
  const view = transform();
  drawNetwork(view);
  drawScenarioAnnotations(view);
  const currentEvents = eventsAt(Number(state.frame.sim_time));
  drawLeaderLines(view, currentEvents);
  for (const vehicle of state.frame.vehicles) drawVehicle(vehicle, view, currentEvents);
}

function renderEvents() {
  const container = document.querySelector('#events');
  const events = nearbyEvents(Number(state.frame.sim_time));
  document.querySelector('#event-count').textContent = `${state.events.length}件`;
  if (!events.length) {
    container.innerHTML = '<p class="empty">前後3秒に交渉イベントはありません。</p>';
    return;
  }
  container.innerHTML = '';
  for (const event of events) {
    const button = document.createElement('button');
    button.className = `event ${Math.abs(Number(event.sim_time) - Number(state.frame.sim_time)) < 0.051 ? 'current' : ''}`;
    button.innerHTML = `<time>${Number(event.sim_time).toFixed(1)}s</time><span><strong>${event.sender_id} → ${event.receiver_id} · ${eventLabel(event)}</strong><small>${eventReason(event)}</small></span>`;
    button.addEventListener('click', () => setFrame(closestFrameIndex(Number(event.sim_time))));
    container.append(button);
  }
}

function renderState() {
  const vehicles = state.frame.vehicles;
  const stopped = vehicles.filter(vehicle => Number(vehicle.speed_mps) < 0.1).length;
  const braking = vehicles.filter(vehicle => signalState(vehicle).brake_light).length;
  const blinking = vehicles.filter(vehicle => {
    const signal = signalState(vehicle);
    return signal.left_blinker || signal.right_blinker || signal.emergency_blinker;
  }).length;
  const values = [['車両数', vehicles.length], ['停止', stopped], ['制動灯', braking], ['方向指示', blinking]];
  document.querySelector('#state-grid').innerHTML = values.map(([key, value]) => `<div><dt>${key}</dt><dd>${value}</dd></div>`).join('');
  renderSelectedVehicle();
}

function renderSelectedVehicle() {
  const container = document.querySelector('#vehicle-details');
  const vehicle = state.frame.vehicles.find(item => String(item.vehicle_id) === state.selectedVehicleId);
  if (!vehicle) {
    container.innerHTML = `<div><dt>車両</dt><dd>${state.selectedVehicleId ? `${state.selectedVehicleId} (この時刻は不在)` : '未選択'}</dd></div>`;
    return;
  }
  const signals = signalState(vehicle);
  const activeSignals = [
    signals.left_blinker && '左ウインカー',
    signals.right_blinker && '右ウインカー',
    signals.emergency_blinker && 'ハザード',
    signals.brake_light && 'ブレーキ',
  ].filter(Boolean).join(' / ') || 'なし';
  const entries = [
    ['車両', `${vehicle.vehicle_id} · ${vehicle.vehicle_group || vehicle.vehicle_type_id || '—'}`],
    ['座標', `(${Number(vehicle.x).toFixed(2)}, ${Number(vehicle.y).toFixed(2)})`],
    ['速度', `${Number(vehicle.speed_mps).toFixed(2)} m/s`],
    ['加速度', `${Number(vehicle.accel_mps2).toFixed(2)} m/s²`],
    ['向き', `${Number(vehicle.angle_deg ?? 0).toFixed(1)}°`],
    ['車線', vehicle.lane_id || '—'],
    ['先行車', vehicle.leader_id ? `${vehicle.leader_id} (${Number(vehicle.leader_gap_m).toFixed(1)} m)` : 'なし'],
    ['灯火', activeSignals],
    ['MCS状態', vehicle.controller_status || '—'],
    ['予定経路', vehicle.planned_path_id || '—'],
  ];
  container.innerHTML = entries.map(([key, value]) => `<div><dt>${key}</dt><dd title="${value}">${value}</dd></div>`).join('');
}

async function setFrame(index) {
  state.index = Math.max(0, Math.min(Number(index), state.meta.frame_count - 1));
  state.frame = await getJSON(apiURL('/api/frame', { index: state.index }));
  timeline.value = String(state.index);
  document.querySelector('#time-badge').textContent = `${Number(state.frame.sim_time).toFixed(1)} s`;
  document.querySelector('#frame-badge').textContent = `${state.index + 1} / ${state.meta.frame_count}`;
  renderState();
  renderEvents();
  draw();
}

function scheduleNext() {
  clearTimeout(state.timer);
  if (!state.playing) return;
  if (state.index >= state.meta.frame_count - 1) {
    state.playing = false;
    playButton.textContent = '▶';
    return;
  }
  const delta = Math.max(0.01, state.meta.times[state.index + 1] - state.meta.times[state.index]);
  const speed = Number(speedSelect.value);
  state.timer = setTimeout(async () => {
    await setFrame(state.index + 1);
    scheduleNext();
  }, delta * 1000 / speed);
}

function togglePlay() {
  state.playing = !state.playing;
  playButton.textContent = state.playing ? '❚❚' : '▶';
  scheduleNext();
}

function jumpEvent(direction) {
  const now = Number(state.frame.sim_time);
  const candidates = direction > 0
    ? state.events.filter(event => Number(event.sim_time) > now + .051)
    : state.events.filter(event => Number(event.sim_time) < now - .051).reverse();
  if (candidates.length) setFrame(closestFrameIndex(Number(candidates[0].sim_time)));
}

async function loadSelection(selectionId) {
  clearTimeout(state.timer);
  state.playing = false;
  playButton.textContent = '▶';
  state.selectionId = String(selectionId);
  state.selectedVehicleId = null;
  state.zoom = 1;
  state.panX = 0;
  state.panY = 0;
  [state.meta, state.network, state.events] = await Promise.all([
    getJSON(apiURL('/api/meta')), getJSON(apiURL('/api/network')),
    getJSON(apiURL('/api/events')),
  ]);
  timeline.max = String(Math.max(0, state.meta.frame_count - 1));
  const manifest = state.meta.manifest;
  document.querySelector('#run-title').textContent = `${caseLabel(manifest.case || 'シミュレーション')} · Seed ${manifest.seed ?? '—'}`;
  const fcdLabel = !state.meta.fcd_available ? 'なし'
    : (state.meta.fcd_complete ? 'あり' : '部分ログ');
  document.querySelector('#run-meta').innerHTML = `${manifest.decision_method || '方式不明'}<br>${state.meta.start_time ?? '—'}–${state.meta.end_time ?? '—'} s · ${state.meta.frame_count}フレーム · FCD ${fcdLabel}`;
  const note = document.querySelector('#scenario-note');
  note.textContent = state.meta.scenario_note || '';
  note.hidden = !state.meta.scenario_note;
  const annotationKinds = new Set(
    (state.network.annotations || []).map(annotation => annotation.kind));
  document.querySelector('#merge-zone-legend').hidden = !annotationKinds.has('merge_zone');
  document.querySelector('#obstacle-legend').hidden = !annotationKinds.has('obstacle');
  await setFrame(0);
  resizeCanvas();
}

async function initialize() {
  state.catalog = await getJSON('/api/catalog');
  const experiments = uniqueBy(state.catalog.entries, entry => entry.experiment_id);
  const defaultEntry = state.catalog.entries.find(
    entry => entry.id === state.catalog.default_id) || state.catalog.entries[0];
  setOptions(experimentSelect, experiments, entry => entry.experiment_id,
    entry => entry.experiment_label, defaultEntry.experiment_id);
  refreshCaseAndSeed(defaultEntry.case, defaultEntry.seed);
  await loadSelection(defaultEntry.id);
}

experimentSelect.addEventListener('change', async () => {
  refreshCaseAndSeed(null, null);
  await loadSelection(selectedCatalogEntry().id);
});
caseSelect.addEventListener('change', async () => {
  refreshCaseAndSeed(caseSelect.value, null);
  await loadSelection(selectedCatalogEntry().id);
});
seedSelect.addEventListener('change', async () => {
  await loadSelection(selectedCatalogEntry().id);
});

document.querySelector('#prev').addEventListener('click', () => setFrame(state.index - 1));
document.querySelector('#next').addEventListener('click', () => setFrame(state.index + 1));
document.querySelector('#prev-event').addEventListener('click', () => jumpEvent(-1));
document.querySelector('#next-event').addEventListener('click', () => jumpEvent(1));
document.querySelector('#fit-button').addEventListener('click', () => { state.zoom = 1; state.panX = 0; state.panY = 0; draw(); });
playButton.addEventListener('click', togglePlay);
speedSelect.addEventListener('change', scheduleNext);
timeline.addEventListener('input', event => setFrame(Number(event.target.value)));
window.addEventListener('resize', resizeCanvas);
window.addEventListener('keydown', event => {
  if (event.key === 'ArrowLeft') setFrame(state.index - 1);
  if (event.key === 'ArrowRight') setFrame(state.index + 1);
  if (event.key === ' ') { event.preventDefault(); togglePlay(); }
});

function zoomAtPointer(event, zoomFactor) {
  const rect = canvas.getBoundingClientRect();
  const pointerX = event.clientX - rect.left;
  const pointerY = event.clientY - rect.top;
  const previousZoom = state.zoom;
  state.zoom = Math.min(8, Math.max(.5, previousZoom * zoomFactor));
  const appliedFactor = state.zoom / previousZoom;
  state.panX = pointerX - canvas.clientWidth / 2
    - (pointerX - canvas.clientWidth / 2 - state.panX) * appliedFactor;
  state.panY = pointerY - canvas.clientHeight / 2
    - (pointerY - canvas.clientHeight / 2 - state.panY) * appliedFactor;
}

canvas.addEventListener('wheel', event => {
  event.preventDefault();
  if (!event.ctrlKey && !event.metaKey && Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
    state.panX -= event.deltaX;
    state.panY -= event.deltaY;
    draw();
    return;
  }

  const zoomFactor = event.ctrlKey || event.metaKey
    ? Math.exp(-event.deltaY * .01)
    : (event.deltaY < 0 ? 1.15 : .87);
  zoomAtPointer(event, zoomFactor);
  draw();
}, { passive: false });
canvas.addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  state.dragPointerId = event.pointerId;
  state.dragX = event.clientX;
  state.dragY = event.clientY;
  state.dragMoved = false;
  canvas.setPointerCapture(event.pointerId);
  canvas.classList.add('dragging');
});
canvas.addEventListener('pointermove', event => {
  if (state.dragPointerId !== event.pointerId) return;
  const deltaX = event.clientX - state.dragX;
  const deltaY = event.clientY - state.dragY;
  if (Math.abs(deltaX) + Math.abs(deltaY) > 1) state.dragMoved = true;
  state.panX += deltaX;
  state.panY += deltaY;
  state.dragX = event.clientX;
  state.dragY = event.clientY;
  draw();
});
function finishDrag(event) {
  if (state.dragPointerId !== event.pointerId) return;
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  state.dragPointerId = null;
  canvas.classList.remove('dragging');
}
canvas.addEventListener('pointerup', finishDrag);
canvas.addEventListener('pointercancel', finishDrag);
canvas.addEventListener('click', event => {
  if (state.dragMoved) {
    state.dragMoved = false;
    return;
  }
  if (!state.frame || !state.network) return;
  const rect = canvas.getBoundingClientRect();
  const pointer = [event.clientX - rect.left, event.clientY - rect.top];
  const view = transform();
  let nearest = null;
  let nearestDistance = 24;
  for (const vehicle of state.frame.vehicles) {
    const [x, y] = view.point(Number(vehicle.x), Number(vehicle.y));
    const distance = Math.hypot(pointer[0] - x, pointer[1] - y);
    if (distance < nearestDistance) {
      nearest = vehicle;
      nearestDistance = distance;
    }
  }
  state.selectedVehicleId = nearest ? String(nearest.vehicle_id) : null;
  renderSelectedVehicle();
  draw();
});

initialize().catch(error => {
  document.querySelector('#run-title').textContent = '読み込みに失敗しました';
  document.querySelector('#run-meta').textContent = error.message;
  console.error(error);
});
