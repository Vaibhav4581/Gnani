"""The mic's stop-on-silence rule (frontend/assets/recorder.js createSpeechGate), run in Node
on made-up level traces: a quiet room, a noisy kitchen, a pan clatter, a quick "haan", the caps."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RECORDER = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "recorder.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")

# Feeds every [level, t] to a fresh gate and prints where it ended.
RUN = """
const { createSpeechGate, LISTEN } = await import(process.argv[1]);
const { samples, noSpeechMs } = JSON.parse(process.argv[2]);
const gate = createSpeechGate({ noSpeechMs: noSpeechMs ?? LISTEN.NO_SPEECH_MS });
let out = { done: null, t: null };
for (const [level, t] of samples) {
  const { done } = gate.feed(level, t);
  if (done) { out = { done, t }; break; }
}
console.log(JSON.stringify({ ...out, ambient: gate.state.ambient, threshold: gate.state.threshold,
                             phase: gate.state.phase, cfg: LISTEN }));
"""

QUIET, KITCHEN, SPEECH = 0.005, 0.03, 0.08
TICK = 50


def trace(*parts: tuple[int, float]) -> list[list[float]]:
    """[(how long in ms, level), ...] -> a reading every 50 ms, like the browser takes them."""
    samples, t = [], 0
    for ms, level in parts:
        for _ in range(ms // TICK):
            samples.append([level, t])
            t += TICK
    return samples


def gate(samples, no_speech_ms=None) -> dict:
    arg = json.dumps({"samples": samples, "noSpeechMs": no_speech_ms})
    run = subprocess.run([NODE, "--input-type=module", "-e", RUN, RECORDER.as_uri(), arg],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_defaults_are_the_agreed_ones():
    cfg = gate(trace((100, QUIET)))["cfg"]
    assert (cfg["CALIBRATE_MS"], cfg["SPEECH_FACTOR"], cfg["SILENCE_MS"]) == (500, 1.8, 1200)
    assert (cfg["NO_SPEECH_MS"], cfg["AUTO_NO_SPEECH_MS"], cfg["MAX_MS"]) == (6000, 8000, 20000)


def test_quiet_room_stops_1200_ms_after_speech_ends():
    out = gate(trace((1000, QUIET), (1500, SPEECH), (4000, QUIET)))
    assert out["done"] == "silence" and out["t"] == 2500 + 1200
    assert out["threshold"] == pytest.approx(0.01)  # a silent room still has a floor


def test_noisy_kitchen_raises_the_bar_and_still_stops():
    out = gate(trace((1000, KITCHEN), (1500, 0.12), (4000, KITCHEN)))
    assert out["ambient"] == pytest.approx(KITCHEN)
    assert out["threshold"] == pytest.approx(KITCHEN * 1.8)
    assert out["done"] == "silence" and out["t"] == 2500 + 1200


def test_kitchen_noise_alone_is_not_speech():
    out = gate(trace((7000, KITCHEN)))
    assert (out["done"], out["t"], out["phase"]) == ("no_speech", 6000, "waiting")


def test_a_pan_clatter_is_too_short_to_count():
    out = gate(trace((1000, KITCHEN), (100, 0.3), (6000, KITCHEN)))
    assert out["done"] == "no_speech" and out["phase"] == "waiting"


def test_a_pause_between_words_does_not_send_early():
    out = gate(trace((600, QUIET), (1000, SPEECH), (800, QUIET), (1000, SPEECH), (3000, QUIET)))
    assert out["done"] == "silence" and out["t"] == 3400 + 1200


def test_a_quick_haan_inside_the_calibration_window_counts():
    out = gate(trace((100, QUIET), (300, SPEECH), (3000, QUIET)))
    assert out["done"] == "silence" and out["t"] == 400 + 1200


def test_talking_straight_away_does_not_lock_the_mic():
    """The window is all speech, so the room looks loud; the first real pause resets it."""
    out = gate(trace((1500, SPEECH), (500, QUIET), (1000, SPEECH), (3000, QUIET)))
    assert out["done"] == "silence" and out["t"] == 3000 + 1200


def test_no_speech_limits_after_a_tap_and_after_a_question():
    assert gate(trace((9000, QUIET)))["t"] == 6000
    assert gate(trace((9000, QUIET)), no_speech_ms=8000)["t"] == 8000


def test_twenty_seconds_is_the_hard_cap():
    out = gate(trace((500, QUIET), (25000, SPEECH)))
    assert (out["done"], out["t"]) == ("max", 20000)

