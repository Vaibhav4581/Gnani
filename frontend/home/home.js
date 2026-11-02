// Home page: the hero slip writes itself in as the sentence is "heard", the live meal count
// comes from /impact, the three small screens are built from the app's own components, and
// the eval table comes from /eval/summary (eval/RESULTS.md). All of it is synthetic demo data.
import { $, getJson } from "/shared/common.js";
import { icon, renderKot, renderNeedSlip, setKotFields, setKotRoute, setKotSpeaking,
         setKotStatus } from "/assets/kot.js";

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// A fixed afternoon, so the countdown always reads the same: cooked 2 pm, now 2:40 pm.
const today = (h, m = 0) => { const d = new Date(); d.setHours(h, m, 0, 0); return d.toISOString(); };
const demoNow = () => new Date(today(14, 40));
const HEARD = "50 plate biryani hai, Hotel Sagar, Vyttila. Do baje bana tha.";
const FOOD = { quantity: 50, unit: "plate", dish: "biryani", veg: true };
const STOPS = [{ name: "Hotel Sagar", icon: "flame" }, { name: "Anjali", icon: "bike" },
               { name: "Karunya", icon: "people" }];

const wait = (ms) => new Promise((r) => setTimeout(r, reducedMotion ? 0 : ms));

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------- hero

async function playHero() {
  const slip = renderKot({ id: 1, kitchen: "Hotel Sagar, Vyttila", status: "RECORDED" },
                         { print: !reducedMotion, now: demoNow });
  $("hero-slip").append(slip);
  setKotRoute(slip, { stops: STOPS, at: 0 });  // the route is there from the start: no growth later
  const heard = $("heard-text");
  // The whole sentence is laid out at once (hidden), then revealed word by word, as if spoken,
  // so the quote never grows and pushes the slip down.
  const words = `“${HEARD}”`.split(" ").map((w) => el("span", "heard-word is-waiting", `${w} `));
  heard.append(...words);
  document.body.classList.remove("is-loading");  // first screen drawn: show it (design.css)
  if (reducedMotion) {
    words.forEach((w) => w.classList.remove("is-waiting"));
    await setKotFields(slip, { ...FOOD, cooked_at: today(14), deadline: today(18) }, { animate: false });
  } else {
    await wait(500);
    slip.classList.add("is-sending");
    for (const word of words) {
      word.classList.remove("is-waiting");
      await wait(170);
    }
    slip.classList.remove("is-sending");
    await setKotFields(slip, { ...FOOD, cooked_at: today(14), deadline: today(18) }, { stagger: 380 });
    await wait(700);
  }
  setKotStatus(slip, "CONFIRMING", { word: "Sahi hai?" });
  setKotSpeaking(slip, !reducedMotion);
  await wait(1800);
  setKotSpeaking(slip, false);
  setKotStatus(slip, "CONFIRMED", { word: "Kitchen said haan" });
  await wait(1300);
  setKotStatus(slip, "OFFERED", { word: "Calling a volunteer" });
  setKotRoute(slip, { stops: STOPS, at: 1 });
  await wait(1600);
  setKotStatus(slip, "ASSIGNED", { word: "Anjali is on the way · 15 min" });
  setKotRoute(slip, { stops: STOPS, at: 2 });
  $("hero-cap").textContent = "Spoken in Hindi, read back, confirmed, and a volunteer is on the way.";
}

// ---------------------------------------------------------------- live count

async function loadCount() {
  try {
    const { all_time: all } = await getJson("/impact");
    const n = all.meals.total;
    $("count-n").textContent = n ? `${all.meals.estimated ? "≈" : ""}${n}` : "";
    $("count-label").textContent = n
      ? `${n === 1 ? "meal" : "meals"} rescued on this demo server so far`
      : "No rescues on this demo server yet. Try the kitchen screen.";
  } catch {
    $("count-label").textContent = "";
  }
}

// ---------------------------------------------------------------- the three small screens

function phone(id, ...children) {
  const inner = el("div", "phone-inner");
  inner.append(...children);
  $(id).append(inner);
}

function bigButton(cls, text) {
  const b = el("span", `btn ${cls}`, text);
  return b;
}

function miniScreens() {
  // 1. Kitchen (Hindi): the slip waiting for "haan", and the mic
  const kot = renderKot({ id: 1, kitchen: "Hotel Sagar", status: "CONFIRMING", ...FOOD,
                          cooked_at: today(14), deadline: today(18) },
                        { now: demoNow, lines: ["food", "deadline"], words: { status: { CONFIRMING: "Sahi hai?" } } });
  const mic = el("span", "mic-btn mic-btn--ring");
  mic.append(icon("mic"), el("span", null, "Dabaakar jawab dijiye"));
  phone("mini-kitchen", kot, mic);

  // 2. Volunteer (Malayalam): a ringing offer with yes / no
  const ring = el("span", "phone-ring ringing");
  ring.append(icon("phone"));
  const offer = renderKot({ id: 1, kitchen: "Hotel Sagar, Vyttila", status: "OFFERED", ...FOOD,
                            deadline: today(18) },
                          { now: demoNow, lines: ["food"], words: { status: { OFFERED: "നിങ്ങൾക്ക്" },
                            units: { plate: ["പ്ലേറ്റ്", "പ്ലേറ്റ്"] } } });
  phone("mini-volunteer", ring, el("p", "phone-title", "പുതിയ പിക്കപ്പ്"), offer,
        bigButton("btn-primary btn-huge", "അതെ, ഞാൻ എടുക്കാം"), bigButton("btn-outline-danger", "ഇല്ല"));

  // 3. Shelter (English): the request, food found, and "has it arrived?"
  const need = renderNeedSlip({ need_id: 1, ngo: "Karunya Children's Home", people_count: 80,
                                needed_by: today(19), veg_only: false, status: "MATCHED" },
                              { now: demoNow });
  const q = el("p", "phone-q");
  q.append(icon("speaker"), document.createTextNode("Has the food arrived?"));
  phone("mini-shelter", need, q, bigButton("btn-primary btn-huge", "Yes, it's here"));
}

// ---------------------------------------------------------------- eval table

const CHECK_NAMES = { dish: "Dish", quantity: "Quantity", unit: "Unit", cooked_time: "Cooked time",
                      location: "Location", "yes/no replies": "Yes / no replies",
                      "whole clip right": "Whole clip right" };

async function loadEval() {
  let r;
  try {
    r = await getJson("/eval/summary");
  } catch { return; }  // no results file: the section stays without a table
  if (!r.columns?.length) return;
  $("eval-head").textContent = (r.headline || "").replace("telephony", "phone line");
  $("eval-cols").replaceChildren(...r.columns.map((c, i) => {
    const th = el("th", null, i ? c.replace("Telephony", "Phone line") : c);
    th.scope = "col";
    return th;
  }));
  $("eval-rows").replaceChildren(...r.rows.map((row) => {
    const tr = el("tr", row[0] === "whole clip right" ? "is-total" : null);
    row.forEach((cell, i) => {
      const td = el(i ? "td" : "th", null, i ? cell : CHECK_NAMES[cell] || cell);
      if (!i) td.scope = "row";
      tr.append(td);
    });
    return tr;
  }));
  $("eval-run").textContent = r.run || "";
  $("eval-caveat").textContent = r.caveat || "";
  $("eval").hidden = false;
}

miniScreens();
loadCount();
loadEval();
playHero();
setInterval(loadCount, 30_000);
