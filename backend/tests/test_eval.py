"""eval/run_eval.py: clip discovery, per-mode transcript caches, scoring and RESULTS.md."""
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
sys.path.insert(0, str(EVAL_DIR))  # make_noisy_clips imports run_eval by name


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EVAL_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_eval = _load("run_eval")
make_noisy_clips = _load("make_noisy_clips")


def add_clip(folder: Path, name: str, meta: dict, audio: bytes = b"RIFF fake") -> Path:
    wav = folder / f"{name}.wav"
    wav.write_bytes(audio)
    wav.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return wav


@pytest.fixture
def setup(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(run_eval, "CACHE_DIR", tmp_path)
    return audio_dir, tmp_path


def cache_transcript(wav: Path, language: str, text: str, mode: str = "clean") -> None:
    cache = run_eval.load_cache(mode)
    cache[run_eval.cache_key(wav, language, run_eval.settings.stt_format)] = {"transcript": text}
    run_eval.save_cache(cache, mode)


def no_api(*_args, **_kwargs):
    pytest.fail("Gnani was called although the transcript was cached")


@pytest.mark.parametrize("name,want,got,ok", [
    ("dish", "Veg Biryani", "veg biryani", True),
    ("dish", ["dal chawal", "dal rice"], "dal rice", True),
    ("dish", "fried rice", None, False),
    ("quantity", 50, 50.0, True),
    ("quantity", 50, 60.0, False),
    ("cooked_time", "14:00", datetime(2026, 1, 1, 14, 0), True),
    ("cooked_time", "14:00", None, False),
    ("location", None, None, True),
    ("location", None, "Half Past", False),
    ("location", "Kakkanad", "Kakkanad", True),
])
def test_field_ok(name, want, got, ok):
    assert run_eval.field_ok(name, want, got) is ok


def test_load_clips_reads_condition_and_needs_ground_truth(setup):
    audio_dir, _ = setup
    add_clip(audio_dir, "a", {"language": "hi-IN", "expected": {"quantity": 50}})
    add_clip(audio_dir, "n", {"language": "hi-IN", "condition": "noisy", "expected": {}})
    (audio_dir / "b.wav").write_bytes(b"x")  # no JSON
    for leftover in ("a.16k.wav", "a.8k.wav"):  # conversion leftovers, ignored
        (audio_dir / leftover).write_bytes(b"x")
    clips, unlabelled = run_eval.load_clips(audio_dir)
    assert [(c.name, c.condition) for c in clips] == [("a.wav", "quiet"), ("n.wav", "noisy")]
    assert unlabelled == ["b.wav"]


def test_telephony_runs_on_quiet_clips_only(setup):
    audio_dir, _ = setup
    add_clip(audio_dir, "q", {"language": "hi-IN", "expected": {}})
    add_clip(audio_dir, "n", {"language": "hi-IN", "condition": "noisy", "expected": {}})
    clips = run_eval.load_clips(audio_dir)[0]
    assert [c.name for c in run_eval.clips_for("telephony", clips)] == ["q.wav"]
    assert len(run_eval.clips_for("clean", clips)) == 2


def test_cache_is_reused_per_mode_without_calling_gnani(setup, monkeypatch):
    """Mock mode: nothing may reach Gnani once a transcript is cached."""
    audio_dir, cache_dir = setup
    monkeypatch.setattr(run_eval.gnani, "transcribe", no_api)
    monkeypatch.setattr(run_eval, "stt", no_api)
    wav = add_clip(audio_dir, "a", {"language": "hi-IN", "expected": {}})
    clip = run_eval.load_clips(audio_dir)[0][0]
    cache_transcript(wav, "hi-IN", "pachaas plate")
    assert (cache_dir / "transcripts_clean.json").exists()
    assert run_eval.transcript_for(clip, run_eval.load_cache("clean"), True, "clean") == "pachaas plate"
    # The clean transcript is not reused for telephony: different audio reaches Prisma.
    assert run_eval.transcript_for(clip, run_eval.load_cache("telephony"), False, "telephony") is None


def test_new_clip_is_transcribed_once_per_mode(setup, monkeypatch):
    audio_dir, cache_dir = setup
    add_clip(audio_dir, "a", {"language": "ml-IN", "expected": {}})
    clip = run_eval.load_clips(audio_dir)[0][0]
    calls = []
    monkeypatch.setattr(run_eval, "stt", lambda c, mode: calls.append(mode) or {"transcript": mode})
    for _ in range(2):
        for mode in ("clean", "telephony"):
            assert run_eval.transcript_for(clip, run_eval.load_cache(mode), True, mode) == mode
    assert calls == ["clean", "telephony"]
    assert {p.name for p in cache_dir.glob("transcripts_*.json")} == {
        "transcripts_clean.json", "transcripts_telephony.json"}


def test_telephony_mode_puts_audio_through_the_phone_filter(setup, monkeypatch):
    audio_dir, _ = setup
    add_clip(audio_dir, "a", {"language": "kn-IN", "expected": {}})
    clip = run_eval.load_clips(audio_dir)[0][0]
    seen = []
    monkeypatch.setattr(run_eval.gnani, "is_mock", lambda: False)
    monkeypatch.setattr(run_eval.audio, "to_wav_16k_mono", lambda p: p)
    monkeypatch.setattr(run_eval.audio, "to_telephony", lambda p: seen.append("phone") or p)
    monkeypatch.setattr(run_eval.gnani, "transcribe",
                        lambda path, lang: seen.append(lang) or {"transcript": "ಹೌದು"})
    run_eval.stt(clip, "clean")
    run_eval.stt(clip, "telephony")
    assert seen == ["kn-IN", "phone", "kn-IN"]


def test_legacy_cache_is_kept_as_clean(setup):
    _, cache_dir = setup
    (cache_dir / "transcripts.json").write_text('{"k": {"transcript": "paid for"}}', encoding="utf-8")
    run_eval.migrate_legacy_cache()
    assert run_eval.load_cache("clean") == {"k": {"transcript": "paid for"}}
    assert not (cache_dir / "transcripts.json").exists()


def test_changed_audio_is_a_new_cache_entry(setup):
    audio_dir, _ = setup
    a = add_clip(audio_dir, "a", {"language": "hi-IN", "expected": {}}, b"one")
    key = run_eval.cache_key(a, "hi-IN", "transcribe")
    a.write_bytes(b"two")
    assert run_eval.cache_key(a, "hi-IN", "transcribe") != key


def test_score_report_and_reply():
    report = run_eval.Clip("r.wav", Path("r.wav"), "hi-IN", "report",
                           {"dish": "veg biryani", "quantity": 50, "unit": "plate",
                            "cooked_time": "14:00", "location": "Kakkanad"}, "real")
    assert run_eval.score(report, "pachaas plate veg biryani, do baje bana, Kakkanad se").all_ok
    reply = run_eval.Clip("y.wav", Path("y.wav"), "ml-IN", "reply",
                          {"answer": "correction", "fields": {"quantity": 60}}, "real")
    assert run_eval.score(reply, "അല്ല 60 പ്ലേറ്റാണ്").all_ok
    assert not run_eval.score(reply, "ശരി").checks["answer"][0]


def test_comparison_table_and_results_md(setup, tmp_path):
    audio_dir, _ = setup
    report = {"language": "hi-IN", "kind": "report", "source": "synthetic-tts",
              "spoken": "pachaas plate biryani do baje",
              "expected": {"dish": "biryani", "quantity": 50, "cooked_time": "14:00"}}
    yes = {"language": "kn-IN", "kind": "reply", "source": "synthetic-tts", "expected": {"answer": "yes"}}
    clips = [  # name, meta, heard (clean), heard (telephony)
        ("r", report, "pachaas plate biryani do baje", "pachaas plate do baje"),
        ("y", yes, "ಹೌದು", "ಹೌದು"),
        ("rn", {**report, "condition": "noisy", "source": "synthetic-tts+noise"},
         "plate biryani do baje", None),
        ("yn", {**yes, "condition": "noisy", "source": "synthetic-tts+noise"}, "ಹೌದು", None),
    ]
    for name, meta, clean, phone in clips:
        wav = add_clip(audio_dir, name, meta, name.encode())
        cache_transcript(wav, meta["language"], clean, "clean")
        if phone:
            cache_transcript(wav, meta["language"], phone, "telephony")
    out = tmp_path / "RESULTS.md"
    assert run_eval.main(["--audio-dir", str(audio_dir), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "| Check | Quiet (2 clips) | Noisy (2 clips) | Telephony (2 clips) |" in md
    assert "| dish | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) |" in md
    assert "| quantity | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) |" in md
    assert "| yes/no replies | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |" in md
    assert "| **whole clip right** | 2/2 (100%) | 1/2 (50%) | 1/2 (50%) |" in md
    assert "Noisy clips have synthetic noise" in md
    assert "| noisy | rn.wav |" in md and "| telephony | r.wav |" in md


def test_noisy_copy_is_deterministic_and_tagged(tmp_path):
    src_dir, out_dir = tmp_path / "src", tmp_path / "noisy"
    src_dir.mkdir()
    out_dir.mkdir()
    tone = run_eval.audio.AudioSegment.silent(duration=200, frame_rate=16000).overlay(
        make_noisy_clips.Sine(440, sample_rate=16000).to_audio_segment(1500) - 12)
    wav = src_dir / "a.wav"
    tone.export(wav, format="wav").close()
    wav.with_suffix(".json").write_text(json.dumps(
        {"language": "en-IN", "source": "synthetic-tts", "expected": {"answer": "yes"}}),
        encoding="utf-8")
    clip = run_eval.load_clips(src_dir)[0][0]
    first = make_noisy_clips.make_noisy(clip, out_dir).read_bytes()
    second = make_noisy_clips.make_noisy(clip, out_dir).read_bytes()
    assert first == second  # same noise every run, so cached transcripts stay valid
    meta = json.loads((out_dir / "a-noisy.json").read_text(encoding="utf-8"))
    assert meta["condition"] == "noisy" and meta["source"] == "synthetic-tts+noise"
    assert meta["expected"] == {"answer": "yes"}


def test_template_without_audio_is_waiting_for_a_recording(setup):
    audio_dir, _ = setup
    (audio_dir / "real").mkdir()
    (audio_dir / "real" / "ml-01.json").write_text('{"language": "ml-IN", "expected": {}}',
                                                   encoding="utf-8")
    add_clip(audio_dir, "done", {"language": "hi-IN", "expected": {}})
    assert run_eval.waiting_for_audio(audio_dir) == ["real/ml-01.json"]
    assert run_eval.load_clips(audio_dir)[0][0].name == "done.wav"
    (audio_dir / "real" / "ml-01.m4a").write_bytes(b"recorded")
    assert run_eval.waiting_for_audio(audio_dir) == []


@pytest.mark.parametrize("template", sorted((EVAL_DIR / "audio" / "real").glob("ml-0*.json")),
                         ids=lambda p: p.stem)
def test_malayalam_templates_are_right_on_their_own_words(template):
    """Ground truth must match what the extractor reads from the exact sentence."""
    meta = json.loads(template.read_text(encoding="utf-8"))
    clip = run_eval.Clip(template.name, template, meta["language"], meta["kind"],
                         meta["expected"], meta["source"], meta["spoken"])
    result = run_eval.score(clip, meta["spoken"])
    assert result.all_ok, run_eval.misses(result)
