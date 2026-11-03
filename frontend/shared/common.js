// Small helpers shared by the kitchen and volunteer pages.
export const $ = (id) => document.getElementById(id);

// localStorage can throw (private mode, blocked storage): treat it as optional.
export function stored(key) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}

export function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* optional */ }
}

// GET and return the JSON body; throws like postJson when the server says no.
export async function getJson(url) {
  return checked(await fetch(url));
}

// POST and return the JSON body; throws an Error carrying `.body` on failure.
export async function postJson(url, options = {}) {
  return checked(await fetch(url, { method: "POST", ...options }));
}

async function checked(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const err = new Error(typeof detail === "string" ? detail : detail?.text || `Error ${res.status}`);
    err.body = typeof detail === "object" ? detail : null;
    err.status = res.status;
    throw err;
  }
  return data;
}

// What went wrong, as the key of a message that says what to do next:
//   "noNetwork"   this device is offline
//   "unreachable" the request never got an answer (server down, or the network dropped)
//   "serverDown"  the server answered with an error of its own (5xx)
//   "server"      the server refused the request (4xx); its message says why
export function failureKey(err) {
  if (!navigator.onLine) return "noNetwork";
  if (!err || err instanceof TypeError || !err.status) return "unreachable";
  return err.status >= 500 ? "serverDown" : "server";
}

// "For example: ..." under a mic: every sentence is laid out in the same spot (the box is as tall
// as the longest, so nothing moves) and one shows at a time, changing every `ms`. Still under
// reduced motion. Returns a function that stops the rotation.
export function rotateExamples(box, sentences, { ms = 6000, lang = null } = {}) {
  box.replaceChildren(...sentences.map((text, i) => {
    const p = document.createElement("p");
    p.className = `example${i === 0 ? " is-on" : ""}`;
    p.textContent = `“${text}”`;
    if (lang) p.lang = lang;
    if (i) p.setAttribute("aria-hidden", "true");
    return p;
  }));
  if (sentences.length < 2 || matchMedia("(prefers-reduced-motion: reduce)").matches) return () => {};
  let at = 0;
  const timer = setInterval(() => {
    if (document.hidden) return;
    const items = box.children;
    items[at].classList.remove("is-on");
    items[at].setAttribute("aria-hidden", "true");
    at = (at + 1) % items.length;
    items[at].classList.add("is-on");
    items[at].removeAttribute("aria-hidden");
  }, ms);
  return () => clearInterval(timer);
}

// A soft tick (and a short buzz on phones) so staff know the mic heard the press without
// looking: a higher tick when recording starts, a lower one when it stops.
let cueAudio = null;
export function cue(kind) {
  try {
    navigator.vibrate?.(30);
    cueAudio ||= new AudioContext();
    const t = cueAudio.currentTime + 0.01;
    const osc = cueAudio.createOscillator();
    const gain = cueAudio.createGain();
    osc.frequency.value = kind === "start" ? 1320 : 880;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.12, t + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
    osc.connect(gain).connect(cueAudio.destination);
    osc.start(t);
    osc.stop(t + 0.07);
  } catch { /* sound and vibration are a nicety */ }
}

export function putJson(url, payload) {
  return postJson(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// A WebSocket that reconnects with backoff until close() is called, with keep-alive pings.
export function liveSocket(path, { onMessage, onState }) {
  let ws = null;
  let closed = false;
  let delay = 1000;
  let ping = null;

  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${path}`);
    ws.onopen = () => {
      delay = 1000;
      onState?.("open");
      ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
    };
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onclose = () => {
      clearInterval(ping);
      if (closed) return;
      onState?.("reconnecting");
      setTimeout(connect, delay);
      delay = Math.min(delay * 2, 15000);
    };
  };
  connect();
  return {
    close() {
      closed = true;
      clearInterval(ping);
      ws?.close();
    },
  };
}
