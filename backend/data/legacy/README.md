# Legacy MPLADS Datasets (Compatibility Layer)

These files are **archived historical MP-level datasets**. They are preserved for
reference and future compatibility work. They are **NOT merged into the project
database** because no safe record-level join to individual projects exists.

## Files

| File | Period | Granularity | Source era |
|---|---|---|---|
| `mplads_mp_summary_2014_2019.csv` | 2014–19 | One row per MP | 17th Lok Sabha MPLADS account summary |
| `mplads_goi_release_2014_2019.csv` | 2014–19 | One row per MP | Pending GOI release as on 21/08/2022 (17th LS) |
| `mplads_goi_release_2009_2014.csv` | 2009–14 | One row per MP | Pending GOI release as on 21/08/2022 (15th LS) |

## Schemas

### mplads_mp_summary_2014_2019.csv
`Sl No, MP Name, Constituency, Entitlement, FundReceivedGOI, AmountAvailable,
WorksRecommCost, WSCost, ActualExpenditureIncurred, UtilizationOverRelease,
UnspentBalance` — all monetary values in **₹ crore**.
No dates, no work IDs, no project-level rows.

### mplads_goi_release_*.csv
`State, House, Sno, MPName, Constituency, District, TotalEntitlementAmount_crore,
TotalGOIRelease_crore, ReleasePendingAmount_crore, UnSanctionBalance_crore,
UnspentBalance_crore, LastInstNumber1, LastInstYear, LastReleaseDate,
LastRelAmount_crore, PendingInstallmentNumberAndYear, ReasonsforNotRel,
ls_start_year, ls_end_year, lok_sabha` (after 5 header/preamble rows).
`LastReleaseDate` is an **MP fund-release date**, not a project date.
`ReasonsforNotRel` (e.g. "Audit Certificate Pending, Eligible MPR not Received")
explains pending **fund releases**, not project delays.

## Why they are not joined to projects

1. **No work/project identifiers** — none of these files carry Work IDs or
   project-level rows. The application's `projects`, `recommended_works`,
   `expenditures` and `completed_works` tables are all work-level.
2. **Identifier spaces differ** — the only shared dimension is MP name +
   constituency, which is one-to-many toward works (an MP has hundreds of works).
   Joining at that granularity would attach one MP's fund-release history to
   every one of their projects — an incorrect match.
3. **Conservative matching policy** — the platform only attaches events to a
   project when the match is unambiguous (exact normalized work description +
   constituency + state, optionally MP-verified). MP-level aggregates fail this
   test by construction.

## Future use

If a future dataset provides work-level identifiers for these eras (e.g. a
MPLADS API with per-work sanction dates), it can be integrated through
`backend/providers/` (implement a new `DataProvider`) and the timeline builder in
`backend/timeline.py` will pick up sanction/commencement events automatically.
