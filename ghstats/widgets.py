"""Neo-glitch themed widgets and rich renderables for ghstats."""

from datetime import datetime

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static

# ── neo-glitch palette ──────────────────────────────────────────────────────
VOID = "#07040c"
VOID_LIGHT = "#151021"
VOID_BRIGHT = "#2a1040"
GREEN = "#00ff9f"
CYAN = "#00e5ff"
MAGENTA = "#ea00d9"
RED = "#ff2a6d"
YELLOW = "#f9f871"
WHITE = "#d8f0ff"
DIM = "#7a6b9a"
PURPLE = "#5d4a7a"

# rich wants RGB triples for truecolor styles
RICH_GREEN = (0, 255, 159)
RICH_CYAN = (0, 229, 255)
RICH_MAGENTA = (234, 0, 217)
RICH_RED = (255, 42, 109)
RICH_YELLOW = (249, 248, 113)
RICH_DIM = (122, 107, 154)


class NeoPanel(Static):
    """A Static wrapped in a heavy-bordered panel with a neon title."""

    def __init__(self, title, render_fn, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.render_fn = render_fn

    def on_mount(self) -> None:
        self.render_content()

    def render_content(self) -> None:
        self.update(
            Panel(
                self.render_fn(),
                title=f"[{GREEN}]{self.title}[/]",
                box=box.HEAVY,
                border_style=PURPLE,
            )
        )


def loading_panel(repo: str) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style=GREEN, justify="right")
    t.add_column(style=WHITE)
    t.add_row(" 󰆍 ", f"jacking into {repo} ...")
    return Panel(t, box=box.HEAVY, border_style=PURPLE, title=f"[{GREEN}]GHSTATS[/]")


def failure_panel(repo: str, refreshed: bool = False) -> Panel:
    note = " (refresh failed)" if refreshed else ""
    hint = (
        f" no response from repos/{repo}{note}\n"
        " check the name or your gh auth (gh auth status)"
    )
    return Panel(
        Text(hint, style=RED),
        title=f"[{RED}]CONNECTION FAILED[/]",
        box=box.HEAVY,
        border_style=PURPLE,
    )


def hero_table(data: dict) -> Table:
    """The repo identity block: name, description, stats, languages."""
    m = data["meta"]
    hero = Table.grid(padding=(0, 2))
    hero.add_column(style=GREEN, justify="right")
    hero.add_column(style=WHITE)
    hero.add_column(style=DIM, justify="left")
    hero.add_row(" 󰊢 ", f"[bold]{m['full_name']}[/]", m.get("description") or "")
    lang = m.get("language") or "—"
    hero.add_row(" 󰚀 ", f"[{CYAN}]{lang}[/]", f"created {m['created_at'][:10]}")
    stars = Text(f"★ {m['stargazers_count']}", style=YELLOW)
    forks = Text(f"⑂ {m['forks_count']}", style=MAGENTA)
    watchers = Text(f"👁 {m['subscribers_count']}", style=CYAN)
    issues = Text(f"issues {m['open_issues_count']}", style=RED)
    pushed = m.get("pushed_at", "")[:10]
    hero.add_row(
        " 󰈔 ", Text.assemble(stars, "   ", forks, "   ", watchers, "   ", issues)
    )
    hero.add_row(" 󰚉 ", f"last push [bold]{pushed}[/]" if pushed else "")
    languages = data.get("languages") or {}
    if languages:
        total = sum(languages.values()) or 1
        langs = Text()
        shades = [GREEN, CYAN, MAGENTA, YELLOW, DIM]
        ordered = sorted(languages.items(), key=lambda kv: -kv[1])
        for i, (lname, nbytes) in enumerate(ordered):
            pct = round(nbytes / total * 100)
            langs.append(Text(f"{lname} {pct}%", style=shades[i % len(shades)]))
            if i < len(ordered) - 1:
                langs.append(Text(" │ ", style=DIM))
        hero.add_row(" 󰗑 ", langs)
    return hero


def traffic_table(traffic: dict, kind: str, color) -> Table:
    """Daily breakdown table for clones/views.

    Payload quirks: the clones endpoint keys its daily list "clones", the
    views endpoint keys it "views" (neither uses "counts"); daily entries
    look like {timestamp: iso, count: int, uniques: int}.
    """
    color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
    t = Table(
        box=box.SIMPLE,
        pad_edge=False,
        show_header=True,
        header_style=f"bold {color_hex}",
    )
    t.add_column("day", style=DIM, width=10)
    t.add_column("total", style=WHITE, justify="right", width=6)
    t.add_column("unique", style=f"bold {color_hex}", justify="right", width=6)
    t.add_column("", ratio=1)
    counts = (traffic.get("counts") or traffic.get(kind) or []) if traffic else []
    mx = max([c["count"] for c in counts] or [1]) or 1
    for c in counts:
        day = datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00")).strftime(
            "%b %d"
        )
        bar = Text(
            "█" * max(1, round(c["count"] / mx * 14)),
            style=f"rgb({color[0]},{color[1]},{color[2]})",
        )
        t.add_row(day, str(c["count"]), str(c["uniques"]), bar)
    return t


def referrer_table(referrers: list) -> Table:
    """Popular referrers: entries are {referrer, count, uniques}."""
    t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {MAGENTA}")
    t.add_column("source", style=WHITE)
    t.add_column("views", justify="right", style=CYAN)
    t.add_column("unique", justify="right", style=GREEN)
    for r in (referrers or [])[:8]:
        t.add_row(r["referrer"], str(r["count"]), str(r["uniques"]))
    if not referrers:
        t.add_row(Text("none yet", style=DIM), "", "")
    return t


def path_table(paths: list, repo: str) -> Table:
    """Top paths: entries are {path, title, count, uniques}."""
    t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {CYAN}")
    t.add_column("path", style=WHITE)
    t.add_column("views", justify="right", style=CYAN)
    t.add_column("unique", justify="right", style=GREEN)
    for p in (paths or [])[:8]:
        t.add_row(p["path"].replace(f"/{repo}", "", 1), str(p["count"]), str(p["uniques"]))
    if not paths:
        t.add_row(Text("none yet", style=DIM), "", "")
    return t


def commit_table(commits: list) -> Table:
    """Recent commits: first line of each message, author, local time."""
    t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {GREEN}")
    t.add_column("when", style=DIM, width=11)
    t.add_column("author", style=MAGENTA, width=12)
    t.add_column("message", style=WHITE, ratio=1)
    for c in (commits or [])[:10]:
        when = datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00"))
        msg = (c["commit"]["message"].splitlines() or [""])[0]
        login = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"][:12]
        t.add_row(when.strftime("%b %d %H:%M"), login, msg[:70])
    if not commits:
        t.add_row(Text("no commits in the last 14 days", style=DIM), "", "")
    return t


def fetched_line(data: dict) -> Text:
    return Text(
        f"\n fetched {data['fetched'].strftime('%H:%M:%S')}"
        " — press r to refresh, q to jack out",
        style=DIM,
    )