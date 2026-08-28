"""Build the one-row-per-member analytic file for the survival analysis."""

import pandas as pd

# Bucket cutoffs use a flat 30-day month.
DAYS_PER_MONTH_BUCKET = 30

# Cutoffs in days, keyed by month.
BUCKET_MONTHS = [3, 6, 12]
BUCKET_DAYS = {m: m * DAYS_PER_MONTH_BUCKET for m in BUCKET_MONTHS}

B_GROUPS = ["< 3", "3-6", "6-12", "12+"]


# Dates carried onto the analytic file, truncated to whole days.
DATE_COLUMNS = ["DeathDt", "APPROVALDATE", "InitStartDt", "FirstSepDt"]


def build_analytic(member_month, population):
    """Reduce the member-month panel to one row per member.

    Each row carries the two quantities the survival analysis needs — how long
    the member waited to transition into housing, and how long they then
    stayed housed.

    Two data-quality resolutions are applied here:

    1. Members with no ``APPROVALDATE`` are dropped. Transition time is the
       predictor and cannot be computed without an approval date.
    2. Where ``DEATHDATE`` is populated it is treated as the source of truth
       for the end of the member's time in the program, so the separation
       date is set to it.

    The censoring date is the last day of the extract, taken across the whole
    panel before the population filter. Members who never separated get
    ``sep = 0`` and are censored at that date.

    Parameters
    ----------
    member_month : pandas.DataFrame
        The full member-month panel, one row per member per enrollment month.
    population : array-like
        Member IDs (``ID``) in the study population, from
        ``pop.population_ids``.

    Returns
    -------
    pandas.DataFrame
        One row per member, indexed positionally.
    """
    # Censoring date: the last day of available data, across the whole panel.
    last_day = pd.to_datetime(member_month["EFFMNTHEND"]).max().normalize()

    panel = member_month[member_month["ID"].isin(population)].copy()
    for column in ["LEASESTARTDATE", "APPROVALDATE", "HOUSESEPDATE", "DEATHDATE"]:
        panel[column] = pd.to_datetime(panel[column])

    # One row per member. LEASESTARTDATE, APPROVALDATE and DEATHDATE are
    # repeated across a member's rows, so the minimum recovers the single
    # value; HOUSESEPDATE is populated only in the separation month, so its
    # minimum is the member's separation date and stays NaT if they never
    # separated.
    analytic = panel.groupby("ID", as_index=False).agg(
        InitStartDt=("LEASESTARTDATE", "min"),
        APPROVALDATE=("APPROVALDATE", "min"),
        FirstSepDt=("HOUSESEPDATE", "min"),
        DeathDt=("DEATHDATE", "min"),
    )

    # Data quality: members approved through software that did not record an
    # approval date. Without it there is no transition time.
    analytic = analytic[analytic["APPROVALDATE"].notna()].reset_index(drop=True)

    # Data quality: a reporting lag can leave the separation date later than
    # the death date. DEATHDATE is the source of truth.
    died = analytic["DeathDt"].notna()
    analytic.loc[died, "FirstSepDt"] = analytic.loc[died, "DeathDt"]

    # Truncate to whole days; any time component would skew the day counts below.
    for column in DATE_COLUMNS:
        analytic[column] = analytic[column].dt.normalize()

    # Approval to first lease start.
    analytic["DaysToTrans"] = (
        analytic["InitStartDt"] - analytic["APPROVALDATE"]
    ).dt.days
    analytic["MonthsToTrans"] = analytic["DaysToTrans"] / DAYS_PER_MONTH_BUCKET

    # The event: 1 if the member separated, 0 if still housed at the end of
    # the data. Members who died count as separating.
    analytic["sep"] = analytic["FirstSepDt"].notna().astype(int)

    # The last day the extract covers, carried onto every row. Reporting it
    # from here is exact; recovering it downstream from HousedEndDt would only
    # work as long as at least one member is censored.
    analytic["DataEndDt"] = last_day

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

    assert not analytic["ID"].duplicated().any(), "more than one row per member"

    return analytic


def add_transition_buckets(analytic):
    """Group members by how long they waited to transition into housing.

    Adds ``b``, the time to transition bucket, which splits transition time at
    3, 6, and 12 months using the flat 30-day month.

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
    b[(days >= BUCKET_DAYS[3]) & (days < BUCKET_DAYS[6])] = "3-6"
    b[(days >= BUCKET_DAYS[6]) & (days < BUCKET_DAYS[12])] = "6-12"
    b[days >= BUCKET_DAYS[12]] = "12+"

    analytic["b"] = pd.Categorical(b, categories=B_GROUPS, ordered=True)

    assert analytic["b"].notna().all(), "b is missing for some members"

    return analytic
