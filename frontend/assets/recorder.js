// Tap to talk. One tap opens the mic, and it closes by itself once the speaker has said
// something and gone quiet, judged against the room's own noise (createSpeechGate). A page can
// also open it without a tap, right after the app asks a yes/no question (listen()), and must
// close it (cancel()) whenever the app starts speaking, so the app never hears itself.
// Tune it in a real kitchen with ?debug=1: a corner panel shows the room, the level and the bar.
import { cue, store, stored } from "../shared/common.js";

// Every threshold in one place. Levels are the RMS of the mic signal, 0 to 1 (0.01 is about -40 dBFS).
export const LISTEN = {
  CALIBRATE_MS: 500,        // after the mic opens, how long to measure the room
  AMBIENT_PERCENTILE: 0.3,  // the room level: this low percentile of that window, not its average
  SPEECH_FACTOR: 1.8,       // speech = louder than the room x this
  MIN_THRESHOLD: 0.01,      // ...and never quieter than this, however silent the room
  SPEECH_START_MS: 150,     // this long above the threshold before it counts as speech (a dropped pan doesn't)
  SILENCE_MS: 1200,         // once speech has started, this long below the threshold sends the clip
  NO_SPEECH_MS: 6000,       // after a tap: no speech in this long cancels ("Kuch sunai nahi diya")
  AUTO_NO_SPEECH_MS: 8000,  // after a question (listen()): stop quietly, the yes/no buttons stay
  MAX_MS: 20000,            // hard cap on any recording
  AFTER_VOICE_MS: 300,      // after the app's voice ends, wait this long before listening
  CUE_MS: 100,              // the start tick: counted neither as the room nor as speech
  TICK_MS: 50,              // how often the level is checked
};

const PARAMS = new URLSearchParams(globalThis.location?.search || "");
export const DEBUG = PARAMS.get("debug") === "1";
// With ?debug=1 other values can be tried from the address bar, e.g. &factor=2.2&silence=1500.
const OVERRIDES = { factor: "SPEECH_FACTOR", silence: "SILENCE_MS", min: "MIN_THRESHOLD",
  calibrate: "CALIBRATE_MS", start: "SPEECH_START_MS", nospeech: "NO_SPEECH_MS",
  auto: "AUTO_NO_SPEECH_MS", max: "MAX_MS" };
if (DEBUG) {
  for (const [param, key] of Object.entries(OVERRIDES)) {
    const value = Number(PARAMS.get(param));
    if (PARAMS.has(param) && value > 0) LISTEN[key] = value;
  }
}

const MIN_RECORD_MS = 400;  // a quicker tap-tap is a slip, not a message
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"];
// Peak RMS below this means the mic gave us nothing usable (muted, or the wrong device).
const MIN_PEAK_LEVEL = 0.01;
const MIC_KEY = "bhk.micId";

// "0:07": how long a recording has run, for the label beside or under a mic.
export function elapsed(since) {
  const s = Math.floor((performance.now() - since) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function extensionFor(type) {
  if (type.includes("ogg")) return "ogg";
  if (type.includes("mp4")) return "m4a";
  return "webm";
}

// When to stop, without the browser: feed(level, ms since the mic opened) -> { phase, done }.
// phase: calibrating | waiting (for speech) | speech. done: null | silence | no_speech | max.
// Someone who starts talking at once can't raise the bar for themselves: the room is a low
// percentile of the window, the window is replayed against the bar (so a quick "haan" inside it
// still counts), and a room found much quieter afterwards resets it. tests/test_listen.py runs
// this in Node.
export function createSpeechGate({ cfg = LISTEN, noSpeechMs = cfg.NO_SPEECH_MS } = {}) {
  const s = { phase: "calibrating", ambient: null, threshold: null, level: 0, t: 0,
              loudSince: null, quietSince: null };
  const early = [];  // [level, t] while calibrating

  const setRoom = (ambient) => {
    s.ambient = ambient;
    s.threshold = Math.max(cfg.MIN_THRESHOLD, ambient * cfg.SPEECH_FACTOR);
  };

  function step(level, t) {
    if (s.phase === "waiting") {
      if (level < s.ambient / cfg.SPEECH_FACTOR) setRoom(level);  // the window held speech
      const loud = level >= s.threshold;
      s.loudSince = loud ? s.loudSince ?? t : null;
      if (loud && t - s.loudSince >= cfg.SPEECH_START_MS) {
        s.phase = "speech";
        s.quietSince = null;
      } else if (t >= noSpeechMs) {
        return "no_speech";
      }
    } else {
      const loud = level >= s.threshold;
      s.quietSince = loud ? null : s.quietSince ?? t;
      if (!loud && t - s.quietSince >= cfg.SILENCE_MS) return "silence";
    }
    if (t >= cfg.MAX_MS) return s.phase === "speech" ? "max" : "no_speech";
    return null;
  }

  return {
    state: s,
    feed(level, t) {
      s.level = level;
      s.t = t;
      if (s.phase !== "calibrating") return { phase: s.phase, done: step(level, t) };
      early.push([level, t]);
      if (t < cfg.CALIBRATE_MS) return { phase: s.phase, done: null };
      const sorted = early.map(([l]) => l).sort((a, b) => a - b);
      setRoom(sorted[Math.floor((sorted.length - 1) * cfg.AMBIENT_PERCENTILE)]);
      s.phase = "waiting";
      for (const [l, at] of early) {
        const done = step(l, at);
        if (done) return { phase: s.phase, done };
      }
      return { phase: s.phase, done: null };
    },
  };
}

// The chosen input device, kept open between recordings.
export class Microphone {
  constructor({ select, row }) {
    this.select = select;
    this.row = row;
    this.stream = null;
    select.addEventListener("change", () => {
      store(MIC_KEY, select.value);
      this.drop();
    });
    this.list();
  }

  async list() {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const mics = (await navigator.mediaDevices.enumerateDevices())
      .filter((d) => d.kind === "audioinput");
    const chosen = stored(MIC_KEY);
    this.select.replaceChildren(...mics.map((d, i) => {
      const opt = new Option(d.label || `Microphone ${i + 1}`, d.deviceId);
      opt.selected = d.deviceId === chosen;
      return opt;
    }));
    // Labels are blank until mic permission is granted, so only show a useful list.
    this.row.hidden = mics.length < 2 || !mics[0].label;
  }

  showPicker() {
    this.row.hidden = false;
  }

  drop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  async get() {
    const live = this.stream?.getAudioTracks().some((t) => t.readyState === "live");
    if (live) return this.stream;
    this.drop();
    const micId = stored(MIC_KEY);
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (micId) audio.deviceId = { exact: micId };
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio });
    } catch (err) {
      if (!micId) throw err;
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true }); // saved mic unplugged
    }
    this.list();
    return this.stream;
  }
}

// Wire a button: a tap opens the mic, a second tap stops it early; otherwise it stops itself on
// silence (or gives up, LISTEN). Calls onBlob(blob) with a clip to send, onProblem(message, code)
// otherwise; code (blocked | nothing | silent | empty) lets a page say it in its own language.
// onStart(mode) / onStop(reason, mode): mode is "tap" or "auto" (listen()). `allowSilence` sends
// a clip without speech when tapped to a stop (mock mode). Returns { isRecording, listen, cancel }.
export function bindTapToTalk(button, { mic, onLevel, allowSilence, onStart, onStop, onBlob, onProblem }) {
  let current = null;  // the recording in progress
  let opening = null;  // { mode, cancelled } while the mic is being opened

  async function open(mode) {
    if (current || opening) return;
    const pending = { mode, cancelled: false };
    opening = pending;
    let stream;
    try {
      stream = await mic.get();
    } catch {
      opening = null;
      if (mode === "tap") onProblem("Microphone blocked. Allow mic access and try again.", "blocked");
      return;  // after a question the yes/no buttons are still there
    }
    opening = null;
    if (pending.cancelled) return;

    cue("start");
    const mimeType = MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;  // about 43 ms of sound per reading at 48 kHz
    ctx.createMediaStreamSource(stream).connect(analyser);
    // Everything this recording needs lives in its own object, so a quick second tap can never
    // swap the chunks out from under it.
    const rec = { mode, recorder, ctx, analyser, buf: new Float32Array(analyser.fftSize), chunks: [],
                  openedAt: performance.now(), peak: 0, reason: null,
                  gate: createSpeechGate({ noSpeechMs: mode === "auto" ? LISTEN.AUTO_NO_SPEECH_MS
                                                                       : LISTEN.NO_SPEECH_MS }) };
    recorder.ondataavailable = (e) => e.data.size && rec.chunks.push(e.data);
    recorder.onstop = () => finish(rec);
    current = rec;
    recorder.start();
    rec.timer = setInterval(() => measure(rec), LISTEN.TICK_MS);  // timers keep going in a background tab
    button.classList.add("recording");
    button.setAttribute("aria-pressed", "true");
    onStart?.(mode);
  }

  function measure(rec) {
    rec.analyser.getFloatTimeDomainData(rec.buf);
    const rms = Math.sqrt(rec.buf.reduce((sum, v) => sum + v * v, 0) / rec.buf.length);
    rec.peak = Math.max(rec.peak, rms);
    onLevel?.(Math.min(1, rms * 4));
    const t = performance.now() - rec.openedAt - LISTEN.CUE_MS;
    if (t < 0) return;
    const { done } = rec.gate.feed(rms, t);
    showDebug(rec, done);
    if (done) close(rec, done);
  }

  // reason: silence | max | no_speech (the gate), tap (stopped early) or cancel (thrown away).
  function close(rec, reason) {
    if (rec.reason) return;
    rec.reason = reason;
    clearInterval(rec.timer);
    if (rec.recorder.state === "recording") rec.recorder.stop();
    else finish(rec);
  }

  function finish(rec) {
    if (current === rec) current = null;
    rec.ctx.close();
    button.classList.remove("recording");
    button.setAttribute("aria-pressed", "false");
    onLevel?.(0);
    if (rec.reason !== "cancel") cue("stop");
    showDebug(rec, rec.reason);
    onStop?.(rec.reason, rec.mode);

    const blob = new Blob(rec.chunks, { type: rec.recorder.mimeType || "audio/webm" });
    const dead = rec.peak < MIN_PEAK_LEVEL && !allowSilence();
    if (rec.reason === "cancel") return;
    if (rec.reason === "no_speech") {
      if (rec.mode === "auto") return;  // nobody answered the question: the buttons stay
      if (dead) {
        mic.showPicker();
        onProblem("Mic heard nothing. Pick another microphone below or check it isn't muted.", "silent");
      } else {
        onProblem("Didn't hear anything. Tap and try again.", "nothing");
      }
    } else if (rec.reason === "tap" && performance.now() - rec.openedAt < MIN_RECORD_MS) {
      // tapped twice by mistake: nothing to say about it
    } else if (!blob.size) {
      onProblem("No audio was recorded. Please try again.", "empty");
    } else if (dead) {
      mic.showPicker();
      onProblem("Mic heard nothing. Pick another microphone below or check it isn't muted.", "silent");
    } else {
      onBlob(blob);
    }
  }

  button.addEventListener("click", () => {
    if (current) close(current, "tap");
    else if (!button.disabled) open("tap");
  });
  button.setAttribute("aria-pressed", "false");
  return {
    isRecording: () => current !== null || opening !== null,
    listen: () => open("auto"),
    cancel: () => {
      if (opening) opening.cancelled = true;
      if (current) close(current, "cancel");
    },
  };
}

// ?debug=1: what the gate sees, live, in a corner (one panel for the page's mics).
function showDebug(rec, done) {
  if (!DEBUG) return;
  let box = document.querySelector(".listen-debug");
  if (!box) {
    box = document.createElement("pre");
    box.className = "listen-debug";
    box.setAttribute("aria-hidden", "true");
    document.body.append(box);
  }
  const s = rec.gate.state;
  const num = (v) => (v == null ? "  –   " : v.toFixed(4));
  const bar = (v) => "█".repeat(Math.round(Math.min(1, (v || 0) * 10) * 24));
  const quiet = s.quietSince == null ? 0 : Math.round(s.t - s.quietSince);
  box.textContent = [
    `${rec.mode} · ${s.phase}${done ? ` → ${done}` : ""} · ${(Math.max(0, s.t) / 1000).toFixed(1)} s`,
    `ambient   ${num(s.ambient)} ${bar(s.ambient)}`,
    `level     ${num(s.level)} ${bar(s.level)}`,
    `threshold ${num(s.threshold)} ${bar(s.threshold)}`,
    `quiet ${quiet} / ${LISTEN.SILENCE_MS} ms · peak ${num(rec.peak)}`,
    `factor ${LISTEN.SPEECH_FACTOR} · min ${LISTEN.MIN_THRESHOLD} · start ${LISTEN.SPEECH_START_MS} ms`,
  ].join("\n");
}
