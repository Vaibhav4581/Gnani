// Small helpers shared by the kitchen and volunteer pages.
export const $ = (id) => document.getElementById(id);

// localStorage can throw (private mode, blocked storage): treat it as optional.
export function stored(key) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}

export function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* optional */ }
}

export async function getJson(url) {
  return (await fetch(url)).json();
}

// POST and return the JSON body; throws an Error carrying `.body` on failure.
export async function postJson(url, options = {}) {
  const res = await fetch(url, { method: "POST", ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const err = new Error(typeof detail === "string" ? detail : detail?.text || `Error ${res.status}`);
    err.body = typeof detail === "object" ? detail : null;
    err.status = res.status;
    throw err;
  }
  return data;
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

// Veg / non-veg / covered chips from the safety check (null = not asked yet: no chip).
export function safetyChips(veg, covered) {
  const chip = (cls, text) => Object.assign(document.createElement("span"),
    { className: `chip ${cls}`, textContent: text });
  const out = [];
  if (veg === true) out.push(chip("veg", "● Veg"));
  if (veg === false) out.push(chip("nonveg", "● Non-veg"));
  if (covered === true) out.push(chip("covered", "Covered ✓"));
  if (covered === false) out.push(chip("uncovered", "Not covered yet"));
  return out;
}
