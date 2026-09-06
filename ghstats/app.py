"""ghstats application entry point.

Wires the GitHubAPI (auth + data) to the dashboard UI, owns the
refresh/cycle bindings and the worker lifecycle.

Usage:
    ghstats [owner/repo]     # omit to auto-pick your most-pushed repo
    ctrl+t                   # cycle through your repos
    r                        # refresh
    q                        # quit
"""

import asyncio
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static

from . import widgets as w
from .api import GitHubAPI
from .ui import build_body


class GhStats(App):
    CSS_PATH = Path(__file__).parent / "styles.tcss"

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("ctrl+t", "next_repo", "Next repo"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, repo: str, api: GitHubAPI | None = None):
        super().__init__()
        self.repo = repo
        self.api = api or GitHubAPI()
        self.data = None
        self.repos = []  # push-access repos, loaded in background
        self.repo_idx = -1  # position in self.repos (for cycling)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="body"):
            yield Static(w.loading_panel(self.repo), id="hero")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"ghstats — {self.repo}"
        self.set_interval(300, self.action_refresh)
        self.run_worker(self._load_repo_list, exclusive=True, group="repos")
        self.run_worker(self.fetch_data, exclusive=True, group="data")

    # ── workers ──────────────────────────────────────────────────────────────

    async def _load_repo_list(self):
        """Fetch the user's repos (push access) once, in the background."""
        self.repos = await asyncio.to_thread(self.api.user_repos)
        if self.repos and self.repo in self.repos:
            self.repo_idx = self.repos.index(self.repo)

    async def fetch_data(self):
        self.data = await asyncio.to_thread(self.api.fetch_all, self.repo)
        self._render_data()

    # ── rendering ────────────────────────────────────────────────────────────

    def _render_data(self):
        if not (self.data and self.data.get("meta")):
            refreshed = self.repo_idx >= 0
            self._show_failure(refreshed)
            return
        build_body(self.query_one("#body"), self.data)

    def _show_failure(self, refreshed: bool):
        """Show the failure panel; handles both fresh-load and refresh cases."""
        try:
            self.query_one("#hero").update(
                w.failure_panel(self.repo, refreshed=refreshed)
            )
        except NoMatches:
            # hero was already replaced by a successful load — swap the whole body
            body = self.query_one("#body")
            body.remove_children()
            body.mount(
                Static(w.failure_panel(self.repo, refreshed=True), id="hero")
            )

    # ── actions ──────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        # #hero only exists before the first successful load — show loading
        # state either way
        try:
            self.query_one("#hero", Static).update(w.loading_panel(self.repo))
        except NoMatches:
            self.sub_title = "jacking in ..."
        self.run_worker(self.fetch_data, exclusive=True, group="data")

    def action_next_repo(self) -> None:
        if not self.repos:
            self.sub_title = "no repos found to cycle"
            return
        self.repo_idx = (self.repo_idx + 1) % len(self.repos)
        self.repo = self.repos[self.repo_idx]
        self.title = f"ghstats — {self.repo}"
        self.sub_title = ""
        self.action_refresh()


def main() -> None:
    api = GitHubAPI()
    repo = sys.argv[1] if len(sys.argv) > 1 else api.default_repo()
    GhStats(repo, api).run()