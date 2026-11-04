# Bacha Hua Khana: voice-first surplus food rescue

Entry for Gnani AI's Great Indian AI Internship Challenge (deadline 10 Nov 2026).
A kitchen reports leftover food by speaking; the app confirms by voice, matches it to
an NGO/shelter that has asked for food (also by voice), and alerts the best volunteer
by voice in their language to carry it there. Prototype only.

## Stack
- Backend: Python 3.10+ (the venv is 3.10), FastAPI, SQLModel + SQLite, httpx, pydub/ffmpeg,
  Pillow + uharfbuzz + fontTools for the impact cards (bundled Noto and Baloo fonts in app/fonts/)
- Frontend: plain HTML/CSS/JS ES modules served by FastAPI (no build step): frontend/home (served
  at "/"), kitchen, volunteer, ngo, dashboard, plus shared/ (base.css, common.js) and
  assets/recorder.js (the mic, below)
- Live updates: FastAPI WebSockets
- One service, one deploy. No auth, no microservices, no Docker unless asked.
- All UI follows DESIGN.md and uses frontend/assets/. Colours only from tokens; sentence case; no
  layout shift (is-loading/data-reveal for script-drawn first screens); language names in .lang-name;
  pages under 300 KB without audio (GZipMiddleware is on). Screenshots: docs/screenshots/.
  On a laptop (>= 900px wide, kitchen/volunteer; 1000px shelter; 1200px dashboard; and >= 600px
  tall) each app screen is exactly one screen: no page scroll, and columns shrink or fold to fit
  (fitMic, fitRequests, fitLanes/fitSide), scrolling inside only as a last resort
  (DESIGN.md "One screen on a laptop"; check at 1366x650 and 1536x730, real browser windows).
  Phones scroll as before. Home (>= 1000px): top-bar tabs Home (hero, count, buttons, apps) /
  How it works / Built on Gnani AI / About, each one screen (home.js).

## Gnani APIs (the only external speech services allowed)
Base URL: https://api.vachana.ai, auth header `X-API-Key-ID: <GNANI_API_KEY>` from backend/.env
- STT (Prisma v2.5): POST /stt/v3, multipart: `audio_file`, `language_code` (e.g. hi-IN).
  Accepts WAV/MP3/OGG/FLAC/AAC/M4A, 8-44.1 kHz, max 60 s. Returns {success, request_id, transcript, model}.
  Browser MediaRecorder gives webm/opus: convert to 16 kHz mono WAV with ffmpeg first.
- TTS (Timbre v2.5): POST /api/v1/tts/inference, JSON:
  {text, voice, model: "timbre-v2.5", language, speed,
   audio_config: {sample_rate, num_channels: 1, sample_width: 2, encoding: "linear_pcm", container: "wav"}}
  Returns binary WAV.
- Existing client: backend/app/gnani.py (transcribe(), speak() with disk cache keyed by
  sha256(text|voice|language|speed); mock audio uses a separate `mock-` prefix). Reuse it.
  Every spoken phrase goes through speak(), as speak(for_voice(text, lang), ...): the Hindi voice
  misreads Roman Hinglish ("dal chawal", Kochi place names), so for_voice swaps each Roman word for
  its Devanagari spelling (languages/hi_voice.py) while the screen keeps the Roman text. A new
  Hindi prompt word, dish or name goes in hi_voice.py too (test_hindi_voice fails otherwise).
  Dish names: Prompts.dish_words writes them in the screen's script (hi: Devanagari -> Roman,
  ml/kn: Latin -> own script; en and the dashboard: any script -> Roman; languages.screen_dish),
  in read-backs, offers, the kitchen ticket
  (dish_shown) and the rail; the stored Report.dish stays as heard. Offers speak whole kilometres
  (offers.spoken_km: "6.2" is read "6 point 2"). gnani._post retries a 5xx/429/dropped
  connection once (seen live). Live checks: scratchpad-style scripts drove the whole workflow
  in all four languages against a second server (own DATABASE_URL, port 8779), 3 Nov. `python -m app.tts_warm` lists which fixed phrases
  are in the live cache (free); `--warm` synthesises the missing ones (spends credits).

## Rules
- Credits are limited (5,000). Cache all TTS by hash. Support MOCK_GNANI=1 to return canned
  STT/TTS responses so UI and logic work without spending credits. Tests must use mock mode.
- Synthetic data only: fake kitchens, volunteers, NGOs, phone numbers. Use Kochi-area coordinates.
- Never act on a guess: every report is confirmed by voice before matching.
- Log latency (ms) per stage (stt, extract, tts) into an Event table.
- Keep functions small and typed. Add pytest tests for extractor, classifier, matcher.
- Never print or commit the API key. .env is gitignored.
- Ask before anything that spends credits (live STT/TTS runs, tts_warm --warm, eval --transcribe).

## Domain flow
Chain: kitchen (supply) -> volunteer (courier) -> NGO/shelter (demand).
RECORDED -> TRANSCRIBED -> EXTRACTED -> CONFIRMING -> CONFIRMED -> SAFETY_CHECK -> MATCHING -> OFFERED -> ASSIGNED -> PICKED_UP -> DELIVERED
(CONFIRMED -> EXPIRED if the pickup deadline has passed when the safety check starts or ends;
 CONFIRMED .. ASSIGNED -> CANCELLED when the kitchen cancels by voice and confirms it)
- SAFETY_CHECK (safety.py): two spoken yes/no questions, "Khana veg hai?" -> Report.veg, then
  "Khana dhaka hua aur saaf bartan mein hai?" -> Report.covered. A no gets "Kripya khana dhak
  dijiye, phir haan boliye" until a yes. Only covered = yes goes to MATCHING; the offer engine
  also refuses any report whose covered is not True. Unclear answers repeat the question.
- Repeat ("kal jaisa" / "innale pole" / "same as yesterday", repeat.py): a new report copies
  dish, quantity, unit, location and veg from the kitchen's most recent report past
  CONFIRMING; the rest of the sentence overrides via the normal merge ("kal jaisa, bas 30
  plate"). cooked_time is never copied: asked unless said. It is still read back in full
  (with veg) and confirmed. A copied veg is dropped if the dish changes, and can be corrected
  while confirming; when it stays, the safety check asks only "covered?". No previous
  report: say so, and read the next reply as a full report.
- Corrections during CONFIRMING update only the changed fields.
- Missing required fields trigger a spoken follow-up question.
- Offer fallback: next-ranked volunteer on "no" or timeout (OFFER_TIMEOUT_SECONDS).
  Only volunteers with the page open (WebSocket connected = on duty) are offered; offline
  or busy ones are skipped. Ranking (matcher.py): available, capacity in plates >= quantity
  (1 kg/litre = 4 plates), arrives before the deadline (and the need), soonest first.
  Nobody fits: the report waits in MATCHING and is retried when a volunteer comes on duty
  (it is not marked EXPIRED automatically; its need is released after the deadline).
  A restart expires open offers and re-queues their reports.
- Pickup deadline = cooked_time + SAFE_WINDOW_HOURS (config).
- NGO needs: an NGO records a Need by voice (people_count, needed_by, veg_only) and
  confirms it the same way: CONFIRMING -> OPEN -> MATCHED -> DELIVERED (or EXPIRED).
- When matching starts, a report is matched to the best OPEN need: veg-compatible
  (veg_only needs get only food answered as veg; unknown or non-veg never), delivered before needed_by and before the
  food's deadline, feeds >= NEED_MIN_SHARE of the people; nearest NGO wins. No fitting
  need -> the default partner drop point (Ngo.is_default: Vyttila Community Kitchen, seed id 4,
  9.9673, 76.3183; Report.drop_ngo_id, "drop_point" event): routed volunteer -> kitchen -> drop
  point before the food's deadline, offer and dashboard say "Drop-off: <name> (no specific
  request open)" (alert_drop; ml/kn voices say drop_word for the Latin name). No one there
  confirms, so it still ends at PICKED_UP; the volunteer's "Delivered" only logs "dropped_off".
  A need confirmed while the food waits replaces the drop point.
- With a need, volunteer routes are volunteer -> kitchen -> NGO, and the alert names both.
- DELIVERED only for reports with a need: the volunteer taps "delivered", the NGO page
  asks "Khana aa gaya?", and the NGO's yes moves report and need to DELIVERED.
- Mic (assets/recorder.js, kitchen / volunteer / NGO): tap to talk, no holding. It stops itself
  on silence: the room is measured for 500 ms, speech = above room x SPEECH_FACTOR (1.8, floor
  MIN_THRESHOLD) for SPEECH_START_MS, then SILENCE_MS (1200) quiet sends; no speech in 6 s
  cancels ("Kuch sunai nahi diya…"), 20 s cap, a second tap stops early. All thresholds in
  LISTEN; createSpeechGate is pure and tested in Node (test_listen.py); ?debug=1 shows a panel
  and takes overrides (&factor=&silence=…). After a yes/no question (kitchen read-back with
  nothing missing, safety, cancel check; volunteer offer; NGO read-back, "Khana aa gaya?") the
  page calls listen() AFTER_VOICE_MS after the audio ends: tick + "Sun rahe hain…", gives up
  quietly after 8 s. Never records while audio plays (mic disabled; play() calls cancel()).
- Buttons are a backup for voice on the kitchen page, and skip STT (no credits): answer=yes|no
  on /reports/{id}/reply, answer=status|yes|no on /reports/{id}/ask, repeat=true on /reports/audio.
  They are logged as "button" events. Live kitchen messages carry volunteer, eta_min, ngo and reason
  so the page can say them in the kitchen's language (kitchen/strings.js).
- UI v2 friendlier (DESIGN.md "Helping first-timers"): rotating "for example" sentences under the
  kitchen and shelter mics come from the language packs (report_examples / need_examples, served on
  /kitchens and /ngos; test_examples runs each through the extractor). Kitchen: today strip
  (/impact?kitchen_id=), three first-time tips, start/stop tick + vibrate, Bigger text. Volunteer:
  ring + vibrate + live announcement, "Saying no is fine". Dashboard: "What am I looking at?",
  map <-> board highlighting. getJson throws on HTTP errors; failureKey(err) picks the message that
  says what to do next. All new strings in hi, ml, en and kn.
- UI v2 setting (DESIGN.md "The setting"): kolam dot grid, counter + thali under the kitchen mic, a
  ticket rail of today's reports (GET /kitchens/{id}/today; "Last report" shows only while it is
  empty), the volunteer's area map (on a laptop also off duty, beside Start duty and today's numbers)
  (GET /map, assets/map.js shared with the dashboard, hand-drawn backwaters) and "Your rescues"
  (recent on /volunteers/{id}/today), the shelter's pinboard, the dashboard's pass shelf.
  Illustrations (assets/illustrations.svg) only in the home hero and empty states.
- Volunteer screen: offers carry kitchen_point and ngo.point (synthetic lat/lng) for "Open in maps"
  (a maps pin, never a name search). A late answer to a closed offer is a 409 whose detail has
  taken_by (first name of the volunteer who accepted, if any). GET /volunteers/{id}/today counts that
  volunteer's finished rescues today, the same way impact.py does.
- Dashboard: a route board. Cards carry lane (reported / finding / on_way / delivered /
  closed; PICKED_UP without a need counts as delivered), declined (who said no or timed
  out) and kitchen_id / ngo_id / volunteer_id for the SVG map. The board has on_duty and map;
  /ws/dashboard also sends `duty` when on-duty volunteers change. Timeline entries carry ms,
  and tts lines carry audio (/tts/<file>).
- NGO screen: /ngos/{id}/needs gives each matched report's volunteer, eta_min to the NGO
  (accepted: ride to kitchen + kitchen->NGO; picked up: kitchen->NGO minus time since pickup;
  rounded to 5, arriving=true under 3 min), veg and deadline. GET /ngos/{id}/today: people
  served, meals and deliveries today (confirmed deliveries, counted like impact.py).
  /needs/{id}/reply takes answer=yes|no as a button (no STT).
- After CONFIRMED the kitchen can ask by voice (intents.py: STATUS / CANCEL / UNKNOWN,
  POST /reports/{id}/ask). Answers come from real state, in the kitchen's language,
  with ETA rounded to 5 min. CANCEL is asked back first; only a yes moves
  CONFIRMED..ASSIGNED -> CANCELLED, withdraws open offers (Offer WITHDRAWN), tells an
  assigned volunteer and reopens a reserved need. After PICKED_UP it is too late.
- Spoken wording never depends on a person's gender (the app doesn't store it).
- A name in a script the listener's voice can't read is spoken as a generic word
  (food_word, shelter_word, volunteer_word in the language packs).
- Impact (impact.py) counts finished rescues only (DELIVERED, or PICKED_UP without a need):
  plates/boxes = 1 meal, kg/litre x MEALS_PER_KG (labelled estimated). Each finished rescue
  has a card at /cards/{id}.png (format=square 1080x1080 or portrait 1080x1350): a KOT slip on
  rice in Baloo (textdraw display=True), drawn once per size (under a lock) into CARDS_DIR.
- Home page "/": hero slip, live count from /impact, three steps, links, Gnani section with
  the eval table from GET /eval/summary (eval_summary.py reads eval/RESULTS.md; 404 if absent).

## Demo reset
POST /admin/seed?confirm=true deletes Report, Offer, Need and Event rows, re-seeds kitchens,
volunteers and NGOs (seed.py), adds a synthetic day so far (demo_history.py: 4 finished
rescues and 2 on the way today, 2 yesterday, with their needs, offers and events; no speech
calls; history=false skips it), opens one demo need (seed.demo_need: Karunya Children's Home,
80 people, any food, ~3 h ahead) and sends `reset` to every page. The history never waits
for a volunteer, holds no pending offer and leaves no other open need, so the live demo
below is unchanged (test_demo_history). For Annapurna Mess's
50 plates the ranking is Anjali Menon then John Mathew (Rahul 40 and Arjun 30 too small,
Deepa off duty), so the demo shows the fallback when Anjali says nahi. The TTS cache is kept.

## Code map (backend/app)
main.py routes · gnani.py / mock.py / audio.py speech I/O · languages/ one pack per language
(word lists + prompts) · extractor.py, confirm.py report understanding and read-back ·
safety.py · repeat.py · intents.py + ask.py kitchen questions · need_extractor.py + needs.py ·
matcher.py + offers.py (OfferEngine) · ws.py hub · dashboard.py + changes.py · impact.py,
cards.py, textdraw.py · eval_summary.py · seed.py, demo_history.py · tts_warm.py. Tests: backend/tests (pytest, mock mode,
temp DB via conftest.py). Accuracy eval: eval/run_eval.py -> eval/RESULTS.md.

## Data model
Kitchen(id, name, lat, lng, phone, language)
Volunteer(id, name, lat, lng, phone, language, capacity, available)
Ngo(id, name, lat, lng, phone, language, is_default)
Need(id, ngo_id, people_count, veg_only, needed_by, status, created_at, transcript)
Report(id, kitchen_id, transcript, dish, quantity, unit, cooked_at, location, deadline, status, created_at,
       veg, covered (both from the safety check; nullable), need_id (nullable),
       drop_ngo_id (nullable: the default drop point when no need fitted))
Offer(id, report_id, volunteer_id, rank, status, sent_at, responded_at, reply_transcript)
  (status PENDING / ACCEPTED / DECLINED / EXPIRED / WITHDRAWN)
Event(id, report_id, type, payload_json, latency_ms, ts)  (NGO need events carry need_id in the
  payload; report_id is null)
