"""GitHub API access for ghstats.

All calls are delegated to the `gh` CLI, which manages its own keyring
auth — no tokens are stored or handled here. Payload quirks of the
traffic endpoints (documented in the methods) are normalized so the UI
layer sees one consistent shape.
"""

import json
import subprocess
from datetime import datetime, timedelta, timezone


class GitHubAPI:
    """Thin wrapper around `gh api` calls."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _call(self, *args):
        """Run a gh api call, return parsed JSON or None."""
        try:
            out = subprocess.run(
                ["gh", "api", *args],
                capture_output=True,
                timeout=self.timeout,
                text=True,
            )
            if out.returncode != 0:
                return None
            s = out.stdout.strip()
            if not s:
                return None
            # mise can print a tool banner before the JSON — start at the
            # first brace/bracket
            for i, ch in enumerate(s):
                if ch in "{[":
                    s = s[i:]
                    break
            else:
                return None
            return json.loads(s)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    # ── authed user ──────────────────────────────────────────────────────────

    def current_user(self) -> dict | None:
        return self._call("user")

    def user_repos(self, limit: int = 30) -> list[str]:
        """Repos the user has push access to, most recently pushed first."""
        user = self.current_user()
        if not user:
            return []
        repos = (
            self._call(
                f"users/{user['login']}/repos?per_page=100&sort=pushed&type=owner"
            )
            or []
        )
        return [
            r["full_name"] for r in repos if r.get("permissions", {}).get("push")
        ][:limit]

    def default_repo(self) -> str:
        """The user's most recently active own repo (best guess)."""
        user = self.current_user()
        if not user:
            raise RuntimeError("gh auth failed — run `gh auth login`")
        events = self._call(f"users/{user['login']}/events?per_page=30") or []
        repos = [
            e["repo"]["name"]
            for e in events
            if e["repo"]["name"].startswith(user["login"] + "/")
        ]
        if not repos:
            raise RuntimeError(
                "no recent activity found — pass a repo explicitly: ghstats owner/repo"
            )
        return max(set(repos), key=repos.count)

    # ── repo data ────────────────────────────────────────────────────────────

    def fetch_all(self, repo: str) -> dict:
        """Pull repo metadata + traffic + commits in one bundle.

        Returns a dict with keys:
            repo, fetched, meta, clones, views, referrers, paths,
            languages, commits
        Traffic payloads keep their raw shape; the widgets layer knows how
        to read them (see ghstats/widgets.py).
        """
        data = {"repo": repo, "fetched": datetime.now()}
        data["meta"] = self._call(f"repos/{repo}")
        data["clones"] = self._call(f"repos/{repo}/traffic/clones")
        data["views"] = self._call(f"repos/{repo}/traffic/views")
        data["referrers"] = self._call(f"repos/{repo}/traffic/popular/referrers")
        data["paths"] = self._call(f"repos/{repo}/traffic/popular/paths")
        data["languages"] = self._call(f"repos/{repo}/languages")
        since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        commits = self._call(f"repos/{repo}/commits?per_page=10&since={since}")
        data["commits"] = commits if isinstance(commits, list) else []
        return data