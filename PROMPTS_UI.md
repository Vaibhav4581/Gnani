# Bacha Hua Khana: UI redesign prompts

Run these after the V2 features are in. One prompt per Claude Code session, in order.
Prompt 0 creates the design system; every later prompt builds on it, so don't skip it.

## Before you start
1. Commit: `git commit -am "before UI redesign"`
2. Install Playwright once so Claude Code can screenshot its own work:
   `pip install playwright && python -m playwright install chromium`
3. Run with `MOCK_GNANI=1`. UI work should cost zero credits.
4. Approve each plan before any code is written. If a plan drifts into React, Tailwind,
   a build step or generic SaaS styling, point it back to DESIGN.md.

## Schedule
| Date | Prompt |
|---|---|
| 31 Oct | 0. Design system, 1. Kitchen screen |
| 1 Nov | 2. Volunteer screen, 3. NGO screen |
| 2 Nov | 4. Dashboard |
| 3 Nov | 5. Home page + impact card, 6. Polish pass, then freeze |

Demo recording moves to 4-5 Nov, posting to 6 Nov. Don't let UI work push it later.

---

## The design idea (read this so you can judge the plans)

**Who uses each screen:**
- **Kitchen screen:** a phone or tablet propped up in a hot, loud kitchen, used with wet hands and read from a metre away.
- **Volunteer screen:** a phone in someone's pocket that should feel like an incoming call.
- **NGO screen:** a coordinator at a shelter with a bit more time.
- **Dashboard:** a coordinator's laptop. It's also what judges watch in the demo.

**The look comes from Indian kitchens, not from SaaS templates:**
- **The memorable element is the KOT slip.** Every restaurant kitchen in India runs on kitchen order tickets (KOTs), so each food report appears as one: a narrow paper ticket with a torn edge, filling in line by line as the app understands the speech. The same ticket travels through the whole app.
- **The colours** are banana-leaf green, haldi yellow, mirchi red and stainless steel.
- **The type** is Baloo 2, a rounded Indian display face in the style of local signage, with Malayalam and Devanagari support.
- **Everything else stays quiet,** so the tickets and the giant mic button stand out.

---

## Prompt 0: design system

```
Read CLAUDE.md and every file in frontend/ first.

Goal: create one shared design system for all pages, recorded in DESIGN.md so every
later session follows it. Plain HTML/CSS/JS only, no build step, no CSS framework.

1. Create DESIGN.md in the project root with exactly this direction:

   Concept: the visual language of an Indian commercial kitchen. Food reports are
   kitchen order tickets (KOT slips). Colours come from banana leaf, haldi, mirchi
   and stainless steel. Warm, practical, trustworthy; never cute, never corporate.

   Colour tokens (CSS custom properties):
     --leaf:      #1E5631  primary actions, "on the way", success
     --leaf-soft: #E3EFE4  success backgrounds
     --haldi:     #F2A900  attention, "new report", live/recording (background only;
                           text on it is --ink, never white)
     --haldi-soft:#FFF4D6
     --mirchi:    #C62E1F  deadlines, declines, errors, "nahi"
     --mirchi-soft:#FBE6E3
     --steel:     #D5DADF  borders, dividers, inactive
     --steel-dark:#5F6A74  secondary text
     --rice:      #FAFAF7  page background
     --paper:     #FFFFFF  KOT slip surface
     --ink:       #17261C  body text
   Status always uses colour + icon + word, never colour alone.
   State colours: reported = haldi, finding volunteer = steel, on the way = leaf,
   delivered = solid leaf, declined/expired/cancelled = mirchi.

   Type: "Baloo 2" (display, numbers, buttons) with "Baloo Chettan 2" for Malayalam
   and Devanagari covered by Baloo 2; body text "Hind" (Latin + Devanagari) with
   "Noto Sans Malayalam" fallback. Self-host the woff2 files in frontend/assets/fonts
   so the demo works offline. Type scale (rem): 0.875, 1, 1.25, 1.563, 1.953, 2.441,
   3.815 for hero numbers. Body line-height 1.5, display 1.1. Max line length 70ch.
   Quantities ("50 plates") are always set big in Baloo 2 semibold.

   Shapes: KOT slip = white paper, 4px radius, zig-zag torn bottom edge (CSS mask or
   SVG), faint dashed rule between lines. Buttons = 14px radius. The mic button is a
   perfect circle. No identical-card grids; hierarchy comes from size and spacing.
   Shadows only on the KOT slip (a soft paper shadow), nowhere else.

   Copy rules: sentence case everywhere, no ALL-CAPS labels, no eyebrow labels above
   headings, no arrows appended to buttons. Buttons say exactly what happens
   ("Send report", "Yes, I'll pick it up"). Errors say what happened and what to do,
   without apologising. Bilingual where it helps: primary language big, English small
   underneath (e.g. "Haan" / "Yes").

   Motion: only in response to actions or live events (recording pulse, ticket
   lines writing in, ticket sliding along the route). Nothing animates on page load
   except the first ticket. Respect prefers-reduced-motion.

   Accessibility floor: WCAG AA contrast, visible focus rings (3px --leaf outline),
   touch targets at least 56px (kitchen and volunteer buttons 88px+), works at 360px
   width with no horizontal scroll, every icon-only button has an aria-label.

2. Create frontend/assets/design.css with the tokens, font-faces, base typography,
   buttons (primary, secondary, danger, huge), status pills, the KOT slip component,
   the mic button component and form basics. Create frontend/assets/icons.svg with a
   small inline SVG icon sprite (mic, stop, play, check, cross, clock, pin, phone,
   bike, leaf/veg mark, non-veg mark, people, flame).
3. Create frontend/assets/kot.js: a reusable function that renders a report as a KOT
   slip (kitchen name, ticket number #BHK-0042, dish, quantity, cooked time, pickup
   deadline with countdown, veg/non-veg mark, status pill) and can update one line at
   a time with a short "writing in" animation.
4. Create frontend/styleguide.html showing every token and component, served by
   FastAPI, so I can review the system in one place.
5. Add a line to CLAUDE.md: "All UI follows DESIGN.md and uses frontend/assets/."

Do not redesign the individual pages yet. Show me a plan first, wait for my OK,
build, then take a Playwright screenshot of styleguide.html at 390px and 1280px
wide and tell me what you would improve.
```

---

## Prompt 1: kitchen screen

```
Read CLAUDE.md, DESIGN.md and frontend/kitchen/ first. Use frontend/assets/ only.

Goal: redesign the kitchen screen for a loud, hot kitchen. Staff have wet hands and
glance at it from a metre away. One thing to do at a time.

Layout (phone first, tablet landscape second):
- Top bar: kitchen name, language switch (Hindi / Malayalam / English as three big
  segmented buttons), small connection dot. Nothing else.
- Centre: one huge circular mic button (about 60vw on phone, max 320px), haldi
  ring. Hold to talk. While recording: the ring pulses with the live mic level
  (Web Audio AnalyserNode), a timer counts up, the label says "Bol rahe hain…
  chhodne par bhej denge" (or Malayalam/English). Releasing sends it.
- Below the mic: the KOT slip for the current report. As the server responds, the
  lines write in one by one (dish, quantity in big type, cooked time, deadline,
  veg mark). Missing fields show as an empty dashed line with the follow-up
  question next to it.
- Confirmation step: the slip stays, and two huge buttons appear under it:
  "Haan, sahi hai" (leaf) and "Nahi, badlo" (outline, mirchi). Voice still works
  too; buttons are a backup. While Timbre speaks, show a small speaker animation on
  the slip and disable the mic.
- Safety check step: two big yes/no questions shown one at a time with veg and
  covered icons.
- After confirmation: the slip gets a status pill that updates live (finding a
  volunteer / Arjun is on the way, 12 min / picked up / delivered) and a small
  route line kitchen -> volunteer -> NGO. "Ask status" and "Same as yesterday" become
  secondary buttons. "Last report" summary sits collapsed at the bottom.

States to design explicitly: first use (mic permission prompt explained in one
sentence), recording, sending (slip skeleton), mic blocked (how to allow it), no
network, server error, deadline already passed (mirchi slip with explanation).

Keep all existing behaviour and endpoints working. Plan first and show an ASCII
wireframe for phone and tablet. Wait for my OK, build, then Playwright-screenshot
every state at 390px and 1024px and fix anything cramped or unreadable.
```

---

## Prompt 2: volunteer screen

```
Read CLAUDE.md, DESIGN.md and frontend/volunteer/ first. Use frontend/assets/ only.

Goal: an offer should feel like an incoming phone call.

1. Off-duty / on-duty screen: volunteer name, area, capacity, and one big
   "Start duty" button (this also unlocks audio autoplay, keep that behaviour).
   On duty shows a calm leaf-soft screen: "You're on duty. We'll ring when food
   is ready nearby." plus today's rescues count.
2. Incoming offer: full-screen haldi background, ringing animation on a phone icon,
   kitchen name big, then the KOT slip (dish, quantity, pickup deadline countdown,
   veg mark), distance and estimated ride time, and the drop-off NGO. Timbre alert
   plays automatically. A thin countdown bar shows the offer timeout.
   Two huge buttons at the bottom like a call screen: "Nahi" (mirchi, left) and
   "Haan, le jaunga" (leaf, right). Voice reply also works; show a small listening
   indicator while it records.
3. Accepted: leaf screen with pickup and drop-off as two stops on a vertical route,
   "Open in maps" link (just a Google Maps search URL with the synthetic address),
   and a big "Picked up" then "Delivered" button flow.
4. Declined or timed out: brief "No problem, we've asked the next volunteer" then
   back to on-duty. Already taken by someone else: "Arjun already took this one,
   thank you."
5. Labels in the volunteer's language with small English underneath.

Plan first with ASCII wireframes, wait for my OK, build, then screenshot each state
at 390px and fix issues.
```

---

## Prompt 3: NGO screen

```
Read CLAUDE.md, DESIGN.md and frontend/ngo/ first. Use frontend/assets/ only.

Goal: the shelter coordinator's screen. Calmer than the kitchen, a bit more
information.

- Top: NGO name and today's summary (people served, meals received).
- Record a need: the same mic component as the kitchen (smaller, about 160px) with
  the extracted need shown as a "need slip" (same KOT component, leaf-soft tint):
  people count big, needed by, veg only.
- Incoming food: list of KOT slips heading to this NGO, each with the volunteer,
  ETA and status, ordered by arrival time.
- Delivery confirmation: when a delivery arrives, the slip expands with
  "Khana aa gaya?" and two big buttons plus voice reply, as now.
- Empty state: "No food on the way yet. Record what you need and nearby kitchens
  will be matched to it." with the mic button.

Plan first with an ASCII wireframe, wait for my OK, build, screenshot at 390px and
1280px.
```

---

## Prompt 4: dashboard

```
Read CLAUDE.md, DESIGN.md and frontend/dashboard/ first. Use frontend/assets/ only.

Goal: the coordinator's live view, and the screen judges see most in the demo.
It should read as a route board: tickets travelling from kitchens to shelters.

Layout (desktop first, 1280px+, must still work on tablet):
- Header: product name, "Live" indicator, phone-line mode badge (if on), and a
  quiet "Reset demo" button.
- Impact strip: meals rescued today in very large Baloo numerals, then rescues,
  people served, volunteers active. Plain numbers with plain labels, no gradients,
  no icons in boxes.
- Main area, the route board: four lanes left to right:
  "Reported" -> "Finding a volunteer" -> "On the way" -> "Delivered".
  Each report is a compact KOT slip. When its state changes, the slip slides to the
  next lane (FLIP animation, 300ms, disabled for reduced motion). Declined offers
  show as small mirchi marks on the slip ("Ravi said no"), so the fallback is
  visible. Deadline countdown on each slip turns mirchi under 30 minutes.
- Right side panel (opens when a slip is clicked): full timeline for that report:
  what the kitchen said (transcript, in its own script), extracted fields, safety
  answers, every volunteer tried with their reply and timing, NGO, delivery.
  Each step shows its latency in ms. Include a play button for each Timbre clip.
- Below the board: a small "Voice pipeline" panel with average speech-to-text,
  extraction and text-to-speech latency, and an "Open needs" list.
- Map: a simple SVG schematic of the Kochi area (no map library, no tiles): dots
  for kitchens (haldi), volunteers (leaf) and NGOs (steel-dark) placed by lat/lng,
  with the active route drawn as a line. Label areas (Vyttila, Edappally, Kakkanad,
  Tripunithura). Keep it small and clean.

Everything updates over the existing WebSocket. Plan first with an ASCII wireframe,
wait for my OK, build, then run a full mock flow and screenshot the dashboard at
four moments (new report, declined, on the way, delivered) at 1440px and 1024px.
```

---

## Prompt 5: home page and impact card

```
Read CLAUDE.md and DESIGN.md first. Use frontend/assets/ only.

1. Home page at "/": a one-screen introduction for judges and anyone who opens the
   link from the LinkedIn post.
   - Opening: a real KOT slip as the hero, writing itself in as if spoken:
     "50 plate biryani · Hotel Sagar, Vyttila · cooked 2 PM", with the headline
     "Leftover food, reported by voice and picked up within the hour" (or better
     copy you propose, plain and specific, no hype). Under it the live
     meals-rescued count from /impact.
   - How it works: three steps (kitchen speaks, volunteer gets a call, shelter
     receives), each shown with a tiny version of that screen. These are a real
     sequence, so numbering is fine.
   - Open the app: four clear links (Kitchen, Volunteer, Shelter, Dashboard) with
     one sentence each on who it's for.
   - Built on Gnani AI: Prisma v2.5 for speech-to-text and Timbre v2.5 for
     text-to-speech, the languages supported, and the eval results table from
     eval/RESULTS.md if it exists.
   - Honest note: prototype with synthetic data; partner organisations verify food.
   - Footer: project name, GitHub link placeholder, #GnaniAI
     #GreatIndianAIInternshipChallenge.
2. Restyle the impact card PNG (Pillow) to match: rice background, a KOT slip in the
   centre with the kitchen, dish and quantity, the route kitchen -> volunteer
   first name -> NGO, the date, and "Bacha Hua Khana · built on Gnani AI" small at
   the bottom. Use the self-hosted Baloo 2 font. 1080x1080 and 1080x1350 versions.

Plan first, wait for my OK, build, screenshot the home page at 390px and 1440px and
generate both card sizes for review.
```

---

## Prompt 6: polish pass (then freeze)

```
Read CLAUDE.md and DESIGN.md. No new features in this session.

1. Run a full mock flow (Hinglish and Malayalam) across all four screens at the same
   time and screenshot each screen at each step with Playwright. Review the
   screenshots against DESIGN.md and list every inconsistency: colours off-token,
   wrong fonts, all-caps labels, misaligned spacing, text overflowing at 360px,
   low contrast, missing focus states, buttons that don't say what they do.
2. Fix everything on that list.
3. Accessibility: keyboard-only walkthrough of each page, aria-live regions for
   status changes and new offers, alt text, prefers-reduced-motion check, Lighthouse
   accessibility score 95+ on every page (report the scores).
4. Performance: fonts preloaded and subset, no layout shift when the KOT lines write
   in, pages under 300 KB excluding audio.
5. Check every Malayalam and Hindi string renders in the right font with no tofu
   boxes.
6. Remove styleguide.html from the navigation (keep the file).
7. Give me a final screenshot set I can use in the README and the submission.
```

---

## Tips
- **Reviewing plans:** if a screen comes back as a grid of identical rounded cards with grey shadows, or with all-caps labels everywhere, reply "This looks like a generic template. Follow DESIGN.md: KOT slips, route lanes, quiet everything else."
- **Showing feedback:** paste the screenshot path back to Claude Code with a specific note ("quantity too small on 390px", "haldi text unreadable"). Specific notes get better fixes than "make it better".
- **For the demo:** record the dashboard and two phones side by side. The ticket sliding across the route board is the shot to build the video around.
