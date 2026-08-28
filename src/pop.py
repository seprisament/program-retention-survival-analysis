"""Filter the member-month panel to the study population.
"""

import pandas as pd

# Lower bound on first lease start: the first day of SFY2017.
SFY2017_START = pd.Timestamp("2016-07-01")


def population_ids(member_month):
    """Return the member IDs eligible for the analysis.

    Only members whose first lease began after SFY2017 are included.

    ``LEASESTARTDATE`` is repeated across all of a member's member-month rows,
    so the per-member minimum is that member's first lease start.

    Parameters
    ----------
    member_month : pandas.DataFrame
        The member-month panel, one row per member per enrollment month.

    Returns
    -------
    numpy.ndarray
        Unique member IDs (``ID``) in the study population.
    """
    lease_start = pd.to_datetime(member_month["LEASESTARTDATE"])
    first_lease = lease_start.groupby(member_month["ID"]).transform("min")

    return member_month.loc[first_lease >= SFY2017_START, "ID"].unique()
