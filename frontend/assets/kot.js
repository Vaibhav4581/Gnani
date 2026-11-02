// The KOT slip: a food report drawn as a kitchen order ticket (see DESIGN.md).
//
//   import { renderKot, setKotFields, setKotStatus } from "/assets/kot.js";
//   const slip = renderKot(report, { print: true, words });  // print: only the first ticket
//   list.append(slip);
//   await setKotFields(slip, { quantity: 30, unit: "plate" });  // changed lines write in, one by one
//   setKotStatus(slip, "ASSIGNED", { word: "John is on the way · 12 min" });
//   setKotNote(slip, "cooked_at", "What time was it cooked?");  // beside a line still missing
//   setKotSpeaking(slip, true);         // while the app's voice plays: the pill's icon moves
//   setKotRoute(slip, { stops: [...], at: 1 });                 // kitchen -> volunteer -> NGO
//
// `report` uses the API's names: id (or report_id), kitchen, dish, quantity, unit, cooked_at,
// deadline (ISO strings), veg (true / false / null), status (Report.status). A value not heard
// yet is a blank dashed slot, like an empty line on a paper ticket. `words` (optional) puts the
// slip's own words in the reader's language; see WORDS for the English defaults.

const ICONS = "/assets/icons.svg";
const SVG = "http://www.w3.org/2000/svg";
const TICK_MS = 30_000;
const FINISHED = ["DELIVERED", "PICKED_UP", "CANCELLED", "EXPIRED"];
const LINE_ORDER = ["food", "cooked_at", "deadline"];  // the order lines write in
const FOOD_FIELDS = ["quantity", "unit", "dish", "veg"];

// Report.status -> pill: tone (colour), icon, word. Colour alone never carries meaning.
export const STATUS = {
  RECORDED: { tone: "reported", icon: "flame", word: "Reported" },
  TRANSCRIBED: { tone: "reported", icon: "flame", word: "Reported" },
  EXTRACTED: { tone: "reported", icon: "flame", word: "Reported" },
  CONFIRMING: { tone: "reported", icon: "flame", word: "Checking details" },
  CONFIRMED: { tone: "checking", icon: "check", word: "Confirmed" },
  SAFETY_CHECK: { tone: "checking", icon: "check", word: "Safety check" },
  MATCHING: { tone: "finding", icon: "clock", word: "Finding volunteer" },
  OFFERED: { tone: "finding", icon: "phone", word: "Asking volunteer" },
  ASSIGNED: { tone: "on-way", icon: "bike", word: "On the way" },
  PICKED_UP: { tone: "on-way", icon: "bike", word: "Picked up" },
  DELIVERED: { tone: "delivered", icon: "check", word: "Delivered" },
  DECLINED: { tone: "stopped", icon: "cross", word: "Declined" },
  CANCELLED: { tone: "stopped", icon: "cross", word: "Cancelled" },
  EXPIRED: { tone: "stopped", icon: "clock", word: "Expired" },
};

// The slip's own words; pass `words` to renderKot to replace any of them.
export const WORDS = {
  labels: { food: "Food", cooked_at: "Cooked", deadline: "Pick up by" },
  status: Object.fromEntries(Object.entries(STATUS).map(([k, s]) => [k, s.word])),
  units: { plate: ["plate", "plates"], kg: ["kg", "kg"], litre: ["litre", "litres"], box: ["box", "boxes"] },
  left: (h, m) => (!h ? `${m} min left` : m ? `${h} h ${m} min left` : `${h} h left`),
  passed: "Pickup time passed",
  notHeard: "not heard yet",
  speaking: "Speaking",
  report: "Food report",
};

const timers = new WeakMap();  // slip -> countdown interval
const state = new WeakMap();   // slip -> { report, now, words }

export function ticketNumber(id) {
  return `#BHK-${String(id ?? 0).padStart(4, "0")}`;
}

export function icon(name, className = "icon") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `${ICONS}#${name}`);
  svg.append(use);
  return svg;
}

// `word` replaces the status word (e.g. "John is on the way · 12 min"); tone and icon stay.
// `table` is STATUS for reports, NEED_STATUS for needs.
export function statusPill(status, word = null, table = STATUS) {
  const s = table[status] || Object.values(table)[0];
  const pill = el("span", `pill pill--${s.tone}`);
  pill.append(icon(s.icon), document.createTextNode(word || s.word));
  return pill;
}

// lines: which lines to draw (default all: "food", "cooked_at", "deadline"); an offer leaves out
// the cooked time, which it doesn't carry.
export function renderKot(report, { print = false, now = () => new Date(), words = {},
                                    lines: shown = LINE_ORDER } = {}) {
  const w = { ...WORDS, ...words, labels: { ...WORDS.labels, ...words.labels },
              status: { ...WORDS.status, ...words.status }, units: { ...WORDS.units, ...words.units } };
  const slip = el("article", "kot");
  slip.dataset.status = report.status || "RECORDED";
  state.set(slip, { report: { ...report }, now, words: w });

  const paper = el("div", "kot-paper");
  const head = el("header", "kot-head");
  const meta = el("div", "kot-meta");  // number and status under the name, so neither squeezes it
  const number = el("span", "kot-number", ticketNumber(report.id ?? report.report_id));
  meta.append(number, pillFor(slip, slip.dataset.status));
  head.append(el("div", "kot-kitchen", report.kitchen || ""), meta);

  const lines = el("ul", "kot-lines");
  for (const field of LINE_ORDER.filter((f) => shown.includes(f))) {
    const line = el("li", field === "food" ? "kot-line kot-line--food" : "kot-line");
    line.dataset.field = field;
    line.append(el("span", field === "food" ? "visually-hidden" : "kot-label", w.labels[field]),
                el(field === "food" ? "div" : "span", "kot-value"));
    lines.append(line);
  }
  paper.append(head, lines);
  slip.append(paper);
  slip.setAttribute("aria-label", `${w.report} ${number.textContent}`);

  for (const field of LINE_ORDER) fillLine(slip, field);
  if (print) slip.classList.add("is-printing");
  startCountdown(slip);
  return slip;
}

export function setKotId(slip, id) {
  const number = ticketNumber(id);
  slip.querySelector(".kot-number").textContent = number;
  slip.setAttribute("aria-label", `${state.get(slip).words.report} ${number}`);
}

// Change one field and redraw only its line, "writing it in".
// field: quantity, unit, dish, veg, cooked_at, deadline or kitchen.
export function updateKotLine(slip, field, value, { animate = true } = {}) {
  state.get(slip).report[field] = value;
  if (field === "kitchen") {
    slip.querySelector(".kot-kitchen").textContent = value;
    return;
  }
  const valueEl = fillLine(slip, FOOD_FIELDS.includes(field) ? "food" : field);
  if (animate && valueEl) writeIn(valueEl);
}

// Apply a set of fields; every line that changed writes in, top to bottom, `stagger` ms apart.
// Resolves once the last line has started writing.
export async function setKotFields(slip, fields, { animate = true, stagger = 180 } = {}) {
  const { report } = state.get(slip);
  const changed = new Set();
  for (const [field, value] of Object.entries(fields)) {
    if (value === undefined || report[field] === value) continue;
    report[field] = value;
    if (FOOD_FIELDS.includes(field)) changed.add("food");
    else if (LINE_ORDER.includes(field)) changed.add(field);
  }
  if (fields.deadline && !timers.has(slip)) startCountdown(slip);
  let first = true;
  for (const line of LINE_ORDER.filter((l) => changed.has(l))) {
    if (!first && animate) await wait(stagger);
    first = false;
    const valueEl = fillLine(slip, line);
    if (animate && valueEl) writeIn(valueEl);
  }
}

export function setKotStatus(slip, status, { word = null } = {}) {
  slip.dataset.status = status;
  slip.querySelector('[data-role="status"]').replaceWith(pillFor(slip, status, word));
  markSpeaking(slip);
  if (FINISHED.includes(status)) stopCountdown(slip);
  else if (!timers.has(slip)) startCountdown(slip);
  else fillLine(slip, "deadline");
}

// A note beside a line, e.g. the follow-up question for a value still missing. null removes it.
export function setKotNote(slip, field, text) {
  const line = slip.querySelector(`[data-field="${field}"]`);
  line?.querySelector(".kot-note")?.remove();
  if (!line || !text) return;
  const note = el("p", "kot-note");
  note.append(icon("mic"), el("span", null, text));
  line.append(note);
}

export function clearKotNotes(slip) {
  slip.querySelectorAll(".kot-note").forEach((n) => n.remove());
}

// While the app's voice plays, the status pill's icon becomes three moving bars. The pill keeps
// its width, so the ticket head never reflows (no layout shift when the voice starts or stops).
export function setKotSpeaking(slip, on) {
  slip.classList.toggle("is-speaking", on);
  state.get(slip).speaking = on;
  markSpeaking(slip);
}

function markSpeaking(slip) {
  const pill = slip.querySelector('[data-role="status"]');
  if (!pill) return;
  const on = Boolean(state.get(slip).speaking);
  pill.querySelector(".speaking-bars")?.remove();
  pill.querySelector(".speaking-word")?.remove();
  pill.querySelector(".icon")?.toggleAttribute("hidden", on);
  if (!on) return;
  const bars = el("span", "speaking-bars");
  bars.setAttribute("aria-hidden", "true");
  bars.append(el("i"), el("i"), el("i"));
  pill.prepend(bars);
  pill.append(el("span", "visually-hidden speaking-word", ` · ${state.get(slip).words.speaking}`));
}

// The route along the bottom of the ticket. stops: [{ name, icon }], at: how many stops the food
// has reached (1 = still at the kitchen). The leg the food is on fills when `at` moves on.
export function setKotRoute(slip, { stops, at }) {
  let route = slip.querySelector(".route");
  if (!route) {
    route = el("ol", "route");
    slip.querySelector(".kot-paper").append(route);
  }
  route.replaceChildren();
  stops.forEach((stop, i) => {
    if (i) {
      const leg = el("li", "route-leg");
      leg.setAttribute("aria-hidden", "true");
      leg.style.setProperty("--fill", i < at ? "1" : "0");
      route.append(leg);
    }
    const li = el("li", `route-stop${i < at ? " is-done" : i === at ? " is-now" : ""}`);
    li.append(icon(stop.icon), el("span", "route-name", stop.name));
    route.append(li);
  });
  route.style.gridTemplateColumns = stops.map(() => "auto").join(" minmax(1.5rem, 1fr) ");
}

export function stopCountdown(slip) {
  clearInterval(timers.get(slip));
  timers.delete(slip);
  fillLine(slip, "deadline");
}

// ------------------------------------------------------------------ drawing

function pillFor(slip, status, word = null) {
  const pill = statusPill(status, word || state.get(slip).words.status[status]);
  pill.dataset.role = "status";
  return pill;
}

function fillLine(slip, field) {
  const valueEl = slip.querySelector(`[data-field="${field}"] .kot-value`);
  if (!valueEl) return null;
  const { report: r } = state.get(slip);
  valueEl.replaceChildren();
  if (field === "food") drawFood(valueEl, r, slip);
  else if (field === "cooked_at") setText(valueEl, clock(r.cooked_at), slip);
  else if (field === "deadline") drawDeadline(valueEl, r, slip);
  return valueEl;
}

function drawFood(valueEl, r, slip) {
  const qty = r.quantity != null ? `${fmt(r.quantity)} ${unitWord(slip, r.unit, r.quantity)}` : null;
  valueEl.append(qty ? el("span", "qty", qty) : slot(slip, "qty"));
  const dish = el("span", "kot-food");
  if (r.veg === true || r.veg === false) {
    const mark = icon(r.veg ? "veg" : "non-veg", "kot-mark");
    mark.removeAttribute("aria-hidden");
    mark.setAttribute("role", "img");
    mark.setAttribute("aria-label", r.veg ? "Veg" : "Non-veg");
    dish.append(mark);
  }
  dish.append(r.dish ? el("span", "kot-dish", r.dish) : slot(slip, "dish"));
  valueEl.append(dish);
}

function drawDeadline(valueEl, r, slip) {
  if (!r.deadline) return valueEl.append(blankDeadline(slip, !FINISHED.includes(slip.dataset.status)));
  const wrap = el("span", "kot-deadline");
  wrap.append(el("span", null, clock(r.deadline)));
  if (timers.has(slip)) {  // a live countdown only while the pickup is still open
    const { now, words } = state.get(slip);
    const left = countdown(new Date(r.deadline) - now(), words);
    const cd = el("span", `kot-countdown${left.urgent ? " is-urgent" : ""}`);
    cd.append(icon("clock"), document.createTextNode(` ${left.text}`));
    wrap.append(cd);
  }
  valueEl.append(wrap);
}

function startCountdown(slip) {
  if (!state.get(slip).report.deadline || FINISHED.includes(slip.dataset.status)) return;
  const tick = () => {
    if (!slip.isConnected && slip.dataset.mounted) return stopCountdown(slip);
    if (slip.isConnected) slip.dataset.mounted = "1";
    fillLine(slip, "deadline");
  };
  timers.set(slip, setInterval(tick, TICK_MS));
  tick();
}

// A deadline not heard yet: the blank line, plus (while a countdown will follow) an invisible
// countdown in the slip's own words, so the line is already as tall as it will be and the
// ticket doesn't grow when the time writes in.
function blankDeadline(slip, withCountdown) {
  const wrap = el("span", "kot-deadline");
  const line = el("span");  // a text line around the blank, as tall as the time it waits for
  line.append(slot(slip, "line"));
  wrap.append(line);
  if (withCountdown) {
    const ghost = el("span", "kot-countdown kot-ghost");
    ghost.setAttribute("aria-hidden", "true");
    ghost.append(icon("clock"), document.createTextNode(` ${state.get(slip).words.left(2, 30)}`));
    wrap.append(ghost);
  }
  return wrap;
}

function writeIn(valueEl) {
  valueEl.classList.remove("is-writing");
  void valueEl.offsetWidth;  // restart the animation when the same line changes twice
  valueEl.classList.add("is-writing");
  valueEl.addEventListener("animationend", () => valueEl.classList.remove("is-writing"), { once: true });
}

// ------------------------------------------------------------------ formatting

export function countdown(ms, words = WORDS) {
  if (ms <= 0) return { text: words.passed, urgent: true };
  const mins = Math.ceil(ms / 60_000);
  return { text: words.left(Math.floor(mins / 60), mins % 60), urgent: mins <= 30 };
}

// 12-hour like the spoken prompts ("raat 11 baje", "11 PM"), whatever the browser's locale.
export function clock(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true })
    .replace(/\s?(am|pm)$/i, (_, p) => ` ${p.toLowerCase()}`);
}

function unitWord(slip, unit, qty) {
  const [one, many] = state.get(slip).words.units[unit] || [unit || "", unit || ""];
  return Number(qty) === 1 ? one : many;
}

function fmt(n) {
  return Number.isInteger(Number(n)) ? String(Number(n)) : String(n);
}

function setText(valueEl, text, slip) {
  valueEl.append(text ? document.createTextNode(text) : slot(slip, "line"));
}

// A blank line to be written on: qty and dish slots match the size of what fills them.
function slot(slip, kind) {
  const blank = el("span", `kot-slot kot-slot--${kind}`);
  blank.append(el("span", "visually-hidden", state.get(slip).words.notHeard));
  return blank;
}

// ------------------------------------------------------------------ the need slip

// What a shelter asked for, drawn as the same ticket on leaf-soft paper:
//   const slip = renderNeedSlip(need, { words });   // need: need_id, ngo, people_count, needed_by,
//   await updateNeedSlip(slip, need);                //       veg_only, status (Need.status)
// Lines carry data-field (people_count, needed_by, veg_only), so setKotNote works on them too.
export const NEED_STATUS = {
  CONFIRMING: { tone: "reported", icon: "flame", word: "Checking details" },
  OPEN: { tone: "finding", icon: "clock", word: "Waiting for food" },
  MATCHED: { tone: "on-way", icon: "bike", word: "Food found" },
  DELIVERED: { tone: "delivered", icon: "check", word: "Delivered" },
  EXPIRED: { tone: "stopped", icon: "clock", word: "Expired" },
};

export const NEED_WORDS = {
  labels: { people_count: "People", needed_by: "Needed by", veg_only: "Food" },
  people: "{n} people",
  vegOnly: "Veg only",
  anyFood: "Any food",
  status: Object.fromEntries(Object.entries(NEED_STATUS).map(([k, s]) => [k, s.word])),
  number: "Request",
};
const NEED_LINES = ["people_count", "needed_by", "veg_only"];

export function renderNeedSlip(need, { print = false, now = () => new Date(), words = {} } = {}) {
  const w = { ...WORDS, ...NEED_WORDS, ...words, labels: { ...NEED_WORDS.labels, ...words.labels },
              status: { ...NEED_WORDS.status, ...words.status } };
  const slip = el("article", "kot kot--need");
  slip.dataset.status = need.status || "CONFIRMING";
  state.set(slip, { report: { ...need }, now, words: w, kind: "need" });
  const number = `#NEED-${String(need.need_id ?? 0).padStart(4, "0")}`;
  const paper = el("div", "kot-paper");
  const head = el("header", "kot-head");
  const meta = el("div", "kot-meta");
  meta.append(el("span", "kot-number", number), needPill(slip));
  head.append(el("div", "kot-kitchen", need.ngo || ""), meta);
  const lines = el("ul", "kot-lines");
  for (const field of NEED_LINES) {
    const line = el("li", field === "people_count" ? "kot-line kot-line--food" : "kot-line");
    line.dataset.field = field;
    line.append(el("span", field === "people_count" ? "visually-hidden" : "kot-label", w.labels[field]),
                el(field === "people_count" ? "div" : "span", "kot-value"));
    lines.append(line);
  }
  paper.append(head, lines);
  slip.append(paper);
  slip.setAttribute("aria-label", `${w.number} ${number}`);
  for (const field of NEED_LINES) fillNeedLine(slip, field);
  if (print) slip.classList.add("is-printing");
  const tick = () => (slip.isConnected || !slip.dataset.mounted ? fillNeedLine(slip, "needed_by")
    : clearInterval(timers.get(slip)));
  timers.set(slip, setInterval(() => { if (slip.isConnected) slip.dataset.mounted = "1"; tick(); }, TICK_MS));
  return slip;
}

// Apply a new reading of the need: changed lines write in, top to bottom; the pill follows status.
export async function updateNeedSlip(slip, need, { animate = true, stagger = 180 } = {}) {
  const { report } = state.get(slip);
  const changed = NEED_LINES.filter((f) => need[f] !== undefined && need[f] !== report[f]);
  Object.assign(report, need);
  if (need.status && need.status !== slip.dataset.status) {
    slip.dataset.status = need.status;
    slip.querySelector('[data-role="status"]').replaceWith(needPill(slip));
    fillNeedLine(slip, "needed_by");
  }
  let first = true;
  for (const field of changed) {
    if (!first && animate) await wait(stagger);
    first = false;
    const valueEl = fillNeedLine(slip, field);
    if (animate && valueEl) writeIn(valueEl);
  }
}

function needPill(slip) {
  const { words } = state.get(slip);
  const pill = statusPill(slip.dataset.status, words.status[slip.dataset.status], NEED_STATUS);
  pill.dataset.role = "status";
  return pill;
}

function fillNeedLine(slip, field) {
  const valueEl = slip.querySelector(`[data-field="${field}"] .kot-value`);
  if (!valueEl) return null;
  const { report: n, words, now } = state.get(slip);
  valueEl.replaceChildren();
  if (field === "people_count") {
    valueEl.append(n.people_count != null
      ? el("span", "qty", words.people.replace("{n}", n.people_count)) : slot(slip, "qty"));
  } else if (field === "needed_by") {
    if (!n.needed_by) {
      valueEl.append(blankDeadline(slip, ["CONFIRMING", "OPEN", "MATCHED"].includes(slip.dataset.status)));
      return valueEl;
    }
    const wrap = el("span", "kot-deadline");
    wrap.append(el("span", null, clock(n.needed_by)));
    if (["CONFIRMING", "OPEN", "MATCHED"].includes(slip.dataset.status)) {
      const left = countdown(new Date(n.needed_by) - now(), words);
      const cd = el("span", `kot-countdown${left.urgent ? " is-urgent" : ""}`);
      cd.append(icon("clock"), document.createTextNode(` ${left.text}`));
      wrap.append(cd);
    }
    valueEl.append(wrap);
  } else if (field === "veg_only") {
    const rule = el("span", "kot-food");
    if (n.veg_only) {
      const mark = icon("veg", "kot-mark");
      rule.append(mark);
    }
    rule.append(el("span", null, n.veg_only ? words.vegOnly : words.anyFood));
    valueEl.append(rule);
  }
  return valueEl;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
