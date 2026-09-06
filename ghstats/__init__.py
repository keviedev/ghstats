"""ghstats — a terminal dashboard for GitHub repo traffic.

Styled in the neo-glitch palette (RGB-split neon on void black).
Auth is delegated entirely to the `gh` CLI — no tokens stored.
"""

__version__ = "0.2.0"

from .api import GitHubAPI
from .app import GhStats, main

__all__ = ["GitHubAPI", "GhStats", "main"]