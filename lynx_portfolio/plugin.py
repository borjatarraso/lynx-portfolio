"""Entry-point registration for the Lince Investor Suite plugin system.

Exposed via ``pyproject.toml`` under the ``lynx_investor_suite.agents``
entry-point group. See :mod:`lynx_investor_core.plugins` for the
discovery contract.
"""

from __future__ import annotations

from lynx_investor_core.plugins import SectorAgent

from lynx_portfolio import __version__


def register() -> SectorAgent:
    """Return this agent's descriptor for the plugin registry."""
    return SectorAgent(
        name="lynx-portfolio",
        short_name="portfolio",
        sector="Portfolio tracker",
        tagline="Multi-currency portfolio tracker with encrypted vault",
        prog_name="lynx-portfolio",
        version=__version__,
        package_module="lynx_portfolio",
        entry_point_module="lynx_portfolio.__main__",
        entry_point_function="main",
        icon="\U0001f4bc",  # briefcase
    )
