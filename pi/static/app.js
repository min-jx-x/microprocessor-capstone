// LightQ 대시보드: 1초마다 /api/state를 읽어 화면을 갱신한다.
// 외부 라이브러리 없이 SVG를 직접 그린다 (핫스팟에 인터넷이 없으므로).
const $ = (id) => document.getElementById(id);
const FILM = { off: "꺼짐", low: "45V", high: "100V" };

async function post(url, data) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!r.ok) throw new Error((await r.json()).error || r.status);
  refresh();
}

// ---------- 그래프 ----------
function path(points, xOf, yOf) {
  let d = "";
  points.forEach((p, i) => {
    const y = yOf(p);
    if (y === null) { d += " "; return; }          // 값이 없으면 선을 끊는다
    d += (d === "" || d.endsWith(" ") ? "M" : "L") + xOf(i).toFixed(1) + "," + y.toFixed(1);
  });
  return d.trim();
}

// 화면 폭에 맞춰 viewBox를 다시 잡는다. 고정 폭이면 휴대폰에서 글자가 옆으로 눌린다.
function fit(svg, H) {
  const W = Math.max(300, Math.round(svg.clientWidth || 600));
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  return W;
}

function drawChart(hist, sim) {
  const H = 220, W = fit($("chart"), H), L = 40, R = 6, T = 8, B = 20;
  const n = Math.max(hist.length, 2);
  const vals = hist.flatMap((p) => [p.lux, p.target || 0, sim ? p.outdoor || 0 : 0]);
  const maxV = niceMax(Math.max(100, ...vals));
  const xOf = (i) => L + (i / (n - 1)) * (W - L - R);
  const yOf = (v) => T + (1 - v / maxV) * (H - T - B);
  let s = "";
  for (let k = 0; k <= 4; k++) {                    // 가로 눈금 5개
    const v = (maxV * k) / 4, y = yOf(v);
    s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>`;
    s += `<text class="tick" x="${L - 4}" y="${y + 4}" text-anchor="end">${Math.round(v)}</text>`;
  }
  if (hist.length) {
    s += `<text class="tick" x="${L}" y="${H - 4}">${hist[0].t.slice(0, 5)}</text>`;
    s += `<text class="tick" x="${W - R}" y="${H - 4}" text-anchor="end">${hist[hist.length - 1].t.slice(0, 5)}</text>`;
  }
  // 목표가 없는 구간(저녁·취침: 0단계 고정)은 회색 띠로 표시한다. 이 구간에는 목표 점선이 없다.
  let runStart = null;
  hist.forEach((p, i) => {
    const off = p.target == null;
    if (off && runStart === null) runStart = i;
    if ((!off || i === hist.length - 1) && runStart !== null) {
      const end = off ? i : i - 1;
      const x0 = xOf(Math.max(runStart - 0.5, 0)), x1 = xOf(Math.min(end + 0.5, n - 1));
      s += `<rect class="p-off" x="${x0}" y="${T}" width="${Math.max(x1 - x0, 1)}" height="${H - T - B}"/>`;
      if (x1 - x0 > 70) s += `<text class="tick" x="${(x0 + x1) / 2}" y="${T + 14}" text-anchor="middle">목표 없음 (차광)</text>`;
      runStart = null;
    }
  });
  if (sim) s += `<path class="p-out" d="${path(hist, xOf, (p) => p.outdoor == null ? null : yOf(Math.min(p.outdoor, maxV)))}"/>`;
  s += `<path class="p-target" d="${path(hist, xOf, (p) => p.target == null ? null : yOf(p.target))}"/>`;
  s += `<path class="p-lux" d="${path(hist, xOf, (p) => yOf(p.lux))}"/>`;
  $("chart").innerHTML = s;
}

function drawLevels(hist, numLevels) {
  const H = 60, W = fit($("levelchart"), H), L = 40, R = 6, T = 4, B = 4;
  const n = Math.max(hist.length, 2), top = numLevels - 1;
  const xOf = (i) => L + (i / (n - 1)) * (W - L - R);
  const yOf = (lv) => T + (1 - lv / top) * (H - T - B);
  let d = "";                                       // 계단 모양: 단계는 바뀌기 전까지 유지되므로
  hist.forEach((p, i) => {
    const x = xOf(i), y = yOf(p.level);
    d += i === 0 ? `M${x},${y}` : `H${x}V${y}`;
  });
  let s = `<text class="tick" x="${L - 4}" y="${yOf(top) + 8}" text-anchor="end">${top}단계</text>`;
  s += `<text class="tick" x="${L - 4}" y="${yOf(0)}" text-anchor="end">0</text>`;
  s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${yOf(0)}" y2="${yOf(0)}"/>`;
  s += `<path class="p-level" d="${d}"/>`;
  $("levelchart").innerHTML = s;
}

function niceMax(v) {                               // 눈금이 깔끔하게 나오도록 올림
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p) return m * p;
  return 10 * p;
}

// ---------- 화면 갱신 ----------
let wakeEdited = false;

function render(st) {
  $("vtime").textContent = st.vtime;
  $("speed").textContent = st.speed === 0 ? "시각 고정" : st.speed !== 1 ? `${st.speed}×` : "";
  $("lux").textContent = st.lux == null ? "-" : Math.round(st.lux);
  const tgt = st.info && st.info.target;
  $("target").textContent = tgt == null ? "차광" : Math.round(tgt);
  $("target-unit").textContent = tgt == null ? "" : "lux";
  $("level").textContent = st.level;
  $("films").textContent = `필름 A ${FILM[st.films.A]} · B ${FILM[st.films.B]}`;
  $("period").textContent = (st.info && st.info.period_name) || "-";
  $("mode-text").textContent = st.mode === "auto" ? "자동 제어 중" : "수동 고정";
  $("switches").textContent = st.switches;
  $("mode-auto").classList.toggle("on", st.mode === "auto");
  $("mode-manual").classList.toggle("on", st.mode === "manual");
  document.querySelectorAll(".lv").forEach((b) =>
    b.classList.toggle("on", Number(b.dataset.level) === st.level));
  if (!wakeEdited) $("wake").value = st.wake_time;
  renderPref(st.pref);
  document.querySelectorAll("[data-brain]").forEach((b) => {
    b.classList.toggle("on", b.dataset.brain === st.brain);
    b.disabled = !st.brains.includes(b.dataset.brain);
  });
  const ans = (st.info && st.info.answers) || {};
  const rate = st.info && st.info.rate != null ? ` · 빛 변화율 ${(st.info.rate * 100).toFixed(0)}%` : "";
  const lutText = st.lut_source === "measured" ? "실측 투과율" : "가정 투과율";
  const meta = (st.ai_meta ? `AI = 결정트리(깊이 ${st.ai_meta.depth}, 시험 정확도 ${(st.ai_meta.test_acc * 100).toFixed(0)}%)` : "AI 모델 파일 없음") + ` · ${lutText}`;
  // 경고: 센서 연속 실패, 또는 투과율표가 바뀌었는데 AI를 다시 학습하지 않음
  const warns = [];
  if (st.sensor_fail >= st.sensor_fail_limit) warns.push(`센서 응답 없음 (${st.sensor_fail}회 연속) → 0단계로 전환함. 센서 배선을 확인하세요.`);
  else if (st.sensor_fail > 0) warns.push(`센서 읽기 실패 ${st.sensor_fail}회`);
  if (st.ai_meta && st.ai_meta.stale) warns.push("AI 모델이 지금과 다른 투과율표로 학습됨 → 노트북에서 python -m pi.ai.retrain 후 다시 올리세요.");
  $("alert").hidden = warns.length === 0;
  $("alert").textContent = warns.join(" / ");
  $("brain-text").textContent = st.info && st.info.target != null
    ? `지금 판단 — 규칙 ${ans.rule ?? "-"}단계, AI ${ans.ai ?? "-"}단계${rate}. ${meta}`
    : `목표가 없는 시간대라 두 방식 모두 0단계. ${meta}`;
  $("sim-panel").hidden = !st.sim;
  if (st.sim) {
    const last = st.history[st.history.length - 1];
    $("outdoor").textContent = last && last.outdoor != null ? Math.round(last.outdoor) : "-";
    document.querySelectorAll("#speeds button").forEach((b) =>
      b.classList.toggle("on", Number(b.dataset.speed) === st.speed));
  }
  drawChart(st.history, st.sim);
  drawLevels(st.history, st.num_levels);
}

// ---------- 개인 선호 ----------
let profileKey = "";
function renderPref(p) {
  if (!p) return;
  const key = p.profiles.join("|") + "#" + p.active;
  if (key !== profileKey && document.activeElement !== $("profile")) {   // 목록이 바뀔 때만 다시 그림
    const sel = $("profile");
    sel.replaceChildren(...p.profiles.map((n) => {   // 이름은 textContent로 넣어 HTML로 해석되지 않게
      const o = document.createElement("option");
      o.textContent = n;
      o.selected = n === p.active;
      return o;
    }));
    profileKey = key;
  }
  for (const g of ["morning", "day"]) {
    const [base, mine] = p.targets[g];
    const pct = Math.round(p.offset[g] * 100);
    $(`pref-${g}`).textContent = base === mine ? `${base} lux` : `${base} → ${mine} lux`;
    $(`pref-${g}-n`).textContent = `학습 ${p.count[g]}회` + (pct ? ` · ${pct > 0 ? "+" : ""}${pct}%` : "");
  }
  const last = p.last;
  $("pref-text").textContent = p.measuring
    ? "선호 조도 측정 중… (3초)"
    : last
      ? `${last.vtime} ${last.period_name} ${last.preferred} lux를 선호로 학습 → 목표 보정 ${last.offset > 0 ? "+" : ""}${Math.round(last.offset * 100)}%`
      : "단계를 직접 바꾸면 3초 동안 실내 조도를 재서 그 밝기를 이 사용자의 선호로 배웁니다.";
}

async function refresh() {
  try {
    const r = await fetch("/api/state");
    render(await r.json());
  } catch (e) {
    $("mode-text").textContent = "연결 끊김";
  }
}

// ---------- 버튼 ----------
document.querySelectorAll(".lv").forEach((b) =>
  b.addEventListener("click", () => post("/api/level", { level: Number(b.dataset.level) })));
document.querySelectorAll("[data-brain]").forEach((b) =>
  b.addEventListener("click", () => post("/api/brain", { brain: b.dataset.brain })));
document.querySelectorAll("[data-mode]").forEach((b) =>
  b.addEventListener("click", () => post("/api/mode", { mode: b.dataset.mode })));
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
$("wake").addEventListener("input", () => { wakeEdited = true; });
$("wake-save").addEventListener("click", async () => {
  try {
    await post("/api/settings", { wake_time: $("wake").value });
    wakeEdited = false;
    $("wake-msg").textContent = "저장됨";
  } catch (e) {
    $("wake-msg").textContent = "실패: " + e.message;
  }
  setTimeout(() => ($("wake-msg").textContent = ""), 2000);
});

refresh();
setInterval(refresh, 1000);
