# H.R. 6938 Appropriations Tables Research

## Bill Overview

- **Bill:** H.R. 6938, 119th Congress
- **Title:** Commerce, Justice, Science; Energy and Water Development; and Interior and Environment Appropriations Act, 2026
- **Status:** Signed into law January 23, 2026 (Public Law 119-74)
- **Introduced:** January 6, 2026 by Mr. Cole (Chair, House Committee on Appropriations)
- **Three Divisions:**
  - Division A: Commerce, Justice, Science, and Related Agencies
  - Division B: Energy and Water Development and Related Agencies
  - Division C: Department of the Interior, Environment, and Related Agencies

## Key Finding: Tables Are NOT in the Bill PDF

The bill text PDF (232 pages) contains only inline dollar amounts in legislative prose. No formatted tables. The bill repeatedly references tables that live in a separate **explanatory statement**.

Section 4 of the bill states the explanatory statement "shall have the same effect with respect to the allocation of funds" as a joint explanatory statement of a committee of conference.

## Where the Tables Actually Are

The appropriations tables are in the **explanatory statement** published in the Congressional Record on January 8, 2026, spanning **pages H255 through H591** (~336 pages).

### Source URLs (best to worst for extraction)

1. **House Rules Committee page** (likely has standalone explanatory statement):
   - https://rules.house.gov/bill/119/PIH-FY2026-CJS-EnergyWater-Interior
   - Try this first, may have a clean PDF of just the explanatory statement

2. **Congressional Record HTML** (searchable, but truncated in single-page view):
   - https://www.govinfo.gov/content/pkg/CREC-2026-01-08/html/CREC-2026-01-08-pt3-PgH255.htm
   - Only covers Division A before truncating

3. **Congress.gov Congressional Record article**:
   - https://www.congress.gov/congressional-record/volume-172/issue-5/house-section/article/H255-1
   - May have better pagination/navigation than govinfo

4. **Full Congressional Record PDF** (very large, contains entire day's proceedings):
   - https://www.govinfo.gov/content/pkg/CREC-2026-01-08/pdf/CREC-2026-01-08.pdf

5. **Enrolled bill** (final signed version, still just bill text, no tables):
   - https://www.govinfo.gov/content/pkg/BILLS-119hr6938enr/pdf/BILLS-119hr6938enr.pdf

6. **House Report 119-424** (Rules Committee report, procedural, not the tables):
   - https://www.govinfo.gov/content/pkg/CRPT-119hrpt424/pdf/CRPT-119hrpt424.pdf

## Tables Found So Far (Division A only)

The HTML page was truncated and only yielded Division A tables. Division B and C tables remain to be extracted.

### Division A: Commerce, Justice, Science

| # | Table Title | Agency | Total Funding |
|---|-------------|--------|---------------|
| 1 | Economic Development Assistance Programs | EDA | $400M |
| 2 | CHIPS Act FY2026 Allocation | NIST | $6.6B |
| 3 | National Ocean Service Operations | NOAA | $677.2M |
| 4 | National Marine Fisheries Service Operations | NOAA | $1.12B |
| 5 | Office of Oceanic & Atmospheric Research | NOAA | $588.9M |
| 6 | National Weather Service Operations | NOAA | $1.35B |
| 7 | NESDIS Operations | NOAA | $397.5M |
| 8 | Mission Support Operations | NOAA | $364.7M |
| 9 | OMAO Operations | NOAA | $361.2M |
| 10 | NOAA Procurement, Acquisition & Construction | NOAA | $1.59B |
| 11 | NOAA Construction (state-by-state) | NOAA | $60M |
| 12 | Violence Against Women Prevention Programs | OVW | $720M |
| 13 | Research, Evaluation & Statistics | OJP | $55M |
| 14 | State & Local Law Enforcement Assistance | OJP | $2.4B |

### Division B: Energy and Water Development
- **Not yet extracted.** Tables are in pages ~H400+ of the Congressional Record.

### Division C: Interior and Environment
- **Not yet extracted.** Tables are in the later pages of the Congressional Record.

## Next Steps

1. **Try the Rules Committee page first** - it may have the explanatory statement as a standalone document, which would be easier to parse than the Congressional Record
2. **If that fails, fetch the full Congressional Record PDF** and extract pages H255-H591
3. **Parse the HTML version in chunks** - the govinfo HTML is paginated; try incrementing the page number in the URL (e.g., PgH300, PgH400, PgH500) to reach Division B and C content
4. **Extract table data** - once we have the full text, parse the tables into structured data (CSV or JSON) for each division
5. **Community Project Funding tables** - the bill references "Community Project Funding/Congressionally Directed Spending" tables multiple times; these earmark tables are also in the explanatory statement

## URL Pattern for Paginated Access

The Congressional Record HTML pages follow this pattern:
```
https://www.govinfo.gov/content/pkg/CREC-2026-01-08/html/CREC-2026-01-08-pt3-PgH{PAGE_NUMBER}.htm
```

Try pages: H255, H300, H350, H400, H450, H500, H550 to find Division B and C content.
