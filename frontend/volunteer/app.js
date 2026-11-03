// Volunteer screen: an offer should feel like an incoming phone call.
// Off duty -> "Start duty" (also unlocks sound) -> on duty, calm -> an offer rings: full-screen
// haldi, the ticket, ride and drop-off, the spoken alert, and call-style Nahi / Haan buttons (voice
// works too) -> accepted: pick up and drop off as two stops -> picked up -> delivered (the NGO is
// then asked to confirm) -> back on duty.
import { $, failureKey, getJson, liveSocket, postJson, store, stored } from "/shared/common.js";
import { Microphone, bindHoldToTalk, extensionFor } from "/shared/recorder.js";
import { clock, renderKot, renderMiniKot, renderSkeletonMini, setKotStatus } from "/assets/kot.js";
import { drawMap } from "/assets/map.js";
import { STRINGS, fill, strings } from "./strings.js";

const ICONS = "/assets/icons.svg";
const VOLUNTEER_KEY = "bhk.volunteerId";
// Two samples of silence: played inside the "Start duty" tap so later audio may autoplay.
const SILENT_WAV = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQQAAAAAAAAA";
const NOTICE_MS = 6000;  // how long "No problem, we've asked the next volunteer" stays

const state = {
  mock: false, volunteers: [], me: null, t: strings("en-IN"), onDuty: false, socketState: "closed",
  offer: null, endsAt: 0, answering: false,
  job: null,  // the accepted pickup: { reportId, s: offer summary, picked }
};
let socket = null;
let audioCtx = null;
let noticeTimer = null;
const player = new Audio();

// ------------------------------------------------------------------ start

async function init() {
  try {
    state.mock = (await getJson("/config")).mock;
  } catch { /* going on duty will show what's wrong */ }
  $("mock-panel").hidden = !state.mock;
  $("settings").open = state.mock;

  const mic = new Microphone({ select: $("mic"), row: $("mic-row") });
  bindHoldToTalk($("talk"), {
    mic,
    allowSilence: () => state.mock,
    onStart: () => listening(state.t.offer.listening, true),
    onStop: () => listening(null),
    onBlob: answerByVoice,
    onProblem: (message, code) => notice(fill(state.t.notice[code] || state.t.notice.server,
                                              { what: message }), "error"),
  });

  const on = (id, fn) => $(id).addEventListener("click", fn);
  on("duty", goOnDuty);
  on("off-duty", goOffDuty);
  on("who-btn", openSheet);
  on("yes", () => answerByButton(true));
  on("no", () => answerByButton(false));
  on("replay", () => play(state.offer?.audio_url));
  on("picked", markPickedUp);
  on("delivered", markDelivered);
  on("mock-send", () => answerByVoice(new Blob([], { type: "audio/webm" })));
  window.addEventListener("online", updateConn);
  window.addEventListener("offline", updateConn);
  await loadVolunteers();
  document.body.classList.remove("is-loading");  // first screen drawn: show it (design.css)
}

// ------------------------------------------------------------------ who am I

async function loadVolunteers() {
  try {
    state.volunteers = await getJson("/volunteers");
  } catch (err) {
    return problem(err);
  }
  const chosen = state.volunteers.find((v) => String(v.id) === stored(VOLUNTEER_KEY));
  useVolunteer(chosen || state.volunteers[0]);
}

function useVolunteer(v) {
  if (state.onDuty) goOffDuty();
  state.me = v;
  state.t = strings(v.language);
  store(VOLUNTEER_KEY, String(v.id));
  document.documentElement.lang = v.language.split("-")[0];
  $("mock-text").placeholder = v.sample_yes;
  applyStrings();
  show("off");
  loadToday();  // the map and today's numbers show off duty too, on a laptop
}

function openSheet() {
  $("sheet-title").textContent = state.t.sheet;
  $("who-list").replaceChildren(...state.volunteers.map((v) => {
    const btn = el("button", "btn btn-secondary");
    btn.type = "button";
    btn.setAttribute("aria-current", String(v.id === state.me.id));
    const small = el("small");
    small.append(el("span", "lang-name", v.native_name), ` · ${v.area}`);
    btn.append(el("span", null, v.name), small);
    btn.addEventListener("click", () => { $("who-sheet").close(); useVolunteer(v); });
    return btn;
  }));
  $("who-sheet").showModal();
}

// Every fixed word on the screen, in the volunteer's language.
function applyStrings() {
  const { t, me } = state;
  $("who-label").textContent = me.name;
  $("me-area").textContent = me.area;
  $("me-carries").textContent = fill(t.duty.carries, { n: me.capacity });
  $("me-lang").textContent = me.native_name;
  $("me-unavailable").hidden = me.available;
  $("me-unavailable-text").textContent = t.duty.unavailable;
  bilingual($("duty"), "duty.start");
  $("duty-hint").textContent = t.duty.hint;
  $("on-title").textContent = fill(t.duty.onTitle, { area: me.area });
  $("area-map").setAttribute("aria-label", t.map.label);
  $("rescues-h").textContent = t.rescues.title;
  $("rescue-empty-text").textContent = t.rescues.empty;
  $("on-body").textContent = t.duty.onBody;
  $("today-label").textContent = t.duty.today;
  $("meals-label").textContent = t.duty.meals;
  bilingual($("off-duty"), "duty.stop");
  $("offer-title").textContent = t.offer.title;
  bilingual($("yes"), "offer.yes");
  $("call-note").textContent = t.noFine;
  bilingual($("no"), "offer.no");
  $("talk-label").textContent = t.offer.hold;
  $("talk").setAttribute("aria-label", t.offer.hold);
  $("accepted-title").textContent = t.accepted.title;
  bilingual($("picked"), "accepted.pickedUp");
  bilingual($("delivered"), "accepted.delivered");
  $("replay").setAttribute("aria-label", t.replay);
  $("settings-title").textContent = t.settings;
  $("mock-label").textContent = t.mock;
  $("mock-send").textContent = t.mockSend;
  $("mic-label").textContent = t.micLabel;
  updateConn();
}

// Primary language big, English small underneath (DESIGN.md).
function bilingual(btn, path) {
  const main = pick(state.t, path);
  const en = pick(STRINGS["en-IN"], path);
  btn.lang = state.me.language.split("-")[0];
  btn.replaceChildren(document.createTextNode(main));
  if (state.me.language !== "en-IN" && en !== main) {
    const sub = el("span", "btn-en", en);
    sub.lang = "en";
    btn.append(sub);
  }
}

// One screen at a time: off | on | offer | accepted. The page colour follows it. The area map
// and today's numbers belong to whichever of off and on is showing.
function show(screen) {
  document.body.dataset.screen = screen;
  const map = $("area-map").parentElement;
  if (screen === "on") {
    $("screen-on").prepend(map);
    $("on-title").parentElement.after($("today"));
  } else if (screen === "off") {
    $("screen-off").prepend(map);
    $("duty-hint").after($("today"));
  }
  for (const name of ["off", "on", "offer", "accepted"]) $(`screen-${name}`).hidden = name !== screen;
  if (screen === "offer" || screen === "accepted") window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ duty

function unlockAudio() {
  audioCtx = audioCtx || new AudioContext();
  audioCtx.resume();
  player.src = SILENT_WAV;
  player.play().catch(() => { /* still fine: the replay button works */ });
}

function goOnDuty() {
  unlockAudio();  // must happen inside this tap
  socket?.close();
  state.socketState = "reconnecting";
  socket = liveSocket(`/ws/volunteer/${state.me.id}`, {
    onMessage,
    onState: (s) => { state.socketState = s; updateConn(); },
  });
  state.onDuty = true;
  show("on");
  updateConn();
  loadToday();
}

function goOffDuty() {
  socket?.close();
  socket = null;
  Object.assign(state, { onDuty: false, offer: null, job: null, answering: false });
  show("off");
  updateConn();
}

async function loadToday() {
  drawAreaMap();
  if (!$("rescue-list").children.length) {  // loading: a blank ticket breathing, not the empty state
    $("rescue-empty").hidden = true;
    $("rescue-list").setAttribute("aria-busy", "true");
    const li = el("li");
    li.append(renderSkeletonMini());
    $("rescue-list").replaceChildren(li);
  }
  try {
    const today = await getJson(`/volunteers/${state.me.id}/today`);
    $("today-rescues").textContent = today.rescues;
    $("today-meals").textContent = today.meals;
    drawRescues(today.recent || []);
  } catch {  // the numbers are a nicety
    drawRescues([]);
  }
}

// The volunteer's own area: kitchens, shelters and other volunteers within 4 km, "you" pulsing.
async function drawAreaMap() {
  const me = state.me;
  try {
    state.places ||= await getJson("/map");
  } catch { return; }
  const self = state.places.volunteers.find((v) => v.id === me.id);
  if (!self || state.me !== me) return;
  drawMap($("area-map"), state.places, { focus: { lat: self.lat, lng: self.lng, km: 4 }, you: me.id,
                                         youLabel: state.t.map.you, width: 360, pad: 46 });
}

// "Your rescues": the last three as small tickets, or the scooter and a line when there are none.
function drawRescues(recent) {
  const t = state.t;
  $("rescue-list").removeAttribute("aria-busy");
  $("rescue-empty").hidden = recent.length > 0;
  $("rescue-list").replaceChildren(...recent.map((r) => {
    const li = el("li");
    li.append(renderMiniKot(r, { words: t.kot,
                                 word: r.status === "DELIVERED" ? t.rescues.done : t.rescues.picked }));
    return li;
  }));
}

// Back to the calm screen, with a short message that clears itself.
function backToDuty(text, kind = "attention") {
  Object.assign(state, { offer: null, job: null, answering: false });
  show(state.onDuty ? "on" : "off");
  if (text) notice(text, kind, { brief: true });
  loadToday();
}

// ------------------------------------------------------------------ offers

async function onMessage(msg) {
  if (msg.type === "offer") {
    showOffer(msg);
    navigator.vibrate?.([400, 200, 400, 200, 400]);  // like a phone ringing, for a phone in a pocket
    await ring();
    play(msg.audio_url);
  } else if (msg.type === "reset") {  // demo data was reset from the dashboard
    hideNotice();
    backToDuty(null);
  } else if (msg.type === "assignment_cancelled" && msg.report_id === state.job?.reportId) {
    play(msg.audio_url);  // the kitchen cancelled after this volunteer accepted
    backToDuty(state.t.after.cancelled);
  } else if (msg.type === "offer_closed" && msg.offer_id === state.offer?.offer_id) {
    play(msg.audio_url);
    backToDuty(msg.status === "WITHDRAWN" ? state.t.after.cancelled : state.t.after.declined);
  }
}

function showOffer(msg) {
  const t = state.t;
  const s = msg.summary;
  state.offer = msg;
  state.endsAt = performance.now() + msg.timeout_s * 1000;
  hideNotice();
  $("offer-kitchen").textContent = s.kitchen;
  const slip = renderKot({ id: msg.report_id, kitchen: s.kitchen, dish: s.dish, quantity: s.quantity,
                           unit: s.unit, deadline: s.deadline, veg: s.veg, status: "OFFERED" },
                         { words: t.kot, lines: ["food", "deadline"] });
  setKotStatus(slip, "OFFERED", { word: t.offer.pill });
  $("offer-slip").replaceChildren(slip);
  const ride = fill(t.offer.ride, { km: s.distance_km, m: s.eta_min });
  $("offer-ride").textContent = s.ngo ? `${ride} · ${fill(t.offer.total, { total: s.ngo.total_km })}` : ride;
  $("offer-drop-row").hidden = !s.ngo;
  if (s.ngo) {
    $("offer-drop-label").textContent = t.offer.dropAt;
    $("offer-drop").textContent = `${s.ngo.name} · ${fill(t.offer.people, { n: s.ngo.people })}`;
  }
  const [one, many] = (t.kot.units || {})[s.unit] || [s.unit, s.unit];
  $("offer-announce").textContent = fill(t.announce, {
    kitchen: s.kitchen, km: s.distance_km,
    food: [s.quantity != null ? `${s.quantity} ${s.quantity === 1 ? one : many}` : null, s.dish]
      .filter(Boolean).join(" ") });
  $("offer-said").textContent = msg.text;
  $("offer-said").lang = (msg.language || state.me.language).split("-")[0];
  setAnswering(true);
  show("offer");
  tick();
}

// The thin bar across the top: how long is left to answer.
function tick() {
  if (!state.offer) return;
  const total = state.offer.timeout_s * 1000;
  const left = Math.max(0, state.endsAt - performance.now());
  $("timeout-bar").style.transform = `scaleX(${total ? left / total : 0})`;
  $("offer-secs").textContent = `${Math.ceil(left / 1000)} s`;
  if (left > 0) requestAnimationFrame(tick);
  else setAnswering(false);  // the server closes the offer and says so
}

function setAnswering(on) {
  state.answering = on;
  for (const id of ["yes", "no", "talk", "mock-send"]) $(id).disabled = !on;
  $("ring-icon").classList.toggle("ringing", on);
}

function listening(word, on = !!word) {
  $("listening").hidden = !on;
  if (word) $("listening-word").textContent = word;
}

function answerByButton(accept) {
  if (!state.offer) return;
  send(`/offers/${state.offer.offer_id}/${accept ? "accept" : "decline"}`);
}

function answerByVoice(blob) {
  if (!state.offer) return;
  const form = new FormData();
  form.append("audio_file", blob, `answer.${extensionFor(blob.type)}`);
  const typed = $("mock-text").value.trim();
  if (state.mock && typed) form.append("mock_transcript", typed);
  $("mock-text").value = "";
  send(`/offers/${state.offer.offer_id}/reply`, { body: form });
}

async function send(url, options) {
  const offer = state.offer;
  setAnswering(false);
  listening(state.t.offer.sending, true);
  try {
    const data = await postJson(url, options);
    $("latency").textContent = Object.entries(data.latency_ms || {})
      .map(([stage, ms]) => `${stage} ${ms} ms`).join(" · ");
    play(data.audio_url);
    if (data.unclear) {  // "haan or nahi?": the offer stays open
      $("offer-said").textContent = data.text;
      setAnswering(true);
    } else if (data.status === "ACCEPTED") {
      accepted(offer);
    } else {
      backToDuty(state.t.after.declined);
    }
  } catch (err) {
    if (err.body) {  // the offer closed before this answer landed
      play(err.body.audio_url);
      const t = state.t.after;
      backToDuty(err.body.taken_by ? fill(t.taken, { v: err.body.taken_by })
        : err.body.status === "WITHDRAWN" ? t.cancelled : t.declined);
    } else {
      problem(err);
      setAnswering(true);
    }
  } finally {
    listening(null);
  }
}

// ------------------------------------------------------------------ the pickup

function accepted(offer) {
  state.offer = null;
  state.job = { reportId: offer.report_id, s: offer.summary, picked: false };
  drawStops();
  show("accepted");
}

function drawStops() {
  const t = state.t.accepted;
  const { s, picked } = state.job;
  const stops = [{ icon: "flame", label: t.pickup, name: s.kitchen, point: s.kitchen_point,
                   detail: fill(t.by, { t: clock(s.deadline) }), done: picked }];
  if (s.ngo) {
    stops.push({ icon: "people", label: t.drop, name: s.ngo.name, point: s.ngo.point,
                 detail: `${fill(state.t.offer.people, { n: s.ngo.people })} · ${fill(t.neededBy, { t: clock(s.ngo.needed_by) })}`,
                 done: false });
  }
  $("stops").replaceChildren(...stops.map((stop) => {
    const li = el("li", `stop${stop.done ? " is-done" : ""}`);
    const dot = el("span", "stop-dot");
    dot.append(icon(stop.done ? "check" : stop.icon));
    const body = el("div", "stop-body");
    body.append(el("span", "stop-label", stop.label), el("span", "stop-name", stop.name),
                el("span", "stop-detail", stop.detail));
    if (stop.point && !stop.done) body.append(mapsLink(stop));
    li.append(dot, body);
    return li;
  }));
  $("picked").hidden = picked;
  $("delivered").hidden = !(picked && s.ngo);
  $("accepted-note").hidden = !picked;
  if (picked && s.ngo) $("accepted-note").textContent = fill(t.nowDeliver, { ngo: s.ngo.name });
}

// A maps pin at the synthetic point, never a name search (which could find a real business).
function mapsLink(stop) {
  const a = el("a", "maps-link");
  const [lat, lng] = stop.point;
  a.href = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
  a.target = "_blank";
  a.rel = "noopener";
  a.setAttribute("aria-label", `${state.t.accepted.maps}: ${stop.name}`);
  a.append(icon("pin"), document.createTextNode(state.t.accepted.maps));
  return a;
}

async function markPickedUp() {
  const job = state.job;
  if (!job) return;
  $("picked").disabled = true;
  try {
    await postJson(`/reports/${job.reportId}/picked-up?by=volunteer`);
    if (job.s.ngo) {
      job.picked = true;
      drawStops();
    } else {
      backToDuty(state.t.accepted.pickedThanks, "success");
    }
  } catch (err) {
    problem(err);
  } finally {
    $("picked").disabled = false;
  }
}

// Every failure says what to do next (common.js failureKey).
function problem(err) {
  notice(fill(state.t.notice[failureKey(err)], { what: err?.message }), "error");
}

// The NGO page then asks "Khana aa gaya?" and the NGO's answer marks it delivered.
async function markDelivered() {
  const job = state.job;
  if (!job) return;
  $("delivered").disabled = true;
  try {
    await postJson(`/reports/${job.reportId}/delivered?by=volunteer`);
    backToDuty(fill(state.t.accepted.deliveredThanks, { ngo: job.s.ngo.name }), "success");
  } catch (err) {
    problem(err);
  } finally {
    $("delivered").disabled = false;
  }
}

// ------------------------------------------------------------------ sound

function play(url) {
  if (!url) return;
  player.src = url;
  player.play().catch(() => { /* autoplay blocked: "Play again" works */ });
}

// Two short phone-style rings, generated here so no audio file is needed.
function ring() {
  if (!audioCtx) return Promise.resolve();
  const t0 = audioCtx.currentTime + 0.05;
  [0, 0.6].forEach((offset) => {
    const gain = audioCtx.createGain();
    gain.gain.setValueAtTime(0, t0 + offset);
    gain.gain.linearRampToValueAtTime(0.25, t0 + offset + 0.02);
    gain.gain.setValueAtTime(0.25, t0 + offset + 0.4);
    gain.gain.linearRampToValueAtTime(0, t0 + offset + 0.45);
    gain.connect(audioCtx.destination);
    [440, 480].forEach((hz) => {
      const osc = audioCtx.createOscillator();
      osc.frequency.value = hz;
      osc.connect(gain);
      osc.start(t0 + offset);
      osc.stop(t0 + offset + 0.46);
    });
  });
  return new Promise((resolve) => setTimeout(resolve, 1200));
}

// ------------------------------------------------------------------ notices and connection

function notice(text, kind = "attention", { brief = false } = {}) {
  clearTimeout(noticeTimer);
  $("notice").className = `callout callout--${kind}`;
  $("notice-icon").setAttribute("href", `${ICONS}#${kind === "error" ? "cross" : kind === "success" ? "check" : "clock"}`);
  $("notice-text").textContent = text;
  $("notice").hidden = false;
  if (brief) noticeTimer = setTimeout(hideNotice, NOTICE_MS);
}

function hideNotice() {
  clearTimeout(noticeTimer);
  $("notice").hidden = true;
}

function updateConn() {
  const s = !navigator.onLine ? "offline" : !state.onDuty ? null
    : state.socketState === "open" ? "live" : "reconnecting";
  $("conn").hidden = !s;  // off duty: nothing is connected, so nothing to show
  if (!s) return;
  $("conn").dataset.state = s;
  $("conn-word").textContent = state.t.conn[s];
  if (s === "offline") notice(state.t.notice.noNetwork, "error");
}

// ------------------------------------------------------------------ helpers

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `${ICONS}#${name}`);
  svg.append(use);
  return svg;
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
