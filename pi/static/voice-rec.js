// 음성 명령 공통 코드: 대시보드(/)와 음성 화면(/voice)이 같이 쓴다.
// 누르고 있는 동안만 듣는다 (부스 소음에서 엉뚱한 말이 들어가지 않게). 방식은 두 가지:
//  ① Pi 음성 인식(whisper.cpp, 오프라인): 녹음 → WAV(16kHz) → /api/voice/audio. 서버가 켜져 있으면 이것을 쓴다
//  ② 브라우저 음성 인식(Web Speech, 대개 인터넷 필요): ①을 못 쓸 때
// 둘 다 HTTPS나 localhost에서만 된다 (브라우저 규칙). 기기 이름은 서버가 '아이폰 1'처럼 자동으로 붙인다.
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const CAN_RECORD = window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  const MAX_REC_S = 8;
  // 마이크는 처음 누를 때 한 번 켜고 계속 열어 둔다 (누를 때마다 켜면 0.1~0.3초 늦어 첫 글자가 잘린다: "눈부셔" → "무조").
  // 누르기 직전 PREROLL_S초도 버퍼에 들고 있다가 녹음 앞에 붙인다. 화면을 벗어나면 마이크를 끈다.
  const PREROLL_S = 0.5;

  function speak(text) {                     // 응답을 소리로 (명령을 보낸 기기에서만)
    if (!("speechSynthesis" in window) || !text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }

  async function sendText(text) {            // 문장 → /api/voice. 결과(d)를 돌려주고 실패면 예외
    const r = await fetch("/api/voice", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.status);
    return d;
  }

  // 관람객에게 보일 짧은 결과: "N단계로 바꿨어요" / 자동 복귀 / 그 밖에는 Pi가 준 답
  function outcome(d) {
    if (d.applied && d.action === "auto") return "자동 제어로 돌렸어요";
    if (d.applied && d.level_after !== d.level_before) return `${d.level_after}단계로 바꿨어요`;
    return d.reply || "";
  }

  // http로 들어온 휴대폰에게 보여 줄 HTTPS 주소 (없으면 null)
  function httpsUrl(status) {
    if (window.isSecureContext || !status || !status.https_port) return null;
    return `https://${location.hostname}:${status.https_port}${location.pathname}`;
  }

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

  // 버튼 하나에 누르고-말하기를 붙인다. ui 콜백:
  //   mode(m)          쓸 방식이 바뀜: "whisper" | "browser" | null(못 씀)
  //   state(s, note)   "idle" | "listening" | "thinking"
  //   interim(text)    브라우저 인식 중간 글자
  //   result(d, note)  Pi 응답 (/api/voice 또는 /api/voice/audio)
  //   message(text, fail)  안내·오류 문구
  // 돌려주는 update(status)를 /api/state의 voice.status로 1초마다 불러 준다.
  function attach(btn, ui) {
    let mode = null, busy = false, pressed = false;
    let live = null;              // {ctx, stream, src, proc, ring, ringLen, recording, timer}
    let stopping = null;
    let srec = null, heard = "", useLocal = false;

    function update(status) {
      const m = CAN_RECORD && status && status.stt ? "whisper" : (SR && window.isSecureContext ? "browser" : null);
      if (m !== mode && !busy) {
        mode = m;
        ui.mode(m);
      }
      return mode;
    }

    function release() {
      if (!live) return;
      try { live.proc.disconnect(); live.src.disconnect(); } catch (e) {}
      live.stream.getTracks().forEach((t) => t.stop());
      live.ctx.close();
      live = null;
    }
    document.addEventListener("visibilitychange", () => { if (document.hidden && !pressed) release(); });

    async function ensureMic() {
      if (live) {
        if (live.ctx.state === "suspended") await live.ctx.resume();
        return live;
      }
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC();                   // 누른 순간(사용자 동작 안)에 만들어야 iOS에서 소리가 들어온다
      ctx.resume();
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      } catch (e) {
        ctx.close();
        throw new Error("마이크 권한이 없어요. 아래 '글자로 입력'을 써 주세요");
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
      if (!pressed) {                         // 처음 권한 창이 떠 있는 동안 손을 뗀 경우: 마이크만 켜 두고 녹음은 안 함
        ui.message("마이크 준비 완료. 다시 누르고 말해 주세요", false);
        return;
      }
      m.recording = m.ring.slice();           // 누르기 직전 0.5초부터
      m.ring = [];
      m.ringLen = 0;
      m.timer = setTimeout(() => stopOnce(`${MAX_REC_S}초가 지나 보냈어요`), MAX_REC_S * 1000);
    }

    // 녹음을 끝내고 보낸다. 손을 뗄 때와 8초 자동 종료가 겹쳐도 한 번만 보내고, busy는 보내기가 끝난 뒤 여기서만 푼다.
    function stopOnce(note = "") {
      if (!stopping) {
        stopping = recStop(note).finally(() => {
          busy = false;
          stopping = null;
        });
      }
      return stopping;
    }

    async function recStop(note) {
      if (!live || !live.recording) { ui.state("idle"); return; }
      const chunks = live.recording;
      live.recording = null;
      clearTimeout(live.timer);
      const wav = encodeWav16k(chunks, live.ctx.sampleRate);
      if (wav.seconds < 0.6 || wav.peak < 0.02) {   // 짧거나 무음이면 보내지 않는다
        ui.state("idle");
        ui.message("소리가 거의 안 들어왔어요. 버튼을 누른 채로 말해 주세요", true);
        return;
      }
      ui.state("thinking", note);
      const form = new FormData();
      form.append("audio", wav.blob, "voice.wav");
      try {
        const res = await fetch("/api/voice/audio", { method: "POST", body: form });
        const d = await res.json();
        if (!res.ok) throw new Error(d.error || res.status);
        ui.state("idle");
        ui.result(d, note);
      } catch (e) {
        ui.state("idle");
        ui.message("음성 인식 실패: " + e.message + " ('글자로 입력'을 써 주세요)", true);
      }
    }

    // --- ② 브라우저 음성 인식 ---
    function srStart() {
      heard = "";
      srec = new SR();
      srec.lang = "ko-KR";
      srec.interimResults = true;
      srec.maxAlternatives = 1;
      if (useLocal && "processLocally" in srec) srec.processLocally = true;   // 인터넷이 없을 때 기기 안 인식 시도
      srec.onresult = (ev) => {
        heard = Array.from(ev.results).map((x) => x[0].transcript).join("");
        ui.interim(heard);
      };
      srec.onerror = (ev) => {
        if (ev.error === "network" && "processLocally" in srec && !useLocal) {
          useLocal = true;
          ui.message("인터넷이 없어 기기 안 인식으로 바꿨어요. 다시 눌러 주세요", false);
        } else if (ev.error !== "no-speech" && ev.error !== "aborted") {
          ui.message("음성 인식 오류: " + ev.error + " ('글자로 입력'을 써 주세요)", true);
        }
      };
      srec.onend = async () => {
        srec = null;
        if (!heard) { busy = false; ui.state("idle"); return; }
        ui.state("thinking");
        try {
          const d = await sendText(heard);
          ui.state("idle");
          ui.result(d, "");
        } catch (e) {
          ui.state("idle");
          ui.message("보내기 실패: " + e.message, true);
        }
        busy = false;
      };
      srec.start();
    }

    // --- 버튼: 누르고 있는 동안 듣기 ---
    // 아이폰 길게 누르기: CSS(user-select/touch-callout/touch-action: none) + 아래 touchstart·contextmenu 막기.
    // 포인터를 버튼에 붙잡아 두어(setPointerCapture) 손가락이 조금 벗어나도 뗄 때까지 녹음한다.
    btn.addEventListener("pointerdown", async (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      if (busy || !mode) return;
      try { btn.setPointerCapture(e.pointerId); } catch (err) {}
      busy = true;
      pressed = true;
      ui.state("listening");
      try {
        if (mode === "whisper") await recStart();
        else srStart();
        if (mode === "whisper" && !pressed && !stopping && !(live && live.recording)) { busy = false; ui.state("idle"); }
      } catch (err) {
        busy = false;
        ui.state("idle");
        ui.message(err.message, true);
      }
    });
    const up = () => {
      if (!pressed) return;
      pressed = false;
      if (!busy) return;
      if (mode === "whisper") {
        if (live && live.recording) stopOnce();     // 이미 자동 종료로 보내는 중이면 stopOnce가 그것을 그대로 둔다
      } else if (srec) {
        srec.stop();                                // onend에서 보낸다
      }
    };
    btn.addEventListener("pointerup", up);
    btn.addEventListener("pointercancel", up);
    btn.addEventListener("lostpointercapture", up);
    window.addEventListener("blur", up);
    btn.addEventListener("contextmenu", (e) => e.preventDefault());
    btn.addEventListener("touchstart", (e) => e.preventDefault(), { passive: false });   // iOS 돋보기·선택 메뉴 방지

    return { update, get mode() { return mode; } };
  }

  // "글자로 입력" 링크: 누르면 입력칸이 펼쳐지고 다시 누르면 접힌다
  function textToggle(link, box, input) {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const open = box.hidden;
      box.hidden = !open;
      link.setAttribute("aria-expanded", String(open));
      if (open) input.focus();
    });
  }

  window.VoiceRec = { attach, sendText, speak, outcome, httpsUrl, textToggle };
})();
