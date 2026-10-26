const state = {
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
};

const canvas = document.querySelector('#map');
const ctx = canvas.getContext('2d');
const timeline = document.querySelector('#timeline');
const playButton = document.querySelector('#play');
const speedSelect = document.querySelector('#speed');

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
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

function signalState(vehicle) {
  if (vehicle.signal_state) return vehicle.signal_state;
  const bits = Number(vehicle.signals || 0);
  return {
    right_blinker: Boolean(bits & 1), left_blinker: Boolean(bits & 2),
    emergency_blinker: Boolean(bits & 4), brake_light: Boolean(bits & 8),
  };
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
  ctx.font = '600 11px -apple-system, sans-serif';
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
  const currentEvents = eventsAt(Number(state.frame.sim_time));
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
    const decision = event.accept === true ? '承諾' : event.accept === false ? '拒否' : event.event;
    button.innerHTML = `<time>${Number(event.sim_time).toFixed(1)}s</time><span><strong>${event.sender_id} → ${event.receiver_id} · ${decision}</strong><small>${event.reason || event.event || ''}</small></span>`;
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
}

async function setFrame(index) {
  state.index = Math.max(0, Math.min(Number(index), state.meta.frame_count - 1));
  state.frame = await getJSON(`/api/frame?index=${state.index}`);
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

async function initialize() {
  [state.meta, state.network, state.events] = await Promise.all([
    getJSON('/api/meta'), getJSON('/api/network'), getJSON('/api/events'),
  ]);
  timeline.max = String(Math.max(0, state.meta.frame_count - 1));
  const manifest = state.meta.manifest;
  document.querySelector('#run-title').textContent = `${manifest.case || 'シミュレーション'} · Seed ${manifest.seed ?? '—'}`;
  document.querySelector('#run-meta').innerHTML = `${manifest.decision_method || '方式不明'}<br>${state.meta.start_time ?? '—'}–${state.meta.end_time ?? '—'} s · ${state.meta.frame_count}フレーム · FCD ${state.meta.fcd_available ? 'あり' : 'なし'}`;
  await setFrame(0);
  resizeCanvas();
}

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
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  state.zoom = Math.min(8, Math.max(.5, state.zoom * (event.deltaY < 0 ? 1.15 : .87)));
  draw();
}, { passive: false });

initialize().catch(error => {
  document.querySelector('#run-title').textContent = '読み込みに失敗しました';
  document.querySelector('#run-meta').textContent = error.message;
  console.error(error);
});
