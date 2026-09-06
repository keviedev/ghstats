#!/usr/bin/env python3
"""ghstats — a terminal dashboard for GitHub repo traffic.

Shows stars/forks/watchers, 14-day clones and views with daily bars,
referrers, top paths, and recent commits — styled in neon on void black
(the neo-glitch palette). Auth is delegated entirely to the `gh` CLI,
so no tokens are stored or handled by this app.

Usage:
    ghstats [owner/repo]     # omit to auto-pick your most-pushed repo
    ctrl+t                   # cycle through your repos
    r                        # refresh
    q                        # quit
"""
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

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

RICH_GREEN = (0, 255, 159)
RICH_CYAN = (0, 229, 255)
RICH_MAGENTA = (234, 0, 217)
RICH_RED = (255, 42, 109)
RICH_YELLOW = (249, 248, 113)
RICH_DIM = (122, 107, 154)


def gh(*args, timeout=15):
    """Run a gh api call, return parsed JSON or None."""
    try:
        out = subprocess.run(
            ["gh", "api", *args],
            capture_output=True, timeout=timeout, text=True,
        )
        if out.returncode != 0:
            return None
        s = out.stdout.strip()
        if not s:
            return None
        # mise can print a tool banner before the JSON — start at the first brace/bracket
        for i, ch in enumerate(s):
            if ch in "{[":
                s = s[i:]
                break
        else:
            return None
        return json.loads(s)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def fetch_user_repos(limit=30):
    """Repos the authed user has push access to, most recently pushed first."""
    user = gh("user")
    if not user:
        return []
    repos = gh(f"users/{user['login']}/repos?per_page=100&sort=pushed&type=owner") or []
    return [r["full_name"] for r in repos if r.get("permissions", {}).get("push")][:limit]


def fetch_all(repo: str) -> dict:
    """Pull repo metadata + traffic in parallel-ish (sequential is fine, fast)."""
    data = {"repo": repo, "fetched": datetime.now()}
    data["meta"] = gh(f"repos/{repo}")
    data["clones"] = gh(f"repos/{repo}/traffic/clones")
    data["views"] = gh(f"repos/{repo}/traffic/views")
    data["referrers"] = gh(f"repos/{repo}/traffic/popular/referrers")
    data["paths"] = gh(f"repos/{repo}/traffic/popular/paths")
    data["languages"] = gh(f"repos/{repo}/languages")
    since = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    commits = gh(f"repos/{repo}/commits?per_page=10&since={since}")
    data["commits"] = commits if isinstance(commits, list) else []
    return data


def traffic_table(traffic: dict, kind: str, color) -> Table:
    """Daily breakdown table for clones/views."""
    color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
    t = Table(box=box.SIMPLE, pad_edge=False, show_header=True, header_style=f"bold {color_hex}")
    t.add_column("day", style=DIM, width=10)
    t.add_column("total", style=WHITE, justify="right", width=6)
    t.add_column("unique", style=f"bold {color_hex}", justify="right", width=6)
    t.add_column("", ratio=1)
    # clones payload keys the list "clones", views payload keys it "views";
    # daily entries use {timestamp, count, uniques}
    counts = (traffic.get("counts") or traffic.get(kind) or []) if traffic else []
    mx = max([c["count"] for c in counts] or [1]) or 1
    for c in counts:
        day = datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00")).strftime("%b %d")
        bar = Text("█" * max(1, round(c["count"] / mx * 14)), style=f"rgb({color[0]},{color[1]},{color[2]})")
        t.add_row(day, str(c["count"]), str(c["uniques"]), bar)
    return t


class NeoPanel(Static):
    def __init__(self, title, render_fn, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.render_fn = render_fn

    def on_mount(self) -> None:
        self.render_content()

    def render_content(self) -> None:
        self.update(Panel(self.render_fn(), title=f"[{GREEN}]{self.title}[/]", box=box.HEAVY, border_style=PURPLE))


class GhStats(App):
    CSS = """
    Screen { background: #07040c; }
    #body { height: 1fr; }
    NeoPanel { border: none; padding: 0 1; }
    NeoPanel.clones-box { border: round #5d4a7a; margin: 0 0 1 0; }
    """
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("ctrl+t", "next_repo", "Next repo"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, repo: str):
        super().__init__()
        self.repo = repo
        self.data = None
        self.repos = []          # populated on mount: repos the user manages
        self.repo_idx = -1       # position in self.repos (kept for cycling)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="body"):
            yield Static(self._loading(), id="hero")
        yield Footer()

    def _loading(self):
        t = Table.grid(padding=(0, 2))
        t.add_column(style=GREEN, justify="right")
        t.add_column(style=WHITE)
        t.add_row(" 󰆍 ", f"jacking into {self.repo} ...")
        return Panel(t, box=box.HEAVY, border_style=PURPLE, title=f"[{GREEN}]GHSTATS[/]")

    def on_mount(self) -> None:
        self.title = f"ghstats — {self.repo}"
        self.set_interval(300, self.action_refresh)
        self.run_worker(self._load_repo_list, exclusive=True, group="repos")
        self.run_worker(self.fetch_data, exclusive=True, group="data")

    async def _load_repo_list(self):
        """Fetch the user's repos (push access) once, in the background."""
        self.repos = await asyncio.to_thread(fetch_user_repos)
        if self.repos and self.repo in self.repos:
            self.repo_idx = self.repos.index(self.repo)

    def action_next_repo(self) -> None:
        if not self.repos:
            self.sub_title = "no repos found to cycle"
            return
        self.repo_idx = (self.repo_idx + 1) % len(self.repos)
        self.repo = self.repos[self.repo_idx]
        self.title = f"ghstats — {self.repo}"
        self.sub_title = ""
        self.action_refresh()

    async def fetch_data(self):
        self.data = await asyncio.to_thread(fetch_all, self.repo)
        self.build_ui()

    def build_ui(self):
        if not self.data.get("meta"):
            try:
                self.query_one("#hero").update(Panel(
                    Text(f" no response from repos/{self.repo}\n check the name or your gh auth (gh auth status)", style=RED),
                    title=f"[{RED}]CONNECTION FAILED[/]", box=box.HEAVY, border_style=PURPLE))
            except NoMatches:
                # hero was already replaced by a successful load — swap the whole body
                body = self.query_one("#body")
                body.remove_children()
                body.mount(Static(Panel(
                    Text(f" no response from repos/{self.repo} (refresh failed)", style=RED),
                    title=f"[{RED}]CONNECTION FAILED[/]", box=box.HEAVY, border_style=PURPLE), id="hero"))
            return
        body = self.query_one("#body")
        body.remove_children()
        d = self.data
        m = d["meta"]

        # hero: repo identity
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
        hero.add_row(" 󰈔 ", Text.assemble(stars, "   ", forks, "   ", watchers, "   ", issues))
        hero.add_row(" 󰚉 ", f"last push [bold]{pushed}[/]" if pushed else "")
        if d.get("languages"):
            total = sum(d["languages"].values()) or 1
            langs = Text()
            for i, (lname, nbytes) in enumerate(sorted(d["languages"].items(), key=lambda kv: -kv[1])):
                pct = round(nbytes / total * 100)
                shade = [GREEN, CYAN, MAGENTA, YELLOW, DIM][i % 5]
                langs.append(Text(f"{lname} {pct}%", style=shade))
                if i < len(d["languages"]) - 1:
                    langs.append(Text(" │ ", style=DIM))
            hero.add_row(" 󰗑 ", langs)
        body.mount(Static(Panel(hero, title=f"[{GREEN}]{m['full_name']}[/]", box=box.HEAVY, border_style=PURPLE)))

        # traffic row: clones + views
        clones, views = d.get("clones") or {}, d.get("views") or {}

        def make_traffic_panel(title, traffic, kind, color):
            return NeoPanel(title, lambda t=traffic: traffic_table(t, kind, color))

        clones_panel = make_traffic_panel(
            f"CLONES 14d — {clones.get('count', 0)} total / {clones.get('uniques', 0)} unique", clones, "clones", RICH_GREEN)
        clones_panel.add_class("clones-box")
        views_panel = make_traffic_panel(
            f"VIEWS 14d — {views.get('count', 0)} total / {views.get('uniques', 0)} unique", views, "views", RICH_CYAN)
        traffic_row = Horizontal(clones_panel, views_panel)
        body.mount(traffic_row)

        # referrers + paths
        row2 = Horizontal()
        def ref_table():
            refs = d.get("referrers") or []
            t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {MAGENTA}")
            t.add_column("source", style=WHITE)
            t.add_column("views", justify="right", style=CYAN)
            t.add_column("unique", justify="right", style=GREEN)
            for r in refs[:8]:
                t.add_row(r["referrer"], str(r["count"]), str(r["uniques"]))
            if not refs:
                t.add_row(Text("none yet", style=DIM), "", "")
            return t
        def path_table():
            paths = d.get("paths") or []
            t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {CYAN}")
            t.add_column("path", style=WHITE)
            t.add_column("views", justify="right", style=CYAN)
            t.add_column("unique", justify="right", style=GREEN)
            for p in paths[:8]:
                t.add_row(p["path"].replace(f"/{d['repo']}", "", 1), str(p["count"]), str(p["uniques"]))
            if not paths:
                t.add_row(Text("none yet", style=DIM), "", "")
            return t
        row2 = Horizontal(
            NeoPanel("REFERRERS", ref_table),
            NeoPanel("TOP PATHS", path_table),
        )
        body.mount(row2)

        # recent commits
        def commit_table():
            t = Table(box=box.SIMPLE, pad_edge=False, header_style=f"bold {GREEN}")
            t.add_column("when", style=DIM, width=11)
            t.add_column("author", style=MAGENTA, width=12)
            t.add_column("message", style=WHITE, ratio=1)
            for c in (d.get("commits") or [])[:10]:
                when = datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00"))
                msg = (c["commit"]["message"].splitlines() or [""])[0]
                login = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"][:12]
                t.add_row(when.strftime("%b %d %H:%M"), login, msg[:70])
            if not d.get("commits"):
                t.add_row(Text("no commits in the last 14 days", style=DIM), "", "")
            return t
        body.mount(NeoPanel("COMMITS (14d)", commit_table))
        body.mount(Static(Text(f"\n fetched {d['fetched'].strftime('%H:%M:%S')} — press r to refresh, q to jack out",
                               style=DIM)))

    def action_refresh(self) -> None:
        # #hero only exists before the first successful load — show loading state either way
        try:
            self.query_one("#hero", Static).update(self._loading())
        except NoMatches:
            self.sub_title = "jacking in ..."
        self.run_worker(self.fetch_data, exclusive=True, group="data")


def default_repo() -> str:
    """Figure out the most interesting repo for the authed user."""
    user = gh("user")
    if not user:
        sys.exit("gh auth failed — run `gh auth login`")
    events = gh(f"users/{user['login']}/events?per_page=30") or []
    repos = [e["repo"]["name"] for e in events if e["repo"]["name"].startswith(user["login"] + "/")]
    if not repos:
        sys.exit("no recent activity found — pass a repo explicitly: ghstats owner/repo")
    return max(set(repos), key=repos.count)


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else default_repo()
    GhStats(repo).run()