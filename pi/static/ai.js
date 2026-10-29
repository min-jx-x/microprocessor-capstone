// 라이트큐 AI 설명 페이지.
// 실험 결과(/api/ai/report)는 처음에 한 번, 지금 판단(/api/ai/explain)은 1초마다 읽는다.
// 외부 라이브러리 없이 SVG를 직접 그린다 (핫스팟에 인터넷이 없으므로).
const $ = (id) => document.getElementById(id);
const pct = (v, d = 1) => (v == null ? "-" : (v * 100).toFixed(d) + "%");
const pp = (a, b) => `${a >= b ? "+" : "−"}${(Math.abs(a - b) * 100).toFixed(1)}%p`;
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
  const L = Math.min(170, Math.round(W * 0.4)), R = 56;
  let s = "";
  items.forEach((it, i) => {
    const y = T + i * row, w = Math.max(1, (it.value / max) * (W - L - R));
    s += `<text class="bl${it.cls === "b-cur" ? " strong" : ""}" x="${L - 8}" y="${y + row / 2 + 4}" text-anchor="end">${esc(it.label)}</text>`;
    s += `<rect class="${it.cls || "b-other"}" x="${L}" y="${y + 5}" width="${w.toFixed(1)}" height="${row - 10}" rx="3"/>`;
    s += `<text class="bv" x="${L + w + 6}" y="${y + row / 2 + 4}">${fmt(it.value)}</text>`;
  });
  svg.innerHTML = s;
}

// 트리 깊이: 깊이별 정확도 꺾은선, 아래에 잎(규칙) 개수
function depthChart(svg, rows, cur) {
  const H = 200, L = 56, R = 12, T = 12, B = 42;
  const W = sized(svg, H);
  const vals = rows.map((r) => r.change);
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
  s += `<path class="p-lux" d="${rows.map((r, i) => (i ? "L" : "M") + xOf(i).toFixed(1) + "," + yOf(r.change).toFixed(1)).join("")}"/>`;
  rows.forEach((r, i) => {
    s += `<circle class="dot" cx="${xOf(i)}" cy="${yOf(r.change)}" r="3.5"/>`;
    s += `<text class="tick" x="${xOf(i)}" y="${H - B + 16}" text-anchor="middle">${r.depth}</text>`;
    s += `<text class="tick dim" x="${xOf(i)}" y="${H - B + 32}" text-anchor="middle">${r.leaves}</text>`;
  });
  s += `<text class="tick" x="${L - 22}" y="${H - B + 16}" text-anchor="end">깊이</text>`;
  s += `<text class="tick dim" x="${L - 22}" y="${H - B + 32}" text-anchor="end">규칙 수</text>`;
  svg.innerHTML = s;
}

// 예측 시간: 직사광 장면의 눈부심 시간(초) 막대, 점선 = 규칙. 너무 큰 값은 잘라서 표시
function horizonChart(svg, rows, rule, cur) {
  const H = 200, L = 34, R = 12, T = 18, B = 40;
  const W = sized(svg, H);
  const cap = Math.ceil(Math.max(rule.burst_glare, ...rows.filter((r) => r.burst_glare < 5).map((r) => r.burst_glare)) * 1.6);
  const yOf = (v) => T + (1 - Math.min(v, cap) / cap) * (H - T - B);
  const gw = (W - L - R) / rows.length, bw = Math.min(40, gw * 0.5);
  let s = "";
  for (let v = 0; v <= cap; v += 1) {
    s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${yOf(v)}" y2="${yOf(v)}"/>`;
    s += `<text class="tick" x="${L - 6}" y="${yOf(v) + 4}" text-anchor="end">${v}</text>`;
  }
  rows.forEach((r, i) => {
    const cx = L + gw * (i + 0.5), v = r.burst_glare;
    s += `<rect class="${r.horizon === cur ? "b-cur" : "b-other"}" x="${cx - bw / 2}" y="${yOf(v)}" width="${bw}" height="${H - B - yOf(v)}" rx="3"/>`;
    s += `<text class="bv" x="${cx}" y="${yOf(v) - 5}" text-anchor="middle">${v > cap ? "↑" : ""}${v.toFixed(1)}</text>`;
    s += `<text class="tick${r.horizon === cur ? " strong" : ""}" x="${cx}" y="${H - B + 16}" text-anchor="middle">${r.horizon}초 앞</text>`;
  });
  s += `<line class="p-target" stroke-dasharray="5 4" x1="${L}" x2="${W - R}" y1="${yOf(rule.burst_glare)}" y2="${yOf(rule.burst_glare)}"/>`;
  s += `<text class="tick" x="${L}" y="${H - 6}">직사광 때 눈부심 시간(초), 낮을수록 좋음 · <tspan class="t-rule">┄ 규칙 ${rule.burst_glare.toFixed(1)}초</tspan></text>`;
  svg.innerHTML = s;
}

// ---------- 실험 결과 ----------
function renderReport(r) {
  report = r;
  const top = r.levels - 1;
  setR("top_level", top);
  setR("stable_count", r.stabilizer.stable_count);
  setR("depth", r.current.depth);
  setR("horizon", r.current.horizon);
  const by = Object.fromEntries(r.models.map((m) => [m.key, m]));
  const tree = by.tree;

  // 모델 비교: 큰 숫자 3개 + 막대 (기준선 중 규칙만 막대에 넣고, 나머지 기준선은 표에)
  const complex = ["forest", "boost", "mlp"].map((k) => by[k]).filter(Boolean);
  const best = complex.reduce((a, b) => (b.change > a.change ? b : a));
  $("s-tree").textContent = pct(tree.change);
  $("s-tree-sub").textContent = `규칙 ${pct(by.rule.change)}보다 ${pp(tree.change, by.rule.change)}`;
  $("s-gap").textContent = pp(best.change, tree.change).replace("+", "");
  $("s-gap-sub").textContent = `${best.name.replace(/ \(.*\)/, "")} ${pct(best.change)}`;
  $("s-kb").textContent = `${tree.size_kb.toFixed(1)} KB`;
  const shown = r.models.filter((m) => !m.baseline || m.key === "rule").sort((a, b) => b.change - a.change);
  hbars($("models-chart"), shown.map((m) => ({
    label: m.name.replace(/ \(깊이 \d+, 현재\)/, " (현재)"), value: m.change,
    cls: m.current ? "b-cur" : m.baseline ? "b-base" : "b-other" })));
  $("metric-hint").textContent = `정확도 = 단계를 바꿔야 하는 순간에 맞힌 비율. 정답의 ${pct(r.dataset.label_share[top], 0)}가 `
    + `"가장 밝은 단계"라, 항상 가장 밝게만 해도 전체 정확도가 ${pct(by.always_top.acc)}이기 때문입니다.`;
  const head = "<tr><th>모델</th><th>바꿔야 할 때</th><th>빛 오르는 중</th><th>전체</th><th>Pi에 올리는 방법</th><th>설명</th></tr>";
  $("models-table").innerHTML = head + r.models.map((m) => `<tr class="${m.current ? "cur" : m.baseline ? "base" : ""}">
    <td>${esc(m.name)}</td><td>${pct(m.change)}</td><td>${pct(m.rising)}</td><td>${pct(m.acc)}</td>
    <td>${m.baseline ? "기준선" : `${esc(m.deploy)} (${m.size_kb < 1024 ? m.size_kb.toFixed(1) + " KB" : (m.size_kb / 1024).toFixed(1) + " MB"})`}</td>
    <td>${m.baseline ? "" : esc(m.explain)}</td></tr>`).join("");

  // 특징: 빼면 얼마나 떨어지나
  const full = r.ablation[0];
  const drop = (k) => r.ablation.find((a) => a.drop.includes(k));
  $("s-rate").textContent = pp(drop("rate1").change, full.change);
  $("s-tneed").textContent = pp(drop("log_tneed").change, full.change);
  hbars($("abl-chart"), r.ablation.map((a, i) => ({
    label: i ? `${a.name} 빼면` : "전부 사용", value: a.change, cls: i ? "b-other" : "b-cur" })));

  // 깊이·예측 시간: 한 줄 결론 + 그래프
  const dc = r.depth.find((d) => d.depth === r.current.depth), dl = r.depth[r.depth.length - 1];
  $("depth-take").innerHTML = `더 깊게 해도 <b>${pp(dl.change, dc.change)}</b>뿐인데, 규칙 수는 <b>${dc.leaves} → ${dl.leaves}개</b>`;
  depthChart($("depth-chart"), r.depth, r.current.depth);
  const hc = r.horizon.find((h) => h.horizon === r.current.horizon);
  $("hz-take").innerHTML = `${hc.horizon}초 앞에서 눈부심 <b>${hc.burst_glare.toFixed(1)}초</b>로 가장 적음 (규칙 ${r.horizon_rule.burst_glare.toFixed(1)}초)`;
  horizonChart($("hz-chart"), r.horizon, r.horizon_rule, r.current.horizon);

  $("report-meta").textContent = `시뮬레이션 결과 (기상청 일사량 곡선 + 합성 직사광, 필름 투과율 ${r.lut_source === "measured" ? "실측값" : "가정값"}). `
    + `실측 후 python -m pi.ai.retrain 으로 다시 계산 · ${r.generated}`;
}

// ---------- 지금 판단 ----------
const lv = (v) => (v == null ? "-" : `${v}단계`);

function renderLive(e) {
  const who = e.mode === "auto" ? `자동 (${e.brain === "ai" ? "AI" : "규칙"})` : "수동";
  $("period-chip").textContent = e.period_name || "-";
  $("live-status").textContent = `${e.target == null ? "목표 없음" : `목표 ${Math.round(e.target)} lux`}`
    + ` · 실내 ${e.lux == null ? "-" : Math.round(e.lux)} lux · ${who}`;
  let note = "";
  if (e.target == null) note = "저녁·취침에는 판단하지 않고 0단계(차광)로 둡니다.";
  else if (!e.ai) note = "AI 모델 파일이 없어 규칙만 씁니다.";
  $("live-note").hidden = !note;
  $("live-note").textContent = note;
  $("live").hidden = e.target == null;
  if (e.target == null) return;

  const ai = e.ai, ans = e.answers || {};
  const val = (k) => ai && (ai.inputs.find((x) => x.feature === k) || {}).value;
  $("inputs").innerHTML = ai ? [["필요 투과율", val("log_tneed")], ["빛 변화", val("rate1")], ["목표", val("target")]]
    .map(([k, v]) => `<span class="chip-in">${k} <b>${esc(v)}</b></span>`).join("") : "";
  $("path").innerHTML = ai ? ai.path.map((c) =>
    `<li>${esc(c.label)} <b>${esc(c.value)}</b> ≤ ${esc(c.threshold)} ? <i class="${c.yes ? "yes" : "no"}">${c.yes ? "예" : "아니오"}</i></li>`).join("")
    + `<li class="end">→ ${ai.level}단계</li>` : "";

  $("ans-rule").textContent = lv(ans.rule);
  if (e.rule) $("rule-why").textContent = `필요 투과율 ${e.rule.t_need.toFixed(2)}에 가까운 단계`;
  $("ans-ai").textContent = lv(ans.ai);
  $("ai-why").textContent = ai ? `빛 변화 ${val("rate1")} · 질문 ${ai.path.length}개` : "";
  $("applied").textContent = lv(e.level);
  const st = e.stab;
  let why = "직접 고름";
  if (e.mode === "auto") {
    if (e.candidate === e.level) why = "유지";
    else why = `${st.direction > 0 ? "밝게" : "어둡게"} 확인 중 ${st.count}/${st.need}` + (st.wait_s > 0 ? ` · ${st.wait_s}초 대기` : "");
  }
  $("applied-why").textContent = why;
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
    if (r.ok) renderReport(d);
    else $("report-meta").textContent = d.error || "실험 결과 없음";
  } catch (err) {
    $("report-meta").textContent = "실험 결과를 불러오지 못함";
  }
}

// 창 폭이 바뀔 때만 그래프를 다시 맞춘다 (실시간 영역 높이 변화로 매초 다시 그리지 않게)
let lastW = 0;
new ResizeObserver(([en]) => {
  const w = Math.round(en.contentRect.width);
  if (report && w !== lastW) renderReport(report);
  lastW = w;
}).observe(document.querySelector(".doc-main"));

init();
refreshLive();
setInterval(refreshLive, 1000);
