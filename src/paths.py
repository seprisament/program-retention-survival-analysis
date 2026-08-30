"""Every path the pipeline reads or writes.

``OUTPUT_ROOT`` may be set in the environment to redirect generated files;
it defaults to ``output/`` inside the project.
"""

import os
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_ROOT.parent

# The member-month panel the analysis starts from, and the generator that wrote it.
SYNTHETIC_DATA_ROOT = PROJECT_ROOT / "synthetic_data"
PANEL_CSV = SYNTHETIC_DATA_ROOT / "member_month.csv"

# The report source lives beside the modules it imports, because Quarto's
# jupyter engine executes it with the working directory set to its own folder.
REPORT_QMD = SRC_ROOT / "report.qmd"

# Everything the pipeline generates.
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", PROJECT_ROOT / "output"))
ANALYTIC_PATH = OUTPUT_ROOT / "analytic_file.pkl"
REPORT_HTML = OUTPUT_ROOT / "report.html"
# The one figure the README embeds. Written when the report renders, so it never
# drifts from the data behind it.
KM_FIGURE = OUTPUT_ROOT / "km_curve.png"
