// Kitchen screen: hold to talk -> the report writes itself onto a KOT slip -> confirm by voice
// or button -> two safety questions -> live status on the slip, with a route line. After that
// the same mic asks "volunteer kab aayega?" or cancels (asked back first). One thing at a time.
import { $, getJson, liveSocket, postJson, putJson, store, stored } from "/shared/common.js";
import { Microphone, bindHoldToTalk, extensionFor } from "/shared/recorder.js";
import { clearKotNotes, clock, renderKot, setKotFields, setKotId, setKotNote, setKotRoute,
         setKotSpeaking, setKotStatus } from "/assets/kot.js";
import { LANG_ORDER, STRINGS, fill, strings } from "./strings.js";

const ICONS = "/assets/icons.svg";
const KITCHEN_KEY = "bhk.kitchenId";
const langKey = (kitchenId) => `bhk.language.${kitchenId}`;
const ANSWERING = ["CONFIRMING", "SAFETY_CHECK"];  // the next thing said answers the app
const MISSING_LINE = { dish: "food", quantity: "food", unit: "food", cooked_time: "cooked_at" };
const NOTICE_KIND = { firstUse: "attention", blocked: "error", noNetwork: "error", server: "error",
                      silent: "attention", short: "attention", hold: "attention", empty: "attention" };

const state = {
  mock: false, kitchens: [], languages: [], kitchen: null, t: strings("hi-IN"),
  report: null,   // { id, status, fields, missing, safety }
  slip: null,
  live: {},       // what the server told us about the pickup: volunteer, eta, ngo, reason
  cancelAsked: false, busy: false, speaking: false, audio: null, audioUrl: null,
  printed: false, notice: null, socketState: "reconnecting",
};
let talk = null;
let socket = null;
let timer = null;

// ------------------------------------------------------------------ start

async function init() {
  try {
    state.mock = (await getJson("/config")).mock;
  } catch { /* the first request will show what went wrong */ }
  $("mock-panel").hidden = !state.mock;
  $("settings").open = state.mock;  // the demo types instead of speaking

  const mic = new Microphone({ select: $("mic"), row: $("mic-row") });
  talk = bindHoldToTalk($("talk"), {
    mic,
    onLevel: (v) => $("talk").style.setProperty("--level", v.toFixed(2)),
    allowSilence: () => state.mock,
    onStart: recordingStarted,
    onStop: recordingStopped,
    onBlob: (blob) => send({ blob }),
    onProblem: (message, code) => showNotice(code === "blocked" ? "blocked" : code || "server",
                                             { what: message }),
  });

  const on = (id, fn) => $(id).addEventListener("click", fn);
  on("confirm-yes", () => send({ answer: "yes" }));
  on("confirm-no", () => send({ answer: "no" }));
  on("safety-yes", () => send({ answer: "yes" }));
  on("safety-no", () => send({ answer: "no" }));
  on("cancel-yes", () => send({ answer: "yes" }));
  on("cancel-no", () => send({ answer: "no" }));
  on("ask-status", () => send({ answer: "status" }));
  on("repeat-btn", () => send({ repeat: true }));
  on("last-repeat", () => send({ repeat: true }));
  on("new-report", resetReport);
  on("replay", () => play(state.audioUrl));
  on("mock-send", () => send({ blob: new Blob([], { type: "audio/webm" }) }));
  on("kitchen-btn", openKitchenSheet);
  on("notice-action", () => mic.get().then(() => hideNotice("firstUse"), () => showNotice("blocked")));

  window.addEventListener("online", () => { updateConn(); hideNotice("noNetwork"); });
  window.addEventListener("offline", () => { updateConn(); showNotice("noNetwork"); });
  watchMicPermission();
  await loadKitchens();
  document.body.classList.remove("is-loading");  // first screen drawn: show it (design.css)
}

// ------------------------------------------------------------------ kitchen and language

async function loadKitchens() {
  try {
    [state.kitchens, state.languages] = await Promise.all([getJson("/kitchens"), getJson("/languages")]);
  } catch (err) {
    return problem(err);
  }
  state.languages.sort((a, b) => LANG_ORDER.indexOf(a.code) - LANG_ORDER.indexOf(b.code));
  const chosen = state.kitchens.find((k) => String(k.id) === stored(KITCHEN_KEY));
  useKitchen(chosen || state.kitchens[0]);
}

function useKitchen(k) {
  state.kitchen = k;
  store(KITCHEN_KEY, String(k.id));
  socket?.close();
  state.socketState = "reconnecting";
  socket = liveSocket(`/ws/kitchen/${k.id}`, {
    onMessage: onLiveMessage,
    onState: (s) => { state.socketState = s; updateConn(); },
  });
  const saved = stored(langKey(k.id));  // the language chosen on this device for this kitchen
  if (saved && saved !== k.language) chooseLanguage(saved);  // e.g. after a demo reset
  else applyLanguage();
}

async function chooseLanguage(code) {
  const k = state.kitchen;
  try {
    Object.assign(k, await putJson(`/kitchens/${k.id}/language`, { language: code }));
  } catch (err) {
    return problem(err);
  }
  store(langKey(k.id), code);
  applyLanguage();
}

function applyLanguage() {
  const k = state.kitchen;
  state.t = strings(k.language);
  document.documentElement.lang = k.language.split("-")[0];
  $("kitchen-label").textContent = k.name;
  $("mock-text").placeholder = k.sample;
  drawLanguages();
  applyStrings();
  resetReport();
}

function drawLanguages() {
  $("langs").replaceChildren(...state.languages.map((l) => {
    const btn = el("button", "seg-btn lang-name", l.native_name);
    btn.type = "button";
    btn.lang = l.code.split("-")[0];
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", String(l.code === state.kitchen.language));
    btn.addEventListener("click", () => l.code !== state.kitchen.language && chooseLanguage(l.code));
    return btn;
  }));
}

function openKitchenSheet() {
  $("sheet-title").textContent = state.t.kitchenSheet;
  $("kitchen-list").replaceChildren(...state.kitchens.map((k) => {
    const btn = el("button", "btn btn-secondary");
    btn.type = "button";
    btn.setAttribute("aria-current", String(k.id === state.kitchen.id));
    btn.append(el("span", null, k.name), el("small", "lang-name", k.native_name));
    btn.addEventListener("click", () => { $("kitchen-sheet").close(); useKitchen(k); });
    return btn;
  }));
  $("kitchen-sheet").showModal();
}

// Every fixed word on the screen, in the kitchen's language.
function applyStrings() {
  const t = state.t;
  bilingual($("confirm-yes"), "confirm.yes");
  bilingual($("confirm-no"), "confirm.no");
  bilingual($("cancel-yes"), "cancel.yes");
  bilingual($("cancel-no"), "cancel.no");
  bilingual($("ask-status"), "after.status");
  bilingual($("repeat-btn"), "after.repeat");
  bilingual($("new-report"), "after.newReport");
  bilingual($("last-repeat"), "after.repeat");
  $("cancel-q").textContent = t.cancel.q;
  $("settings-title").textContent = t.settings;
  $("mock-label").textContent = t.mock;
  $("mock-send").textContent = t.mockSend;
  $("mic-label").textContent = t.micLabel;
  $("replay").setAttribute("aria-label", t.replay);
  $("last-title").textContent = t.lastReport;
  updateConn();
  updateMic();
  if (state.notice) showNotice(state.notice.key, state.notice.vars);
}

// Primary language big, English small underneath (DESIGN.md).
function bilingual(btn, path) {
  const main = pick(state.t, path);
  const en = pick(STRINGS["en-IN"], path);
  btn.classList.add("btn-bilingual");
  btn.lang = state.kitchen.language.split("-")[0];
  btn.replaceChildren(document.createTextNode(main));
  if (state.kitchen.language !== "en-IN" && en !== main) {
    const sub = el("span", "btn-en", en);
    sub.lang = "en";
    btn.append(sub);
  }
}

// ------------------------------------------------------------------ talking to the server

function target(repeat) {
  const r = state.report;
  if (repeat || !r) return { url: "/reports/audio", fresh: true };
  if (ANSWERING.includes(r.status)) return { url: `/reports/${r.id}/reply` };
  return { url: `/reports/${r.id}/ask`, ask: true };
}

// One request: a recording (blob), a tapped answer ("yes" / "no" / "status"), or "kal jaisa".
async function send({ blob = null, answer = null, repeat = false } = {}) {
  if (state.busy) return;
  const to = target(repeat);
  const form = new FormData();
  if (blob) form.append("audio_file", blob, `speech.${extensionFor(blob.type)}`);
  if (answer) form.append("answer", answer);
  if (repeat) form.append("repeat", "true");
  const typed = $("mock-text").value.trim();
  if (state.mock && blob && typed) form.append("mock_transcript", typed);
  if (to.fresh) {
    form.append("kitchen_id", state.kitchen.id);
    startTicket();
  }
  setBusy(true);
  hideNotice();
  try {
    const data = await postJson(to.url, { body: form });
    $("mock-text").value = "";
    play(data.audio_url);
    if (to.ask) showAnswer(data);
    else await showReport(data);
    $("latency").textContent = Object.entries(data.latency_ms || {})
      .map(([stage, ms]) => `${stage} ${ms} ms`).join(" · ");
  } catch (err) {
    if (to.fresh) clearTicket();
    problem(err);
  } finally {
    setBusy(false);
  }
}

function problem(err) {
  if (!navigator.onLine || err instanceof TypeError) return showNotice("noNetwork");
  if (err.status === 422 && /speech/i.test(err.message)) return showNotice("silent");
  showNotice("server", { what: err.message });
}

// ------------------------------------------------------------------ the ticket

// A blank ticket while the first request is on its way: its slots breathe until lines write in.
function startTicket() {
  resetReport({ keepLast: true });
  const t = state.t;
  state.slip = renderKot({ kitchen: state.kitchen.name, status: "RECORDED" },
                         { print: !state.printed, words: { ...t.kot, status: t.status } });
  state.printed = true;
  state.slip.classList.add("is-sending");
  $("slip-holder").replaceChildren(state.slip);
  $("stage").classList.add("has-slip");
}

function clearTicket() {
  if (!state.report) resetReport();
}

async function showReport(data) {
  const slip = state.slip;
  const first = !state.report;
  if (first) setKotId(slip, data.report_id);
  slip.classList.remove("is-sending");
  state.report = { id: data.report_id, status: data.status, fields: data.fields,
                   missing: data.missing || [], safety: data.safety_question };
  say(data.prompt_text, data.language);
  clearKotNotes(slip);
  setKotStatus(slip, data.status, { word: statusWord(data.status) });
  renderStep();
  await setKotFields(slip, data.fields, { stagger: first ? 220 : 160 });
  if (data.status === "CONFIRMING" && state.report.missing.length) {
    setKotNote(slip, MISSING_LINE[state.report.missing[0]] || "food", followUp(data.prompt_text));
  }
  if (!ANSWERING.includes(data.status)) {
    drawRoute();
    loadLastReport();  // this report is now the one "kal jaisa" copies
    // Done answering: bring back what the app said and the ticket's live status.
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("say").scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
  }
}

// The trailing question(s) of a prompt: "Pichhli report jaisa: … Khana kitne baje bana tha?"
// -> "Khana kitne baje bana tha?". Shown beside the line it asks about.
function followUp(prompt) {
  const parts = (prompt || "").split(/(?<=[.?!।])\s+/);
  const out = [];
  while (parts.length && parts[parts.length - 1].trim().endsWith("?")) out.unshift(parts.pop());
  return out.join(" ") || null;
}

function showAnswer(data) {
  say(data.text, data.language);
  state.cancelAsked = data.action === "cancel_confirm";
  if (data.volunteer) state.live.volunteer = data.volunteer;
  if (data.eta_min) state.live.eta = data.eta_min;
  if (data.status) state.report.status = data.status;
  setKotStatus(state.slip, state.report.status, { word: statusWord(state.report.status) });
  drawRoute();
  renderStep();
}

// Live updates for the report on screen (volunteer asked, accepted, picked up, delivered).
function onLiveMessage(msg) {
  if (msg.type === "reset") {
    hideNotice();
    return resetReport();
  }
  if (msg.type !== "match" || !state.report || msg.report_id !== state.report.id) return;
  state.report.status = msg.status;
  if (msg.volunteer) state.live.volunteer = msg.volunteer;
  if (msg.eta_min) state.live.eta = msg.eta_min;
  if (msg.ngo) state.live.ngo = msg.ngo;
  state.live.reason = msg.reason || null;
  if (msg.status === "OFFERED" || msg.reason === "declined" || msg.reason === "no_answer") {
    state.live.eta = null;  // a new volunteer, a new estimate
  }
  if (msg.status === "CANCELLED") state.cancelAsked = false;
  // What the app last said ("we're finding a volunteer") is out of date now; the ticket's pill
  // carries the live status. Asking ("volunteer kab aayega?") brings a fresh answer back.
  if (!state.speaking) $("say").hidden = true;
  setKotStatus(state.slip, msg.status, { word: statusWord(msg.status) });
  drawRoute();
  renderStep();
}

function statusWord(status) {
  const s = state.t.status;
  const v = firstName(state.live.volunteer);
  if (status === "MATCHING" && state.live.reason === "no_volunteer") return s.waiting;
  if (status === "OFFERED") return v ? fill(s.OFFERED, { v }) : s.MATCHING;
  if (status === "ASSIGNED" && v) return fill(s.ASSIGNED, { v, m: state.live.eta ?? "…" });
  return s[status] || null;
}

// Kitchen -> volunteer -> NGO along the foot of the ticket, once matching has started.
function drawRoute() {
  const r = state.report;
  const at = { MATCHING: 0, OFFERED: 0, ASSIGNED: 1, PICKED_UP: 2, DELIVERED: 3 }[r?.status];
  if (at === undefined) return state.slip?.querySelector(".route")?.remove();
  const stops = [
    { name: state.kitchen.name.split(",")[0], icon: "flame" },
    { name: firstName(state.live.volunteer) || state.t.routeVolunteer, icon: "bike" },
  ];
  if (state.live.ngo) stops.push({ name: state.live.ngo, icon: "people" });
  setKotRoute(state.slip, { stops, at: Math.min(at, stops.length) });
}

// Which panel shows under the ticket: one thing to do at a time.
function renderStep() {
  const r = state.report;
  const status = r?.status;
  const confirming = status === "CONFIRMING" && !r.missing.length;
  const safety = status === "SAFETY_CHECK";
  const expired = status === "EXPIRED";
  const after = !!r && !ANSWERING.includes(status) && !state.cancelAsked;
  show("confirm-actions", confirming);
  show("safety", safety);
  show("cancel", state.cancelAsked);
  show("expired-note", expired, false);
  show("after-actions", after, false);  // the ticket's live status matters more than these
  $("ask-status").hidden = ["DELIVERED", "CANCELLED", "EXPIRED"].includes(status);
  if (safety) drawSafety();
  if (expired) {
    $("expired-text").textContent = fill(state.t.notice.expired,
      { cooked: clock(r.fields.cooked_at), deadline: clock(r.fields.deadline) });
  }
  updateMic();
}

// Show or hide a panel. One that asks for an answer is brought into view when it appears,
// since on a phone the ticket and its answers can be taller than the screen.
function show(id, on, reveal = true) {
  const panel = $(id);
  const appearing = on && panel.hidden;
  panel.hidden = !on;
  if (appearing && reveal) {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => panel.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" }));
  }
}

function drawSafety() {
  const t = state.t;
  const { safety, fields } = state.report;
  const veg = safety === "veg";
  const coverFirst = !veg && fields.covered === false;
  $("safety-step").textContent = fill(t.safetyStep, { n: veg ? 1 : 2 });
  $("safety-icon").setAttribute("href", `${ICONS}#${veg ? "veg" : "covered"}`);
  $("safety-q").textContent = veg ? t.veg.q : coverFirst ? t.covered.first : t.covered.q;
  bilingual($("safety-yes"), veg ? "veg.yes" : coverFirst ? "covered.done" : "covered.yes");
  bilingual($("safety-no"), veg ? "veg.no" : "covered.no");
}

function resetReport({ keepLast = false } = {}) {
  Object.assign(state, { report: null, slip: null, live: {}, cancelAsked: false });
  $("slip-holder").replaceChildren();
  $("stage").classList.remove("has-slip");
  $("say").hidden = true;
  $("latency").textContent = "";
  renderStep();
  if (!keepLast) loadLastReport();
}

// ------------------------------------------------------------------ last report

async function loadLastReport() {
  const k = state.kitchen;
  if (!k) return;
  let last = null;
  try {
    last = await getJson(`/kitchens/${k.id}/last-report`);
  } catch { /* the card is optional */ }
  if (state.kitchen !== k) return;
  $("last").hidden = !last;
  if (!last) return;
  const t = state.t;
  const [one, many] = (t.kot.units || {})[last.unit] || [last.unit, last.unit];
  const amount = `${last.quantity} ${last.quantity === 1 ? one : many}`;
  const summary = $("last").querySelector("summary");
  summary.querySelector(".summary-food")?.remove();
  summary.insertBefore(el("span", "summary-food", `· ${amount} ${last.dish}`), summary.lastElementChild);
  $("last-food").textContent = [amount, last.dish, last.location,
    `${(t.kot.labels || {}).cooked_at || "Cooked"} ${clock(last.cooked_at)}`].filter(Boolean).join(" · ");
  $("last-hint").textContent = fill(t.lastHint, { phrase: k.repeat_hint });
}

// ------------------------------------------------------------------ voice out

function say(text, language) {
  if (!text) return;
  $("say").hidden = false;
  $("say-text").textContent = text;
  $("say-text").lang = (language || state.kitchen.language).split("-")[0];
}

function play(url) {
  if (!url) return;
  state.audioUrl = url;
  state.audio?.pause();
  const audio = new Audio(url);
  state.audio = audio;
  audio.addEventListener("playing", () => setSpeaking(true));
  for (const ev of ["ended", "pause", "error"]) audio.addEventListener(ev, () => setSpeaking(false));
  audio.play().catch(() => setSpeaking(false));  // autoplay blocked: the replay button stays
}

// While the app speaks: a speaker on the ticket, and the mic waits.
function setSpeaking(on) {
  state.speaking = on;
  if (state.slip) setKotSpeaking(state.slip, on);
  $("say").classList.toggle("is-speaking", on);
  updateMic();
}

// ------------------------------------------------------------------ mic

function updateMic() {
  const t = state.t;
  const r = state.report;
  const mode = !r ? "report" : ANSWERING.includes(r.status) ? "reply" : "ask";
  const label = state.busy ? t.mic.sending : state.speaking ? t.mic.speaking : t.mic[mode];
  $("talk").disabled = state.busy || state.speaking;
  if (!talk?.isRecording()) {
    $("talk-label").textContent = label;
    $("mic-caption").textContent = label;
  }
  $("mic-hint").textContent = state.busy || state.speaking ? ""
    : mode === "report" ? t.hint.report : mode === "ask" ? t.hint.ask : "";
}

function recordingStarted() {
  $("talk").classList.add("is-recording");
  $("talk-icon").setAttribute("href", `${ICONS}#stop`);
  $("talk-label").textContent = state.t.mic.recording;
  $("mic-caption").textContent = state.t.mic.recording;
  $("mic-hint").textContent = "";
  const started = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - started) / 1000);
    $("timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  tick();
  $("timer").hidden = false;
  timer = setInterval(tick, 250);
  hideNotice();
}

function recordingStopped() {
  clearInterval(timer);
  $("timer").hidden = true;
  $("talk").classList.remove("is-recording");
  $("talk").style.setProperty("--level", "0");
  $("talk-icon").setAttribute("href", `${ICONS}#mic`);
  updateMic();
}

function setBusy(on) {
  state.busy = on;
  for (const id of ["confirm-yes", "confirm-no", "safety-yes", "safety-no", "cancel-yes", "cancel-no",
                    "ask-status", "repeat-btn", "new-report", "last-repeat", "mock-send"]) {
    $(id).disabled = on;
  }
  updateMic();
}

async function watchMicPermission() {
  try {
    const perm = await navigator.permissions.query({ name: "microphone" });
    const apply = () => {
      if (perm.state === "prompt") showNotice("firstUse");
      else if (perm.state === "denied") showNotice("blocked");
      else hideNotice("firstUse") || hideNotice("blocked");
    };
    perm.onchange = apply;
    apply();
  } catch { /* no permission query (Firefox): the browser asks on the first hold */ }
}

// ------------------------------------------------------------------ notices and connection

function showNotice(key, vars = {}) {
  state.notice = { key, vars };
  const kind = NOTICE_KIND[key] || "error";
  $("notice").className = `callout callout--${kind}`;
  $("notice-icon").setAttribute("href", `${ICONS}#${key === "firstUse" ? "mic" : kind === "error" ? "cross" : "clock"}`);
  $("notice-text").textContent = fill(state.t.notice[key] || state.t.notice.server, vars);
  $("notice-action").hidden = key !== "firstUse";
  $("notice-action").textContent = state.t.notice.allow;
  $("notice").hidden = false;
}

// Hide the notice, or only a notice of this kind. Returns whether one was hidden.
function hideNotice(key = null) {
  if (!state.notice || (key && state.notice.key !== key)) return false;
  state.notice = null;
  $("notice").hidden = true;
  return true;
}

function updateConn() {
  const s = !navigator.onLine ? "offline" : state.socketState === "open" ? "live" : "reconnecting";
  $("conn").dataset.state = s;
  $("conn-word").textContent = state.t.conn[s];
}

// ------------------------------------------------------------------ helpers

function firstName(name) {
  return name ? name.split(" ")[0] : null;
}

function pick(obj, path) {
  return path.split(".").reduce((o, k) => o?.[k], obj);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

init();
