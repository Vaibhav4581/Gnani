# Bacha Hua Khana design system

Every screen follows this file and uses `frontend/assets/`. Plain HTML, CSS and JS: no build step,
no CSS framework. To review everything in one place, open `/styleguide.html`.

## Concept

The visual language of an Indian commercial kitchen. Food reports are kitchen order tickets
(KOT slips). Colours come from banana leaf, haldi, mirchi and stainless steel. Warm, practical and
trustworthy; never cute, never corporate.

## Colour

| Token | Value | Use |
|---|---|---|
| `--leaf` | `#1E5631` | Primary actions, "on the way", success |
| `--leaf-soft` | `#E3EFE4` | Success backgrounds |
| `--haldi` | `#F2A900` | Attention, "new report", live and recording. **Background only**: text on it is `--ink`, never white |
| `--haldi-soft` | `#FFF4D6` | Attention backgrounds |
| `--mirchi` | `#C62E1F` | Deadlines, declines, errors, "nahi" |
| `--mirchi-soft` | `#FBE6E3` | Error backgrounds |
| `--steel` | `#D5DADF` | Borders, dividers, inactive |
| `--steel-dark` | `#5F6A74` | Secondary text |
| `--rice` | `#FAFAF7` | Page background |
| `--paper` | `#FFFFFF` | KOT slip surface |
| `--ink` | `#17261C` | Body text |
| `--leaf-hover` | `#17462A` | Hover on leaf buttons only |
| `--mirchi-hover` | `#A82618` | Hover on mirchi buttons only |
| `--leaf-deep` | `#143D23` | Dark leaf in large illustrated areas only (the hero's banana leaf) |
| `--counter` | `#E9ECEA` | The stainless counter the mic stands on; the dashboard's pass shelf |
| `--counter-edge` | `#C3C9CE` | The counter's top edge, the shelf lip, thali rings |
| `--rail` | `#8A949C` | The ticket rail bar, its clips, pins |
| `--water` | `#A8C3D1` | Backwaters and the sea edge, on maps only |

Every colour in every stylesheet is one of these tokens (a test checks it).

**Status always uses colour + icon + word, never colour alone.**

| State | Colour |
|---|---|
| Reported | haldi |
| Finding volunteer | steel |
| On the way | leaf |
| Delivered | solid leaf |
| Declined, expired, cancelled | mirchi |

**Deadlines:** a pickup countdown is ink while there is time and turns mirchi (bold) at 30 minutes
left or once it has passed. A countdown that is always red stops meaning "hurry".

### Contrast (WCAG 2.2)

AA needs 4.5:1 for body text, and 3:1 for large text (24px, or 18.7px bold), icons and the borders of controls.

| Foreground on background | Ratio | Allowed for |
|---|---|---|
| ink on rice / paper | 15.1 / 15.8 | everything |
| white on leaf, leaf on paper | 8.6 | everything |
| leaf on leaf-soft | 7.3 | everything |
| ink on haldi | 7.9 | everything |
| ink on haldi-soft | 14.4 | everything |
| white on mirchi, mirchi on paper | 5.5 | everything |
| mirchi on mirchi-soft | 4.6 | everything (just) |
| steel-dark on rice / paper | 5.3 / 5.5 | everything |
| steel-dark on haldi-soft / leaf-soft | 5.0 / 4.7 | everything |
| ink / steel-dark on counter | 13.3 / 4.6 | everything |
| steel-dark on steel | 3.9 | large text and icons only (disabled buttons; WCAG exempts inactive controls) |
| **white on haldi, haldi on paper** | **2.0** | **never** |
| **steel on paper** | **1.4** | **decoration only** |

Two rules follow from the table:
- **Haldi is never text and never takes white text.**
- **Steel is never the only border of a control.** Inputs, selects and outlined buttons use a
  `--steel-dark` border. Steel is for dividers, the KOT's dashed rules and inactive fills.

## Type

- **Display, numbers, buttons:** "Baloo 2". Malayalam uses "Baloo Chettan 2"; Devanagari is covered by
  Baloo 2. Kannada uses "Baloo Tamma 2", the same family (added: the brief had no Kannada face, and
  Udupi Grand is a Kannada kitchen).
- **Body:** "Hind" (Latin and Devanagari), with "Noto Sans Malayalam" and "Noto Sans Kannada" as fallbacks.
- **Hosting:** the woff2 files are self-hosted in `frontend/assets/fonts/` (SIL OFL, see `OFL.txt`), so
  the demo works offline. There is one `@font-face` per script subset, so a page downloads only the
  scripts it shows. The total is about 615 KB.

| Step | rem | Token | Typical use |
|---|---|---|---|
| -1 | 0.875 | `--step--1` | Small print, labels, pills |
| 0 | 1 | `--step-0` | Body |
| 1 | 1.25 | `--step-1` | Buttons, card titles |
| 2 | 1.563 | `--step-2` | h3, dish names, huge buttons |
| 3 | 1.953 | `--step-3` | h2 |
| 4 | 2.441 | `--step-4` | h1, quantities (`.qty`) |
| hero | 3.815 | `--step-hero` | Hero numbers (`.hero-number`) |

Body line-height is 1.5 and display line-height is 1.1. The maximum line length is 70ch.

**Reading from a metre away:** the kitchen and volunteer screens are propped up in a hot kitchen or
glanced at on a scooter. They put `class="reading-far"` on `<body>`, which raises body text one step (to
1.25rem) and small text to 1rem through `--text-small`. The NGO and dashboard screens keep the base sizes.

**Preload** the two Latin faces that every page draws first, so the first paint doesn't swap fonts:

```html
<link rel="preload" href="/assets/fonts/baloo2-latin-400-800.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/hind-latin-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/design.css">
```
**Quantities ("50 plates") are always set big in Baloo 2 semibold:** use `.qty`.

## Shapes

- **The KOT slip:** white paper with a 4px radius, a zig-zag torn bottom edge (a CSS mask, with teeth
  10px deep so it reads across a room) and a faint dashed rule between lines.
- **Buttons:** 14px radius. **The mic button** is a perfect circle.
- **No identical-card grids.** Hierarchy comes from size and spacing.
- **Shadows only on the KOT slip** (a soft paper shadow), nowhere else.

## Copy

- **Case:** sentence case everywhere. No all-caps labels, no eyebrow labels above headings, no arrows
  appended to buttons.
- **Buttons say exactly what happens:** "Send report", "Yes, I'll pick it up".
- **Errors say what happened and what to do,** without apologising: "No speech heard. Check that this
  microphone is switched on, then tap the button again."
- **Bilingual where it helps:** the primary language big, English small underneath ("Haan" / "Yes").

## Motion

- **Only in response to actions or live events:** the recording pulse, ticket lines writing in, a
  ticket sliding along the route.
- **Nothing animates on page load** except the first ticket.
- **Respect `prefers-reduced-motion`:** `design.css` shortens every animation and removes the pulse.
- **Animate transforms and opacity, not size:** the speaking bars scale (`scaleY`), they don't
  change `height`, so they cost no layout.

## The setting

Each screen is a place in a kitchen, kept quiet so the KOT slip and the mic stay the brightest
things on screen. Solid fills only: no gradient washes, no glassmorphism.

- **Kolam dot grid** on every page background: 2px dots of `--steel-dark` at 35%, 24px apart
  (`--kolam-dot`, `--kolam-step`). The dots cover under 1% of the page, so text on it keeps its
  contrast (axe checks every screen).
- **Kolam loops** (`.kolam`, the `kolam` drawing): `--steel-dark` at 30%, in one corner of the home
  hero and of empty states. Always in the corner beside the illustration, never behind text. The
  hero's loops are hidden on phones, where they would sit under the words.
- **The counter** (`.counter`): the mic stands on it. On the kitchen phone screen it runs edge to edge
  and fills the lower 55% of the screen, shrinking to a strip with the small mic while a ticket is
  open. On a tablet it is the left column.
- **The thali** (`.thali`): two `--counter-edge` rings round the mic; the haldi level ring moves
  inside them.
- **The ticket rail** (`.rail-wrap`, `.rail`): a 6px `--rail` bar, each ticket hanging from a clip.
  It shows the kitchen's reports today as mini slips, newest first, scrolling sideways. Empty, it
  says "Today's reports will hang here."
- **The pinboard** (`.pinboard`, `.pinned`): a `--leaf-soft` board for the shelter's requests.
  Pinned slips are white paper with a 4px leaf band under a steel pin, so a leaf-soft need slip
  doesn't vanish into the board.
- **The pass shelf:** the dashboard's lane headings are a `--counter` strip with a `--counter-edge`
  lip; the lane colour is the thin line on top. Slips sit below on the dots.
- **Maps** (`/assets/map.js`, shared by the dashboard and the volunteer screen): dots by lat/lng, with
  backwaters and the sea edge drawn by hand in `--water`, thin and light so they never read as roads.
  The volunteer's own dot pulses gently (not under reduced motion).

### Illustrations (`/assets/illustrations.svg`)

Banana leaf (and `banana-leaf-tall`, the same leaf upright), steel tiffin, scooter with a delivery
bag, shelter, thali, and the kolam. They are flat, use 2-3 palette colours each (the design tokens,
as CSS variables), and have rounded 2px strokes.

**Use them only in:** the home hero, empty states (`.empty-state`), and the volunteer's "no rescues
yet". A test checks it.

The home hero is the one bold image in the product: the self-writing slip lies on a large upright
banana leaf (`--leaf`, `--leaf-deep` veins), turned 2.5°, with a tiffin below it. The leaf stays
inside the hero's own box, never over the quote or the caption.

### Mini slip

`renderMiniKot(report, { words, word })` in `kot.js` draws a small ticket: number, amount and dish,
status pill. It's static, with no countdown or write-in. Used on the kitchen's rail and in the
volunteer's "Your rescues", where the last three are fanned like slips on a spike.

## Helping first-timers

The aim: anyone can use each screen within 10 seconds without being told how.

- **"For example:" under a mic** (kitchen and shelter):
  - the lead-in is in the screen's language, with the English lead-in under it, then one real
    example that changes every 6 seconds (still under reduced motion);
  - the examples live in the language packs (`report_examples`, `need_examples`), and a test runs
    every one through the real extractor, so saying an example word for word always works;
  - all examples share one grid cell (`.examples`), so the box is as tall as the longest and
    nothing moves when they change.
- **First-time tips** (`.tip`, kitchen):
  - three at most: the mic (below the example, so the first screen shows the mic and what to
    say), the slip, and the Haan/Nahi buttons;
  - each appears the first time its target does, with "Got it" and "Hide tips";
  - they are inline and never a modal, and are remembered on the device;
  - doing the thing (tapping the mic, answering) also counts as "got it".
- **Feedback without looking:** a soft tick when recording starts (higher) and stops (lower), and a
  30 ms buzz on phones. A new offer on the volunteer screen rings, vibrates in a phone-call
  pattern, and is announced in an assertive live region.
- **"Saying no is fine, we'll ask someone else."** sits above the volunteer's No / Yes.
- **Bigger text** (kitchen top bar, "A+"): the whole page at 125% (every size is in rem), except the
  language switch, whose names already fit. Remembered on the device.
- **"What am I looking at?"** (dashboard): a one-line haldi-soft note over the impact strip and under
  each lane's shelf. It's on for a first visit until someone turns it off (remembered).
- **Map and board point at each other:** hovering or focusing a kitchen, shelter or on-duty volunteer
  dot outlines its slips in leaf and steps the rest back; a slip enlarges its dots. Those dots take
  focus (with the usual leaf ring) and have names.
- **Loading is the slip itself:** blank lines breathing (`.is-skeleton`, `renderSkeletonMini()`) on the
  kitchen rail, "Your rescues" and the dashboard's detail panel. Never a spinner on its own.
- **Every error says what to do next.** `failureKey(err)` in `shared/common.js` picks one of four:
  - **offline:** "No internet. Check the Wi-Fi, then …";
  - **unreachable:** "Can't reach the server. Check the internet and tap the button again.";
  - **server down:** "The server had a problem. Wait a moment, then …";
  - **refused:** the server's own reason, then the next step.

  Each screen ends with its own action (tap the button / tap again / press Reset demo again).
  The dashboard shows them on the page, never in an `alert()`.

## One screen on a laptop

On a laptop or bigger (and at least 600px tall), each app screen is exactly one screen: neither
the page nor a column scrolls. A phone scrolls as usual. Check the real window sizes, not the
screen sizes: a 1366x768 laptop leaves about 1366x650 inside the browser, and 1920x1080 at 125%
scaling about 1536x730. Under 800px tall the screens tighten (smaller mic, side-by-side rows).

- **Home** (1000px and up): the top bar's tabs switch what fills the screen. "Home" (first):
  headline, live count, the two buttons and the four apps on the left, the slip on its leaf on
  the right. "How it works", "Built on Gnani AI" (the accuracy table beside the engines) and
  "About" each have the screen to themselves. On a phone the sections read one after another.
- **Kitchen:** the mic grows with the window's height and shrinks to fit what is under it. With
  a ticket open, the conversation (what the app said, the answers, the safety and cancel
  questions) stands on the counter under a smaller mic with its label beside it, and the ticket
  has the right column to itself. The tips stand in the ticket column. Under 1000px tall the
  ticket rail folds to its one line while a report is open; "Last report" hides until it ends.
- **Volunteer:** on duty, the area map on the left and the day on the right; an offer puts its
  ticket on the left and the route, the voice and No / Yes on the right.
- **Shelter:** the two columns fill the height. When the requests don't fit under the mic, the
  oldest fold to one row (head count, number, status), then step behind "+N more".
- **Dashboard:** the side column (map, open needs, voice timings) runs the full height beside
  the impact strip and the board; the map shrinks to fit. A full lane folds its oldest slips to
  their heading, then shows "+N more"; either "+N more" opens the list in full, scrolling inside
  itself, until "Show less". A slip's timeline takes over the side column and scrolls inside it.

The fitting is done by small functions that measure and adjust (kitchen fitMic, shelter
fitRequests, dashboard fitLanes and fitSide), so a longer language, Bigger text or a busier
day still fits. A column scrolls inside itself only as a last resort.

## No layout shift

Nothing on screen jumps as data arrives:
- **First render:** a page whose first screen is drawn by its script puts `class="is-loading"` on
  `<body>` and `data-reveal` on those regions. They stay invisible until the script removes the class
  after drawing, or for 2 s if the script fails.
- **Blank KOT lines are as tall as the values that fill them.** The quantity and dish blanks are
  sized like their text. A blank pickup time carries an invisible countdown in the slip's own words
  (`.kot-ghost`), and the countdown always sits under the time, so the line doesn't grow when it
  writes in.
- **The voice playing doesn't reflow the ticket:** the status pill's icon turns into the moving bars,
  and the pill keeps its width.
- **Text that arrives late keeps its line:** placeholder text in the HTML (`&nbsp;`, English defaults),
  or a `min-height` for numbers fetched later.

## Fonts and page weight

- Every font is a script subset (`unicode-range`), so a page downloads only the scripts it shows.
- **Language names** (हिन्दी, മലയാളം, ಕನ್ನಡ) use `.lang-name`: 3-4 KB subsets holding just those words.
  A page doesn't fetch a whole Devanagari or Kannada font (up to 112 KB) only to name the language.
- The Latin display and body fonts are preloaded on every page.
- The server gzips HTML, CSS, JS and JSON.
- Every page is under 300 KB without audio. The heaviest, the kitchen in Malayalam, is about 240 KB.

## Accessibility floor

- WCAG AA contrast (see the table above).
- Visible focus rings: a 3px `--leaf` outline (`:focus-visible`).
- Touch targets of at least 56px (`--tap`). Kitchen and volunteer buttons are 88px or more (`--tap-big`, `.btn-huge`).
  - **One exception:** the dashboard timeline's inline Play buttons are 44px. They are a dense list on
    the coordinator's laptop screen, and still well above WCAG 2.5.8's 24px.
- One `<h1>` per screen and a `<main>` landmark. Where the design has no visible title (kitchen,
  shelter, off-duty volunteer), the `<h1>` is `.visually-hidden`.
- **Live regions:**
  - **Kitchen:** what the app says (polite), and the safety question.
  - **Volunteer:** a new offer (assertive), with notices as alerts.
  - **Shelter:** food on the way (polite) and "has it arrived?" (assertive).
  - **Dashboard:** a slip arriving or moving lane (polite: "#BHK-0003, On the way: John Mathew is on
    the way").
- **Ticket numbers** (`#BHK-0001`, `#NEED-0002`) are identifiers printed as on a real KOT, not
  labels. They are the only capitals; everything else is sentence case.
- Works at 360px wide with no horizontal scroll.
- Every icon-only button has an `aria-label`. Decorative icons have `aria-hidden="true"`.

## Using the system

Link the stylesheet and use the classes; page CSS only adds layout.

```html
<link rel="stylesheet" href="/assets/design.css">
```

### Tokens beyond the brief

- **Spacing:** a 4px grid, `--space-1` (4px) to `--space-8` (64px).
- **Radii:** `--radius-slip` 4px, `--radius-control` 10px (inputs), `--radius-button` 14px.
- **Favicon:** `/assets/favicon.svg`, a white KOT slip on leaf, linked from every page.
- **Other:** `--tap`, `--tap-big`, `--focus-ring`, `--paper-shadow`, `--tooth` (the KOT edge's tooth
  width), and `--text-small` (small text size; one step up under `.reading-far`).

### Buttons

| Class | Use |
|---|---|
| `.btn.btn-primary` | The one main action (leaf) |
| `.btn.btn-secondary` | Anything else (paper, steel-dark border) |
| `.btn.btn-danger` | Declines and cancels (mirchi) |
| `+ .btn-huge` | 88px, full width: kitchen and volunteer actions |
| `+ .btn-bilingual` | `<button class="btn btn-primary btn-huge btn-bilingual" lang="hi">Haan<span class="btn-en" lang="en">Yes</span></button>` |
| `.btn.btn-outline-danger` | A "no" that isn't destructive, e.g. "Nahi, badlo" (outlined in mirchi) |
| `.btn.btn-inverse` | The main action on a leaf screen (paper with leaf text), e.g. "Picked up" |

Disabled buttons turn steel with steel-dark text.

### Status pills

`statusPill(status)` in `kot.js` builds one from a `Report.status` value. By hand, use
`<span class="pill pill--on-way"><svg class="icon">…</svg>On the way</span>`.

| `Report.status` | Pill | Icon | Word |
|---|---|---|---|
| RECORDED, TRANSCRIBED, EXTRACTED | `pill--reported` (haldi) | flame | Reported |
| CONFIRMING | `pill--reported` | flame | Checking details |
| CONFIRMED, SAFETY_CHECK | `pill--checking` (haldi-soft) | check | Confirmed / Safety check |
| MATCHING | `pill--finding` (steel) | clock | Finding volunteer |
| OFFERED | `pill--finding` | phone | Asking volunteer |
| ASSIGNED | `pill--on-way` (leaf outline) | bike | On the way |
| PICKED_UP | `pill--on-way` | bike | Picked up |
| DELIVERED | `pill--delivered` (solid leaf) | check | Delivered |
| an offer that was declined | `pill--stopped` (mirchi) | cross | Declined |
| CANCELLED | `pill--stopped` | cross | Cancelled |
| EXPIRED | `pill--stopped` | clock | Expired |

### The KOT slip (`/assets/kot.js`)

```js
import { renderKot, updateKotLine, setKotStatus } from "/assets/kot.js";
const slip = renderKot(report, { print: true });  // print: only the first ticket on a page
updateKotLine(slip, "quantity", 30);              // redraws one line, "writing in"
setKotStatus(slip, "ASSIGNED");
```

- **Input:** `report` uses the API's field names: `id` (or `report_id`), `kitchen`, `dish`, `quantity`,
  `unit`, `cooked_at`, `deadline`, `veg`, `status`.
- **What the slip shows:**
  - the kitchen name on its own line (never squeezed), with the ticket number (`#BHK-0042`) and status pill below it;
  - the quantity in `.qty` with the dish, and the veg or non-veg mark;
  - the cooked time;
  - the pickup time with a live countdown: ink, then mirchi from 30 minutes left.
- **Missing values** are blank dashed lines, sized like the value that will fill them (a big slot for the
  quantity), with "not heard yet" for screen readers.
- **Countdown:** it ticks every 30 s, stops once the food is picked up, delivered, cancelled or expired,
  and stops by itself when the slip is removed from the page.

### Mic button

```html
<button class="mic-btn" type="button">
  <svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#mic"/></svg>
  <span>Tap to report food</span>
</button>
```

- **Tap to talk:** one tap starts; the recording stops by itself about a second after the speaker
  stops (judged against the room's own noise), and a second tap stops it early. No holding.
- **Recording:** add `.is-recording` (a haldi fill, ink text and a pulsing ring) and swap to the `stop` icon.
  The label says what to do: "Bol dijiye… ruk jaane par bhej denge".
- **Listening by itself:** right after the app asks anything (the read-back, a follow-up such as
  "Khana kitne baje bana tha?", a question asked again because it didn't understand, the safety
  questions, "cancel karein?", the volunteer's offer, the shelter's questions and "Khana aa gaya?") the
  mic opens on its own with a soft tick and "Sun rahe hain…". If nobody answers in 8 s it closes
  quietly and the Haan / Nahi buttons are still there.
- **Never while the app speaks:** the mic is disabled while a reply plays, and any sound starting
  cancels a recording, so the app can't hear itself.
- **Busy:** `disabled`. It turns steel, and the label stays ink because "Understanding…" is real information.

### Icons (`/assets/icons.svg`)

`<svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#NAME"/></svg>`. They are drawn on a
24px grid with a 2px stroke in `currentColor`.

Names: mic, stop, play, check, cross, clock, pin, phone, bike (a scooter), veg, non-veg, people, flame,
chevron-down, speaker, covered (a pot with its lid on).
The veg and non-veg marks keep their own colours: the standard square-and-dot and square-and-triangle
shapes, with non-veg in mirchi rather than the label brown, to stay in the palette.

### Forms and messages

- **Fields:** `.field` contains `.field-label`, then `.input` or `.select`, then `.field-hint`. Add
  `.has-error` to the field and a `.field-error` line (cross icon and text) under it.
- **Messages:** `.callout--error`, `.callout--attention` and `.callout--success`, always with an icon and words.

### Components added with the kitchen screen

These live in `design.css` and `kot.js`, so the other screens reuse them rather than redrawing them.

- **`.mic-btn--ring`:** the mic with a haldi ring. While recording, the ring follows the live mic level:
  set `--level` (0 to 1) on the button. `bindTapToTalk({ onLevel })` in `assets/recorder.js` supplies
  it from a Web Audio AnalyserNode (the same reading decides when to stop).
- **`.seg` / `.seg-btn`:** a segmented control for one choice from a few that stay in view, such as
  the language. Use `role="radiogroup"` on the group, with `role="radio"` and `aria-checked` on each button.
- **`.conn`:** the connection state as a dot and a word. `data-state` is `live`, `reconnecting` or `offline`.
- **`.disclosure`:** a `<details>` for things kept out of the way, such as the last report or settings.
- **KOT extras:**
  - **Notes:** `setKotNote(slip, line, text)` puts the follow-up question beside a missing line.
  - **Speaking:** `setKotSpeaking(slip, on)` shows the speaker and bars while the app's voice plays.
  - **Route:** `setKotRoute(slip, { stops, at })` draws kitchen → volunteer → NGO along the foot of
    the ticket, filling a leg as the food moves on.
  - **Sending:** `.kot.is-sending` makes the blank slots breathe while the first request is on its way.
- **The slip's words:** `renderKot(report, { words })` takes the labels, units, status words and
  countdown in the reader's language, from `assets/kot-words.js` (shared by every screen).
  `renderKot(report, { lines: ["food", "deadline"] })` draws only some lines; an offer leaves out the
  cooked time, which it doesn't carry.

### The home page and the impact card

- **Home page** (`frontend/home/`): rice background, white bands for "How it works" and
  "Built on Gnani AI".
  - **Hero:** the headline, then a real KOT slip. The heard sentence appears word by word on
    a haldi-soft quote, the lines write in, and the pill moves to "on the way". It plays
    once; under reduced motion it starts finished. On phones the slip comes straight after
    the headline.
  - **Small screens** (`.phone`): the real components at 60% inside a phone outline. They
    are not screenshots, so they keep up with the app.
  - **The meal count** is a big leaf number.
  - **The eval table** scrolls sideways inside its own box on phones.
- **Impact card** (`cards.py`):
  - the date as a small label and the meals as a leaf Baloo headline, over a KOT slip on rice;
  - the slip has the kitchen, ticket number and a Delivered or Picked up pill, the quantity big
    and the dish in its own script with the veg mark;
  - the route is drawn as stops with filled legs, like `.route`;
  - "Bacha Hua Khana · built on Gnani AI" sits small at the foot;
  - square and portrait use the same pieces, and the slip scales to fit.

### Components added with the dashboard

The coordinator's screen is a route board, read from a laptop beside the phones. It keeps
the base type sizes, is desktop first (1280px+), and still works on a tablet.
- **Lanes:** Reported → Finding a volunteer → On the way → Delivered. Each has a heading
  with a 4px rule in its tone: haldi, steel-dark, leaf, then a double leaf rule. Cancelled
  and expired slips go to a collapsed "Closed today" row, not a lane.
- **The compact slip** (`.kot--compact`): the same KOT with smaller type and two lines, food
  and pick-up-by, so the countdown still turns mirchi under 30 minutes. Under the lines:
  - who carries it to which shelter;
  - a small mirchi mark (`.no-mark`, cross icon) for each volunteer who said no or didn't
    answer, so the fallback is visible.

  A pickup-only rescue that is picked up gets the Delivered pill. The whole slip is one
  button (`.slip-open`); the open one is marked with a leaf bar and leaf-soft paper.
- **Moving lanes:** a slip slides to its new lane with a 300ms FLIP animation, and jumps
  under reduced motion.
- **The detail panel** sits beside the board from 1200px and slides over it below that.
  It shows:
  - what the kitchen said, in its own script, on a haldi-soft quote;
  - the fields and safety answers, each with an icon and a word;
  - every volunteer tried, with their reply and timing;
  - a timeline with every step's latency right-aligned, and a play button (`.play-btn`)
    for every Timbre clip.
- **The impact strip:** plain numbers with plain labels. Meals rescued today is the biggest
  number on any screen, in leaf.
- **The map:** an inline SVG schematic placed by lat/lng, with no tiles or library. It uses
  shape as well as colour:
  - kitchens are haldi circles;
  - volunteers are small leaf dots, hollow when off duty;
  - shelters are steel-dark squares.

  The open slip's route is solid leaf, or dashed while a volunteer is still being asked.
  Each route is named under the map, never on top of the dots.

### Components added with the NGO screen

- **The need slip:** `renderNeedSlip(need, { words })` and `updateNeedSlip(slip, need)` in `kot.js`.
  It's the same ticket on leaf-soft paper (`.kot--need`):
  - the people count big, like a quantity;
  - needed-by with a countdown;
  - "Veg only" with the veg mark, or "Any food".

  Its pills come from `NEED_STATUS`: Checking details, Waiting for food, Food found, Delivered and
  Expired. Lines carry `data-field`, so `setKotNote` works on them too.
- **`statusPill(status, word, table)`** takes `NEED_STATUS` as the table for needs.

### Components added with the volunteer screen

- **`.stops`:** where to go, top to bottom, as a vertical route. Each `.stop` holds a `.stop-dot` (an icon)
  and a `.stop-body` (`.stop-label`, `.stop-name`, details), and `.is-done` marks a stop behind you.
  It takes its colour from the text, so it works on leaf.
- **`.ringing`:** the shake of a ringing phone, for an incoming offer. It's still under reduced motion,
  and is only applied while the offer can be answered.
- **`.sheet`:** a `<dialog>` holding a short list of big buttons to pick from (which kitchen, which
  volunteer). `aria-current="true"` marks the current one.
- **Screen colour:** the volunteer page sets `data-screen` on `<body>`:
  - **off duty:** rice;
  - **on duty:** leaf-soft, calm;
  - **offer:** haldi, like a call;
  - **accepted:** leaf.

  On leaf, focus rings and the connection dot turn paper.

## Do and don't

- **Do** let the mic button and the KOT slip be the biggest, boldest things on a voice screen.
- **Do** put the primary language first and English small underneath, on answer buttons.
- **Don't** put white text on haldi, or use haldi as text colour.
- **Don't** add shadows to anything but the KOT slip.
- **Don't** add hover-only information. Kitchen and volunteer screens are touched, not hovered.
- **Don't** animate on page load, except the first ticket.
