// 라이트큐 대시보드: 1초마다 /api/state를 읽어 화면을 갱신한다.
// 외부 라이브러리 없이 SVG를 직접 그린다 (핫스팟에 인터넷이 없으므로).
const $ = (id) => document.getElementById(id);
const FILM = { off: "꺼짐", low: "45V", high: "100V" };
let last = null;          // 마지막으로 받은 상태 (창 크기가 바뀌면 다시 그릴 때 사용)

async function post(url, data) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!r.ok) throw new Error((await r.json()).error || r.status);
  refresh();
}

// ---------- 그래프 ----------
// SVG를 상자 크기에 맞춘다. 고정 크기면 화면에 따라 글자가 눌리거나 늘어난다.
function fit(svg) {
  const box = svg.parentElement.getBoundingClientRect();
  const W = Math.max(280, Math.round(box.width)), H = Math.max(60, Math.round(box.height));
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  return [W, H];
}

function path(points, xOf, yOf) {
  let d = "";
  points.forEach((p, i) => {
    const y = yOf(p);
    if (y === null) { d += " "; return; }          // 값이 없으면 선을 끊는다
    d += (d === "" || d.endsWith(" ") ? "M" : "L") + xOf(i).toFixed(1) + "," + y.toFixed(1);
  });
  return d.trim();
}

function niceMax(v) {                               // 눈금이 깔끔하게 나오도록 올림
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p) return m * p;
  return 10 * p;
}

function drawChart(hist, sim) {
  const svg = $("chart");
  const [W, H] = fit(svg);
  const L = 44, R = 8, T = 10, B = 22;
  const n = Math.max(hist.length, 2);
  const vals = hist.flatMap((p) => [p.lux, p.target || 0, sim ? p.outdoor || 0 : 0]);
  const maxV = niceMax(Math.max(100, ...vals));
  const xOf = (i) => L + (i / (n - 1)) * (W - L - R);
  const yOf = (v) => T + (1 - v / maxV) * (H - T - B);
  let s = "";
  // 목표가 없는 구간(저녁·취침)은 회색 띠
  let start = null;
  hist.forEach((p, i) => {
    const off = p.target == null;
    if (off && start === null) start = i;
    if ((!off || i === hist.length - 1) && start !== null) {
      const end = off ? i : i - 1;
      const x0 = xOf(Math.max(start - 0.5, 0)), x1 = xOf(Math.min(end + 0.5, n - 1));
      s += `<rect class="p-off" x="${x0}" y="${T}" width="${Math.max(x1 - x0, 1)}" height="${H - T - B}"/>`;
      start = null;
    }
  });
  for (let k = 0; k <= 4; k++) {
    const v = (maxV * k) / 4, y = yOf(v);
    s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>`;
    s += `<text class="tick" x="${L - 6}" y="${y + 4}" text-anchor="end">${Math.round(v)}</text>`;
  }
  // 시간 눈금 5개
  if (hist.length > 1) {
    for (let k = 0; k <= 4; k++) {
      const i = Math.round((k / 4) * (hist.length - 1));
      const anchor = k === 0 ? "start" : k === 4 ? "end" : "middle";
      s += `<text class="tick" x="${xOf(i)}" y="${H - 5}" text-anchor="${anchor}">${hist[i].t.slice(0, 5)}</text>`;
    }
  }
  if (sim) s += `<path class="p-out" d="${path(hist, xOf, (p) => p.outdoor == null ? null : yOf(Math.min(p.outdoor, maxV)))}"/>`;
  s += `<path class="p-target" d="${path(hist, xOf, (p) => p.target == null ? null : yOf(p.target))}"/>`;
  s += `<path class="p-lux" d="${path(hist, xOf, (p) => yOf(p.lux))}"/>`;
  svg.innerHTML = s;
}

function drawLevels(hist, numLevels) {
  const svg = $("levelchart");
  const [W, H] = fit(svg);
  const L = 44, R = 8, T = 6, B = 6;
  const n = Math.max(hist.length, 2), top = numLevels - 1;
  const xOf = (i) => L + (i / (n - 1)) * (W - L - R);
  const yOf = (lv) => T + (1 - lv / top) * (H - T - B);
  let d = "";                                       // 계단 모양: 단계는 바뀌기 전까지 유지되므로
  hist.forEach((p, i) => {
    const x = xOf(i), y = yOf(p.level);
    d += i === 0 ? `M${x},${y}` : `H${x}V${y}`;
  });
  let s = `<text class="tick" x="${L - 6}" y="${yOf(top) + 8}" text-anchor="end">${top}단계</text>`;
  s += `<text class="tick" x="${L - 6}" y="${yOf(0)}" text-anchor="end">0</text>`;
  s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${yOf(0)}" y2="${yOf(0)}"/>`;
  s += `<path class="p-level" d="${d}"/>`;
  svg.innerHTML = s;
}

// ---------- 화면 갱신 ----------
let wakeEdited = false;
let profileKey = "";

function setSwitch(el, on) { el.setAttribute("aria-checked", on ? "true" : "false"); }

function render(st) {
  last = st;
  const info = st.info || {};
  const tgt = info.target;
  // 헤더
  $("vtime").textContent = st.vtime;
  $("speed").textContent = st.speed === 0 ? "시각 고정" : st.speed !== 1 ? `${st.speed}×` : "";
  $("period-chip").textContent = info.period_name || "-";
  // 조도
  $("lux").textContent = st.lux == null ? "-" : Math.round(st.lux);
  const who = st.mode === "auto" ? `자동 제어 (${st.brain === "ai" ? "AI" : "규칙"})` : "수동 고정";
  $("lux-sub").textContent = (tgt == null ? "목표 없음 · 차광" : `목표 ${Math.round(tgt)} lux`) + ` · ${who}`;
  // 단계
  document.querySelectorAll(".lv").forEach((b) => b.classList.toggle("on", Number(b.dataset.level) === st.level));
  $("films").textContent = `필름 A ${FILM[st.films.A]} · B ${FILM[st.films.B]}`;
  setSwitch($("auto-switch"), st.mode === "auto");
  // 판단
  document.querySelectorAll("[data-brain]").forEach((b) => {
    b.classList.toggle("on", b.dataset.brain === st.brain);
    b.disabled = !st.brains.includes(b.dataset.brain);
  });
  const ans = info.answers || {};
  $("ans-rule").textContent = tgt == null ? "0" : ans.rule ?? "-";
  $("ans-ai").textContent = tgt == null ? "0" : ans.ai ?? "-";
  $("rate").textContent = info.rate != null ? `${info.rate > 0 ? "+" : ""}${Math.round(info.rate * 100)}%` : "-";
  const lutText = st.lut_source === "measured" ? "실측 투과율" : "가정 투과율";
  const m = st.ai_meta;
  $("brain-text").textContent = (m
    ? `AI = 결정트리 (깊이 ${m.depth}` + (m.change_acc != null
      ? `, 바꿔야 할 때 정확도 ${Math.round(m.change_acc * 100)}% · 규칙 ${Math.round(m.rule_change_acc * 100)}%)`
      : `, 시험 정확도 ${Math.round(m.test_acc * 100)}%)`)
    : "AI 모델 파일 없음") + ` · ${lutText}`;
  // 경고
  const warns = [];
  if (st.sensor_fail >= st.sensor_fail_limit) warns.push(`센서 응답 없음 (${st.sensor_fail}회 연속) → 0단계로 전환함. 센서 배선을 확인하세요.`);
  else if (st.sensor_fail > 0) warns.push(`센서 읽기 실패 ${st.sensor_fail}회`);
  if (st.ai_meta && st.ai_meta.stale) warns.push("AI 모델이 지금과 다른 투과율표로 학습됨 → 노트북에서 python -m pi.ai.retrain");
  $("alert").hidden = warns.length === 0;
  $("alert").textContent = warns.join(" / ");
  // 설정
  if (!wakeEdited) $("wake").value = st.wake_time;
  $("wake-big").textContent = st.wake_time;
  renderPref(st.pref);
  // 시뮬레이션
  $("sim-panel").hidden = !st.sim;
  if (st.sim) {
    const lp = st.history[st.history.length - 1];
    $("outdoor").textContent = lp && lp.outdoor != null ? Math.round(lp.outdoor) : "-";
    document.querySelectorAll("#speeds button").forEach((b) => b.classList.toggle("on", Number(b.dataset.speed) === st.speed));
  }
  $("switches").textContent = st.switches;
  drawChart(st.history, st.sim);
  drawLevels(st.history, st.num_levels);
  renderVoice(st.voice);
}

function renderPref(p) {
  if (!p) return;
  const key = p.profiles.join("|") + "#" + p.active;
  if (key !== profileKey && document.activeElement !== $("profile")) {
    $("profile").replaceChildren(...p.profiles.map((n) => {   // 이름은 textContent로 (HTML로 해석되지 않게)
      const o = document.createElement("option");
      o.textContent = n;
      o.selected = n === p.active;
      return o;
    }));
    profileKey = key;
  }
  for (const g of ["morning", "day"]) {
    const box = $(`pref-${g}`);
    const [base, mine] = p.targets[g];
    const off = p.offset[g];
    const pos = Math.min(1, Math.max(0, (off + 0.3) / 0.6)) * 100;   // -30% ~ +30%를 0~100%로
    box.querySelector(".sl i").style.width = `${pos}%`;
    box.querySelector(".sl b").style.left = `${pos}%`;
    box.querySelector('[data-k="t"]').textContent = base === mine ? `${base} lux` : `${base} → ${mine} lux`;
    const diff = mine - base;
    box.querySelector('[data-k="tag"]').textContent =
      p.count[g] ? `학습 보정 ${diff > 0 ? "+" : ""}${diff} lux · ${p.count[g]}회` : "학습 전";
  }
  setSwitch($("learn-switch"), p.learn !== false);
  const l = p.last;
  let msg = "직접 바꾼 단계를 선호도에 반영 (아침·주간, 3초 측정)";
  if (p.learn === false) msg = "꺼짐: 단계를 직접 바꿔도 목표가 바뀌지 않습니다";
  else if (p.measuring) msg = "선호 밝기 측정 중… 3초 동안 그대로 두세요";
  else if (l && l.skipped) msg = `${l.vtime} ${l.period_name}에는 목표가 없어 배우지 않았습니다`;
  else if (l) msg = `${l.vtime} ${l.period_name} ${l.preferred} lux를 '${p.active}'의 선호로 학습`;
  $("pref-text").textContent = msg;
}

async function refresh() {
  try {
    const r = await fetch("/api/state");
    render(await r.json());
    $("conn").textContent = "로컬 연결";
    $("conn").classList.remove("off");
  } catch (e) {
    $("conn").textContent = "연결 끊김";
    $("conn").classList.add("off");
  }
}

// ---------- 조작 ----------
document.querySelectorAll(".lv").forEach((b) =>
  b.addEventListener("click", () => post("/api/level", { level: Number(b.dataset.level) })));
$("auto-switch").addEventListener("click", () =>
  post("/api/mode", { mode: last && last.mode === "auto" ? "manual" : "auto" }));
document.querySelectorAll("[data-brain]").forEach((b) =>
  b.addEventListener("click", () => post("/api/brain", { brain: b.dataset.brain })));
document.querySelectorAll("#speeds button").forEach((b) =>
  b.addEventListener("click", () => post("/api/sim/speed", { speed: Number(b.dataset.speed) })));
$("burst").addEventListener("click", () => post("/api/sim/burst"));
$("profile").addEventListener("change", () => post("/api/pref/profile", { name: $("profile").value }));
$("profile-add").addEventListener("click", async () => {
  const name = $("new-profile").value.trim();
  if (!name) return;
  await post("/api/pref/profile", { name });
  $("new-profile").value = "";
});
$("pref-reset").addEventListener("click", () => post("/api/pref/reset"));
$("learn-switch").addEventListener("click", () =>
  post("/api/pref/learn", { enabled: !(last && last.pref && last.pref.learn !== false) }));
$("wake").addEventListener("input", () => { wakeEdited = true; });
$("wake-save").addEventListener("click", async () => {
  try {
    await post("/api/settings", { wake_time: $("wake").value });
    wakeEdited = false;
    $("wake-msg").textContent = "저장됨";
  } catch (e) {
    $("wake-msg").textContent = "실패: " + e.message;
  }
  setTimeout(() => ($("wake-msg").textContent = "기상 준비 20 → 200 lux"), 2000);
});
// 테마: 자동(시스템 따라감) → 밝게 → 어둡게 순서로 바뀜. 이 브라우저에만 기억
const THEMES = [["", "자동"], ["light", "밝게"], ["dark", "어둡게"]];
function showTheme() {
  const cur = document.documentElement.dataset.theme || "";
  $("theme").textContent = "테마: " + THEMES.find((t) => t[0] === cur)[1];
}
$("theme").addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme || "";
  const next = THEMES[(THEMES.findIndex((t) => t[0] === cur) + 1) % THEMES.length][0];
  if (next) document.documentElement.dataset.theme = next;
  else delete document.documentElement.dataset.theme;
  try { next ? localStorage.setItem("lightq-theme", next) : localStorage.removeItem("lightq-theme"); } catch (e) {}
  showTheme();
  if (last) render(last);
});
showTheme();

// 창 크기가 바뀌면 그래프를 다시 맞춘다
new ResizeObserver(() => { if (last) { drawChart(last.history, last.sim); drawLevels(last.history, last.num_levels); } })
  .observe($("chart-box"));

// 핫스팟에는 인터넷이 없어 Pi 시각이 틀릴 수 있으므로, 열 때 휴대폰 시각을 보낸다
function syncTime() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const local = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  post("/api/time", { local }).catch(() => {});
}

// ---------- 음성(문장) 명령 ----------
// 입력 경로 두 가지: ① 마이크 버튼(브라우저 음성 인식, HTTPS나 localhost에서만) ② 입력칸(휴대폰 키보드 받아쓰기 포함).
// 어느 쪽이든 문장을 /api/voice 로 보내고, 의도 판단(분류기 → 필요하면 LLM)은 Pi가 한다.
const SRC = { model: "분류기", llm: "LLM", none: "못 알아들음" };
let voiceKey = "";

function store(key, value) {               // 이 브라우저에만 기억. 저장소를 못 쓰면 무시
  try {
    if (value !== undefined) localStorage.setItem(key, value);
    return localStorage.getItem(key);
  } catch (e) { return null; }
}
$("voice-device").value = store("lightq-device") || "";
$("voice-device").addEventListener("change", () => store("lightq-device", $("voice-device").value.trim()));

function speak(text) {                     // 응답을 소리로 (명령을 보낸 기기에서만)
  if (!("speechSynthesis" in window) || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ko-KR";
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

async function sendVoice(text) {
  text = (text || "").trim();
  if (!text) return;
  const box = $("voice-reply");
  box.classList.remove("fail");
  box.textContent = "판단 중…";
  try {
    const r = await fetch("/api/voice", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, device: $("voice-device").value.trim() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.status);
    showResult(d);
    $("voice-text").value = "";
    refresh();
  } catch (e) {
    box.textContent = "보내기 실패: " + e.message;
    box.classList.add("fail");
  }
}

function renderVoice(v) {
  if (!v) return;
  const s = v.status;
  $("voice-engine").textContent = !s.model && !s.llm ? "모델 없음"
    : (s.model ? "분류기" : "") + (s.model && s.llm ? " + " : "") + (s.llm ? "Gemini" : "")
      + (s.llm && s.llm_error ? ` (LLM: ${s.llm_error})` : "")
      + (s.stt ? " · 음성: Whisper" : "");
  setSwitch($("voice-learn"), s.learn);
  updateMic(s);
  const key = v.recent.map((r) => r.id).join("|");
  if (key === voiceKey) return;
  voiceKey = key;
  // 관람객이 입력한 문장이 들어가므로 HTML로 넣지 않고 textContent로만 만든다
  $("voice-log").replaceChildren(...v.recent.map((r) => {
    const li = document.createElement("li");
    const who = document.createElement("b");
    who.textContent = `${r.device}: "${r.text}"`;
    const src = document.createElement("span");
    src.className = "src";
    src.textContent = SRC[r.source] + (r.source === "model" ? ` ${Math.round(r.confidence * 100)}%` : "");
    li.append(`${r.time.slice(0, 5)} `, who, ` → ${r.applied ? `${r.level_before}→${r.level_after}단계` : r.reply}`, src);
    return li;
  }));
}

$("voice-send").addEventListener("click", () => sendVoice($("voice-text").value));
$("voice-text").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) sendVoice($("voice-text").value); });
$("voice-learn").addEventListener("click", () =>
  post("/api/voice/learn", { enabled: !(last && last.voice && last.voice.status.learn) }));

// ---------- 마이크 ----------
// 누르고 있는 동안만 듣는다 (부스 소음에서 엉뚱한 말이 들어가지 않게). 방식은 두 가지:
//  ① Pi 음성 인식(whisper.cpp, 오프라인): 녹음 → WAV(16kHz) → /api/voice/audio. 서버가 켜져 있으면 이것을 쓴다
//  ② 브라우저 음성 인식(Web Speech, 대개 인터넷 필요): ①을 못 쓸 때
// 둘 다 HTTPS나 localhost에서만 된다 (브라우저 규칙). http로 들어온 휴대폰에는 HTTPS 주소를 안내한다.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const CAN_RECORD = window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
const MAX_REC_S = 8;
let micMode = null;           // "whisper" | "browser" | null
let micBusy = false;

function showResult(d) {
  const box = $("voice-reply");
  box.textContent = (d.heard ? `"${d.heard}" → ` : "") + d.reply;
  box.classList.toggle("fail", d.source === "none" || d.action === "cooldown");
  speak(d.reply);
}

function micIdle() {
  const mic = $("mic");
  mic.classList.remove("on");
  mic.textContent = micMode === "whisper" ? "누르고 있는 동안 말하기 (Pi 음성 인식)" : "누르고 있는 동안 말하기";
}

function updateMic(s) {
  const mode = CAN_RECORD && s.stt ? "whisper" : (SR && window.isSecureContext ? "browser" : null);
  const hint = $("voice-hint");
  if (mode !== micMode && !micBusy) {
    micMode = mode;
    $("mic").hidden = !mode;
    micIdle();
  }
  if (mode) {
    hint.textContent = "버튼을 누른 채로 말하고 떼면 보냅니다. 입력칸에 직접 써도 됩니다";
  } else if (!window.isSecureContext && s.stt && s.https_port) {
    // http로 들어온 휴대폰: 마이크를 쓰려면 HTTPS 주소로 (처음 한 번 '안전하지 않음' → 계속)
    const url = `https://${location.hostname}:${s.https_port}`;
    hint.replaceChildren("마이크로 말하려면 ", Object.assign(document.createElement("a"), { href: url, textContent: url }),
      " 로 접속하세요 (경고가 뜨면 고급 → 계속). 지금은 키보드 마이크로 입력해도 됩니다");
  } else {
    hint.textContent = "휴대폰은 입력칸을 누르고 키보드의 마이크 버튼으로 말해도 됩니다";
  }
}

// --- ① Pi 음성 인식: 녹음해서 WAV로 보낸다 ---
function encodeWav16k(chunks, rate) {
  const len = chunks.reduce((n, c) => n + c.length, 0);
  const all = new Float32Array(len);
  let o = 0, peak = 0;
  for (const c of chunks) { all.set(c, o); o += c.length; }
  for (let i = 0; i < len; i++) peak = Math.max(peak, Math.abs(all[i]));
  const ratio = rate / 16000, n = Math.floor(len / ratio);
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const str = (p, s) => { for (let i = 0; i < s.length; i++) v.setUint8(p + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {            // 구간 평균으로 16kHz로 낮춘다
    const s = Math.floor(i * ratio), e = Math.max(s + 1, Math.min(len, Math.floor((i + 1) * ratio)));
    let sum = 0;
    for (let j = s; j < e; j++) sum += all[j];
    v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, sum / (e - s))) * 0x7fff, true);
  }
  return { blob: new Blob([buf], { type: "audio/wav" }), seconds: len / rate, peak };
}

// 마이크는 처음 누를 때 한 번 켜고 계속 열어 둔다 (누를 때마다 켜면 0.1~0.3초 늦어 첫 글자가 잘린다: "눈부셔" → "무조").
// 누르기 직전 PREROLL_S초도 버퍼에 들고 있다가 녹음 앞에 붙인다. 화면을 벗어나면 마이크를 끈다.
const PREROLL_S = 0.5;
let live = null;              // {ctx, stream, src, proc, ring, ringLen, recording, timer}
let pressed = false;

function micRelease() {
  if (!live) return;
  try { live.proc.disconnect(); live.src.disconnect(); } catch (e) {}
  live.stream.getTracks().forEach((t) => t.stop());
  live.ctx.close();
  live = null;
}
document.addEventListener("visibilitychange", () => { if (document.hidden && !pressed) micRelease(); });

async function ensureMic() {
  if (live) {
    if (live.ctx.state === "suspended") await live.ctx.resume();
    return live;
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC();                     // 누른 순간(사용자 동작 안)에 만들어야 iOS에서 소리가 들어온다
  ctx.resume();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    ctx.close();
    throw new Error("마이크 권한이 없어요");
  }
  const m = { ctx, stream, ring: [], ringLen: 0, recording: null, timer: null };
  m.src = ctx.createMediaStreamSource(stream);
  m.proc = ctx.createScriptProcessor(4096, 1, 1);
  m.proc.onaudioprocess = (e) => {
    const d = new Float32Array(e.inputBuffer.getChannelData(0));
    if (m.recording) { m.recording.push(d); return; }
    m.ring.push(d);
    m.ringLen += d.length;
    while (m.ring.length > 1 && m.ringLen - m.ring[0].length > ctx.sampleRate * PREROLL_S) m.ringLen -= m.ring.shift().length;
  };
  m.src.connect(m.proc);
  m.proc.connect(ctx.destination);
  live = m;
  return m;
}

async function recStart() {
  const m = await ensureMic();
  if (!pressed) {                           // 처음 권한 창이 떠 있는 동안 손을 뗀 경우: 마이크만 켜 두고 녹음은 안 함
    $("voice-reply").textContent = "마이크 준비 완료. 다시 누르고 말해 주세요";
    return;
  }
  m.recording = m.ring.slice();             // 누르기 직전 0.5초부터
  m.ring = [];
  m.ringLen = 0;
  m.timer = setTimeout(recStop, MAX_REC_S * 1000);
}

async function recStop() {
  if (!live || !live.recording) return;
  const chunks = live.recording;
  live.recording = null;
  clearTimeout(live.timer);
  const rate = live.ctx.sampleRate;
  const box = $("voice-reply");
  box.classList.remove("fail");
  const wav = encodeWav16k(chunks, rate);
  if (wav.seconds < 0.6 || wav.peak < 0.02) {
    box.textContent = "소리가 거의 안 들어왔어요. 버튼을 누른 채로 말해 주세요";
    box.classList.add("fail");
    return;
  }
  box.textContent = "알아듣는 중…";
  const form = new FormData();
  form.append("audio", wav.blob, "voice.wav");
  form.append("device", $("voice-device").value.trim());
  try {
    const res = await fetch("/api/voice/audio", { method: "POST", body: form });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.status);
    showResult(d);
    refresh();
  } catch (e) {
    box.textContent = "음성 인식 실패: " + e.message + " (입력칸을 써 주세요)";
    box.classList.add("fail");
  }
}

// --- ② 브라우저 음성 인식 ---
let srec = null, heard = "", useLocal = false;
function srStart() {
  heard = "";
  srec = new SR();
  srec.lang = "ko-KR";
  srec.interimResults = true;
  srec.maxAlternatives = 1;
  if (useLocal && "processLocally" in srec) srec.processLocally = true;   // 인터넷이 없을 때 기기 안 인식 시도
  srec.onresult = (ev) => {
    heard = Array.from(ev.results).map((x) => x[0].transcript).join("");
    $("voice-text").value = heard;
  };
  srec.onerror = (ev) => {
    if (ev.error === "network" && "processLocally" in srec && !useLocal) {
      useLocal = true;
      $("voice-reply").textContent = "인터넷이 없어 기기 안 인식으로 바꿨어요. 다시 눌러 주세요";
    } else if (ev.error !== "no-speech" && ev.error !== "aborted") {
      $("voice-reply").textContent = "음성 인식 오류: " + ev.error + " (입력칸을 써 주세요)";
    }
  };
  srec.onend = () => {
    srec = null;
    micBusy = false;
    micIdle();
    if (heard) sendVoice(heard);
  };
  srec.start();
}

// --- 버튼 ---
const mic = $("mic");
mic.addEventListener("pointerdown", async (e) => {
  e.preventDefault();
  if (micBusy || !micMode) return;
  micBusy = true;
  pressed = true;
  mic.classList.add("on");
  mic.textContent = "듣는 중… 다 말하면 떼세요";
  try {
    if (micMode === "whisper") await recStart();
    else srStart();
  } catch (err) {
    micBusy = false;
    micIdle();
    $("voice-reply").textContent = err.message;
    $("voice-reply").classList.add("fail");
  }
});
const micUp = async () => {
  pressed = false;
  if (!micBusy) return;
  if (micMode === "whisper") {
    micIdle();
    await recStop();
    micBusy = false;
  } else if (srec) {
    srec.stop();                            // onend에서 정리
  }
};
mic.addEventListener("pointerup", micUp);
mic.addEventListener("pointerleave", micUp);
mic.addEventListener("pointercancel", micUp);
mic.addEventListener("contextmenu", (e) => e.preventDefault());

syncTime();
refresh();
setInterval(refresh, 1000);
