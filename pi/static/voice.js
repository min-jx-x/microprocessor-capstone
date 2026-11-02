// 라이트큐 음성 화면(/voice): 휴대폰 관람객용. 큰 마이크 하나 + 지금 상태.
// 녹음·전송은 voice-rec.js (대시보드와 같은 코드). 상태는 /api/state를 1초마다 읽는다.
const $ = (id) => document.getElementById(id);
let last = null;

const STATE_TEXT = {
  idle: "버튼을 누른 채로 말해 보세요",
  listening: "듣고 있어요",
  thinking: "알아듣는 중…",
};

function setState(st, note) {
  $("mic").classList.toggle("on", st === "listening");
  $("mic").classList.toggle("busy", st === "thinking");
  document.body.dataset.state = st;
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
  if (!text) return;
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

function render(st) {
  last = st;
  $("level").textContent = st.level;
  $("lux").textContent = st.lux == null ? "-" : Math.round(st.lux);
  $("mode").textContent = st.mode === "auto" ? "자동" : "수동";
  $("mode").classList.toggle("manual", st.mode !== "auto");
  $("auto").disabled = st.mode === "auto";
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
      Object.assign(document.createElement("a"), { href: url, textContent: "여기를 눌러 다시 접속" }),
      " (경고가 뜨면 고급 → 계속)");
  } else {
    notice.hidden = false;
    notice.textContent = "이 브라우저에서는 마이크를 쓸 수 없어요. 아래 예시를 누르거나 '글자로 입력'을 써 주세요";
  }
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

$("auto").addEventListener("click", async () => {
  try {
    const r = await fetch("/api/mode", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "auto" }),
    });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    setResult("자동 제어로 돌렸어요", false);
    refresh();
  } catch (e) {
    setResult("실패: " + e.message, true);
  }
});

VoiceRec.textToggle($("text-toggle"), $("text-box"), $("voice-text"));
$("text-box").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (await say($("voice-text").value)) $("voice-text").value = "";
});

// 핫스팟에는 인터넷이 없어 Pi 시각이 틀릴 수 있으므로, 열 때 휴대폰 시각을 보낸다 (대시보드와 같음)
(function syncTime() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const local = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  fetch("/api/time", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ local }) }).catch(() => {});
})();

refresh();
setInterval(refresh, 1000);
