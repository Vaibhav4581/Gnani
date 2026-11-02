# Claude Code prompts, one per session

Commit before each phase: git commit -am "phase N done"

## Phase 1: kitchen loop
```
Read CLAUDE.md and backend/app/gnani.py first.

Goal for this session: Phase 1, the kitchen loop working end to end.
Kitchen speaks a report -> transcript -> structured fields -> spoken confirmation ->
staff replies yes / no / correction -> report reaches CONFIRMED.

Build:
1. Project structure: backend/app/{main.py, config.py, models.py, db.py, gnani.py,
   audio.py, extractor.py, confirm.py, mock.py}, backend/tests/, frontend/kitchen/,
   README with run steps. requirements.txt, .env.example and .gitignore already exist.
2. audio.py: convert uploaded webm/ogg to 16 kHz mono WAV using ffmpeg (pydub).
3. MOCK_GNANI=1 support in gnani.py: canned transcript and a short silent WAV.
4. extractor.py, rule-based only for now: from Hinglish/English transcripts extract
   dish, quantity (digits and Hindi number words like pachaas, sau, do sau),
   unit (plate/kg/litre/box), cooked_time (e.g. "do baje", "2 baje", "subah 11"),
   location. Return missing fields explicitly. Design it so an LLM extractor can
   be plugged in later behind the same interface.
5. confirm.py: build the confirmation sentence; classify replies as yes / no /
   correction using keyword sets (haan, ha, sahi, theek, yes, ok / nahi, galat, no);
   on correction, re-extract and merge only the fields present in the reply;
   ask a follow-up question for any missing required field.
6. Endpoints: POST /reports/audio (upload -> report draft + confirmation audio URL),
   POST /reports/{id}/reply (audio reply -> next state + audio URL),
   GET /tts/{file} (serve cached audio). Record stage latencies in Event.
7. Kitchen page: big hold-to-talk button (MediaRecorder), shows transcript and the
   extracted fields as a card, plays the confirmation audio, then lets staff reply
   by voice. Mobile-friendly, large touch targets.
8. Pytest tests (mock mode) for at least 10 extractor cases, the yes/no/correction
   classifier, and correction merging.

Process:
- Start by showing me a short plan and the file list. Wait for my OK before writing code.
- After building, run the tests and fix failures.
- Then give me exact commands to run the server and test it in the browser.
- Do not build matching, volunteers or the dashboard yet.
```

## Phase 2: matching and volunteers
```
Read CLAUDE.md. Phase 2: seed 3 kitchens and 8 volunteers around Kochi
(Tripunithura, Vyttila, Edappally, Kakkanad) with mixed languages.
Build matcher.py (haversine, filter available + capacity + can arrive before deadline,
ranked list) and offers.py (asyncio offer engine with timeout fallback, idempotent
accept). Add a volunteer page: "I'm on duty" button to unlock audio autoplay,
receives offers over WebSocket, plays a ring then the Timbre alert in the volunteer's
language, records haan/nahi. Tests for matcher and fallback. Plan first, then build.
```

## Phase 3: dashboard
```
Read CLAUDE.md. Phase 3: dashboard page with live WebSocket updates. Three columns
(Reported, Matched, Picked up), a per-report timeline (transcript, fields, each
volunteer tried, outcome), and average latency per stage. Add POST /admin/seed
to reset demo data and a "mark picked up" action. Plan first, then build.
```

## Phase 4: evaluation
```
Read CLAUDE.md. Phase 4: eval/run_eval.py. For each clip in eval/audio/ with a
matching ground-truth JSON, transcribe once (cache transcripts to eval/transcripts.json
so reruns spend no credits), run the extractor, and report per-field accuracy and
yes/no accuracy as a table plus a markdown summary for the submission.
```
