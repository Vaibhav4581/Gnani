# Bacha Hua Khana: fill the space and make it friendlier

Run after PROMPTS_UI.md. Two sessions, both today/tomorrow, then freeze.
Commit first: `git commit -am "before UI v2"`

The aim is not decoration. Empty space gets filled two ways:
1. **A kitchen setting:** a faint kolam dot-grid texture, a steel ticket rail, a counter
   surface, a schematic map of Kochi. Each screen feels like a place.
2. **Useful content where there's nothing yet:** example phrases, today's numbers,
   recent tickets, nearby kitchens. An empty screen should tell people what to do.

---

## Prompt A: backgrounds, surfaces and illustrations

```
Read CLAUDE.md, DESIGN.md and frontend/ first. Use frontend/assets/ only, no new
libraries, no images heavier than inline SVG or CSS.

Problem: every page sits on a flat --rice background and feels empty. Give each
screen a setting drawn from an Indian kitchen, kept quiet so KOT slips and the
mic button still stand out. Update DESIGN.md with every new token and rule.

1. Global texture: a kolam-style dot grid on the page background (CSS
   radial-gradient dots, 22-26px spacing, --steel at about 40% opacity, 1.5px
   dots). On the home page and empty states only, add a few faint kolam loops
   (thin SVG curves joining dots, --steel-dark at 12% opacity) in one corner.
   Never behind text blocks at full strength; check AA contrast still passes.

2. New surface tokens:
     --counter:      #E9ECEA  stainless counter surface
     --counter-edge: #C3C9CE  counter top edge
     --rail:         #8A949C  ticket rail bar
     --leaf-deep:    #143D23  dark leaf for large illustrated areas
   Use solid fills, no gradient washes, no glassmorphism.

3. Kitchen screen:
   - Top: a steel ticket rail (a 6px --rail bar with small clips) holding today's
     reports as mini KOT slips, scrollable sideways, newest first, each with its
     status colour. Empty rail says "Today's reports will hang here."
   - The mic sits in the middle of a --counter band that fills the lower 55% of
     the screen, with a --counter-edge top line, like the mic is on the counter.
   - Behind the mic, a faint thali circle (two concentric steel rings) that the
     live mic level ring animates inside.

4. Volunteer screen (on duty, waiting):
   - Fill the screen with a small schematic SVG map of the volunteer's area
     (same style as the dashboard map): their dot pulsing gently, nearby kitchens
     and shelters as dots, area names. Caption: "You're on duty in Vyttila."
   - Below: "Your rescues" as a small stack of past KOT slips (or an empty state
     with a scooter illustration: "Your first pickup will show up here").
   - Incoming offer keeps the full haldi screen, plus a faint enlarged phone-ring
     line pattern behind the kitchen name.

5. NGO screen: a soft --leaf-soft board behind the needs list, with need slips
   pinned (a small steel pin at the top of each slip).

6. Dashboard:
   - Lane headers styled as a steel kitchen pass shelf (a --counter strip with a
     --counter-edge line), lane bodies on the dot-grid background.
   - The Kochi schematic map gets backwaters: a few thin, faint blue-grey curves
     (#C9D6DC) for the backwaters and the sea edge, drawn by hand in SVG. No tiles.
   - Empty lanes show a dashed slip outline with one helpful line ("New reports
     arrive here when a kitchen speaks").

7. Illustrations: create a small set of simple, flat inline SVGs in the palette,
   2-3 colours each, rounded line ends, consistent 2px stroke: banana leaf,
   steel tiffin, scooter with a delivery bag, shelter building, thali. Put them in
   frontend/assets/illustrations.svg as a sprite. Use them only in: home hero,
   empty states, and the volunteer "no rescues yet" state.

8. Home page hero: the self-writing KOT slip placed on a large banana leaf
   illustration (--leaf and --leaf-deep), slightly rotated, with a tiffin beside
   it. This is the one bold image in the product; everything else stays restrained.

Plan first with an ASCII sketch per screen and wait for my OK. Then build and take
Playwright screenshots of every screen at 390px and 1280px, compare against the
old screenshots, and tell me where the background now competes with content.
Fix those spots.
```

---

## Prompt B: make it friendlier

```
Read CLAUDE.md and DESIGN.md first. No new backend features; small endpoint
additions only if a screen needs data that already exists.

Goal: anyone can use each screen within 10 seconds without being told how.

Kitchen screen:
1. Idle hint under the mic, in the kitchen's language with English below:
   "Hold the button and say what's left, for example:" then one example that
   rotates every 6 seconds ("Pachaas plate biryani bachi hai, do baje bani thi" /
   "Ambathu plate biryani und, randu manikku undakkiyathu" / "Fifty plates of
   biryani, made at 2 pm"). Rotation pauses under reduced motion.
2. Today strip: "Today: 3 reports, 140 meals shared" from /impact for this kitchen.
3. First-time coach marks (3 steps max, dismissable, remembered in localStorage
   with try/catch): mic button, the slip, the Haan/Nahi buttons.
4. Sound and touch feedback: short soft tick when recording starts and stops,
   navigator.vibrate(30) on phones (feature-checked), so staff know it heard them
   without looking.
5. A "Bigger text" toggle in the top bar (scales root font size 1.25x).

Volunteer screen:
6. Vibrate pattern plus ring sound for a new offer; the offer screen announces
   itself in an aria-live region.
7. One-line explanation under Haan/Nahi: "Saying no is fine, we'll ask someone else."

NGO screen:
8. Example phrase under the mic like the kitchen screen.

Dashboard:
9. A "What am I looking at?" toggle that shows a one-line explanation over each
   lane and the impact strip, for judges seeing it for the first time.
10. Hovering or focusing a map dot highlights its slips on the board and vice versa.

Everywhere:
11. Loading states use the slip skeleton, never a spinner alone.
12. Every error tells the person what to do next ("Can't reach the server.
    Check the internet and hold the button again.").
13. All new strings in hi, ml and en.

Plan first, wait for my OK, build, then do a 10-second test: screenshot each screen
in its first-visit state and tell me, for each one, what a first-time user would
do first. If the answer isn't the right action, fix the screen.
```

---

## After both
- Run Prompt 6 from PROMPTS_UI.md (the polish pass) again. It catches contrast and
  spacing problems the new backgrounds introduce.
- Freeze. Record the demo on 4-5 Nov, post on 6 Nov.
