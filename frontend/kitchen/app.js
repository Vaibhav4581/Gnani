// Kitchen screen: tap to talk (it stops when you do) -> the report writes itself onto a KOT slip
// -> confirm by voice or button -> two safety questions -> live status on the slip, with a route
// line. After each yes/no question the mic opens by itself. After that the same mic asks
// "volunteer kab aayega?" or cancels (asked back first). One thing at a time.
import { $, failureKey, getJson, liveSocket, postJson, putJson, rotateExamples, store,
         stored } from "/shared/common.js";
import { LISTEN, Microphone, bindTapToTalk, extensionFor } from "/assets/recorder.js";
import { clearKotNotes, clock, renderKot, renderMiniKot, renderSkeletonMini, setKotFields, setKotId,
         setKotNote, setKotRoute, setKotSpeaking, setKotStatus } from "/assets/kot.js";
import { LANG_ORDER, STRINGS, fill, strings } from "./strings.js";

const ICONS = "/assets/icons.svg";
const KITCHEN_KEY = "bhk.kitchenId";
const langKey = (kitchenId) => `bhk.language.${kitchenId}`;
const ANSWERING = ["CONFIRMING", "SAFETY_CHECK"];  // the next thing said answers the app
const MISSING_LINE = { dish: "food", quantity: "food", unit: "food", cooked_time: "cooked_at" };
const BIG_TEXT_KEY = "bhk.bigText";
const TIPS_KEY = "bhk.tips.kitchen";
const TIP_ORDER = ["mic", "slip", "answers"];  // first-time tips, each shown when its target appears
const ONE_SCREEN = matchMedia("(min-width: 900px) and (min-height: 600px)");  // as kitchen.css
const NOTICE_KIND = { firstUse: "attention", blocked: "error", noNetwork: "error", server: "error",
                      unreachable: "error", serverDown: "error",
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
let listenTimer = null;  // opens the mic just after a yes/no question has been spoken
let stopExamples = () => {};

// Bigger text before anything draws, so the page doesn't jump.
document.documentElement.classList.toggle("big-text", stored(BIG_TEXT_KEY) === "1");

// ------------------------------------------------------------------ start

async function init() {
  try {
    state.mock = (await getJson("/config")).mock;
  } catch { /* the first request will show what went wrong */ }
  $("mock-panel").hidden = !state.mock;
  $("settings").open = state.mock;  // the demo types instead of speaking

  const mic = new Microphone({ select: $("mic"), row: $("mic-row") });
  talk = bindTapToTalk($("talk"), {
    mic,
    onLevel: (v) => $("talk").style.setProperty("--level", v.toFixed(2)),
    allowSilence: () => state.mock,
    onStart: recordingStarted,
    onStop: recordingStopped,
    onBlob: (blob) => send({ blob }),
    onProblem: (message, code) => showNotice(code || "server", { what: message }),
  });

  const on = (id, fn) => $(id).addEventListener("click", fn);
  on("text-size", toggleBigText);
  on("tip-ok", () => { tipDone($("tip").dataset.step); offerTips(); });
  placeTalk();
  ONE_SCREEN.addEventListener("change", placeTalk);
  ONE_SCREEN.addEventListener("change", offerTips);  // the mic tip moves between column and counter
  ONE_SCREEN.addEventListener("change", fitMic);
  const fit = new ResizeObserver(fitMic);  // a longer example, Bigger text, a shorter window
  [$("talk").closest(".mic-col"), $("mic-hint").parentElement, $("notice"), $("tip"), $("conversation")]
    .forEach((node) => fit.observe(node));
  on("tip-hide", () => { store(TIPS_KEY, "off"); $("tip").hidden = true; });
  on("confirm-yes", () => { tipDone("answers"); send({ answer: "yes" }); });
  on("confirm-no", () => { tipDone("answers"); send({ answer: "no" }); });
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
  // "Tap the button and say what's left, for example:" in this kitchen's language
  stopExamples();
  stopExamples = rotateExamples($("examples"), k.examples || [], { lang: k.language.split("-")[0] });
  $("example-lead").textContent = state.t.example;
  $("text-size-label").textContent = ` ${state.t.bigger}`;
  $("text-size").title = state.t.bigger;
  $("text-size").setAttribute("aria-pressed", String(document.documentElement.classList.contains("big-text")));
  offerTips();
}

function toggleBigText() {
  const on = !document.documentElement.classList.contains("big-text");
  document.documentElement.classList.toggle("big-text", on);
  $("text-size").setAttribute("aria-pressed", String(on));
  store(BIG_TEXT_KEY, on ? "1" : "0");
}

// ------------------------------------------------------------------ first-time tips

// Three short tips, each the first time its target shows: the mic, the slip, the Haan/Nahi
// buttons. "Got it" moves on, "Hide tips" ends them; remembered on this device.
function tipsSeen() {
  const v = stored(TIPS_KEY);
  return v === "off" ? TIP_ORDER.length : Number(v) || 0;
}

function tipDone(step) {
  const i = TIP_ORDER.indexOf(step);
  if (i < 0 || i < tipsSeen() - 1) return;
  store(TIPS_KEY, String(Math.max(tipsSeen(), i + 1)));
  if ($("tip").dataset.step && TIP_ORDER.indexOf($("tip").dataset.step) <= i) $("tip").hidden = true;
}

// On a laptop the conversation (what the app said, the answers, the questions) stands on the
// counter under the mic and the ticket has its column to itself; on a phone it all reads in one
// column, around the ticket.
const TALK = ["say", "confirm-actions", "safety", "cancel", "expired-note", "after-actions"];

function placeTalk() {
  if (ONE_SCREEN.matches) $("conversation").append(...TALK.map($));
  else {
    $("slip-holder").before($("say"));
    $("slip-holder").after(...TALK.slice(1).map($));
  }
}

// On a laptop the counter never scrolls: the mic shrinks by whatever its words below overflow
// (never under 9rem, where its label would no longer fit the circle, or 6rem with a ticket open,
// when the label stands beside it). Otherwise kitchen.css sizes it.
function fitMic() {
  const mic = $("talk");
  const col = mic.closest(".mic-col");
  mic.style.removeProperty("width");
  if (!ONE_SCREEN.matches) return;
  const over = col.scrollHeight - col.clientHeight;
  if (over <= 0) return;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const min = ($("stage").classList.contains("has-slip") ? 6 : 9) * rem;
  const width = mic.getBoundingClientRect().width;
  mic.style.width = `${Math.min(width, Math.max(min, width - over - 2))}px`;
}

// Show the next tip if its target is on screen now.
function offerTips() {
  const r = state.report;
  if (r && TIP_ORDER[tipsSeen()] === "mic") tipDone("mic");  // reported already (mic, button or typed)
  const step = TIP_ORDER[tipsSeen()];
  const confirming = r?.status === "CONFIRMING" && !r.missing.length;
  const target = { mic: !r && $("talk").closest(".mic-zone").querySelector(".mic-side"),
                   slip: confirming && $("slip-holder"),
                   answers: confirming && $("confirm-actions") }[step];
  const tip = $("tip");
  if (!target) {
    tip.hidden = true;
    return;
  }
  const t = state.t.tips;
  tip.dataset.step = step;
  $("tip-step").textContent = fill(t.step, { n: TIP_ORDER.indexOf(step) + 1 });
  $("tip-text").textContent = t[step];
  $("tip-ok").textContent = t.ok;
  $("tip-hide").textContent = t.hide;
  // On a laptop every tip stands in the ticket column, which has room: the mic's and the
  // answers' point back across at the counter, the ticket's points up at it (kitchen.css).
  const wide = ONE_SCREEN.matches;
  if (wide && step === "mic") $("slip-holder").before(tip);
  else if (wide) $("slip-holder").after(tip);
  else target.after(tip);
  tip.classList.toggle("tip--side", wide && step !== "slip");
  tip.hidden = false;
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
  $("rail-empty").textContent = t.rail.empty;
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

// Every failure says what to do next (common.js failureKey).
function problem(err) {
  if (err?.status === 422 && /speech/i.test(err.message)) return showNotice("silent");
  showNotice(failureKey(err), { what: err?.message });
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
  loadRail();
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
  const shown = data.dish_shown ? { ...data.fields, dish: data.dish_shown } : data.fields;  // in the read-back's script
  await setKotFields(slip, shown, { stagger: first ? 220 : 160 });
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
  loadRail();
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
  offerTips();
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
    const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    requestAnimationFrame(() => {
      // On a laptop the column scrolls, not the page (if it must): from the top if everything
      // above this panel fits, so nothing above the answers is cut off.
      const col = ONE_SCREEN.matches && panel.closest(".slip-col, .mic-col");
      const fits = col && panel.getBoundingClientRect().bottom - col.getBoundingClientRect().top
                          + col.scrollTop <= col.clientHeight;
      if (fits) col.scrollTo({ top: 0, behavior });
      else panel.scrollIntoView({ block: "nearest", behavior });
    });
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

// ------------------------------------------------------------------ the ticket rail

// Today's reports from this kitchen, newest first, as small tickets on the rail; its heading
// says the day so far ("Today: 3 reports, 140 meals shared").
async function loadRail() {
  const k = state.kitchen;
  if (!k) return;
  if (!$("rail").children.length) {  // first load: two blank tickets breathing, not a spinner
    $("rail-empty").hidden = true;
    $("rail").setAttribute("aria-busy", "true");
    $("rail").replaceChildren(...[0, 1].map(() => {
      const li = document.createElement("li");
      li.append(renderSkeletonMini());
      return li;
    }));
  }
  let today = [];
  let meals = null;
  try {
    [today, meals] = await Promise.all([getJson(`/kitchens/${k.id}/today`),
      getJson(`/impact?kitchen_id=${k.id}`).then((i) => i.today.meals).catch(() => null)]);
  } catch {
    $("rail").replaceChildren();
    $("rail").removeAttribute("aria-busy");
    $("rail-h").textContent = state.t.rail.empty;
    return;  // the rail is a record; the page works without it
  }
  if (state.kitchen !== k) return;
  const t = state.t;
  const m = meals ? `${meals.estimated ? "≈" : ""}${meals.total}` : "0";
  $("rail-h").textContent = !today.length ? t.rail.empty  // one line: what will hang here
    : fill(today.length === 1 ? t.today.one : t.today.many, { n: today.length, m });
  $("rail").removeAttribute("aria-busy");
  $("rail-empty").hidden = true;
  $("rail").replaceChildren(...today.map((r) => {
    const li = el("li");
    li.append(renderMiniKot(r, { words: t.kot, word: railWord(r.status) }));
    return li;
  }));
}

function railWord(status) {
  const s = state.t.status;
  if (status === "OFFERED") return s.MATCHING;
  if (status === "ASSIGNED") return state.t.rail.onWay;
  return s[status] || null;
}

// ------------------------------------------------------------------ last report

async function loadLastReport() {
  const k = state.kitchen;
  if (!k) return;
  loadRail();
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
  talk?.cancel();  // never record while the app speaks: it would hear itself
  clearTimeout(listenTimer);
  state.audioUrl = url;
  state.audio?.pause();
  const audio = new Audio(url);
  state.audio = audio;
  audio.addEventListener("playing", () => setSpeaking(true));
  for (const ev of ["ended", "pause", "error"]) audio.addEventListener(ev, () => setSpeaking(false));
  audio.addEventListener("ended", () => {
    listenTimer = setTimeout(() => {
      if (state.audio === audio && !state.busy && !state.speaking && askedYesNo()) talk?.listen();
    }, LISTEN.AFTER_VOICE_MS);
  });
  audio.play().catch(() => setSpeaking(false));  // autoplay blocked: the replay button stays
}

// The app has just asked a yes/no question: the read-back ("…Sahi hai?", nothing missing),
// a safety question, or "cancel karein?". A follow-up like "kitne baje bana tha?" waits for a tap.
function askedYesNo() {
  const r = state.report;
  if (!r) return false;
  if (state.cancelAsked || r.status === "SAFETY_CHECK") return true;
  return r.status === "CONFIRMING" && !r.missing.length;
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
  const idle = mode === "report" && !state.busy && !state.speaking && !talk?.isRecording();
  $("example-box").hidden = !idle;  // the examples say it better than the hint, while idle
  $("mic-hint").textContent = state.busy || state.speaking || idle ? "" : mode === "ask" ? t.hint.ask : "";
}

// mode: "tap" (they tapped) or "auto" (the mic opened after a question: "Sun rahe hain…").
function recordingStarted(mode) {
  tipDone("mic");
  $("tip").hidden = true;
  $("talk").classList.add("is-recording");
  $("talk-icon").setAttribute("href", `${ICONS}#stop`);
  const word = mode === "auto" ? state.t.mic.listening : state.t.mic.recording;
  $("talk-label").textContent = word;
  $("mic-caption").textContent = word;
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
