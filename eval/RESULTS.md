# Bacha Hua Khana: speech understanding evaluation

Run 25 Oct 2026. 18 labelled recordings (4 English, 4 Hindi, 5 Kannada, 5 Malayalam), plus 18 noisy versions, transcribed with Gnani Prisma v2.5 (`format=transcribe`) and read by the app's rule-based extractor and reply classifier. A check passes only if it matches what was **spoken**, so speech-to-text errors count against us.

**Whole clips right:** quiet 16/18 (89%), noisy 16/18 (89%), telephony 16/18 (89%).

## Quiet vs noisy vs phone line

| Check | Quiet (18 clips) | Noisy (18 clips) | Telephony (18 clips) |
|---|---|---|---|
| dish | 5/7 (71%) | 5/7 (71%) | 5/7 (71%) |
| quantity | 6/7 (86%) | 6/7 (86%) | 6/7 (86%) |
| unit | 6/7 (86%) | 6/7 (86%) | 6/7 (86%) |
| cooked_time | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| location | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| yes/no replies | 8/8 (100%) | 8/8 (100%) | 8/8 (100%) |
| **whole clip right** | 16/18 (89%) | 16/18 (89%) | 16/18 (89%) |

- **Quiet:** clean recordings through the app's normal 16 kHz pipeline.
- **Noisy:** the same sentences with kitchen-style background noise mixed in.
- **Telephony:** the quiet clips passed through `audio.to_telephony()`, as the app does with `TELEPHONY_MODE=1`: 8 kHz mono, 300–3400 Hz band-pass, light compression, G.711 μ-law codec.

> All speech is Gnani Timbre TTS voices reading known sentences, not real kitchen staff; expect lower accuracy on real accents. Noisy clips have synthetic noise (fan hum plus random clatter, about 10 dB below the speech, from `eval/make_noisy_clips.py`), not real kitchen recordings.

## Quiet clips in detail

### Fields by language

| Field | en-IN | hi-IN | kn-IN | ml-IN | All |
|---|---|---|---|---|---|
| dish | 1/2 (50%) | 1/1 (100%) | 1/2 (50%) | 2/2 (100%) | 5/7 (71%) |
| quantity | 1/2 (50%) | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) | 6/7 (86%) |
| unit | 1/2 (50%) | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) | 6/7 (86%) |
| cooked_time | 2/2 (100%) | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) | 7/7 (100%) |
| location | 2/2 (100%) | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) | 7/7 (100%) |
| **every field right** | 1/2 (50%) | 1/1 (100%) | 1/2 (50%) | 2/2 (100%) | 5/7 (71%) |

### Replies

| Expected reply | Classified correctly |
|---|---|
| yes | 4/4 (100%) |
| no | 4/4 (100%) |
| correction | 3/3 (100%) |
| **yes/no overall** | 8/8 (100%) |

### Where the errors come from

Each clip is scored twice: from what Prisma heard, and from the exact words. A gap between the columns is speech-to-text error; what fails in both is the extractor.

| Check | From speech (end to end) | From the exact words (extractor only) |
|---|---|---|
| answer | 11/11 (100%) | 11/11 (100%) |
| dish | 5/7 (71%) | 7/7 (100%) |
| quantity | 8/9 (89%) | 9/9 (100%) |
| unit | 8/9 (89%) | 9/9 (100%) |
| cooked_time | 8/8 (100%) | 8/8 (100%) |
| location | 7/7 (100%) | 7/7 (100%) |
| **whole clip right** | 16/18 (89%) | 18/18 (100%) |

## Clips with errors (6 of 54 runs)

| Condition | Clip | Heard (Prisma) | What went wrong |
|---|---|---|---|
| noisy | noisy/05-kn-report-rice-sambar-noisy.wav | 20 ಕೆ ಜಿಯನ್ನು ಸಾಂಬಾರಿದೆ ಬೆಳಿಗ್ಗೆ 11:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು | dish: got 'ಸಾಂಬಾರ್', expected 'ಅನ್ನ ಸಾಂಬಾರ್' |
| noisy | noisy/08-en-report-fried-rice-noisy.wav | 01:30 | dish: got None, expected 'fried rice'; quantity: got None, expected 30; unit: got None, expected 'kg' |
| quiet | synthetic/05-kn-report-rice-sambar.wav | 20 ಕೆ ಜಿಯನ್ನು ಸಾಂಬಾರಿದೆ ಬೆಳಿಗ್ಗೆ 11:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು | dish: got 'ಸಾಂಬಾರ್', expected 'ಅನ್ನ ಸಾಂಬಾರ್' |
| quiet | synthetic/08-en-report-fried-rice.wav | 01:30 | dish: got None, expected 'fried rice'; quantity: got None, expected 30; unit: got None, expected 'kg' |
| telephony | synthetic/05-kn-report-rice-sambar.wav | 20 ಕೆ ಜಿಯನ್ನು ಸಾಂಬಾರಿದೆ ಬೆಳಿಗ್ಗೆ 11:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು | dish: got 'ಸಾಂಬಾರ್', expected 'ಅನ್ನ ಸಾಂಬಾರ್' |
| telephony | synthetic/08-en-report-fried-rice.wav | 01:30 | dish: got None, expected 'fried rice'; quantity: got None, expected 30; unit: got None, expected 'kg' |
