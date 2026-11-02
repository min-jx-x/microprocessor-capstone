// 라이트큐 휴대폰 앱(/app): 홈 / 음성 / 설정 탭. 탭은 주소 해시(#home 등)로 바꿔 페이지를 다시 읽지 않는다.
// 상태는 /api/state를 1초마다 읽고, 조작은 대시보드와 같은 API를 쓴다. 녹음은 voice-rec.js (대시보드와 같은 코드).
const $ = (id) => document.getElementById(id);
const TABS = ["home", "voice", "settings"];
let last = null;

async function post(url, data) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  refresh();
}

function setSwitch(el, on) { el.setAttribute("aria-checked", on ? "true" : "false"); }

// ---------- 탭 ----------
function showTab() {
  let tab = location.hash.slice(1);
  if (!TABS.includes(tab)) {
    tab = "home";
    history.replaceState(null, "", "#home");
  }
  document.body.dataset.tab = tab;
  TABS.forEach((t) => { $(`tab-${t}`).hidden = t !== tab; });
  document.querySelectorAll(".m-tabs a").forEach((a) => {
    if (a.dataset.tab === tab) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", showTab);
showTab();

// ---------- 화면 갱신 ----------
function levelName(lv, top) { return lv === 0 ? "불투명" : lv === top ? "투명" : "반투명"; }

function renderHome(st) {
  const info = st.info || {};
  const top = st.num_levels - 1;
  $("lux").textContent = st.lux == null ? "-" : Math.round(st.lux);
  $("period").textContent = info.period_name || "";
  const tgt = info.target;
  const goal = tgt == null ? "목표 없음 · 차광" : `목표 ${Math.round(tgt)} lux`;
  $("status-line").textContent = st.mode === "auto"
    ? `${st.brain === "ai" ? "AI가" : "규칙이"} 조절 중 · ${goal}`
    : `직접 고정 · ${st.level}단계 (${goal})`;
  $("status-line").classList.toggle("manual", st.mode !== "auto");
  // 창문: 단계가 낮을수록 뿌옇게 (유리 위 흰 막 + 바깥 풍경 흐림)
  const fog = top > 0 ? 1 - st.level / top : 0;
  $("frost").style.opacity = (0.06 + 0.8 * fog).toFixed(2);
  $("fog-blur").setAttribute("stdDeviation", (5 * fog).toFixed(1));
  $("window-cap").textContent = `${st.level}단계 · ${levelName(st.level, top)}`;
  document.querySelectorAll(".m-lv").forEach((b) => b.classList.toggle("on", Number(b.dataset.level) === st.level));
  setSwitch($("auto-switch"), st.mode === "auto");
  $("home-auto").hidden = st.mode === "auto";
}

let wakeEdited = false;
let profileKey = "";

function renderSettings(st) {
  const lock = !!st.demo_lock;
  $("lock-badge").hidden = !lock;
  $("lock-note").hidden = !lock;
  ["profile", "new-profile", "profile-add", "pref-reset", "learn-switch", "voice-learn"].forEach((id) => { $(id).disabled = lock; });

  if (!wakeEdited) $("wake").value = st.wake_time;
  $("wake-big").textContent = st.wake_time;

  const p = st.pref;
  if (p) {
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
      const pos = Math.min(1, Math.max(0, (p.offset[g] + 0.3) / 0.6)) * 100;   // -30% ~ +30%를 0~100%로
      box.querySelector(".m-sl i").style.width = `${pos}%`;
      box.querySelector(".m-sl b").style.left = `${pos}%`;
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
  if (st.voice) setSwitch($("voice-learn"), st.voice.status.learn);
}

function renderVoiceTab(st) {
  $("v-level").textContent = `${st.level}단계`;
  $("v-lux").textContent = st.lux == null ? "-" : `${Math.round(st.lux)} lux`;
  $("v-mode").textContent = st.mode === "auto" ? "자동" : "수동";
  $("v-mode").classList.toggle("manual", st.mode !== "auto");
  $("voice-auto").disabled = st.mode === "auto";
  const s = st.voice && st.voice.status;
  if (!s) return;
  mic.update(s);
  // 마이크를 못 쓸 때 이유와 대안을 위에 띄운다
  const notice = $("notice");
  const url = VoiceRec.httpsUrl(s);
  if (mic.mode) {
    notice.hidden = true;
  } else if (url) {
    notice.hidden = false;
    notice.replaceChildren("마이크는 보안 주소에서만 켜져요. ",
      Object.assign(document.createElement("a"), { href: url + location.hash, textContent: "여기를 눌러 다시 접속" }),
      " (경고가 뜨면 고급 → 계속)");
  } else {
    notice.hidden = false;
    notice.textContent = "이 브라우저에서는 마이크를 쓸 수 없어요. 아래 예시를 누르거나 '글자로 입력'을 써 주세요";
  }
}

function render(st) {
  last = st;
  renderHome(st);
  renderVoiceTab(st);
  renderSettings(st);
}

async function refresh() {
  try {
    const r = await fetch("/api/state");
    render(await r.json());
    $("conn").textContent = "연결됨";
    $("conn").classList.remove("off");
  } catch (e) {
    $("conn").textContent = "연결 끊김";
    $("conn").classList.add("off");
  }
}

// ---------- 홈 조작 ----------
function homeMsg(text, fail) {
  $("home-msg").textContent = text;
  $("home-msg").classList.toggle("fail", !!fail);
}
async function tryPost(url, data, onFail) {
  try { await post(url, data); return true; } catch (e) { onFail("실패: " + e.message, true); return false; }
}
document.querySelectorAll(".m-lv").forEach((b) => b.addEventListener("click", async () => {
  if (await tryPost("/api/level", { level: Number(b.dataset.level) }, homeMsg))
    homeMsg("수동으로 바꿨어요. 다시 맡기려면 '자동으로 돌아가기'", false);
}));
$("auto-switch").addEventListener("click", () =>
  tryPost("/api/mode", { mode: last && last.mode === "auto" ? "manual" : "auto" }, homeMsg));
$("home-auto").addEventListener("click", async () => {
  if (await tryPost("/api/mode", { mode: "auto" }, homeMsg)) homeMsg("자동 제어로 돌렸어요", false);
});

// ---------- 음성 탭 ----------
const STATE_TEXT = { idle: "버튼을 누른 채로 말해 보세요", listening: "듣고 있어요", thinking: "알아듣는 중…" };

function setState(st, note) {
  $("mic").classList.toggle("on", st === "listening");
  $("mic").classList.toggle("busy", st === "thinking");
  document.body.dataset.voice = st;
  $("state").textContent = (note && st === "thinking" ? note + " · " : "") + STATE_TEXT[st];
  if (st !== "idle") setResult("", false);
}

function setResult(text, fail) {
  $("result").textContent = text;
  $("result").classList.toggle("fail", !!fail);
}

// 결과: "다 가려 줘" → 0단계로 바꿨어요
function showResult(d, note = "") {
  const said = d.heard || d.text;
  const out = VoiceRec.outcome(d);
  setResult((note ? note + " · " : "") + (said ? `"${said}" → ` : "") + out,
    d.source === "none" || d.action === "cooldown");
  VoiceRec.speak(out);
  refresh();
}

async function say(text) {
  text = (text || "").trim();
  if (!text) return false;
  setState("thinking");
  try {
    const d = await VoiceRec.sendText(text);
    setState("idle");
    showResult(d);
    return true;
  } catch (e) {
    setState("idle");
    setResult("보내기 실패: " + e.message, true);
    return false;
  }
}

const mic = VoiceRec.attach($("mic"), {
  mode(m) {
    $("mic").disabled = !m;
    if (!m) $("state").textContent = "마이크를 쓸 수 없어요";
    else setState("idle");
  },
  state: setState,
  interim(text) { $("state").textContent = `"${text}"`; },
  result: showResult,
  message: setResult,
});

document.querySelectorAll("[data-say]").forEach((b) => b.addEventListener("click", () => say(b.dataset.say)));
$("voice-auto").addEventListener("click", async () => {
  if (await tryPost("/api/mode", { mode: "auto" }, setResult)) setResult("자동 제어로 돌렸어요", false);
});
VoiceRec.textToggle($("text-toggle"), $("text-box"), $("voice-text"));
$("text-box").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (await say($("voice-text").value)) $("voice-text").value = "";
});

// ---------- 설정 탭 ----------
// 시연 잠금이면 서버가 403("시연 중에는 잠겨 있어요")을 돌려주고, 그 문구를 그대로 보여 준다
function prefMsg(text, fail) {
  $("pref-msg").textContent = text;
  $("pref-msg").classList.toggle("fail", !!fail);
}
$("wake").addEventListener("input", () => { wakeEdited = true; });
$("wake-save").addEventListener("click", async () => {
  const ok = await tryPost("/api/settings", { wake_time: $("wake").value }, (t) => { $("wake-msg").textContent = t; });
  if (ok) { wakeEdited = false; $("wake-msg").textContent = "저장됨"; }
  setTimeout(() => ($("wake-msg").textContent = "20분 전부터 밝게 · 기상 준비 20 → 200 lux"), 2000);
});
$("profile").addEventListener("change", () => tryPost("/api/pref/profile", { name: $("profile").value }, prefMsg));
$("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("new-profile").value.trim();
  if (!name) return;
  if (await tryPost("/api/pref/profile", { name }, prefMsg)) {
    $("new-profile").value = "";
    prefMsg(`'${name}' 사용자로 바꿨어요`, false);
  }
});
$("pref-reset").addEventListener("click", async () => {
  if (await tryPost("/api/pref/reset", {}, prefMsg)) prefMsg("학습한 선호 밝기를 지웠어요", false);
});
$("learn-switch").addEventListener("click", () =>
  tryPost("/api/pref/learn", { enabled: !(last && last.pref && last.pref.learn !== false) }, prefMsg));
$("voice-learn").addEventListener("click", () =>
  tryPost("/api/voice/learn", { enabled: !(last && last.voice && last.voice.status.learn) }, prefMsg));

// 핫스팟에는 인터넷이 없어 Pi 시각이 틀릴 수 있으므로, 열 때 휴대폰 시각을 보낸다 (대시보드와 같음)
(function syncTime() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const local = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  fetch("/api/time", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ local }) }).catch(() => {});
})();

refresh();
setInterval(refresh, 1000);
