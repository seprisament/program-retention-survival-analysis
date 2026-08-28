"""Filter the member-month panel to the study population.
"""

import pandas as pd

# Lower bound on first lease start: the first day of SFY2017.
SFY2017_START = pd.Timestamp("2016-07-01")


def population_ids(member_month):
    """Return the member IDs eligible for the analysis.

    The population is members whose *first* housing lease can be tied to a
    housing-approval date and located inside their own enrollment span. A
    member is kept when all of the following hold on at least one of their
    member-month rows:

    1. Both ``MINLEASESTART`` (first lease start) and ``DHHSDETDATE``
       (housing approval) are present. A few records carry a first lease
       with no approval date; many carry an approval date with no lease.
       Neither can produce a transition time.
    2. ``DHHSDETDATE < MINLEASESTART`` — approval strictly precedes the
       lease. A few records have approval falling after the first lease
       start. The comparison is strict, so approval and lease on the same
       day is also excluded.
    3. ``MINLEASESTART`` falls inside that row's member-month span,
       ``EFFMNTHBEGIN`` to ``EFFMNTHEND``, both bounds inclusive. This is
       what anchors the analysis on the *first* lease: a member whose first
       lease predates their enrollment span, but who has a later lease
       overlapping it, appears in the panel with no member-month containing
       ``MINLEASESTART``, and is therefore excluded.
    4. ``MINLEASESTART >= 2016-07-01`` — the SFY2017 floor.

    Parameters
    ----------
    member_month : pandas.DataFrame
        The member-month panel, one row per member per enrollment month.

    Returns
    -------
    numpy.ndarray
        Unique member IDs (``CNDSID``) in the study population.
    """
    lease_start = pd.to_datetime(member_month["MINLEASESTART"])
    approval = pd.to_datetime(member_month["DHHSDETDATE"])
    span_begin = pd.to_datetime(member_month["EFFMNTHBEGIN"])
    span_end = pd.to_datetime(member_month["EFFMNTHEND"])

    keep = (
        lease_start.notna()
        & approval.notna()
        & (approval < lease_start)
        & (lease_start >= span_begin)
        & (lease_start <= span_end)
        & (lease_start >= SFY2017_START)
    )

    return member_month.loc[keep, "CNDSID"].unique()
