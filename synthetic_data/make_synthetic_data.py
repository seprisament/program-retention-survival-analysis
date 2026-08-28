"""Generate a synthetic member-month panel.

All data produced here are synthetic. No real member, program, or organization
is represented, and every number the analysis reports is a property of this
generator rather than of any real housing program.

The generator encodes the *qualitative shape* of two findings and nothing more:

1. Separation risk is identical for everyone who transitioned in under twelve
   months, so the three faster buckets should not differ meaningfully.
2. Members who took twelve months or longer separate faster, so that bucket
   should sit below the others.

Transition time touches separation through exactly one switch,
``LONG_WAIT_HAZARD_MULTIPLIER``, applied above ``LONG_WAIT_DAYS``. Nothing else
in the generator knows about the buckets, and no target p-value, percentage, or
survival probability is written down anywhere. Whether the log-rank tests reach
significance is a consequence of that multiplier and the sample size.

A small share of members are given deliberately broken records — no approval
date, approval after the lease, a lease outside the enrollment span, a lease
before the SFY2017 floor — so the population filter in ``pop.py`` has real work
to do.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# This script sits beside the panel it writes rather than beside the pipeline,
# so src/ has to be on the path before paths.py can be imported from it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from paths import PANEL_CSV  # noqa: E402

SEED = 20250101
N_MEMBERS = 6000

# Last day the extract covers. Members still housed here are censored.
DATA_END = pd.Timestamp("2025-01-31")
# First leases are spread across this window.
LEASE_WINDOW_START = pd.Timestamp("2016-07-01")
LEASE_WINDOW_END = pd.Timestamp("2023-12-31")

# Transition time in days is lognormal: a median under three months with a long
# right tail, so most members transition quickly and a minority wait a year or more.
TRANSITION_MEDIAN_DAYS = 75
TRANSITION_LOG_SD = 1.2
TRANSITION_MAX_DAYS = 1800

# Monthly probability of separating, higher during the first year housed. This is
# what gives the survival curves their steep early drop and long flat tail.
HAZARD_EARLY = 0.030
HAZARD_LATE = 0.011
EARLY_MONTHS = 12

# The one place transition time enters. Members who waited at least this long
# carry a higher monthly separation hazard; below it every member is identical.
LONG_WAIT_DAYS = 360
LONG_WAIT_HAZARD_MULTIPLIER = 1.7

# Enrollment continues this long past a separation before the member drops out
# of the panel. Keeps the panel a realistic size rather than carrying every
# member to the end of the extract.
MONTHS_ENROLLED_AFTER_SEPARATION = 3

# Share of separating members who die within a month of separating.
DEATH_SHARE_OF_SEPARATORS = 0.28
DEATH_WINDOW_DAYS = 30

# Records that the population filter should exclude.
SHARE_NO_APPROVAL = 0.02
SHARE_APPROVAL_AFTER_LEASE = 0.015
SHARE_LEASE_OUTSIDE_SPAN = 0.02
SHARE_LEASE_BEFORE_FLOOR = 0.015


def draw_members(rng):
    """One row per member: the latent facts the panel is built from."""
    lease_span_days = (LEASE_WINDOW_END - LEASE_WINDOW_START).days
    lease_start = LEASE_WINDOW_START + pd.to_timedelta(
        rng.integers(0, lease_span_days, N_MEMBERS), unit="D"
    )

    transition_days = np.clip(
        np.round(
            TRANSITION_MEDIAN_DAYS * np.exp(TRANSITION_LOG_SD * rng.standard_normal(N_MEMBERS))
        ).astype(int)
        + 1,
        1,
        TRANSITION_MAX_DAYS,
    )

    members = pd.DataFrame(
        {
            "CNDSID": [f"S{i:06d}" for i in range(N_MEMBERS)],
            "lease_start": lease_start,
            "transition_days": transition_days,
        }
    )
    members["approval"] = members["lease_start"] - pd.to_timedelta(
        members["transition_days"], unit="D"
    )
    return members


def draw_separations(members, rng):
    """Months housed until separation, or censoring at the end of the extract.

    Walks month by month so the hazard can change with time housed. Members whose
    separation would land past the end of the extract are censored instead.
    """
    long_wait = members["transition_days"] >= LONG_WAIT_DAYS
    sep_dates = []
    for lease_start, waited_long in zip(members["lease_start"], long_wait):
        multiplier = LONG_WAIT_HAZARD_MULTIPLIER if waited_long else 1.0
        month = 0
        sep_date = pd.NaT
        while True:
            month += 1
            candidate = lease_start + pd.DateOffset(months=month)
            if candidate > DATA_END:
                break
            hazard = HAZARD_EARLY if month <= EARLY_MONTHS else HAZARD_LATE
            if rng.random() < hazard * multiplier:
                # Separation falls somewhere inside the month it occurs.
                sep_date = candidate + pd.Timedelta(int(rng.integers(0, 28)), "D")
                if sep_date > DATA_END:
                    sep_date = pd.NaT
                break
        sep_dates.append(sep_date)

    members = members.copy()
    members["sep_date"] = pd.to_datetime(pd.Series(sep_dates, index=members.index))

    separated = members.index[members["sep_date"].notna()]
    dying = rng.choice(
        separated,
        size=int(round(len(separated) * DEATH_SHARE_OF_SEPARATORS)),
        replace=False,
    )
    members["death_date"] = pd.NaT
    members.loc[dying, "death_date"] = members.loc[dying, "sep_date"] + pd.to_timedelta(
        rng.integers(0, DEATH_WINDOW_DAYS, len(dying)), unit="D"
    )
    members.loc[members["death_date"] > DATA_END, "death_date"] = pd.NaT
    return members


def break_some_records(members, rng):
    """Give a few members records the population filter is meant to exclude."""
    members = members.copy()
    members["span_start_offset_months"] = 0

    pool = rng.permutation(members.index)
    sizes = [
        int(round(share * N_MEMBERS))
        for share in (
            SHARE_NO_APPROVAL,
            SHARE_APPROVAL_AFTER_LEASE,
            SHARE_LEASE_OUTSIDE_SPAN,
            SHARE_LEASE_BEFORE_FLOOR,
        )
    ]
    edges = np.cumsum([0] + sizes)
    no_approval, approval_late, outside_span, before_floor = (
        pool[edges[i] : edges[i + 1]] for i in range(4)
    )

    members.loc[no_approval, "approval"] = pd.NaT
    # Approval after the lease start, which cannot produce a transition time.
    members.loc[approval_late, "approval"] = members.loc[
        approval_late, "lease_start"
    ] + pd.to_timedelta(rng.integers(1, 60, len(approval_late)), unit="D")
    # Enrollment begins after the first lease, so no member-month contains it.
    members.loc[outside_span, "span_start_offset_months"] = 2
    # First lease before the SFY2017 floor.
    members.loc[before_floor, "lease_start"] = LEASE_WINDOW_START - pd.to_timedelta(
        rng.integers(30, 400, len(before_floor)), unit="D"
    )
    return members


def build_panel(members):
    """Expand one row per member into one row per member per enrollment month.

    Enrollment starts the month the member was approved, so the wait for housing
    sits inside the panel, and runs to the end of the extract.
    """
    rows = []
    for m in members.itertuples():
        anchor = m.approval if pd.notna(m.approval) else m.lease_start
        span_start = (
            anchor.to_period("M").to_timestamp()
            + pd.DateOffset(months=m.span_start_offset_months)
        )
        if pd.notna(m.lease_start) and span_start < m.lease_start:
            span_start = min(span_start, m.lease_start)
        span_end = DATA_END
        if pd.notna(m.sep_date):
            span_end = min(
                DATA_END,
                m.sep_date + pd.DateOffset(months=MONTHS_ENROLLED_AFTER_SEPARATION),
            )

        month = span_start
        while month <= span_end:
            begin = month
            end = month + pd.DateOffset(months=1) - pd.Timedelta(1, "D")
            rows.append(
                {
                    "CNDSID": m.CNDSID,
                    "EFFMNTHBEGIN": begin,
                    "EFFMNTHEND": min(end, DATA_END),
                    "MINLEASESTART": m.lease_start,
                    "DHHSDETDATE": m.approval,
                    # Carried on every month from the separation onward, so that
                    # taking the minimum per member recovers the first separation.
                    "HOUSESEPDATE": m.sep_date
                    if pd.notna(m.sep_date) and m.sep_date <= end
                    else pd.NaT,
                    "DEATHDATE": m.death_date,
                }
            )
            month = month + pd.DateOffset(months=1)
    return pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(SEED)
    members = draw_members(rng)
    members = draw_separations(members, rng)
    members = break_some_records(members, rng)
    panel = build_panel(members)

    PANEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_CSV, index=False)

    print(f"wrote {PANEL_CSV}")
    print(f"  members:      {panel['CNDSID'].nunique():,}")
    print(f"  member-months:{len(panel):>8,}")
    print(f"  separated:    {members['sep_date'].notna().mean():.1%}")
    print(f"  died:         {members['death_date'].notna().mean():.1%}")
    waited_long = members["transition_days"] >= LONG_WAIT_DAYS
    print(f"  waited {LONG_WAIT_DAYS}+ days: {waited_long.mean():.1%}")


if __name__ == "__main__":
    main()
