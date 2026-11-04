// Coordinator dashboard: a route board. Each report is a compact KOT slip in one of four lanes
// (Reported -> Finding a volunteer -> On the way -> Delivered); when its state changes the slip
// slides to its new lane (FLIP, 300 ms, off under reduced motion). Clicking a slip opens its full
// timeline beside the board. Below: voice pipeline latency, open needs and a schematic map.
// Everything stays live over /ws/dashboard (changed cards, needs, impact, who is on duty).
import { $, failureKey, getJson, liveSocket, postJson, store, stored } from "/shared/common.js";
import { NEED_STATUS, clock, icon, renderKot, setKotFields, setKotStatus, statusPill,
         ticketNumber } from "/assets/kot.js";
import { drawMap, svgEl } from "/assets/map.js";

const LANES = ["reported", "finding", "on_way", "delivered"];
const UNITS = { plate: "plates", kg: "kg", litre: "litres", box: "boxes" };
const PIPELINE = [["stt", "Speech to text"], ["extract", "Understanding"], ["tts", "Text to speech"]];
const STEP_ICON = { start: "flame", speech: "mic", voice: "speaker", info: "check", good: "check",
                    offer: "phone", warn: "cross", muted: "clock" };
const MOVE_MS = 300;
const LANE_NAMES = { reported: "Reported", finding: "Finding a volunteer", on_way: "On the way",
                     delivered: "Delivered", closed: "Closed" };

const state = {
  cards: new Map(),   // id -> card from the server
  nodes: new Map(),   // id -> <li> holding its slip
  openId: null,
  onDuty: [],
  places: null,
  impact: null,
  loaded: false,      // after the first board load, new slips print in
  share: null,
  socket: "reconnecting",
};
const player = new Audio();
let playing = null;  // the play button whose clip is playing

function init() {
  getJson("/config").then((cfg) => ($("phone-mode").hidden = !cfg.telephony)).catch(() => {});
  $("reset").addEventListener("click", resetDemo);
  $("explain").addEventListener("click", () => toggleExplain());
  toggleExplain(stored("bhk.explain") !== "off");
  new ResizeObserver(() => fitLanes()).observe($("board"));
  const side = new ResizeObserver(() => fitSide());  // new needs, timings, a resized window
  document.querySelectorAll(".below, .below .panel").forEach((node) => side.observe(node));
  ONE_SCREEN.addEventListener("change", fitLanes);
  // map <-> board: a dot's slips light up, and a slip's dots
  $("map").addEventListener("pointerover", (e) => linkFromDot(e.target));
  $("map").addEventListener("focusin", (e) => linkFromDot(e.target));
  $("map").addEventListener("pointerout", unlink);
  $("map").addEventListener("focusout", unlink);
  for (const lane of [...LANES, "closed"]) {
    const list = $(`lane-${lane}`);
    list.addEventListener("pointerover", (e) => linkFromSlip(e.target));
    list.addEventListener("focusin", (e) => linkFromSlip(e.target));
    list.addEventListener("pointerout", unlink);
    list.addEventListener("focusout", unlink);
  }
  $("d-close").addEventListener("click", closeDetail);
  $("d-pickup").addEventListener("click", () => markPickedUp(state.openId));
  $("d-share").addEventListener("click", () => openShare(state.cards.get(state.openId)));
  $("s-close").addEventListener("click", () => $("share").close());
  $("s-share").addEventListener("click", shareCard);
  document.querySelectorAll(".share-size .seg-btn").forEach((b) =>
    b.addEventListener("click", () => showCard(b.dataset.format)));
  $("s-img").addEventListener("error", () => ($("s-error").hidden = false));
  $("s-img").addEventListener("load", () => ($("s-error").hidden = true));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.openId && !$("share").open) closeDetail();
  });
  player.addEventListener("ended", stopClip);
  player.addEventListener("error", stopClip);
  window.addEventListener("online", showConn);
  window.addEventListener("offline", showConn);
  liveSocket("/ws/dashboard", {
    onMessage,
    onState: (s) => {
      state.socket = s;
      showConn();
      if (s === "open") loadBoard();  // catch up on anything missed while away
    },
  });
}

// ---------------------------------------------------------------- data

async function loadBoard() {
  let board;
  try {
    board = await getJson("/dashboard/board");
  } catch (err) {
    document.body.classList.remove("is-loading");
    return showProblem("load", err);
  }
  $("problem").hidden = true;
  state.cards = new Map(board.cards.map((c) => [c.id, c]));
  state.onDuty = board.on_duty || [];
  state.places = board.map;
  state.impact = board.impact;
  renderBoard();
  renderPipeline(board.stats);
  renderNeeds(board.needs);
  renderStrip();
  renderMap();
  state.loaded = true;
  document.body.classList.remove("is-loading");  // first board drawn: show it (design.css)
  if (state.openId && !state.cards.has(state.openId)) closeDetail();
}

function onMessage(msg) {
  if (msg.type === "reset") {
    closeDetail();
    state.nodes.forEach((li) => li.remove());
    state.nodes.clear();
    state.loaded = false;
    loadBoard();
    return;
  }
  if (msg.type === "duty") {
    state.onDuty = msg.on_duty;
    renderStrip();
    renderMap();
    return;
  }
  if (msg.type !== "update") return;
  msg.cards.forEach((c) => state.cards.set(c.id, c));
  renderBoard();
  renderPipeline(msg.stats);
  if (msg.needs) renderNeeds(msg.needs);
  if (msg.impact) state.impact = msg.impact;
  renderStrip();
  renderMap();
  if (state.openId && msg.cards.some((c) => c.id === state.openId)) loadDetail(state.openId);
}

async function markPickedUp(id) {
  if (!id) return;
  try {
    await postJson(`/reports/${id}/picked-up?by=dashboard`);
    $("problem").hidden = true;
  } catch (err) {
    showProblem("pickup", err);
  }
}

async function resetDemo() {
  if (!confirm("Reset the demo? This deletes every report, offer, need and event, and restores the demo kitchens, volunteers and NGOs.")) return;
  try {
    await postJson("/admin/seed?confirm=true");
    $("problem").hidden = true;
  } catch (err) {
    showProblem("reset", err);
  }
}

// Every failure says what happened and what to do next, on the page (never an alert box).
const FAILED = {
  load: ["Couldn't load the board", "It tries again by itself when the connection comes back."],
  reset: ["Couldn't reset the demo", "Then press Reset demo again."],
  pickup: ["Couldn't mark it picked up", "Then press Mark picked up again."],
};
const WHY = {
  noNetwork: "this computer is offline. Check the Wi-Fi.",
  unreachable: "can't reach the server. Check that it's running.",
  serverDown: "the server had a problem. Wait a moment.",
};

function showProblem(action, err) {
  const key = failureKey(err);
  const [what, next] = FAILED[action];
  $("problem-text").textContent = `${what}: ${WHY[key] || `${err.message}.`} ${next}`;
  $("problem").hidden = false;
}

// "What am I looking at?": one-line notes over the impact strip and under each lane's shelf.
// On for a first visit (a judge seeing it cold) until someone turns it off; remembered.
function toggleExplain(force) {
  const on = typeof force === "boolean" ? force : $("explain").getAttribute("aria-pressed") !== "true";
  if (typeof force !== "boolean") store("bhk.explain", on ? "on" : "off");
  $("explain").setAttribute("aria-pressed", String(on));
  document.querySelectorAll(".explain").forEach((p) => (p.hidden = !on));
  fitLanes();
}

function showConn() {
  const s = !navigator.onLine ? "offline" : state.socket === "open" ? "live" : "reconnecting";
  $("conn").dataset.state = s;
  $("conn-word").textContent = { live: "Live", reconnecting: "Reconnecting…", offline: "Offline" }[s];
}

// ---------------------------------------------------------------- the route board

function renderBoard() {
  const before = new Map();
  state.nodes.forEach((li, id) => li.isConnected && before.set(id, li.getBoundingClientRect()));

  const sorted = [...state.cards.values()].sort((a, b) => b.id - a.id);
  const moved = [];
  for (const c of sorted) {
    const li = state.nodes.get(c.id);
    if (state.loaded && (!li || li.dataset.lane !== laneOf(c))) moved.push(c);
    if (li) updateSlip(li.firstChild, c);
    else state.nodes.set(c.id, slipItem(c));
  }
  for (const lane of [...LANES, "closed"]) {
    const items = sorted.filter((c) => laneOf(c) === lane).map((c) => state.nodes.get(c.id));
    $(`n-${lane}`).textContent = items.length;
    $(`lane-${lane}`).replaceChildren(...(items.length || lane === "closed" ? items
      : [emptyLane(lane)]));
  }
  $("closed").hidden = !sorted.some((c) => laneOf(c) === "closed");
  state.nodes.forEach((li, id) => (li.dataset.lane = laneOf(state.cards.get(id))));
  // Screen readers hear each slip that arrives or moves lane, in a word: "#BHK-0003, On the way: ..."
  if (moved.length) $("announce").textContent = moved.map((c) =>
    `${ticketNumber(c.id)}, ${LANE_NAMES[laneOf(c)]}: ${c.badge}`).join(". ");
  fitLanes();
  if (!reducedMotion()) slide(before);
}

// On a laptop the board is one screen and a lane never scrolls: when it runs out of room its
// oldest slips fold to their heading (kitchen, number, status), oldest first, and if even that
// is too tall the oldest step behind "+N more", which opens the lane in full (dashboard.css).
const ONE_SCREEN = matchMedia("(min-width: 1200px) and (min-height: 600px)");  // as dashboard.css

function fitLanes() {
  fitSide();
  for (const lane of LANES) {
    const list = $(`lane-${lane}`);
    const items = [...list.querySelectorAll(":scope > .slip-item")];
    list.querySelector(".lane-more")?.remove();
    items.forEach((li) => { li.classList.remove("is-folded"); li.hidden = false; });
    if (!ONE_SCREEN.matches || list.classList.contains("is-open")) {
      if (list.classList.contains("is-open")) list.append(moreButton(list, 0));
      continue;
    }
    const over = () => list.scrollHeight > list.clientHeight + 1;
    for (let i = items.length - 1; i >= 0 && over(); i--) items[i].classList.add("is-folded");
    if (!over()) continue;
    const more = moreButton(list, 0);
    list.append(more);
    let hidden = 0;
    for (let i = items.length - 1; i >= 1 && over(); i--) {
      items[i].hidden = true;
      more.querySelector("button").textContent = `+${++hidden} more`;
    }
    if (!hidden) more.remove();
  }
}

// The side column fits the same way: the map gives up whatever height the needs and the voice
// timings under it need (never below 6rem).
function fitSide() {
  const map = $("map");
  map.style.removeProperty("max-height");
  const side = map.closest(".below");
  const over = side.scrollHeight - side.clientHeight;
  if (!ONE_SCREEN.matches || over <= 0) return;
  const min = 6 * parseFloat(getComputedStyle(document.documentElement).fontSize);
  map.style.maxHeight = `${Math.max(min, map.getBoundingClientRect().height - over - 2)}px`;
}

function moreButton(list, n) {
  const li = el("li", "lane-more");
  const btn = el("button", "quiet-btn", n ? `+${n} more` : "Show less");
  btn.type = "button";
  btn.addEventListener("click", () => {
    list.classList.toggle("is-open");
    fitLanes();
  });
  li.append(btn);
  return li;
}

// An empty lane: a dashed slip outline (torn bottom edge) saying what arrives here.
const LANE_EMPTY = {
  reported: "New reports arrive here when a kitchen speaks.",
  finding: "Confirmed food waits here while volunteers are asked.",
  on_way: "Food moves here when a volunteer says yes.",
  delivered: "Finished rescues land here.",
};

function emptyLane(lane) {
  const li = el("li", "lane-empty");
  const outline = svgEl("svg", { viewBox: "0 0 200 120", preserveAspectRatio: "none", "aria-hidden": "true" });
  const teeth = Array.from({ length: 10 }, (_, i) => `L${190 - i * 20} 119 L${180 - i * 20} 113`).join(" ");
  outline.append(svgEl("path", { d: `M1 1 H199 V113 ${teeth} Z` }));  // right to left along the tear
  li.append(outline, el("p", null, LANE_EMPTY[lane] || ""));
  return li;
}

// FLIP: each slip starts where it was and glides to where it is now.
function slide(before) {
  state.nodes.forEach((li, id) => {
    const from = before.get(id);
    if (!from || !li.isConnected) return;
    const to = li.getBoundingClientRect();
    const dx = from.left - to.left;
    const dy = from.top - to.top;
    if (!to.width || (Math.abs(dx) < 1 && Math.abs(dy) < 1)) return;
    li.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
               { duration: MOVE_MS, easing: "cubic-bezier(.2, .7, .2, 1)" });
  });
}

function laneOf(c) {
  return c.lane || "reported";
}

function slipItem(c) {
  const slip = renderKot(c, { lines: ["food", "deadline"], print: state.loaded });
  slip.classList.add("kot--compact");
  slip.dataset.id = c.id;
  slip.querySelector(".kot-paper").append(el("div", "slip-extra"));
  const open = el("button", "slip-open");
  open.type = "button";
  open.append(el("span", "visually-hidden", `Open ${ticketNumber(c.id)}, ${c.kitchen}`));
  open.addEventListener("click", () => openDetail(c.id));
  open.dataset.id = c.id;
  slip.append(open);
  setKotStatus(slip, pillStatus(c), { word: c.badge });
  drawExtras(slip, c);
  const li = el("li", "slip-item");
  li.append(slip);
  return li;
}

function updateSlip(slip, c) {
  setKotFields(slip, { quantity: c.quantity, unit: c.unit, dish: c.dish, veg: c.veg,
                       deadline: c.deadline });
  setKotStatus(slip, pillStatus(c), { word: c.badge });
  drawExtras(slip, c);
}

// A pickup-only rescue is finished once picked up: it gets the delivered pill.
function pillStatus(c) {
  return laneOf(c) === "delivered" ? "DELIVERED" : c.status;
}

// Who carries it where, and a mirchi mark for everyone who said no.
function drawExtras(slip, c) {
  slip.classList.toggle("is-selected", c.id === state.openId);
  const extra = slip.querySelector(".slip-extra");
  extra.replaceChildren();
  const vol = c.chain.volunteer;
  const lane = laneOf(c);
  if (lane !== "reported" && lane !== "closed" && (vol || c.ngo || lane !== "finding")) {
    const to = el("p", "slip-to");
    if (vol) to.append(icon("bike"), el("span", null, first(vol)));
    to.append(vol ? el("span", null, "→") : "", icon("people"),
              el("span", null, !c.ngo ? "Pickup only, no shelter"
                : c.drop_off ? `Drop-off: ${short(c.ngo)} (no specific request open)` : short(c.ngo)));
    extra.append(to);
  }
  if (c.declined?.length) {
    const nos = el("p", "slip-nos");
    for (const d of c.declined) {
      const mark = el("span", "no-mark");
      mark.append(icon(d.reason === "no" ? "cross" : "clock"),
                  el("span", null, `${first(d.volunteer)} ${d.reason === "no" ? "said no" : "didn't answer"}`));
      nos.append(mark);
    }
    extra.append(nos);
  }
}

// ---------------------------------------------------------------- the detail panel

function openDetail(id) {
  state.openId = id;
  $("detail").hidden = false;
  $("main").classList.add("has-detail");
  markSelected();
  renderMap();
  loadDetail(id);
}

function closeDetail() {
  delete $("detail").dataset.shown;  // ids restart after a demo reset
  if (!state.openId && $("detail").hidden) return;
  const id = state.openId;
  state.openId = null;
  $("detail").hidden = true;
  $("main").classList.remove("has-detail");
  stopClip();
  player.pause();
  markSelected();
  renderMap();
  state.nodes.get(id)?.querySelector(".slip-open")?.focus({ preventScroll: true });
}

function markSelected() {
  state.nodes.forEach((li, id) => li.firstChild.classList.toggle("is-selected", id === state.openId));
}

async function loadDetail(id) {
  const fresh = $("detail").dataset.shown !== String(id);
  if (fresh) {  // a different slip: its ticket, blank and breathing, until the timeline arrives
    const blank = renderKot({ status: "RECORDED" }, { lines: ["food", "deadline"] });
    blank.classList.add("is-skeleton");
    $("d-skeleton").replaceChildren(blank);
    $("d-skeleton").hidden = false;
    $("d-number").textContent = ticketNumber(id);
    $("d-title").textContent = state.cards.get(id)?.kitchen || "";
    $("detail").classList.add("is-loading-detail");
    $("detail").setAttribute("aria-busy", "true");
  }
  let t;
  try {
    t = await getJson(`/dashboard/reports/${id}`);
  } catch (err) {
    if (state.openId === id) {
      $("d-skeleton").hidden = true;
      $("detail").removeAttribute("aria-busy");
      showProblem("load", err);
    }
    return;
  }
  if (state.openId !== id || !t.card) return;
  $("detail").dataset.shown = String(id);
  $("d-skeleton").hidden = true;
  $("detail").classList.remove("is-loading-detail");
  $("detail").removeAttribute("aria-busy");
  const c = t.card;
  state.cards.set(c.id, { ...state.cards.get(c.id), ...c });
  $("d-number").replaceChildren(`${ticketNumber(c.id)} · `, el("span", "lang-name", c.native_name));
  $("d-title").textContent = c.kitchen;

  const status = $("d-status");
  status.replaceChildren(statusPill(pillStatus(c), c.badge));
  if (c.deadline) status.append(el("span", "text-muted text-small", `pick up by ${clock(c.deadline)}`));

  const heard = $("d-heard");
  heard.lang = c.language || "en-IN";
  heard.classList.toggle("is-empty", !t.transcript);
  heard.textContent = t.transcript ? `“${t.transcript}”` : "Nothing heard yet";

  $("d-fields").replaceChildren(...facts(t).flatMap(([k, v]) => [el("dt", null, k), v]));
  $("d-tried").replaceChildren(...(t.tried.length ? t.tried.map(triedRow)
    : [el("li", "text-muted", "Nobody asked yet")]));
  $("d-steps").replaceChildren(...t.entries.map(stepRow));

  $("d-pickup").hidden = c.status !== "ASSIGNED";
  $("d-share").hidden = laneOf(c) !== "delivered";
}

function facts(t) {
  const f = t.fields;
  const c = t.card;
  const n = t.need;
  const yesNo = (v, yes, no) => {
    if (v == null) return el("dd", "text-muted", "not asked yet");
    const dd = el("dd", v ? null : "is-no");
    dd.append(icon(v ? "check" : "cross"), ` ${v ? yes : no}`);
    return dd;
  };
  const food = f.quantity != null || f.dish
    ? [f.quantity != null ? `${num(f.quantity)} ${UNITS[f.unit] || f.unit || ""}` : null, f.dish]
        .filter(Boolean).join(" · ")
    : null;
  return [
    ["Food", el("dd", food ? null : "text-muted", food || "not heard yet")],
    ["Veg", yesNo(f.veg, "veg", "non-veg")],
    ["Covered", yesNo(c.covered, "covered, clean vessel", "not covered yet")],
    ["Cooked", el("dd", null, clock(f.cooked_at) || "–")],
    ["Pick up by", el("dd", null, clock(f.deadline) || "–")],
    ["Location", el("dd", null, f.location || "the kitchen's address")],
    ["Deliver to", el("dd", null, n
      ? `${n.ngo} · ${n.people_count} people · by ${clock(n.needed_by)}${n.veg_only ? " · veg only" : ""}`
      : t.drop_off ? t.drop_off.text : "No shelter need: pickup only")],
  ];
}

const TRIED = {
  ACCEPTED: ["is-yes", "check", "said yes"],
  DECLINED: ["is-no", "cross", "said no"],
  EXPIRED: ["is-no", "clock", "no answer"],
  PENDING: ["is-wait", "phone", "asking…"],
  WITHDRAWN: ["is-muted", "cross", "withdrawn"],
};

function triedRow(o) {
  const [tone, ic, word] = TRIED[o.status] || ["is-muted", "clock", o.status.toLowerCase()];
  const who = el("span", "tried-name", o.volunteer);
  const secs = o.sent_at && o.responded_at ? (new Date(o.responded_at) - new Date(o.sent_at)) / 1000 : null;
  const said = [o.reply ? `“${o.reply}”` : null, secs != null ? `after ${secs.toFixed(1)} s` : null]
    .filter(Boolean).join(" · ");
  if (said) who.append(el("span", "tried-said", said));
  const st = el("span", `tried-state ${tone}`);
  st.append(icon(ic), word);
  const li = el("li");
  li.append(el("span", "tried-rank num", `#${o.rank}`), who, st);
  return li;
}

function stepRow(e) {
  const li = el("li", `is-${e.kind}`);
  const iconBox = el("span", "step-icon");
  iconBox.append(icon(STEP_ICON[e.kind] || "check"));
  const text = el("div", "step-text", e.text);
  if (e.detail) text.append(el("span", "step-detail", e.detail));
  if (e.audio) text.append(playButton(e.audio));
  li.append(el("span", "step-time", clock(e.ts) || ""), iconBox, text, el("span", "step-ms", ms(e.ms)));
  return li;
}

function playButton(url) {
  const btn = el("button", "play-btn");
  btn.type = "button";
  btn.append(icon("play"), el("span", null, "Play"));
  btn.setAttribute("aria-label", "Play this clip");
  btn.addEventListener("click", () => {
    if (playing === btn) {
      player.pause();
      return stopClip();
    }
    stopClip();
    playing = btn;
    btn.classList.add("is-playing");
    btn.replaceChildren(icon("stop"), el("span", null, "Stop"));
    player.src = url;
    player.play().catch(stopClip);
  });
  return btn;
}

function stopClip() {
  if (!playing) return;
  playing.classList.remove("is-playing");
  playing.replaceChildren(icon("play"), el("span", null, "Play"));
  playing = null;
}

// ---------------------------------------------------------------- strip, pipeline, needs

function renderStrip() {
  const today = state.impact?.today;
  $("i-duty").textContent = state.onDuty.length;
  if (!today) return;
  $("i-meals").textContent = `${today.meals.estimated ? "≈" : ""}${today.meals.total}`;
  $("i-rescues").textContent = today.rescues;
  $("i-people").textContent = today.people_served;
  const all = state.impact.all_time;
  $("i-note").textContent = [
    today.meals.estimated ? `≈ ${today.meals.estimated} of today's meals are estimated from kg or litres.` : null,
    `${all.meals.total} meals rescued all time.`,
  ].filter(Boolean).join(" ");
}

function renderPipeline(stats = []) {
  const by = Object.fromEntries(stats.map((s) => [s.stage, s]));
  $("pipeline").replaceChildren(...PIPELINE.map(([key, label]) => {
    const s = by[key] || {};
    const dd = el("dd");
    dd.append(el("span", "pipe-ms num", ms(s.avg_ms) || "–"),
              el("span", "pipe-n", s.count ? `${s.count} ${s.count === 1 ? "call" : "calls"}` : "no calls yet"));
    const row = el("div");
    row.append(el("dt", null, label), dd);
    return row;
  }));
  const answer = by.answer;
  $("pipe-note").textContent = answer?.count
    ? `Volunteers answer an offer in ${ms(answer.avg_ms)} on average.`
    : "Prisma speech to text and Timbre text to speech, by Gnani.";
}

function renderNeeds(needs = []) {
  $("n-needs").textContent = needs.length;
  $("needs").replaceChildren(...(needs.length ? needs.map((n) => {
    const li = el("li", "need-row");
    const word = n.status === "MATCHED" && n.report_id ? `Food found · ${ticketNumber(n.report_id)}` : null;
    li.append(el("span", "need-name", n.ngo),
              statusPill(n.status, word, NEED_STATUS),
              el("span", "need-meta", [`${n.people_count ?? "?"} people`, `by ${clock(n.needed_by)}`,
                                       n.veg_only ? "veg only" : "any food"].join(" · ")));
    return li;
  }) : [el("li", "need-row is-empty", "No shelter is waiting for food right now.")]));
}

// ---------------------------------------------------------------- map <-> board

function linkFromDot(target) {
  const dot = target.closest?.(".m-dot");
  if (!dot) return;
  const id = Number(dot.dataset.id);
  const key = { kitchen: "kitchen_id", ngo: "ngo_id", vol: "volunteer_id" }[dot.dataset.kind];
  dot.classList.add("is-related");
  $("content").querySelector(".board").classList.add("is-linking");
  state.nodes.forEach((li, cid) => li.classList.toggle("is-related", state.cards.get(cid)?.[key] === id));
}

function linkFromSlip(target) {
  const btn = target.closest?.(".slip-open") || target.closest?.(".slip-item")?.querySelector(".slip-open");
  const c = btn && state.cards.get(Number(btn.dataset.id));
  if (!c) return;
  const svg = $("map");
  for (const [kind, id] of [["kitchen", c.kitchen_id], ["ngo", c.ngo_id], ["vol", c.volunteer_id]]) {
    if (id != null) svg.querySelector(`.m-dot[data-kind="${kind}"][data-id="${id}"]`)?.classList.add("is-related");
  }
}

function unlink() {
  $("content").querySelector(".board").classList.remove("is-linking");
  state.nodes.forEach((li) => li.classList.remove("is-related"));
  $("map").querySelectorAll(".m-dot.is-related").forEach((d) => d.classList.remove("is-related"));
}

// ---------------------------------------------------------------- the map

// Drawn by /assets/map.js. A slip open: its route bold (dashed while still asking), the rest
// faint. Nothing open: every route on the way is drawn. Bold routes are named under the map.
function renderMap() {
  const p = state.places;
  if (!p) return;
  const live = [...state.cards.values()].filter((c) => ["finding", "on_way"].includes(laneOf(c)));
  const open = state.cards.get(state.openId);
  const ordered = open ? [open, ...live.filter((c) => c.id !== open.id)] : live;
  const routes = [];
  const named = [];  // [tone, stops]
  for (const c of ordered.reverse()) {
    const stops = routeStops(c, p);
    if (stops.length < 2) continue;
    const lead = open ? c.id === open.id : laneOf(c) === "on_way";
    const tone = lead ? (laneOf(c) === "finding" ? "is-asking" : "is-active") : "";
    routes.push({ stops, tone });
    if (lead) named.unshift([tone, stops]);
  }
  drawMap($("map"), p, { duty: new Set(state.onDuty), routes, linkable: true });
  $("map-routes").replaceChildren(...named.map(([tone, stops]) => {
    const key = svgEl("svg", { viewBox: "0 0 28 8", "aria-hidden": "true" });
    key.append(svgEl("line", { x1: 2, y1: 4, x2: 26, y2: 4, class: `m-route ${tone}` }));
    const li = el("li");
    li.append(key, el("span", null, stops.map((s) => s.label).join(" → ")
      + (tone === "is-asking" ? " (asking)" : "")));
    return li;
  }));
}

// volunteer (if any) -> kitchen -> shelter (if any), each with a short label
function routeStops(c, p) {
  const find = (list, id) => list.find((x) => x.id === id);
  const v = find(p.volunteers, c.volunteer_id);
  const k = find(p.kitchens, c.kitchen_id);
  const n = find(p.ngos, c.ngo_id);
  const picked = c.status === "PICKED_UP" || c.status === "DELIVERED";
  return [
    v && !picked ? { ...v, label: first(v.name) } : null,
    k ? { ...k, label: short(k.name) } : null,
    n ? { ...n, label: short(n.name) } : null,
  ].filter(Boolean);
}

// ---------------------------------------------------------------- sharing

const CARD_SIZES = { square: [1080, 1080, "1080 × 1080"], portrait: [1080, 1350, "1080 × 1350 (4:5)"] };

function openShare(c) {
  if (!c) return;
  state.share = { card: c };
  $("s-share").hidden = !navigator.canShare;
  showCard("square");
  $("share").showModal();
}

// Square for LinkedIn and WhatsApp, portrait 4:5 for an Instagram post.
function showCard(format) {
  const c = state.share?.card;
  if (!c) return;
  const [w, h, label] = CARD_SIZES[format];
  const url = `/cards/${c.id}.png?status=${c.status}&format=${format}`;
  Object.assign(state.share, { url, name: `bacha-hua-khana-rescue-${c.id}-${format}.png` });
  document.querySelectorAll(".share-size .seg-btn").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.format === format)));
  $("s-error").hidden = true;
  $("s-img").width = w;
  $("s-img").height = h;
  $("s-img").src = url;
  $("s-download").href = url;
  $("s-download").download = state.share.name;
  $("s-note").textContent = `${label}, ready for Instagram, LinkedIn or WhatsApp.`;
}

// Phones and tablets: hand the PNG straight to Instagram, LinkedIn, WhatsApp... via the share sheet.
async function shareCard() {
  const { url, name, card } = state.share || {};
  if (!url) return;
  try {
    const blob = await (await fetch(url)).blob();
    const file = new File([blob], name, { type: "image/png" });
    if (!navigator.canShare({ files: [file] })) throw new Error("no share");
    await navigator.share({ files: [file], title: "Bacha Hua Khana", text: `${card.kitchen} shared food today.` });
  } catch (err) {
    if (err.name === "AbortError") return;
    $("s-error").textContent = "This browser can't share the image here. Use Download PNG instead, then post it.";
    $("s-error").hidden = false;
  }
}

// ---------------------------------------------------------------- helpers

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function ms(v) {
  if (v == null) return "";
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
}

function num(n) {
  return Number.isInteger(Number(n)) ? String(Number(n)) : String(n);
}

const first = (name) => (name || "").split(" ")[0];
const short = (name) => (name || "").split(",")[0];
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

init();
