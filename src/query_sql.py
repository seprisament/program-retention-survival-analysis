"""How the member-month panel used to be pulled. Kept for reference only.

This is not part of the pipeline and nothing imports it.

This analysis used to read its data from a reporting warehouse: a single
``MemberMonth`` table, one row per member per enrollment month, queried with
credentials supplied through the environment and never written into the code.
That warehouse is no longer accessible, so the pipeline now starts from a CSV
extract of the same panel instead — see ``run_time_to_transition.py``.

The query is preserved here because it documents where the data came from and
which columns the analysis depends on. ``read_member_month`` takes an open
DB-API connection rather than opening one, since there is no longer a database
for this module to connect to.
"""

import pandas as pd

TABLE = "MemberMonth"

# Columns the analysis needs. Named explicitly so a schema change surfaces here
# rather than as a missing column three steps downstream.
COLUMNS = [
    "ID",
    "EFFMNTHBEGIN",
    "EFFMNTHEND",
    "LEASESTARTDATE",
    "APPROVALDATE",
    "HOUSESEPDATE",
    "DEATHDATE",
]

DATE_COLUMNS = [
    "EFFMNTHBEGIN",
    "EFFMNTHEND",
    "LEASESTARTDATE",
    "APPROVALDATE",
    "HOUSESEPDATE",
    "DEATHDATE",
]

QUERY = f"SELECT {', '.join(COLUMNS)} FROM {TABLE} ORDER BY ID, EFFMNTHBEGIN"


def read_member_month(conn):
    """Read the member-month panel from an open connection.

    Parameters
    ----------
    conn : DB-API connection
        A connection to a database holding the ``MemberMonth`` table.

    Returns
    -------
    pandas.DataFrame
        One row per member per enrollment month, with dates parsed.
    """
    return pd.read_sql_query(QUERY, conn, parse_dates=DATE_COLUMNS)
