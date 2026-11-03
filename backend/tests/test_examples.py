"""The example sentences shown under the mic must work if someone says them word for word."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.extractor import get_extractor
from app.languages import LANGUAGES
from app.main import app
from app.need_extractor import get_need_extractor

NOW = datetime(2026, 11, 2, 16, 30)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_report_examples_parse_completely(code):
    examples = LANGUAGES[code].report_examples
    assert len(examples) >= 2
    for sentence in examples:
        r = get_extractor().extract(sentence, NOW)
        assert r.quantity and r.unit and r.dish and r.cooked_time, (code, sentence)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_need_examples_parse_completely(code):
    examples = LANGUAGES[code].need_examples
    assert len(examples) >= 2
    for sentence in examples:
        n = get_need_extractor().extract(sentence, NOW)
        assert n.people_count and n.needed_by, (code, sentence)


def test_examples_are_served_with_each_kitchen_and_shelter():
    with TestClient(app) as client:
        kitchen = client.get("/kitchens").json()[0]
        ngo = client.get("/ngos").json()[0]
    assert kitchen["examples"] == list(LANGUAGES[kitchen["language"]].report_examples)
    assert ngo["examples"] == list(LANGUAGES[ngo["language"]].need_examples)
