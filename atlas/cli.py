from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from atlas.agents.campaign import CampaignRequest
from atlas.agents.fake import FakeProvider
from atlas.config import Settings
from atlas.game import CampaignService
from atlas.state.store import CampaignNotFound


def _settings(args: argparse.Namespace) -> Settings:
    overrides: dict[str, object] = {}
    if getattr(args, "data_dir", None):
        overrides["data_dir"] = Path(args.data_dir)
    if getattr(args, "provider", None):
        overrides["provider"] = args.provider
    return Settings(**overrides)  # type: ignore[arg-type]


def cmd_serve(args: argparse.Namespace) -> int:
    settings = _settings(args)
    settings.validate_provider()
    host = args.host or settings.host
    port = args.port or settings.port
    if args.reload:
        # The reloader imports the factory in a subprocess, so pass overrides
        # through the environment rather than as a prebuilt app object.
        os.environ["ATLAS_DATA_DIR"] = str(settings.data_dir)
        os.environ["ATLAS_PROVIDER"] = settings.provider
        uvicorn.run(
            "atlas.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
        )
        return 0

    from atlas.app import create_app

    uvicorn.run(create_app(settings), host=host, port=port)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    service = CampaignService(_settings(args))
    campaigns = service.list_campaigns()
    if not campaigns:
        print("No campaigns yet.")
        return 0
    for campaign in campaigns:
        print(
            f"{campaign.id}  {campaign.title}  "
            f"(turn {campaign.turn_count}, {campaign.world_time_minutes} world minutes)"
        )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    overrides: dict[str, object] = {"provider": "fake"}
    if args.data_dir:
        overrides["data_dir"] = Path(args.data_dir)
    settings = Settings(**overrides)  # type: ignore[arg-type]
    service = CampaignService(settings, provider=FakeProvider())
    state, _ = service.create_campaign(
        CampaignRequest(
            prompt=args.prompt,
            title=args.title,
        )
    )
    print(f"Campaign: {state.meta.id} — {state.meta.title}")
    print()
    print(state.turns[0].narration)
    print()
    result = service.play_turn(state.meta.id, args.action)
    print(f"> {args.action}")
    print()
    print(result.narration)
    if result.rolls:
        for roll in result.rolls:
            print(
                f"  roll: {roll.label} {roll.dice[0]}+{roll.dice[1]}"
                f"{roll.modifier:+d} = {roll.total} vs {roll.difficulty} ({roll.outcome})"
            )
    print()
    print(f"Campaign directory: {state.root}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    service = CampaignService(_settings(args))
    try:
        view = service.player(args.campaign_id)
    except CampaignNotFound:
        print(f"No such campaign: {args.campaign_id}", file=sys.stderr)
        return 1
    campaign = view["campaign"]
    print(f"{campaign['title']} ({campaign['id']})")
    print(f"{campaign['world_time']} — turn {campaign['turn_count']}")
    print()
    print(view["narration"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas", description="ATLAS roleplay harness")
    parser.add_argument("--data-dir", default=None, help="campaign storage directory")
    parser.add_argument("--provider", default=None, choices=["fake", "openai"])
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the localhost server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")
    # Accept storage overrides after the subcommand as well as before it.
    serve.add_argument("--data-dir", default=argparse.SUPPRESS)
    serve.add_argument("--provider", default=argparse.SUPPRESS, choices=["fake", "openai"])
    serve.set_defaults(func=cmd_serve)

    listing = sub.add_parser("list", help="list campaigns")
    listing.set_defaults(func=cmd_list)

    demo = sub.add_parser("demo", help="create and play a campaign with the offline fake provider")
    demo.add_argument("--title", default="")
    demo.add_argument("--prompt", default="A rain-soaked harbor town with a missing shipment.")
    demo.add_argument("--action", default="look around")
    demo.set_defaults(func=cmd_demo)

    show = sub.add_parser("show", help="print the latest player view of a campaign")
    show.add_argument("campaign_id")
    show.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    except (ValueError, CampaignNotFound) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
