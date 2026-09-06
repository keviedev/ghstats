"""Dashboard construction for ghstats.

Builds the widget tree for a loaded repo bundle (see GitHubAPI.fetch_all):
hero panel, clones/views traffic row, referrers/paths row, commits, and
the footer status line.
"""

from rich import box
from rich.panel import Panel

from textual.containers import Horizontal
from textual.widgets import Static

from . import widgets as w
from .widgets import NeoPanel


def hero_panel(data: dict) -> Static:
    """The repo identity block: name, description, stats, languages."""
    return Static(
        Panel(
            w.hero_table(data),
            title=f"[{w.GREEN}]{data['meta']['full_name']}[/]",
            box=box.HEAVY,
            border_style=w.PURPLE,
        )
    )


def build_body(body, data: dict) -> None:
    """Mount the full dashboard into the given container (replaces children)."""
    body.remove_children()

    # hero: repo identity
    body.mount(hero_panel(data))

    # traffic row: clones + views
    clones = data.get("clones") or {}
    views = data.get("views") or {}
    clones_panel = NeoPanel(
        f"CLONES 14d — {clones.get('count', 0)} total / {clones.get('uniques', 0)} unique",
        lambda: w.traffic_table(clones, "clones", w.RICH_GREEN),
    )
    views_panel = NeoPanel(
        f"VIEWS 14d — {views.get('count', 0)} total / {views.get('uniques', 0)} unique",
        lambda: w.traffic_table(views, "views", w.RICH_CYAN),
    )
    body.mount(Horizontal(clones_panel, views_panel))

    # referrers + paths
    body.mount(
        Horizontal(
            NeoPanel(
                "REFERRERS", lambda: w.referrer_table(data.get("referrers"))
            ),
            NeoPanel(
                "TOP PATHS", lambda: w.path_table(data.get("paths"), data["repo"])
            ),
        )
    )

    # recent commits
    body.mount(
        NeoPanel("COMMITS (14d)", lambda: w.commit_table(data.get("commits")))
    )

    # status line
    body.mount(Static(w.fetched_line(data)))