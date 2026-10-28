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
  $("brain-text").textContent = (st.ai_meta
    ? `AI = 결정트리 (깊이 ${st.ai_meta.depth}, 시험 정확도 ${Math.round(st.ai_meta.test_acc * 100)}%)`
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

syncTime();
refresh();
setInterval(refresh, 1000);
