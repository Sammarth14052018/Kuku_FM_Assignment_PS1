import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import find_promos as app
from parser import parse
from prompts import critic_prompt, single_prompt


def candidate(*segments: tuple[int, int, int]) -> dict:
    return dict(segments=[dict(ep=e, start=a, end=b) for e, a, b in segments],
                hook="An accusation", cliffhanger="Who sent it?", why="Clear stakes.")


def test_validation() -> None:
    eps = parse("00:00 First\n00:20 Second\n00:40 Third\n01:01 End")
    for segs, reason in [([(1, -1, 0)], "index"), ([(1, 2, 1)], "index"),
                         ([(1, 0, 2)], "duration"), ([(1, 0, 1), (1, 1, 2)], "overlap")]:
        with pytest.raises(ValueError, match=reason):
            app.validate(candidate(*segs), eps, 1 if len(segs) == 1 else None)
    assert app.validate(candidate((1, 0, 0)), eps, 1)["duration_s"] == 20


def test_sample_cli(tmp_path: Path) -> None:
    def mock(system: str, user: str) -> dict:
        data = json.loads(user)
        if system == single_prompt():
            ep = data["ep"]
            return dict(summary="A discovery. Someone interferes.",
                        candidates=[candidate((ep, 0, 2))])
        if system == critic_prompt():
            assert data["first_3s"] and data["clip"] and data["after_cut"]
            return dict(hook=8, cliffhanger=9, standalone=7, scroll_stop_3s=True,
                        resolved_right_after=False, spoils_big_twist=False, issues=[])
        return dict(candidates=[candidate((1, 0, 1), (2, 0, 0))])

    sample = Path(__file__).resolve().parents[1] / "sample_screenplay.txt"
    with patch.object(app, "ask_json", side_effect=mock):
        assert app.main([str(sample), "--out", str(tmp_path)]) == 0
    ranked = json.loads((tmp_path / "promos.json").read_text())
    assert len(ranked) == 3 and ranked[0]["score"] == 8
    assert "Dedup dropped: 1" in (tmp_path / "quality_report.md").read_text()
    assert "Why #1 goes first" in (tmp_path / "promos.md").read_text()
    with (tmp_path / "eval_sheet.csv").open() as sheet:
        assert list(csv.DictReader(sheet))[0]["human_hook_1to5"] == ""


def test_penalties_and_critic_types() -> None:
    flags = dict(hook=10, cliffhanger=10, standalone=10, scroll_stop_3s=False,
                 resolved_right_after=True, spoils_big_twist=True, issues=["Too much context"])
    assert app.score(flags) == 6
    with pytest.raises(ValueError):
        app.score({**flags, "scroll_stop_3s": "false"})


def test_stitch_context_and_failure_recovery() -> None:
    from collections import Counter
    eps = parse("Episode 1\n00:00 Ring\n00:02 Door\n00:20 End\n"
                "Episode 2\n00:00 A silent train arrives\n00:20 Answer\n00:23 A\n00:24 B\n00:25 C")
    critic = dict(hook=8, cliffhanger=8, standalone=8, scroll_stop_3s=True,
                  resolved_right_after=True, spoils_big_twist=False, issues=[])
    replies = [None, dict(summary="Quiet. Too quiet.", candidates=[]),
               dict(candidates=[candidate((1, 0, 0), (2, 0, 0))]), critic]
    stats = Counter()
    with patch.object(app, "ask_json", side_effect=replies) as mocked:
        kept, flags = app.rank(eps, 1, stats)
    context = json.loads(mocked.call_args.args[1])
    assert context["first_3s"] == ["Ring", "A"]
    assert context["after_cut"] == ["Answer", "A", "B"]
    assert kept[0]["kind"] == "stitched" and kept[0]["duration_s"] == 22
    assert flags and stats["llm"] == 1


def test_json_retry() -> None:
    import sys
    from unittest.mock import MagicMock
    import llm
    sdk = MagicMock()
    create = sdk.OpenAI.return_value.chat.completions.create
    responses = [MagicMock(), MagicMock()]
    responses[0].choices[0].message.content = "broken"
    responses[1].choices[0].message.content = 'Here is JSON: ```json\n{"ok": true}\n```'
    create.side_effect = responses
    with patch.dict(sys.modules, openai=sdk), patch.dict("os.environ", PROVIDER="openai"):
        assert llm.ask_json(critic_prompt(), "{}") == {"ok": True}
    assert create.call_count == 2 and create.call_args.kwargs["temperature"] == 0
