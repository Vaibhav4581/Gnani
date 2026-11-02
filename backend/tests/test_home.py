"""Home page at "/" and the eval summary it shows."""
import pytest
from fastapi.testclient import TestClient

from app import eval_summary, main
from app.main import app

RESULTS = """# Bacha Hua Khana: speech understanding evaluation

Run 25 Oct 2026. 18 labelled recordings, transcribed with Gnani Prisma v2.5 (`format=transcribe`).

**Whole clips right:** quiet 16/18 (89%), noisy 16/18 (89%).

## Quiet vs noisy

| Check | Quiet (18 clips) | Noisy (18 clips) |
|---|---|---|
| dish | 5/7 (71%) | 5/7 (71%) |
| **whole clip right** | 16/18 (89%) | 16/18 (89%) |

> All speech is Gnani Timbre TTS voices reading known sentences.

| Field | en-IN |
|---|---|
| dish | 1/2 (50%) |
"""


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_home_page_is_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    for words in ("Leftover food, reported by voice", "How it works", "Open the app",
                  "Built on Gnani AI", "Prisma v2.5", "Timbre v2.5", "This is a prototype",
                  "#GnaniAI #GreatIndianAIInternshipChallenge"):
        assert words in r.text
    for link in ('href="/kitchen/"', 'href="/volunteer/"', 'href="/ngo/"', 'href="/dashboard/"'):
        assert link in r.text
    assert "/assets/design.css" in r.text and "/shared/base.css" not in r.text
    assert client.get("/home/home.js").status_code == 200
    assert client.get("/home/home.css").status_code == 200


def test_eval_summary_reads_the_first_table(tmp_path):
    path = tmp_path / "RESULTS.md"
    path.write_text(RESULTS, encoding="utf-8")
    s = eval_summary.summary(path)
    assert s["run"].startswith("Run 25 Oct 2026") and "`" not in s["run"]
    assert s["headline"] == "Whole clips right: quiet 16/18 (89%), noisy 16/18 (89%)."
    assert s["columns"] == ["Check", "Quiet (18 clips)", "Noisy (18 clips)"]
    assert s["rows"] == [["dish", "5/7 (71%)", "5/7 (71%)"],
                         ["whole clip right", "16/18 (89%)", "16/18 (89%)"]]
    assert s["caveat"] == "All speech is Gnani Timbre TTS voices reading known sentences."


def test_eval_summary_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "EVAL_RESULTS", tmp_path / "missing.md")
    assert client.get("/eval/summary").status_code == 404
    path = tmp_path / "RESULTS.md"
    path.write_text(RESULTS, encoding="utf-8")
    monkeypatch.setattr(main, "EVAL_RESULTS", path)
    assert client.get("/eval/summary").json()["rows"][0][0] == "dish"


def test_the_real_results_file_parses():
    s = eval_summary.summary(main.EVAL_RESULTS)
    if s is None:
        pytest.skip("eval not run yet")
    assert s["columns"][0] == "Check" and s["rows"]
