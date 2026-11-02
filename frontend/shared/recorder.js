// Hold-to-talk recording with a live level meter and a microphone picker.
import { store, stored } from "./common.js";

const MIN_RECORD_MS = 400;
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"];
// Peak RMS below this (about -40 dBFS) means the mic gave us nothing usable.
const MIN_PEAK_LEVEL = 0.01;
const MIC_KEY = "bhk.micId";

export function extensionFor(type) {
  if (type.includes("ogg")) return "ogg";
  if (type.includes("mp4")) return "m4a";
  return "webm";
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

// Live input level, so people can see whether the mic is hearing them: a bar's width, and/or
// onLevel(0..1) for anything else (the kitchen's haldi ring).
function startMeter(stream, rec, bar, onLevel) {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const tick = () => {
    if (rec.done) return;
    analyser.getFloatTimeDomainData(buf);
    const rms = Math.sqrt(buf.reduce((sum, v) => sum + v * v, 0) / buf.length);
    rec.peak = Math.max(rec.peak, rms);
    if (bar) bar.style.width = `${Math.min(100, rms * 400)}%`;
    onLevel?.(Math.min(1, rms * 4));
    requestAnimationFrame(tick);
  };
  return { ctx, tick };
}

// Wire a button so holding it records. Calls onBlob(blob) with usable audio,
// onProblem(message, code) otherwise; code (blocked | hold | short | empty | silent) lets a page
// say it in its own language. `allowSilence` skips the level check (mock mode). `level` and
// `levelBar` (a meter) and `onLevel` are optional.
export function bindHoldToTalk(button, { mic, level, levelBar, onLevel, allowSilence, onStart, onStop,
  onBlob, onProblem }) {
  let current = null; // the recording in progress
  let starting = false;
  let releasedWhileStarting = false;

  async function start() {
    if (current || starting || button.disabled) return;
    starting = true;
    releasedWhileStarting = false;
    let stream;
    try {
      stream = await mic.get();
    } catch {
      onProblem("Microphone blocked. Allow mic access and try again.", "blocked");
      return;
    } finally {
      starting = false;
    }
    if (releasedWhileStarting) {
      onProblem("Keep holding the button while you speak.", "hold");
      return;
    }
    const mimeType = MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    // Everything this recording needs lives in its own object, so a quick
    // second tap can never swap the chunks out from under it.
    const rec = { recorder, chunks: [], startedAt: performance.now(), peak: 0, done: false };
    const meter = startMeter(stream, rec, levelBar, onLevel);
    rec.ctx = meter.ctx;
    recorder.ondataavailable = (e) => e.data.size && rec.chunks.push(e.data);
    recorder.onstop = () => finish(rec);
    current = rec;
    recorder.start();
    meter.tick();
    button.classList.add("recording");
    if (level) level.hidden = false;
    onStart?.();
  }

  function stop() {
    if (starting) { releasedWhileStarting = true; return; }
    if (current?.recorder.state === "recording") current.recorder.stop();
  }

  function finish(rec) {
    if (current === rec) current = null;
    rec.done = true;
    rec.ctx.close();
    button.classList.remove("recording");
    if (level) level.hidden = true;
    onLevel?.(0);
    onStop?.();

    const blob = new Blob(rec.chunks, { type: rec.recorder.mimeType || "audio/webm" });
    if (performance.now() - rec.startedAt < MIN_RECORD_MS) {
      onProblem("Too short. Hold the button while you speak.", "short");
    } else if (!blob.size) {
      onProblem("No audio was recorded. Please try again.", "empty");
    } else if (rec.peak < MIN_PEAK_LEVEL && !allowSilence()) {
      mic.showPicker();
      onProblem("Mic heard nothing. Pick another microphone below or check it isn't muted.", "silent");
    } else {
      onBlob(blob);
    }
  }

  button.addEventListener("pointerdown", (e) => { e.preventDefault(); start(); });
  ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => button.addEventListener(ev, stop));
  button.addEventListener("contextmenu", (e) => e.preventDefault());
  button.addEventListener("keydown", (e) => {
    if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); start(); }
  });
  button.addEventListener("keyup", (e) => {
    if (e.key === " " || e.key === "Enter") stop();
  });
  return { isRecording: () => current !== null };
}
