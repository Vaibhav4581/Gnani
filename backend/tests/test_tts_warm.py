"""The pre-demo cache list holds the fixed phrases exactly as the code speaks them."""
from datetime import timedelta

import pytest

from app import safety, tts_warm
from app.confirm import handle_reply
from app.extractor import Extraction
from app.languages import LANGUAGES
from app.models import Report

from .conftest import NOW


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_fixed_phrases_have_no_placeholders(code):
    phrases = tts_warm.fixed_phrases(LANGUAGES[code])
    assert len(phrases) > 30 and all(p and "{" not in p for p in phrases)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_fixed_phrases_match_what_the_flows_say(code):
    lang = LANGUAGES[code]
    phrases = set(tts_warm.fixed_phrases(lang))
    report = Report(kitchen_id=1, deadline=NOW + timedelta(hours=2))
    said = [safety.begin(report, NOW, lang).prompt]
    said.append(safety.answer(report, lang.mock_reply, NOW, lang).prompt)  # veg: yes
    said.append(safety.answer(report, "hmm", NOW, lang).prompt)  # unclear
    no = sorted(lang.lexicon.no_words)[0]
    said.append(safety.answer(report, no, NOW, lang).prompt)  # covered: no
    said.append(safety.answer(report, lang.mock_reply, NOW, lang).prompt)  # covered: yes
    full = Extraction("biryani", 50, "plate", NOW.replace(hour=14))
    said.append(handle_reply(full, lang.mock_reply, NOW, lang).prompt)  # confirmed
    assert set(said) <= phrases, set(said) - phrases


def test_check_spends_nothing(monkeypatch, capsys):
    def no_calls(*_, **__):
        raise AssertionError("checking the cache must not call Timbre")
    monkeypatch.setattr(tts_warm.gnani, "speak", no_calls)
    assert tts_warm.main(warm=False) == 0
    assert "hi-IN" in capsys.readouterr().out
