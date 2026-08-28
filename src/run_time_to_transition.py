"""Entry point for the time-to-transition survival analysis.

Runs three steps in order, each depending only on what the previous produced:

    1. read the member-month panel from CSV
    2. pop              filter to the study population
    3. create_analytic  reduce to one row per member and derive the survival
                        variables, then write the analytic file

then renders the report from that file.

    python run_time_to_transition.py
"""

import shutil
import subprocess
import sys

import pandas as pd

import create_analytic
import pop
from paths import ANALYTIC_PATH, KM_FIGURE, PANEL_CSV, REPORT_QMD, SITE_ROOT

DATE_COLUMNS = [
    "EFFMNTHBEGIN",
    "EFFMNTHEND",
    "MINLEASESTART",
    "DHHSDETDATE",
    "HOUSESEPDATE",
    "DEATHDATE",
]


def read_panel():
    """Step 1: the member-month panel, one row per member per enrollment month."""
    if not PANEL_CSV.exists():
        raise FileNotFoundError(f"no member-month panel at {PANEL_CSV}")
    panel = pd.read_csv(PANEL_CSV, parse_dates=DATE_COLUMNS)
    print(f"read {PANEL_CSV.name}: {len(panel):,} rows, {panel['CNDSID'].nunique():,} members")
    return panel


def build_analytic_file():
    """Steps 1 to 3: panel to analytic file."""
    panel = read_panel()

    population = pop.population_ids(panel)
    excluded = panel["CNDSID"].nunique() - len(population)
    print(f"population: {len(population):,} members ({excluded:,} excluded by the filter)")

    analytic = create_analytic.add_transition_buckets(
        create_analytic.build_analytic(panel, population)
    )

    ANALYTIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_pickle(ANALYTIC_PATH)
    print(f"wrote {ANALYTIC_PATH}: {len(analytic):,} members")
    return analytic


def render():
    """Render the report locally, into ``src/_site/``.

    Quarto is not importable, so it is invoked as a command. It runs the report
    with the working directory set to the report source's own folder, which is
    why that source sits beside the modules it imports. If Quarto is missing,
    say so rather than failing — the analytic file is already written and is
    the input the report needs.

    This renders only. Publishing the site is a separate, deliberate step:
    ``cd src && quarto publish gh-pages``.
    """
    if shutil.which("quarto") is None:
        print(
            "\nquarto is not on PATH, so the report was not rendered.\n"
            "Install Quarto 1.4 or later, then run:\n"
            f"    cd {REPORT_QMD.parent.name} && quarto render"
        )
        return

    subprocess.run(["quarto", "render"], cwd=REPORT_QMD.parent, check=True)
    print(f"\nrendered {SITE_ROOT / 'index.html'}")
    print(f"figure for the README: {KM_FIGURE}")


def main():
    build_analytic_file()
    render()
    return 0


if __name__ == "__main__":
    sys.exit(main())
