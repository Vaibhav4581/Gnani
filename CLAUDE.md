# Bacha Hua Khana: voice-first surplus food rescue

Entry for Gnani AI's Great Indian AI Internship Challenge (deadline 10 Nov 2026).
A kitchen reports leftover food by speaking; the app confirms by voice, matches it to
an NGO/shelter that has asked for food (also by voice), and alerts the best volunteer
by voice in their language to carry it there. Prototype only.

## Stack
- Backend: Python 3.10+ (the venv is 3.10), FastAPI, SQLModel + SQLite, httpx, pydub/ffmpeg,
  Pillow + uharfbuzz + fontTools for the impact cards (bundled Noto and Baloo fonts in app/fonts/)
- Frontend: plain HTML/CSS/JS ES modules served by FastAPI (no build step): frontend/home (served
  at "/"), kitchen, volunteer, ngo, dashboard, plus shared/ (base.css, common.js, recorder.js)
- Live updates: FastAPI WebSockets
- One service, one deploy. No auth, no microservices, no Docker unless asked.
- All UI follows DESIGN.md and uses frontend/assets/. Colours only from tokens; sentence case; no
  layout shift (is-loading/data-reveal for script-drawn first screens); language names in .lang-name;
  pages under 300 KB without audio (GZipMiddleware is on). Screenshots: docs/screenshots/.

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
  Every spoken phrase goes through speak(). `python -m app.tts_warm` lists which fixed phrases
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
  need -> volunteer-only pickup, ending at PICKED_UP.
- With a need, volunteer routes are volunteer -> kitchen -> NGO, and the alert names both.
- DELIVERED only for reports with a need: the volunteer taps "delivered", the NGO page
  asks "Khana aa gaya?", and the NGO's yes moves report and need to DELIVERED.
- Buttons are a backup for voice on the kitchen page, and skip STT (no credits): answer=yes|no
  on /reports/{id}/reply, answer=status|yes|no on /reports/{id}/ask, repeat=true on /reports/audio.
  They are logged as "button" events. Live kitchen messages carry volunteer, eta_min, ngo and reason
  so the page can say them in the kitchen's language (kitchen/strings.js).
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
volunteers and NGOs (seed.py), opens one demo need (seed.demo_need: Karunya Children's Home,
80 people, any food, ~3 h ahead) and sends `reset` to every page. For Annapurna Mess's
50 plates the ranking is Anjali Menon then John Mathew (Rahul 40 and Arjun 30 too small,
Deepa off duty), so the demo shows the fallback when Anjali says nahi. The TTS cache is kept.

## Code map (backend/app)
main.py routes · gnani.py / mock.py / audio.py speech I/O · languages/ one pack per language
(word lists + prompts) · extractor.py, confirm.py report understanding and read-back ·
safety.py · repeat.py · intents.py + ask.py kitchen questions · need_extractor.py + needs.py ·
matcher.py + offers.py (OfferEngine) · ws.py hub · dashboard.py + changes.py · impact.py,
cards.py, textdraw.py · eval_summary.py · seed.py · tts_warm.py. Tests: backend/tests (pytest, mock mode,
temp DB via conftest.py). Accuracy eval: eval/run_eval.py -> eval/RESULTS.md.

## Data model
Kitchen(id, name, lat, lng, phone, language)
Volunteer(id, name, lat, lng, phone, language, capacity, available)
Ngo(id, name, lat, lng, phone, language)
Need(id, ngo_id, people_count, veg_only, needed_by, status, created_at, transcript)
Report(id, kitchen_id, transcript, dish, quantity, unit, cooked_at, location, deadline, status, created_at,
       veg, covered (both from the safety check; nullable), need_id (nullable))
Offer(id, report_id, volunteer_id, rank, status, sent_at, responded_at, reply_transcript)
  (status PENDING / ACCEPTED / DECLINED / EXPIRED / WITHDRAWN)
Event(id, report_id, type, payload_json, latency_ms, ts)  (NGO need events carry need_id in the
  payload; report_id is null)
