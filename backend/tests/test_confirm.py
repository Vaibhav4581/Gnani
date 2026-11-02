from datetime import datetime

import pytest

from app.confirm import (ReplyKind, classify_reply, confirmation_text, handle_reply,
                         merge_correction, next_prompt)
from app.extractor import Extraction
from app.languages.hi import PROMPTS as HI
from app.languages.hi import spoken_time

CONFIRMED_TEXT = HI.confirmed

FULL = Extraction("veg biryani", 50, "plate", datetime(2026, 10, 23, 14, 0), "Kakkanad")


@pytest.mark.parametrize("text", ["haan", "haan sahi hai", "ha ji", "theek hai",
                                  "yes", "ok", "bilkul sahi", "हाँ सही है"])
def test_classify_yes(text, now):
    assert classify_reply(text, now)[0] is ReplyKind.YES


@pytest.mark.parametrize("text", ["nahi", "galat hai", "no", "sahi nahi hai", "नहीं"])
def test_classify_no(text, now):
    assert classify_reply(text, now)[0] is ReplyKind.NO


@pytest.mark.parametrize("text", ["nahi, saath plate hai", "galat, teen baje bana tha",
                                  "nahi 20 kilo", "location Kaloor hai"])
def test_classify_correction(text, now):
    assert classify_reply(text, now)[0] is ReplyKind.CORRECTION


def test_classify_unclear(now):
    assert classify_reply("hmm accha", now)[0] is ReplyKind.UNCLEAR


def test_merge_changes_only_fields_in_reply():
    merged = merge_correction(FULL, Extraction(quantity=60))
    assert merged == Extraction("veg biryani", 60, "plate", FULL.cooked_time, "Kakkanad")


def test_correction_turn_merges_and_reconfirms(now):
    turn = handle_reply(FULL, "nahi, teen baje bana tha", now)
    assert turn.kind is ReplyKind.CORRECTION and not turn.confirmed
    assert turn.fields.cooked_time == datetime(2026, 10, 23, 15, 0)
    assert turn.fields.quantity == 50 and turn.fields.dish == "veg biryani"
    assert turn.prompt.startswith("Theek hai, badal diya.") and turn.prompt.endswith("Sahi hai?")


def test_yes_confirms_complete_report(now):
    turn = handle_reply(FULL, "haan sahi hai", now)
    assert turn.confirmed and turn.prompt == CONFIRMED_TEXT


def test_repeating_a_value_with_yes_is_a_yes(now):
    assert handle_reply(FULL, "haan, do baje hi bana tha", now).confirmed


def test_no_keeps_fields_and_asks_again(now):
    turn = handle_reply(FULL, "nahi galat hai", now)
    assert turn.kind is ReplyKind.NO and turn.fields == FULL and not turn.confirmed


def test_yes_cannot_confirm_incomplete_report(now):
    partial = Extraction(dish="biryani")
    turn = handle_reply(partial, "haan", now)
    assert not turn.confirmed
    assert "Kitna khana" in turn.prompt


def test_follow_up_asks_first_missing_field():
    assert next_prompt(Extraction(dish="biryani")) == \
        "Kitna khana bacha hai? Kitne plate ya kitne kilo?"
    assert next_prompt(Extraction("biryani", 50)) == "50 kya? Plate, kilo, litre ya dabba?"
    assert next_prompt(Extraction("biryani", 50, "plate")) == "Khana kitne baje bana tha?"


def test_bare_answer_fills_missing_field(now):
    turn = handle_reply(Extraction("biryani", None, "plate", FULL.cooked_time), "do", now)
    assert turn.fields.quantity == 2
    assert turn.prompt.startswith("Theek hai. 2 plate biryani")


def test_confirmation_sentence():
    assert confirmation_text(FULL) == (
        "50 plate veg biryani, dopahar 2 baje bana tha, Kakkanad se. "
        "Pickup shaam 6 baje tak hona chahiye. Sahi hai?")


@pytest.mark.parametrize("h,m,spoken", [(14, 30, "dopahar dhai baje"),
                                        (11, 0, "subah 11 baje"),
                                        (20, 45, "raat paune 9 baje"),
                                        (13, 30, "dopahar dedh baje")])
def test_spoken_time(h, m, spoken):
    assert spoken_time(datetime(2026, 10, 23, h, m)) == spoken
