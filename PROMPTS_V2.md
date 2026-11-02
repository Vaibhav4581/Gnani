# Bacha Hua Khana: enhancement prompts (V2)

One feature per Claude Code session. Order matters: later features build on earlier ones.

## Before every session
1. `git status` should be clean. Commit: `git commit -am "before feature N"`
2. Keep `MOCK_GNANI=1` while building. Switch to `0` only for the final real test of each feature.
3. After each feature: run `pytest`, test the full flow once in the browser, then commit.
4. If Claude Code proposes React, Docker, auth or new services, tell it to stick to CLAUDE.md.

## Suggested schedule (feature freeze 2 Nov)
| Date | Feature |
|---|---|
| 25-26 Oct | 1. Telephony eval mode |
| 26-28 Oct | 2. Malayalam / Manglish flow |
| 28-29 Oct | 3. NGO demand side |
| 29-30 Oct | 4. Impact card |
| 30-31 Oct | 5. Voice status check + 6. Safety check |
| 1 Nov | 7. "Same as yesterday" |
| 2 Nov | 8. Final integration pass, freeze |

If you fall behind, drop 7, then 5. Never drop 1 or 2.

---

## Feature 1: telephony eval mode (Noise Canceller award)

```
Read CLAUDE.md, backend/app/audio.py and eval/run_eval.py first.

Goal: prove the app works on narrow-band phone-line audio, not just clean mic audio.

Build:
1. audio.py: add to_telephony(path) -> path that resamples to 8 kHz mono 16-bit,
   applies a 300-3400 Hz band-pass filter, and lightly compresses, so it sounds like
   a phone call. Keep the existing 16 kHz conversion unchanged.
2. Config flag TELEPHONY_MODE (default 0). When 1, the live app passes every
   uploaded clip through to_telephony() before Prisma.
3. eval/run_eval.py: add --mode clean|telephony|all. Cache transcripts per mode in
   eval/transcripts_<mode>.json so reruns spend no credits. Clips can be tagged
   quiet/noisy in their ground-truth JSON ("condition" field).
4. Output a comparison table: rows = field (dish, quantity, unit, cooked_time,
   location) + yes/no accuracy; columns = quiet / noisy / telephony. Also write it
   to eval/RESULTS.md as markdown, ready to paste into the submission.
5. Show the mode on the dashboard (small "Phone line mode" badge) so it is visible
   in the demo.
6. Tests: to_telephony output is 8 kHz mono; eval cache is reused (no API call when
   cached), using mock mode.

Process: show a short plan and file list, wait for my OK, build, run tests, then
give me the exact eval commands.
```

---

## Feature 2: full Malayalam and Manglish flow (Main Character / Small Town)

```
Read CLAUDE.md, backend/app/extractor.py, confirm.py and gnani.py first.

Goal: a Kochi kitchen can report in Malayalam or Manglish and hear the
confirmation back in Malayalam. The Hinglish flow must keep working.

Build:
1. Language per kitchen (Kitchen.language: hi-IN, ml-IN, en-IN). Kitchen page gets
   a one-time language picker (big buttons: Hindi, Malayalam, English) stored in
   localStorage with try/catch. Pass language to Prisma.
2. Check the Gnani STT docs for an automatic language detection option. If it
   exists, add LANG_AUTO=1 support; if not, keep the picker. Tell me which.
3. extractor.py: refactor into language packs (extractor/lang_hi.py, lang_ml.py,
   lang_en.py) behind the same interface. Malayalam pack handles:
   - number words in Malayalam script and Manglish (onnu, randu, moonnu, naalu,
     anju, pathu, irupathu, muppathu, nalpathu, ambathu, nooru, irunooru...)
   - Manglish phrasing ("biryani baakki und", "ambathu plate", "Vyttila il")
   - time words (raavile, uchakku, vaikunneram, "rendu manikku")
   Transcripts may come back in Malayalam script or romanised; handle both.
4. confirm.py: confirmation templates per language, Malayalam yes/no keywords
   (athe, sheri, ok, aanu / illa, alla, venda, thettu). Corrections still merge
   only changed fields.
5. Timbre: speak confirmations in the kitchen's language. Pick a Malayalam voice
   from the voice catalog and put it in .env as TTS_VOICE_ML.
6. Tests: at least 10 Malayalam/Manglish extractor cases (both scripts), Malayalam
   yes/no/correction classification, and all existing Hinglish tests still pass.
7. Add 5 Malayalam ground-truth templates in eval/ so I can record matching clips.

Process: plan first and wait for my OK. Do not change matching or the dashboard.
```

---

## Feature 3: NGO demand side (Real Deal)

```
Read CLAUDE.md, models.py, matcher.py and offers.py first.

Goal: food goes to where it is needed, not just to the nearest volunteer.
Chain becomes: kitchen (supply) -> volunteer (courier) -> NGO/shelter (demand).

Build:
1. Models: Ngo(id, name, lat, lng, phone, language) and
   Need(id, ngo_id, people_count, veg_only, needed_by, status, created_at,
   transcript). Report gets need_id. Seed 3 synthetic NGOs/shelters in Kochi.
2. NGO page (frontend/ngo/): hold-to-talk need recording, e.g.
   "aaj raat 80 logon ke liye khana chahiye" / Malayalam equivalent. Reuse the
   extractor pattern: people_count, needed_by, veg_only. Voice confirmation loop
   exactly like the kitchen flow.
3. Need matching (matcher.py): for a CONFIRMED report, pick the best open Need by
   (needed_by after pickup is possible, deadline still met, quantity covers a
   reasonable share of people_count, distance kitchen->NGO, veg compatibility).
   Add a nullable Report.veg field now; while it is null, only match needs with
   veg_only = false (Feature 6 will fill it by voice later).
   If no need matches, fall back to the current volunteer-only behaviour.
4. Volunteer matching now uses distance volunteer->kitchen plus kitchen->NGO, and
   the volunteer alert says where to collect AND where to deliver.
5. On delivery, the NGO page plays "Khana aa gaya? Haan/nahi" and the reply moves
   the report to DELIVERED. Add DELIVERED after PICKED_UP in the state flow and
   update CLAUDE.md.
6. Dashboard: show the full chain per report (kitchen -> volunteer -> NGO) and an
   "open needs" list.
7. Tests: need matching (veg filter, deadline, distance), fallback when no need,
   state transitions to DELIVERED.

Process: plan first and wait for my OK.
```

---

## Feature 4: impact summary and shareable card

```
Read CLAUDE.md and the dashboard code first.

Goal: visible impact numbers and a shareable image per completed rescue.

Build:
1. Impact endpoint GET /impact: meals rescued (sum of quantity for DELIVERED or
   PICKED_UP reports with unit plate/box; convert kg using a MEALS_PER_KG config
   value, default 4, and label it as an assumption), number of rescues, kitchens,
   volunteers, NGOs, people served (from Needs). Today and all-time.
   Counted numbers only. No CO2 or money estimates.
2. Dashboard: a big impact strip at the top that updates live over WebSocket.
3. Impact card: when a report reaches DELIVERED (or PICKED_UP if no NGO), generate
   a 1080x1080 PNG with Pillow: "Hotel Sagar shared 50 meals", volunteer first name,
   NGO name, date, "Bacha Hua Khana · built on Gnani AI". Clean design, large type,
   works for Instagram/LinkedIn. Serve at GET /cards/{report_id}.png.
4. A "Share" button on the dashboard per report that opens the card and offers
   download.
5. Bundle a free font (e.g. Noto Sans + Noto Sans Malayalam/Devanagari) so names in
   any script render.
6. Tests: impact numbers from seeded data, card file generated with expected size.

Process: plan first and wait for my OK.
```

---

## Feature 5: voice status check

```
Read CLAUDE.md, confirm.py and offers.py first.

Goal: after confirming, the kitchen can hold the mic and ask
"volunteer kab aayega?" / "aaraanu varunnathu?" and hear the live status.

Build:
1. Intent classifier (intents.py) with keyword sets per language for:
   STATUS ("kab aayega", "kaun aa raha", "status", "eppo varum", "aaraanu"),
   CANCEL ("cancel", "rehne do", "venda"), and UNKNOWN. Keep yes/no in confirm.py.
2. POST /reports/{id}/ask: audio in -> transcript -> intent -> spoken answer from
   real state, e.g. "Arjun aa raha hai, lagbhag 12 minute mein" (ETA = distance /
   AVG_SPEED_KMPH config), "Abhi volunteer dhoondh rahe hain", "Khana pahunch gaya".
   CANCEL moves the report to CANCELLED and withdraws open offers.
3. Kitchen page: after confirmation, show a "Ask status" hold-to-talk button and
   the live status line.
4. Answers in the kitchen's language (hi-IN / ml-IN / en-IN). Cache TTS.
5. Tests: intent classification per language, status answers for each state,
   cancel withdraws offers.

Process: plan first and wait for my OK.
```

---

## Feature 6: spoken safety check

```
Read CLAUDE.md and confirm.py first.

Goal: make food safety concrete. After the report is confirmed, Timbre asks two
quick yes/no questions before matching starts.

Build:
1. Questions (per language): "Khana veg hai?" and "Khana dhaka hua aur saaf
   bartan mein hai?" (Malayalam and English equivalents).
2. New state SAFETY_CHECK between CONFIRMED and MATCHING. Store veg (bool) and
   covered (bool) on Report.
3. If covered = no: speak "Kripya khana dhak dijiye, phir haan boliye" and wait
   for a yes before matching. Never match uncovered food.
4. If the pickup deadline has already passed at this point, speak that it cannot
   be picked up and mark the report EXPIRED.
5. veg flag feeds Feature 3 need matching (veg_only NGOs only get veg food).
6. Show veg/non-veg and covered badges on the dashboard and in the volunteer alert.
7. Update the state flow in CLAUDE.md.
8. Tests: both answers, the "cover it first" loop, expired deadline, veg filter.

Keep it to two questions so the flow stays fast. Plan first and wait for my OK.
```

---

## Feature 7: "same as yesterday" for regular donors

```
Read CLAUDE.md, extractor.py and confirm.py first.

Goal: a hostel or canteen that reports daily can say "kal jaisa" / "innale
pole" / "same as yesterday" and skip dictating everything again.

Build:
1. Repeat intent keywords per language, plus optional overrides in the same
   sentence: "kal jaisa, bas 30 plate" updates only quantity.
2. Look up the kitchen's most recent CONFIRMED report; copy dish, unit, location
   and veg; set cooked_time to today (ask for it if the template had a time and
   none was given now). Apply overrides via the existing merge logic.
3. Always read back the full filled-in report for confirmation. Never skip the
   confirmation loop.
4. If there is no previous report, say so and ask for a full report.
5. Kitchen page: show "Last report" summary card so staff know what "kal jaisa"
   will copy.
6. Tests: repeat with no override, with override, no previous report, each
   language.

Plan first and wait for my OK.
```

---

## Feature 8: final integration pass (2 Nov, then freeze)

```
Read CLAUDE.md and the whole codebase.

Goal: make everything solid for the demo. No new features.

1. Run all tests and fix failures.
2. Walk the full state machine for one Hinglish and one Malayalam report end to
   end (kitchen -> safety -> NGO need -> volunteer decline -> fallback -> pickup ->
   delivered -> impact card) in mock mode, and list anything broken.
3. Check every Timbre phrase is cached and every page works on a mobile screen.
4. Make /admin/seed reset everything into a clean demo state, with one open NGO
   need and volunteers ranked so the fallback happens in the demo.
5. Update README: feature list, architecture diagram (Mermaid), state diagram,
   how to run, eval results from eval/RESULTS.md, honest limits, what's next.
6. Update CLAUDE.md so it matches the final code.
7. Give me a checklist of anything that still needs a real (non-mock) test.
```

---

## After the freeze
- Record new eval clips covering Malayalam and the safety and repeat flows, then run `python eval/run_eval.py --mode all` and paste `eval/RESULTS.md` into the submission.
- Rehearse the demo against a fresh `/admin/seed`.
- Re-check the credit balance before demo week and keep about 1,000 in reserve.
