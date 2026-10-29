// 라이트큐 AI 설명 페이지.
// 실험 결과(/api/ai/report)와 모델(/api/ai/model)은 처음에 한 번, 지금 판단(/api/ai/explain)은 1초마다 읽는다.
// 외부 라이브러리 없이 SVG를 직접 그린다 (핫스팟에 인터넷이 없으므로).
const $ = (id) => document.getElementById(id);
const pct = (v, d = 1) => (v == null ? "-" : (v * 100).toFixed(d) + "%");
const pp = (a, b) => `${((a - b) * 100).toFixed(1)}%p`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const setR = (key, text) => document.querySelectorAll(`[data-r="${key}"]`).forEach((e) => (e.textContent = text));
let report = null;

// ---------- 그래프 ----------
// 폭은 상자에 맞추고 높이는 내용(막대 개수)에 맞춘다.
function sized(svg, H) {
  const W = Math.max(280, Math.round(svg.parentElement.getBoundingClientRect().width));
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("height", H);
  return W;
}

// 가로 막대. items: [{label, value, cls}]
function hbars(svg, items, { max = 1, fmt = (v) => pct(v) } = {}) {
  const row = 30, T = 4;
  const W = sized(svg, T * 2 + row * items.length);
  const L = Math.min(190, Math.round(W * 0.42)), R = 56;
  let s = "";
  items.forEach((it, i) => {
    const y = T + i * row, w = Math.max(1, (it.value / max) * (W - L - R));
    s += `<text class="bl" x="${L - 8}" y="${y + row / 2 + 4}" text-anchor="end">${esc(it.label)}</text>`;
    s += `<rect class="${it.cls || "b-other"}" x="${L}" y="${y + 5}" width="${w.toFixed(1)}" height="${row - 10}" rx="3"/>`;
    s += `<text class="bv" x="${L + w + 6}" y="${y + row / 2 + 4}">${fmt(it.value)}</text>`;
  });
  svg.innerHTML = s;
}

// 트리 깊이: 시험·학습 정확도 꺾은선, 아래에 잎 개수
function depthChart(svg, rows, cur) {
  const H = 210, L = 56, R = 12, T = 12, B = 42;
  const W = sized(svg, H);
  const vals = rows.flatMap((r) => [r.change, r.train_change]);
  const lo = Math.floor(Math.min(...vals) * 20) / 20, hi = Math.ceil(Math.max(...vals) * 20) / 20;
  const xOf = (i) => L + (i / (rows.length - 1)) * (W - L - R);
  const yOf = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let s = "";
  for (let v = lo; v <= hi + 1e-9; v += 0.05) {
    s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${yOf(v)}" y2="${yOf(v)}"/>`;
    s += `<text class="tick" x="${L - 6}" y="${yOf(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`;
  }
  const ci = rows.findIndex((r) => r.depth === cur);
  if (ci >= 0) s += `<rect class="p-off" x="${xOf(ci) - 12}" y="${T}" width="24" height="${H - T - B}"/>`;
  const line = (k, cls) => `<path class="${cls}" d="${rows.map((r, i) => (i ? "L" : "M") + xOf(i).toFixed(1) + "," + yOf(r[k]).toFixed(1)).join("")}"/>`;
  s += line("train_change", "p-target") + line("change", "p-lux");
  rows.forEach((r, i) => {
    s += `<circle class="dot" cx="${xOf(i)}" cy="${yOf(r.change)}" r="3.5"/>`;
    s += `<text class="tick" x="${xOf(i)}" y="${H - B + 16}" text-anchor="middle">${r.depth}</text>`;
    s += `<text class="tick dim" x="${xOf(i)}" y="${H - B + 32}" text-anchor="middle">${r.leaves}</text>`;
  });
  s += `<text class="tick" x="${L - 22}" y="${H - B + 16}" text-anchor="end">깊이</text>`;
  s += `<text class="tick dim" x="${L - 22}" y="${H - B + 32}" text-anchor="end">잎</text>`;
  s += `<text class="tick" x="${W - R}" y="${T + 10}" text-anchor="end">― 시험  ┄ 학습</text>`;
  svg.innerHTML = s;
}

// 예측 시간: 시간마다 반응(초)·눈부심(초) 묶음 막대, 점선 = 규칙. 너무 큰 값은 잘라서 표시
function horizonChart(svg, rows, rule, cur) {
  const H = 210, L = 34, R = 12, T = 16, B = 42;
  const W = sized(svg, H);
  const inner = rows.filter((r) => r.burst_delay < 15).flatMap((r) => [r.burst_delay, r.burst_glare]);
  const cap = Math.ceil(Math.max(rule.burst_delay, ...inner) * 1.25);
  const yOf = (v) => T + (1 - Math.min(v, cap) / cap) * (H - T - B);
  const gw = (W - L - R) / rows.length, bw = Math.min(26, gw * 0.3);
  let s = "";
  for (let v = 0; v <= cap; v += cap > 10 ? 4 : 2) {
    s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${yOf(v)}" y2="${yOf(v)}"/>`;
    s += `<text class="tick" x="${L - 6}" y="${yOf(v) + 4}" text-anchor="end">${v}</text>`;
  }
  rows.forEach((r, i) => {
    const cx = L + gw * (i + 0.5);
    if (r.horizon === cur) s += `<rect class="p-off" x="${cx - gw / 2 + 4}" y="${T}" width="${gw - 8}" height="${H - T - B}"/>`;
    [["burst_delay", "b-cur", -1], ["burst_glare", "b-warn", 0]].forEach(([k, cls, off]) => {
      const v = r[k], x = cx + off * bw + (off ? -2 : 2);
      s += `<rect class="${cls}" x="${x}" y="${yOf(v)}" width="${bw}" height="${H - B - yOf(v)}" rx="2"/>`;
      s += `<text class="bv sm" x="${x + bw / 2}" y="${yOf(v) - 4}" text-anchor="middle">${v > cap ? "↑" : ""}${v.toFixed(1)}</text>`;
    });
    s += `<text class="tick" x="${cx}" y="${H - B + 16}" text-anchor="middle">${r.horizon}초</text>`;
  });
  [["burst_delay", "p-lux"], ["burst_glare", "p-target"]].forEach(([k, cls]) =>
    (s += `<line class="${cls}" stroke-dasharray="4 4" x1="${L}" x2="${W - R}" y1="${yOf(rule[k])}" y2="${yOf(rule[k])}"/>`));
  s += `<text class="tick" x="${L}" y="${H - 6}"><tspan class="t-cur">■</tspan> 어둡게 바꿀 때까지(초)  <tspan class="t-warn">■</tspan> 눈부심 시간(초)  ┄ 규칙</text>`;
  svg.innerHTML = s;
}

// ---------- 실험 결과 ----------
function renderReport(r) {
  report = r;
  const top = r.levels - 1;
  setR("top_level", top);
  setR("stable_count", r.stabilizer.stable_count);
  setR("min_interval", r.stabilizer.min_interval_s);
  setR("depth", r.current.depth);
  setR("horizon", r.current.horizon);
  const by = Object.fromEntries(r.models.map((m) => [m.key, m]));
  const tree = by.tree;

  hbars($("models-chart"), r.models.map((m) => ({
    label: m.name, value: m.change, cls: m.current ? "b-cur" : m.baseline ? "b-base" : "b-other" })));
  const head = "<tr><th>모델</th><th>바꿔야 할 때</th><th>빛 오르는 중</th><th>단계별 평균</th><th>전체</th><th>Pi에 올리는 방법</th><th>설명</th></tr>";
  $("models-table").innerHTML = head + r.models.map((m) => `<tr class="${m.current ? "cur" : m.baseline ? "base" : ""}">
    <td>${esc(m.name)}</td><td>${pct(m.change)}</td><td>${pct(m.rising)}</td><td>${pct(m.balanced)}</td><td>${pct(m.acc)}</td>
    <td>${m.baseline ? "기준선" : `${esc(m.deploy)} (${m.size_kb < 1024 ? m.size_kb.toFixed(1) + " KB" : (m.size_kb / 1024).toFixed(1) + " MB"})`}</td>
    <td>${m.baseline ? "" : esc(m.explain)}</td></tr>`).join("");
  const best = Math.max(...["forest", "boost", "mlp"].filter((k) => by[k]).map((k) => by[k].change));
  $("gap").textContent = pp(best, tree.change);
  $("tree-kb").textContent = `${tree.size_kb.toFixed(1)} KB`;
  $("top-share").textContent = pct(r.dataset.label_share[top], 0);
  $("top-acc").textContent = pct(by.always_top.acc);

  const maxImp = Math.max(...r.importance.map((x) => x.value));
  hbars($("imp-chart"), r.importance.map((x) => ({ label: x.label, value: x.value, cls: "b-cur" })),
    { max: maxImp, fmt: (v) => pct(v, 0) });
  hbars($("abl-chart"), r.ablation.map((a, i) => ({
    label: i ? `${a.name} 빼면` : a.name, value: a.change, cls: i ? "b-other" : "b-cur" })));
  const full = r.ablation[0];
  const why = { rate1: "AI가 규칙보다 나은 이유. 빛이 오르는 속도를 봐야 미리 어둡게 할 수 있다",
                log_tneed: "가장 중요한 입력. 규칙은 이 값 하나만 본다",
                target: "시간대(아침·주간)마다 목표가 달라 조금 도움이 된다",
                cur: "거의 차이 없음. 필요 투과율 계산에 현재 단계가 이미 들어 있다" };
  $("feature-points").innerHTML = r.ablation.slice(1).map((a) =>
    `<li><b>${esc(a.name)}</b> 없이: ${pct(full.change)} → ${pct(a.change)} (${pp(a.change, full.change)}). ${why[a.drop[0]] || ""}</li>`).join("");

  depthChart($("depth-chart"), r.depth, r.current.depth);
  const dc = r.depth.find((d) => d.depth === r.current.depth), dl = r.depth[r.depth.length - 1];
  $("depth-text").textContent = `깊이 ${dc.depth}에서 ${pct(dc.change)}. 가장 깊은 ${dl.depth}도 ${pct(dl.change)}로 `
    + `차이가 ${pp(dl.change, dc.change)}인데, 잎(사람이 읽어야 할 규칙 수)은 ${dc.leaves} → ${dl.leaves}개로 늘어납니다. `
    + `학습 날짜와 시험 날짜의 차이도 ${pp(dc.train_change, dc.change)}라 과적합이 작습니다.`;

  horizonChart($("hz-chart"), r.horizon, r.horizon_rule, r.current.horizon);
  const hc = r.horizon.find((h) => h.horizon === r.current.horizon);
  const h0 = r.horizon[0], hn = r.horizon[r.horizon.length - 1], rr = r.horizon_rule;
  let t = `${hc.horizon}초: 반응 ${hc.burst_delay.toFixed(1)}초, 눈부심 ${hc.burst_glare.toFixed(1)}초 `
    + `(규칙 ${rr.burst_delay.toFixed(1)}초, ${rr.burst_glare.toFixed(1)}초). `;
  if (h0.burst_glare > hc.burst_glare) t += `${h0.horizon}초는 미리 보는 시간이 짧아 안정화 지연을 못 메웁니다(눈부심 ${h0.burst_glare.toFixed(1)}초). `;
  if (hn.burst_glare > hc.burst_glare) t += `${hn.horizon}초는 먼 미래라 예측이 흔들려 오히려 늦어집니다(반응 ${hn.burst_delay.toFixed(1)}초).`;
  $("hz-text").textContent = t;

  $("lut-src").textContent = r.lut_source === "measured" ? "실측값" : "가정값";
  $("report-meta").textContent = `실험 ${r.generated} · 학습 ${r.dataset.train_rows}행 / 시험 ${r.dataset.test_rows}행 · `
    + `${r.levels}단계, 투과율 ${r.lut_source === "measured" ? "실측" : "가정값"} [${r.lut.join(", ")}] · python -m pi.ai.compare_models`;
}

function noReport(msg) {
  ["models-table"].forEach((id) => ($(id).innerHTML = `<tr><td>${esc(msg)}</td></tr>`));
}

// ---------- 트리 ----------
function treeHTML(n) {
  if (n.level != null) return `<span class="tl">${n.level}단계</span>`;
  if (n.levels) return `<span class="tmore">아래로 더 나뉨 → ${n.levels.join("·")}단계</span>`;
  return `<span class="tq">${esc(n.label)} ≤ ${esc(n.threshold)} ?</span>
    <ul><li><i class="yes">예</i>${treeHTML(n.yes)}</li><li><i class="no">아니오</i>${treeHTML(n.no)}</li></ul>`;
}

function renderModel(m) {
  if (!m.top) { $("tree-meta").textContent = "AI 모델 파일 없음 → 규칙만 사용"; return; }
  const meta = m.meta || {};
  $("tree-meta").textContent = `깊이 ${meta.depth}, 잎 ${meta.leaves}개, 학습 ${meta.trained}`
    + (meta.stale ? " · 주의: 지금 투과율과 다르게 학습됨 → 규칙으로 시작 (python -m pi.ai.retrain)" : "");
  $("tree").innerHTML = treeHTML(m.top);
}

// ---------- 지금 판단 ----------
const lv = (v) => (v == null ? "-" : `${v}단계`);

function renderLive(e) {
  const who = e.mode === "auto" ? `자동 (${e.brain === "ai" ? "AI" : "규칙"})` : "수동 고정";
  $("period-chip").textContent = e.period_name || "-";
  $("live-status").textContent = `${e.period_name || "-"} · ${e.target == null ? "목표 없음" : `목표 ${Math.round(e.target)} lux`}`
    + ` · 실내 ${e.lux == null ? "-" : Math.round(e.lux)} lux · ${who}`;
  let note = "";
  if (e.target == null) note = "저녁·취침에는 목표가 없어 판단하지 않고 0단계(차광)로 둡니다.";
  else if (!e.ai) note = "AI 모델 파일이 없어 규칙만 씁니다.";
  $("live-note").hidden = !note;
  $("live-note").textContent = note;
  $("live").hidden = e.target == null;
  if (e.target == null) return;

  const ai = e.ai;
  $("inputs").innerHTML = ai ? ai.inputs.map((x) => `<dt>${esc(x.label)}</dt><dd>${esc(x.value)}</dd>`).join("") : "";
  $("path").innerHTML = ai ? ai.path.map((c) =>
    `<li>${esc(c.label)} <b>${esc(c.value)}</b> ≤ ${esc(c.threshold)} ? <i class="${c.yes ? "yes" : "no"}">${c.yes ? "예" : "아니오"}</i></li>`).join("") : "";
  $("leaf").textContent = ai ? `→ ${ai.level}단계` : "-";

  const ans = e.answers || {};
  $("ans-rule").textContent = lv(ans.rule);
  if (e.rule) {
    const best = e.rule.levels.reduce((a, b) => (b.err < a.err ? b : a));
    let w = `필요 투과율 ${e.rule.t_need.toFixed(2)}에 가장 가까운 ${best.level}단계(${best.t.toFixed(2)})`;
    if (ans.rule !== best.level) w += `, 지금 단계도 오차 ${e.rule.deadband} 안이라 유지`;
    $("rule-why").textContent = w;
  }
  $("ans-ai").textContent = lv(ans.ai);
  $("ai-why").textContent = ai ? `트리 질문 ${ai.path.length}개를 거쳐 도착` : "";

  const st = e.stab;
  if (e.mode !== "auto") {
    $("stab").textContent = "-";
    $("stab-why").textContent = "수동 모드에서는 쓰지 않음";
  } else if (e.candidate === e.level) {
    $("stab").textContent = "유지";
    $("stab-why").textContent = "후보가 지금 단계와 같음";
  } else {
    $("stab").textContent = `${st.count}/${st.need}회`;
    $("stab-why").textContent = `${st.direction > 0 ? "밝게" : "어둡게"} 후보가 연속 ${st.count}번`
      + (st.wait_s > 0 ? `, 다음 전환까지 ${st.wait_s}초` : "");
  }
  $("applied").textContent = lv(e.level);
  $("applied-why").textContent = e.mode === "auto" ? `${e.brain === "ai" ? "AI" : "규칙"} 판단을 안정화한 결과` : "사용자가 직접 고름";
}

async function refreshLive() {
  try {
    renderLive(await (await fetch("/api/ai/explain")).json());
  } catch (err) {
    $("live-status").textContent = "연결 끊김";
  }
}

async function init() {
  try {
    const r = await fetch("/api/ai/report");
    const d = await r.json();
    r.ok ? renderReport(d) : noReport(d.error || "실험 결과 없음");
  } catch (err) {
    noReport("실험 결과를 불러오지 못함");
  }
  try { renderModel(await (await fetch("/api/ai/model")).json()); } catch (err) { /* 모델 정보는 없어도 됨 */ }
}

// 창 크기가 바뀌면 그래프를 다시 맞춘다
let lastW = 0;
new ResizeObserver(([en]) => {
  const w = Math.round(en.contentRect.width);
  if (report && w !== lastW) renderReport(report);
  lastW = w;
}).observe(document.querySelector(".doc-main"));

init();
refreshLive();
setInterval(refreshLive, 1000);
