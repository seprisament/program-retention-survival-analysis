"""Generate a synthetic member-month panel.

All data produced here are synthetic. No real member, program, or organization
is represented, and every number the analysis reports is a property of this
generator rather than of any real housing program.

The panel matches the structure described under "Data Description" in the
README: one row per member per enrollment month, running from the member's
lease start to their separation or to the end of the extract, whichever comes
first. ``EFFMNTHBEGIN`` is the first of the month except in the member's first
month, where it is the lease start; ``EFFMNTHEND`` is the last of the month
except in the separation month, where it is the separation date.

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

Two groups of members are given records the pipeline is meant to act on, so the
population filter and the data-quality resolutions have real work to do:

- a first lease before the SFY2017 floor, which ``pop.py`` drops
- no approval date, which ``create_analytic.py`` drops
- a death recorded ahead of the separation date, which ``create_analytic.py``
  resolves by treating the death date as the source of truth

Nothing else is broken on purpose. The pipeline no longer filters on approval
falling after the lease, or on the lease sitting outside the enrollment span,
so the generator does not manufacture those cases either.
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
N_MEMBERS = 3000

# Last day the extract covers. Members still housed here are censored.
DATA_END = pd.Timestamp("2025-01-31")

# The SFY2017 floor that pop.py applies to the first lease start.
SFY2017_START = pd.Timestamp("2016-07-01")
# Leases inside the study window are spread across this range.
LEASE_WINDOW_START = SFY2017_START
LEASE_WINDOW_END = pd.Timestamp("2023-12-31")
# Leases the SFY2017 floor is meant to drop are spread across this one.
PRE_FLOOR_WINDOW_START = pd.Timestamp("2014-01-01")

# Attrition between the extract and the analysis population. The README puts
# the surviving share at roughly three quarters and the missing approval dates
# at under one percent, which leaves the SFY2017 floor accounting for the rest.
SHARE_LEASE_BEFORE_FLOOR = 0.243
SHARE_NO_APPROVAL = 0.007

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

# Share of separating members who died. The death is recorded first and the
# separation date catches up later, so DEATHDATE lands on or before HOUSESEPDATE
# — the reporting lag the README describes under "Resolve Data-Quality Issues."
DEATH_SHARE_OF_SEPARATORS = 0.28
DEATH_REPORTING_LAG_DAYS = 30


def draw_members(rng):
    """One row per member: the latent facts the panel is built from."""
    before_floor = rng.random(N_MEMBERS) < SHARE_LEASE_BEFORE_FLOOR

    pre_span = (SFY2017_START - PRE_FLOOR_WINDOW_START).days
    post_span = (LEASE_WINDOW_END - LEASE_WINDOW_START).days
    pre_floor = PRE_FLOOR_WINDOW_START + pd.to_timedelta(
        rng.integers(0, pre_span, N_MEMBERS), unit="D"
    )
    in_window = LEASE_WINDOW_START + pd.to_timedelta(
        rng.integers(0, post_span, N_MEMBERS), unit="D"
    )
    lease_start = pd.Series(np.where(before_floor, pre_floor, in_window))

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
            "ID": [f"S{i:06d}" for i in range(N_MEMBERS)],
            "lease_start": lease_start,
            "transition_days": transition_days,
        }
    )
    members["approval"] = members["lease_start"] - pd.to_timedelta(
        members["transition_days"], unit="D"
    )

    # Members approved through software that never recorded an approval date.
    no_approval = rng.random(N_MEMBERS) < SHARE_NO_APPROVAL
    members.loc[no_approval, "approval"] = pd.NaT

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

    # Deaths are recorded ahead of the separation date, never after it, so the
    # analytic step has a reporting lag to resolve rather than invent.
    separated = members.index[members["sep_date"].notna()]
    dying = rng.choice(
        separated,
        size=int(round(len(separated) * DEATH_SHARE_OF_SEPARATORS)),
        replace=False,
    )
    members["death_date"] = pd.NaT
    members.loc[dying, "death_date"] = members.loc[
        dying, "sep_date"
    ] - pd.to_timedelta(rng.integers(0, DEATH_REPORTING_LAG_DAYS, len(dying)), unit="D")
    # A death cannot precede the lease it is recorded against.
    too_early = members["death_date"] < members["lease_start"]
    members.loc[too_early, "death_date"] = members.loc[too_early, "lease_start"]
    return members


def build_panel(members):
    """Expand one row per member into one row per member per enrollment month.

    Enrollment runs from the lease start to the separation date, or to the end
    of the extract for members who never separated.
    """
    rows = []
    for m in members.itertuples():
        last_day = m.sep_date if pd.notna(m.sep_date) else DATA_END

        month_begin = m.lease_start
        while month_begin <= last_day:
            # The last day of the month, pulled back to the separation date or
            # the end of the extract when either falls first.
            month_end = min(month_begin + pd.offsets.MonthEnd(0), last_day)
            rows.append(
                {
                    "ID": m.ID,
                    "EFFMNTHBEGIN": month_begin,
                    "EFFMNTHEND": month_end,
                    "LEASESTARTDATE": m.lease_start,
                    "APPROVALDATE": m.approval,
                    # Populated only in the separation month.
                    "HOUSESEPDATE": m.sep_date
                    if pd.notna(m.sep_date) and month_end == m.sep_date
                    else pd.NaT,
                    "DEATHDATE": m.death_date,
                }
            )
            month_begin = month_end + pd.Timedelta(1, "D")
    return pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(SEED)
    members = draw_members(rng)
    members = draw_separations(members, rng)
    panel = build_panel(members)

    PANEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_CSV, index=False)

    before_floor = members["lease_start"] < SFY2017_START
    no_approval = members["approval"].isna()
    retained = ~before_floor & ~no_approval

    print(f"wrote {PANEL_CSV}")
    print(f"  members:      {panel['ID'].nunique():,}")
    print(f"  member-months:{len(panel):>8,}")
    print(f"  separated:    {members['sep_date'].notna().mean():.1%}")
    print(f"  died:         {members['death_date'].notna().mean():.1%}")
    waited_long = members["transition_days"] >= LONG_WAIT_DAYS
    print(f"  waited {LONG_WAIT_DAYS}+ days: {waited_long.mean():.1%}")
    print(f"  lease before SFY2017 floor: {before_floor.mean():.1%}")
    print(f"  no approval date:           {no_approval.mean():.1%}")
    print(f"  expected analysis population: {retained.sum():,} ({retained.mean():.1%})")


if __name__ == "__main__":
    main()
