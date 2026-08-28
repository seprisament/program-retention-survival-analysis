"""Every path the pipeline reads or writes, defined once.

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
# It is named index.qmd so the published site serves it at the root.
REPORT_QMD = SRC_ROOT / "index.qmd"
# Rendered output. Not committed: the site is published to the gh-pages branch,
# and this directory is rebuilt on every render.
SITE_ROOT = SRC_ROOT / "_site"

# The one figure the README embeds. Written when the report renders, so it never
# drifts from the data behind it, and committed so GitHub can display it.
KM_FIGURE = PROJECT_ROOT / "readme_diag" / "km_curve.png"

OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", PROJECT_ROOT / "output"))
ANALYTIC_PATH = OUTPUT_ROOT / "sa_analytic.pkl"
