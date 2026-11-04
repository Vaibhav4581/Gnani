// NGO screen: the shelter coordinator asks for food by voice (read back as a need slip, confirmed
// by voice or button), follows the food on its way as tickets (soonest first, with the volunteer
// and ETA), and answers "Khana aa gaya?" on the arriving ticket by voice or with Haan / Nahi.
// Both mics are tap to talk, and open by themselves after those two yes/no questions.
import { $, failureKey, getJson, liveSocket, postJson, rotateExamples, store, stored } from "/shared/common.js";
import { LISTEN, Microphone, bindTapToTalk, elapsed, extensionFor } from "/assets/recorder.js";
import { clearKotNotes, clock, renderKot, renderNeedSlip, setKotNote, setKotRoute, setKotStatus,
         updateNeedSlip } from "/assets/kot.js";
import { STRINGS, fill, strings } from "./strings.js";

const ICONS = "/assets/icons.svg";
const NGO_KEY = "bhk.ngoId";
const ON_THE_WAY = ["MATCHING", "OFFERED", "ASSIGNED", "PICKED_UP"];
const REFRESH_MS = 60_000;  // ETAs move on; read them again once a minute while food is coming

const state = {
  mock: false, ngos: [], ngo: null, t: strings("en-IN"), socketState: "reconnecting",
  need: null,      // the need being asked for: { id, status, missing }
  needSlip: null,
  delivery: null,  // the arriving food's question: { report_id, text, audio_url, language }
  busy: false, audioUrl: null,
  asked: null,     // the yes/no question just spoken: "need" (the read-back) | "delivery" | null
};
let socket = null;
let talk = null;
let arrivalTalk = null;
let listenTimer = null;  // opens the right mic just after a yes/no question has been spoken
let micClock = null;     // the timer beside "Bol dijiye…" / "Sun rahe hain…"
let stopExamples = () => {};
let refresh = null;
const player = new Audio();

// ------------------------------------------------------------------ start

async function init() {
  try {
    state.mock = (await getJson("/config")).mock;
  } catch { /* the first request will show what went wrong */ }
  $("mock-panel").hidden = !state.mock;
  $("settings").open = state.mock;

  const mic = new Microphone({ select: $("mic"), row: $("mic-row") });
  const problem = (message, code) => notice(fill(state.t.notice[code] || state.t.notice.server,
                                                 { what: message }), "error");
  talk = bindTapToTalk($("talk"), {
    mic, allowSilence: () => state.mock, onProblem: problem,
    onLevel: (v) => $("talk").style.setProperty("--level", v.toFixed(2)),
    onStart: (mode) => recording($("talk"), "talk-icon", true, mode),
    onStop: () => recording($("talk"), "talk-icon", false),
    onBlob: (blob) => sendNeed({ blob }),
  });
  arrivalTalk = bindTapToTalk($("arrival-talk"), {
    mic, allowSilence: () => state.mock, onProblem: problem,
    onStart: (mode) => recording($("arrival-talk"), "arrival-talk-icon", true, mode),
    onStop: () => recording($("arrival-talk"), "arrival-talk-icon", false),
    onBlob: (blob) => answerDelivery({ blob }),
  });

  const on = (id, fn) => $(id).addEventListener("click", fn);
  on("confirm-yes", () => sendNeed({ answer: "yes" }));
  on("confirm-no", () => sendNeed({ answer: "no" }));
  on("more", resetNeed);
  on("replay", () => play(state.audioUrl, readingBack() ? "need" : null));
  on("arrival-yes", () => answerDelivery({ answer: "yes" }));
  on("arrival-no", () => answerDelivery({ answer: "no" }));
  on("arrival-replay", () => play(state.delivery?.audio_url, "delivery"));
  // Never record while the app speaks; once a yes/no question has been spoken, listen for it.
  player.addEventListener("playing", () => {
    for (const id of ["talk", "arrival-talk"]) $(id).disabled = true;
  });
  for (const ev of ["ended", "pause", "error"]) {
    player.addEventListener(ev, () => {
      for (const id of ["talk", "arrival-talk"]) $(id).disabled = state.busy;
    });
  }
  player.addEventListener("ended", () => {
    listenTimer = setTimeout(() => {
      if (!player.ended || state.busy) return;
      if (state.asked === "delivery" && state.delivery) arrivalTalk.listen();
      else if (state.asked === "need" && readingBack()) talk.listen();
    }, LISTEN.AFTER_VOICE_MS);
  });
  on("ngo-btn", openSheet);
  on("mock-send", () => {
    const blob = new Blob([], { type: "audio/webm" });
    if (state.delivery) answerDelivery({ blob });
    else sendNeed({ blob });
  });
  window.addEventListener("online", updateConn);
  window.addEventListener("offline", updateConn);
  const fit = new ResizeObserver(() => fitRequests());  // a window, a need being read back, settings
  document.querySelectorAll(".ask, .ask > :not(.requests)").forEach((node) => fit.observe(node));
  ONE_SCREEN.addEventListener("change", fitRequests);
  await loadNgos();
  document.body.classList.remove("is-loading");  // first screen drawn: show it (design.css)
}

// ------------------------------------------------------------------ which NGO

async function loadNgos() {
  try {
    state.ngos = await getJson("/ngos");
  } catch (err) {
    return problem(err);
  }
  const chosen = state.ngos.find((n) => String(n.id) === stored(NGO_KEY));
  useNgo(chosen || state.ngos[0]);
}

function useNgo(n) {
  state.ngo = n;
  state.t = strings(n.language);
  store(NGO_KEY, String(n.id));
  document.documentElement.lang = n.language.split("-")[0];
  $("mock-text").placeholder = n.sample;
  socket?.close();
  state.socketState = "reconnecting";
  socket = liveSocket(`/ws/ngo/${n.id}`, {
    onMessage,
    onState: (s) => {
      state.socketState = s;
      updateConn();
      if (s === "open") loadNeeds();  // catch up after a reconnect
    },
  });
  applyStrings();
  resetNeed();
  hideNotice();
  loadToday();
}

function openSheet() {
  $("sheet-title").textContent = state.t.sheet;
  $("ngo-list").replaceChildren(...state.ngos.map((n) => {
    const btn = el("button", "btn btn-secondary");
    btn.type = "button";
    btn.setAttribute("aria-current", String(n.id === state.ngo.id));
    const small = el("small");
    small.append(el("span", "lang-name", n.native_name), ` · ${n.area}`);
    btn.append(el("span", null, n.name), small);
    btn.addEventListener("click", () => { $("ngo-sheet").close(); useNgo(n); });
    return btn;
  }));
  $("ngo-sheet").showModal();
}

function applyStrings() {
  const t = state.t;
  $("ngo-label").textContent = state.ngo.name;
  $("today-people-label").textContent = t.today.people;
  $("today-meals-label").textContent = t.today.meals;
  $("incoming-h").textContent = t.incoming.title;
  $("incoming-empty-text").textContent = t.incoming.empty;
  $("arrival-q").textContent = t.arrival.q;
  bilingual($("arrival-yes"), "arrival.yes");
  bilingual($("arrival-no"), "arrival.no");
  $("arrival-hold").textContent = t.arrival.hold;
  $("arrival-talk").setAttribute("aria-label", t.arrival.hold);
  $("ask-h").textContent = t.ask.title;
  $("ask-hint").textContent = t.ask.hint;
  $("example-lead").textContent = t.example;
  stopExamples();
  stopExamples = rotateExamples($("examples"), state.ngo.examples || [],
                                { lang: state.ngo.language.split("-")[0] });
  bilingual($("confirm-yes"), "confirm.yes");
  bilingual($("confirm-no"), "confirm.no");
  bilingual($("more"), "ask.more");
  $("requests-h").textContent = t.requests.title;
  $("settings-title").textContent = t.settings;
  $("mock-label").textContent = t.mock;
  $("mock-send").textContent = t.mockSend;
  $("mic-label").textContent = t.micLabel;
  for (const id of ["replay", "arrival-replay"]) $(id).setAttribute("aria-label", t.replay);
  updateConn();
  updateMic();
}

// Primary language big, English small underneath (DESIGN.md).
function bilingual(btn, path) {
  const main = pick(state.t, path);
  const en = pick(STRINGS["en-IN"], path);
  btn.lang = state.ngo.language.split("-")[0];
  btn.replaceChildren(document.createTextNode(main));
  if (state.ngo.language !== "en-IN" && en !== main) {
    const sub = el("span", "btn-en", en);
    sub.lang = "en";
    btn.append(sub);
  }
}

// ------------------------------------------------------------------ asking for food

// A recording, or a tapped yes / no to the read-back.
async function sendNeed({ blob = null, answer = null } = {}) {
  if (state.busy) return;
  const replying = state.need?.status === "CONFIRMING";
  const url = replying ? `/needs/${state.need.id}/reply` : "/needs/audio";
  const form = new FormData();
  if (blob) form.append("audio_file", blob, `speech.${extensionFor(blob.type)}`);
  if (answer) form.append("answer", answer);
  if (!replying) form.append("ngo_id", state.ngo.id);
  addMockText(form, blob);
  setBusy(true);
  hideNotice();
  try {
    const data = await postJson(url, { body: form });
    const readBack = data.status === "CONFIRMING" && !(data.missing || []).length;
    play(data.audio_url, readBack ? "need" : null);  // "…Sahi hai?"; a follow-up waits for a tap
    await showNeed(data);
    if (data.status === "OPEN") loadNeeds();
    $("latency").textContent = Object.entries(data.latency_ms || {})
      .map(([stage, ms]) => `${stage} ${ms} ms`).join(" · ");
  } catch (err) {
    problem(err);
  } finally {
    setBusy(false);
  }
}

async function showNeed(data) {
  const t = state.t;
  const need = { need_id: data.need_id, ngo: state.ngo.name, status: data.status, ...data.fields };
  state.need = { id: data.need_id, status: data.status, missing: data.missing || [] };
  say(data.prompt_text, data.language);
  if (!state.needSlip) {
    state.needSlip = renderNeedSlip({ need_id: data.need_id, ngo: state.ngo.name, status: data.status },
                                    { words: { ...t.kot, ...t.need } });
    $("need-holder").replaceChildren(state.needSlip);
  }
  clearKotNotes(state.needSlip);
  await updateNeedSlip(state.needSlip, need);
  const missing = state.need.missing[0];
  if (data.status === "CONFIRMING" && missing) setKotNote(state.needSlip, missing, followUp(data.prompt_text));
  $("confirm-actions").hidden = !(data.status === "CONFIRMING" && !missing);
  $("more").hidden = data.status === "CONFIRMING";
  updateMic();
}

// The trailing question(s) of a prompt, shown beside the line it asks about.
function followUp(prompt) {
  const parts = (prompt || "").split(/(?<=[.?!।])\s+/);
  const out = [];
  while (parts.length && parts[parts.length - 1].trim().endsWith("?")) out.unshift(parts.pop());
  return out.join(" ") || null;
}

function resetNeed() {
  Object.assign(state, { need: null, needSlip: null });
  $("need-holder").replaceChildren();
  $("say").hidden = true;
  $("confirm-actions").hidden = true;
  $("more").hidden = true;
  updateMic();
  loadNeeds();
}

// ------------------------------------------------------------------ food on the way

function onMessage(msg) {
  if (msg.type === "reset") {
    state.delivery = null;
    resetNeed();
    loadToday();
  } else if (msg.type === "need") {
    loadNeeds();
  } else if (msg.type === "delivery_check") {
    state.delivery = msg;
    play(msg.audio_url, "delivery");
    loadNeeds();
  }
}

async function loadNeeds() {
  const n = state.ngo;
  if (!n) return;
  let needs;
  try {
    needs = await getJson(`/ngos/${n.id}/needs`);
  } catch {
    return;
  }
  if (state.ngo !== n) return;
  const arriving = needs.find((x) => x.delivery_question);
  if (!arriving) state.delivery = null;
  else if (!state.delivery || state.delivery.report_id !== arriving.report.id) {
    state.delivery = { report_id: arriving.report.id, ...arriving.delivery_question };
  }
  drawFood(needs);
  drawRequests(needs);
  clearInterval(refresh);
  if ($("food-list").children.length) refresh = setInterval(loadNeeds, REFRESH_MS);
}

// Tickets for food heading here, soonest first; the arriving one carries the question.
function drawFood(needs) {
  const t = state.t;
  const coming = needs.filter((x) => x.report && ON_THE_WAY.includes(x.report.status))
    .sort((a, b) => arrivalOrder(a.report) - arrivalOrder(b.report));
  $("incoming-empty").hidden = coming.length > 0;
  $("arrival").hidden = !state.delivery;
  if (!state.delivery) document.querySelector(".layout").append($("arrival"));  // park it
  $("food-list").replaceChildren(...coming.map((x) => {
    const r = x.report;
    const li = el("li", "food-item");
    const slip = renderKot({ id: r.id, kitchen: r.kitchen, dish: r.dish, quantity: r.quantity, unit: r.unit,
                             veg: r.veg, deadline: r.deadline, status: r.status },
                           { words: t.kot, lines: ["food"] });
    setKotStatus(slip, r.status, { word: foodWord(r) });
    const at = { MATCHING: 0, OFFERED: 0, ASSIGNED: 1, PICKED_UP: 2 }[r.status];
    setKotRoute(slip, { at, stops: [
      { name: r.kitchen.split(",")[0], icon: "flame" },
      { name: firstName(r.volunteer) || t.kot.routeVolunteer || "Volunteer", icon: "bike" },
      { name: t.incoming.here, icon: "people" },  // this shelter
    ] });
    li.append(slip);
    if (state.delivery?.report_id === r.id) li.append($("arrival"));
    return li;
  }));
}

function arrivalOrder(r) {
  if (r.arriving) return 0;
  return r.eta_min ?? Number.MAX_SAFE_INTEGER;
}

function foodWord(r) {
  const t = state.t.incoming;
  const v = firstName(r.volunteer);
  if (!v) return t.finding;
  return r.arriving ? fill(t.arriving, { v }) : r.eta_min ? fill(t.eta, { v, m: r.eta_min }) : v;
}

function drawRequests(needs) {
  const t = state.t;
  const words = { ...t.kot, ...t.need };
  const label = (n) => [
    (words.people || "{n} people").replace("{n}", n.people_count ?? "?"),
    n.needed_by ? clock(n.needed_by) : null,
    n.veg_only ? (words.vegOnly || "Veg only") : null,
  ].filter(Boolean).join(" · ");
  // Each request is its need slip, pinned to the board (white paper, a leaf band, a steel pin).
  const list = needs.filter((n) => n.status !== "CONFIRMING");
  $("request-list").replaceChildren(...(list.length ? list.map((n) => {
    const li = el("li", "pinned");
    const slip = renderNeedSlip({ ...n, ngo: "" }, { words });
    slip.setAttribute("aria-label", `${label(n)}: ${slip.querySelector('[data-role="status"]').textContent}`);
    li.append(slip);
    return li;
  }) : [el("li", "empty", t.requests.none)]));
  fitRequests();
}

// On a laptop the page is one screen: when the requests don't fit under the mic, the oldest
// fold to one row (head count, number, status), oldest first, and if even that is too tall the
// oldest step behind "+N more", which opens the list in full (ngo.css).
const ONE_SCREEN = matchMedia("(min-width: 1000px) and (min-height: 600px)");  // as ngo.css

function fitRequests() {
  const list = $("request-list");
  const col = list.closest(".ask");
  const items = [...list.querySelectorAll(":scope > .pinned")];
  list.querySelector(".request-more")?.remove();
  items.forEach((li) => { li.classList.remove("is-folded"); li.hidden = false; });
  if (!ONE_SCREEN.matches) return;
  const open = list.classList.contains("is-open");
  const over = () => col.scrollHeight > col.clientHeight + 1;
  for (let i = items.length - 1; i >= 0 && (open || over()); i--) items[i].classList.add("is-folded");
  if (open) return list.append(moreRequests(state.t.requests.less));
  if (!over()) return;
  const more = moreRequests("");
  list.append(more);
  let hidden = 0;
  for (let i = items.length - 1; i >= 1 && over(); i--) {
    items[i].hidden = true;
    more.firstChild.textContent = fill(state.t.requests.more, { n: ++hidden });
  }
  if (!hidden) more.remove();
}

function moreRequests(text) {
  const li = el("li", "request-more");
  const btn = el("button", "btn btn-secondary", text);
  btn.type = "button";
  btn.addEventListener("click", () => {
    $("request-list").classList.toggle("is-open");
    fitRequests();
  });
  li.append(btn);
  return li;
}

// ------------------------------------------------------------------ "Khana aa gaya?"

async function answerDelivery({ blob = null, answer = null } = {}) {
  const d = state.delivery;
  if (!d || state.busy) return;
  const form = new FormData();
  if (blob) form.append("audio_file", blob, `answer.${extensionFor(blob.type)}`);
  if (answer) form.append("answer", answer);
  addMockText(form, blob);
  setBusy(true);
  try {
    const data = await postJson(`/reports/${d.report_id}/delivery-reply`, { body: form });
    play(data.audio_url, data.unclear ? "delivery" : null);  // "haan ya nahi?" asks again
    if (data.unclear) {
      notice(data.text, "attention");
      return;
    }
    notice(data.text, data.delivered ? "success" : "attention");
    if (data.delivered) {
      state.delivery = null;
      loadToday();
    }
    loadNeeds();
  } catch (err) {
    problem(err);
  } finally {
    setBusy(false);
  }
}

async function loadToday() {
  try {
    const today = await getJson(`/ngos/${state.ngo.id}/today`);
    $("today-people").textContent = today.people_served;
    $("today-meals").textContent = today.meals;
  } catch { /* the numbers are a nicety */ }
}

// ------------------------------------------------------------------ voice out, mic, busy

function say(text, language) {
  if (!text) return;
  $("say").hidden = false;
  $("say-text").textContent = text;
  $("say-text").lang = (language || state.ngo.language).split("-")[0];
}

// `asked`: the yes/no question this audio asks, so the mic opens once it has been said.
function play(url, asked = null) {
  if (!url) return;
  talk?.cancel();  // never record while the app speaks: it would hear itself
  arrivalTalk?.cancel();
  clearTimeout(listenTimer);
  state.asked = asked;
  state.audioUrl = url;
  player.src = url;
  player.play().catch(() => { /* autoplay blocked: the replay buttons work */ });
}

// The need has been read back in full and waits for "haan" or a correction.
function readingBack() {
  return state.need?.status === "CONFIRMING" && !state.need.missing.length;
}

function updateMic() {
  const m = state.t.mic;
  const confirming = state.need?.status === "CONFIRMING";
  const label = state.busy ? m.sending : confirming ? m.reply : m.ask;
  if (!talk?.isRecording()) $("talk-label").textContent = label;
  // idle: "Tap the button and say what you need, for example: ..." instead of the plain hint
  const idle = !state.busy && !confirming && !talk?.isRecording();
  $("example-box").hidden = !idle;
  $("ask-hint").hidden = idle;
}

// mode: "tap" or "auto" (opened after a question: "Sun rahe hain…").
function recording(button, iconId, on, mode = "tap") {
  button.classList.toggle("is-recording", on);
  $(iconId).setAttribute("href", `${ICONS}#${on ? "stop" : "mic"}`);
  clearInterval(micClock);
  const word = mode === "auto" ? state.t.mic.listening : state.t.mic.recording;
  const label = button.id === "arrival-talk" ? $("arrival-hold") : $("talk-label");
  if (on) {
    const since = performance.now();
    const show = () => { label.textContent = `${word} ${elapsed(since)}`; };
    show();
    micClock = setInterval(show, 250);
  }
  if (button.id === "arrival-talk" && !on) $("arrival-hold").textContent = state.t.arrival.hold;
  if (button.id === "talk" && !on) {
    $("talk-label").textContent = "";
    button.style.setProperty("--level", "0");
    updateMic();
  }
}

function setBusy(on) {
  state.busy = on;
  for (const id of ["talk", "confirm-yes", "confirm-no", "arrival-yes", "arrival-no", "arrival-talk",
                    "mock-send", "more"]) {
    $(id).disabled = on;
  }
  updateMic();
}

function addMockText(form, blob) {
  const typed = $("mock-text").value.trim();
  if (state.mock && blob && typed) form.append("mock_transcript", typed);
  $("mock-text").value = "";
}

// Every failure says what to do next (common.js failureKey).
function problem(err) {
  notice(fill(state.t.notice[failureKey(err)], { what: err?.message }), "error");
}

// ------------------------------------------------------------------ notices and connection

function notice(text, kind = "attention") {
  $("notice").className = `callout callout--${kind}`;
  $("notice-icon").setAttribute("href", `${ICONS}#${kind === "error" ? "cross" : kind === "success" ? "check" : "clock"}`);
  $("notice-text").textContent = text;
  $("notice").hidden = false;
}

function hideNotice() {
  $("notice").hidden = true;
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
