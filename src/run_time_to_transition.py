"""Entry point for the time-to-transition survival analysis.

Runs five steps in order, each depending only on what the previous produced:

    1. read the member-month panel from CSV
    2. pop              filter to the study population
    3. create_analytic  reduce to one row per member and derive the survival
                        variables
    4. write the analytic file, which is the input to report.qmd
    5. render report.qmd

Steps 1 through 4 run in Python. Step 5 requires Quarto; without it, the
analytic file is still produced.

    python run_time_to_transition.py
"""

import os
import shutil
import subprocess
import sys

import pandas as pd

import create_analytic
import pop
from paths import (
    ANALYTIC_PATH,
    KM_FIGURE,
    OUTPUT_ROOT,
    PANEL_CSV,
    REPORT_HTML,
    REPORT_QMD,
)

DATE_COLUMNS = [
    "EFFMNTHBEGIN",
    "EFFMNTHEND",
    "LEASESTARTDATE",
    "APPROVALDATE",
    "HOUSESEPDATE",
    "DEATHDATE",
]


def read_panel():
    """Step 1: the member-month panel, one row per member per enrollment month."""
    if not PANEL_CSV.exists():
        raise FileNotFoundError(f"no member-month panel at {PANEL_CSV}")
    panel = pd.read_csv(PANEL_CSV, parse_dates=DATE_COLUMNS)
    print(f"read {PANEL_CSV.name}: {len(panel):,} rows, {panel['ID'].nunique():,} members")
    return panel


def build_analytic_file():
    """Steps 1 to 4: panel to analytic file."""
    panel = read_panel()

    population = pop.population_ids(panel)
    excluded = panel["ID"].nunique() - len(population)
    print(f"population: {len(population):,} members ({excluded:,} excluded by the SFY2017 filter)")

    analytic = create_analytic.add_transition_buckets(
        create_analytic.build_analytic(panel, population)
    )
    no_approval = len(population) - len(analytic)
    print(
        f"analytic: {len(analytic):,} members "
        f"({no_approval:,} dropped for a missing approval date)"
    )

    ANALYTIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_pickle(ANALYTIC_PATH)
    print(f"wrote {ANALYTIC_PATH}: {len(analytic):,} members")
    return analytic


def render():
    """Step 5: render the report into ``output/``.

    Quarto is not importable, so it is invoked as a command. It runs the report
    with the working directory set to the report source's own folder, which is
    why that source sits beside the modules it imports. If Quarto is missing,
    say so rather than failing — the analytic file is already written and is
    the input the report needs.
    """
    if shutil.which("quarto") is None:
        print(
            "\nquarto is not on PATH, so the report was not rendered.\n"
            "Install Quarto 1.4 or later, then run:\n"
            f"    cd {REPORT_QMD.parent.name} && "
            f"quarto render {REPORT_QMD.name} --output-dir ../output"
        )
        return

    output_dir = os.path.relpath(OUTPUT_ROOT, REPORT_QMD.parent)
    subprocess.run(
        ["quarto", "render", REPORT_QMD.name, "--output-dir", output_dir],
        cwd=REPORT_QMD.parent,
        check=True,
    )
    print(f"\nrendered {REPORT_HTML}")
    print(f"figure for the README: {KM_FIGURE}")


def main():
    build_analytic_file()
    render()
    return 0


if __name__ == "__main__":
    sys.exit(main())
