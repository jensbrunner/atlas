from __future__ import annotations

from pathlib import Path

from atlas.state.render import usage_view
from atlas.state.schemas import CampaignSeed, TurnRecord, Usage
from atlas.state.store import CampaignStore
from tests.support import seed_payload


def test_usage_view_sums_turns_and_models(tmp_path: Path) -> None:
    state = CampaignStore(tmp_path / "campaigns").create(
        CampaignSeed.model_validate(seed_payload()), narrator_model="fake"
    )
    state.turns[0].usage = Usage(
        input_tokens=100,
        output_tokens=50,
        estimated_usd=0.01,
    )
    state.turns.append(
        TurnRecord(
            turn=1,
            kind="player",
            action="look",
            model="gpt-6-luna",
            usage=Usage(input_tokens=200, output_tokens=100, estimated_usd=0.02),
            narration="A scene.",
        )
    )

    view = usage_view(state)

    assert view["totals"]["input_tokens"] == 300
    assert view["totals"]["output_tokens"] == 150
    assert view["totals"]["total_tokens"] == 450
    assert view["totals"]["estimated_usd"] == 0.03
    assert view["totals"]["turns"] == 2
    assert view["totals"]["billable_turns"] == 2
    assert view["totals"]["average_tokens_per_turn"] == 225
    assert view["models"] == ["fake", "gpt-6-luna"]
    assert len(view["turns"]) == 2
    assert view["turns"][1]["model"] == "gpt-6-luna"
