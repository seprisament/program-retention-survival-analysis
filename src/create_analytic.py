"""Build the one-row-per-member analytic file for the survival analysis."""

import pandas as pd

# Bucket cutoffs use a flat 30-day month.
DAYS_PER_MONTH_BUCKET = 30

# Cutoffs in days, keyed by month.
BUCKET_MONTHS = [3, 6, 12]
BUCKET_DAYS = {m: m * DAYS_PER_MONTH_BUCKET for m in BUCKET_MONTHS}

B_GROUPS = ["< 3", "3-6","6-12", "12+"]



# Dates carried onto the analytic file, truncated to whole days.
DATE_COLUMNS = ["DeathDt", "DHHSDETDATE", "InitStartDt", "FirstSepDt"]


def build_analytic(member_month, population):
    """Reduce the member-month panel to one row per member.

    Each surviving row is the member's *transition record*: the member-month
    whose span contains their first lease start. The row carries the two
    quantities the survival analysis needs — how long the member waited to
    transition into housing, and how long they then stayed housed.

    Two orderings matter:

    1. ``FirstSepDt`` is the earliest separation date across *all* of the
       member's rows, computed before the panel is reduced to the transition
       record. It therefore reflects every lease, not just the first.
    2. The censoring date is the last day of the extract, taken
       before the population filter.

    Members who never separated get ``sep = 0`` and are censored at that date.

    Parameters
    ----------
    member_month : pandas.DataFrame
        The full member-month panel, one row per member per enrollment month.
    population : array-like
        Member IDs (``CNDSID``) in the study population, from
        ``pop.population_ids``.

    Returns
    -------
    pandas.DataFrame
        One row per member, indexed positionally.
    """
    # Censoring date: the last day of available data, across the whole panel.
    last_day = pd.to_datetime(member_month["EFFMNTHEND"]).max().normalize()

    panel = member_month[member_month["CNDSID"].isin(population)].copy()

    # Earliest separation across all of the member's leases. Computed on the
    # full set of the member's rows, before reducing to the transition record.
    # Members who never separated keep NaT.
    panel["HOUSESEPDATE"] = pd.to_datetime(panel["HOUSESEPDATE"])
    panel["FirstSepDt"] = panel.groupby("CNDSID")["HOUSESEPDATE"].transform("min")

    # The transition record: the member-month span containing the first lease
    # start. Both bounds inclusive, as in the population filter.
    lease_start = pd.to_datetime(panel["MINLEASESTART"])
    span_begin = pd.to_datetime(panel["EFFMNTHBEGIN"])
    span_end = pd.to_datetime(panel["EFFMNTHEND"])
    is_transition_record = (lease_start >= span_begin) & (lease_start <= span_end)

    analytic = (
        panel.loc[
            is_transition_record,
            [
                "CNDSID",
                "DHHSDETDATE",
                "MINLEASESTART",
                "FirstSepDt",
                "DEATHDATE"
            ],
        ]
        .rename(columns={"MINLEASESTART": "InitStartDt", "DEATHDATE": "DeathDt"})
        .reset_index(drop=True)
    )

    # Truncate to whole days; any time component would skew the day counts below.
    for column in DATE_COLUMNS:
        analytic[column] = pd.to_datetime(analytic[column]).dt.normalize()

    # Approval to first lease start.
    analytic["DaysToTrans"] = (
        analytic["InitStartDt"] - analytic["DHHSDETDATE"]
    ).dt.days
    analytic["MonthsToTrans"] = analytic["DaysToTrans"] / DAYS_PER_MONTH_BUCKET

    # The event: 1 if the member separated, 0 if still housed at the end of
    # the data. Members who died count as separating.
    analytic["sep"] = analytic["FirstSepDt"].notna().astype(int)

    analytic["SepDaysToDeath"] = (analytic["DeathDt"] - analytic["FirstSepDt"]).dt.days
    # Strictly under 30 days. A missing value is 0, not missing — a comparison
    # against NaT is already False, so the cast handles it.
    analytic["SepDeath"] = (analytic["SepDaysToDeath"] < 30).astype(int)

    # Follow-up time: lease start to separation, or to the end of the data for
    # members who never separated.
    analytic["HousedEndDt"] = analytic["FirstSepDt"].where(
        analytic["sep"] == 1, last_day
    )
    # Plus one day, so both the first day housed and the last are counted.
    analytic["DaysHoused"] = (
        analytic["HousedEndDt"] - analytic["InitStartDt"]
    ).dt.days + 1
    analytic["MonthsHoused"] = analytic["DaysHoused"] / DAYS_PER_MONTH_BUCKET

    assert not analytic["CNDSID"].duplicated().any(), (
        "more than one transition record per member"
    )

    return analytic


def add_transition_buckets(analytic):
    """Group members by how long they waited to transition into housing.

    Adds ``b``, the time to transition bucket, which splits transition time at 3 ,6, and 12 months using the
    flat 30-day month.

    Parameters
    ----------
    analytic : pandas.DataFrame
        Output of ``build_analytic``.

    Returns
    -------
    pandas.DataFrame
        The same frame with ``b`` added.
    """
    analytic = analytic.copy()
    days = analytic["DaysToTrans"]

    b = pd.Series(None, index=analytic.index, dtype=object)
    b[days < BUCKET_DAYS[3]] = "< 3"
    b[days.between(BUCKET_DAYS[3] , BUCKET_DAYS[6])] = "3-6"
    b[days.between(BUCKET_DAYS[6], BUCKET_DAYS[12])] = "6-12"
    b[days >= BUCKET_DAYS[12]] = "12+"

    analytic["b"] = pd.Categorical(b, categories=B_GROUPS, ordered=True)

    assert analytic["b"].notna().all(), "b is missing for some members"
    
    return analytic
