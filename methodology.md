# Methodology: How We Extract Funding Amounts from Appropriations Bills

## What This Tool Does

This tool reads the official XML text of U.S. appropriations bills from Congress.gov and extracts dollar amounts into a spreadsheet-friendly format (CSV). It identifies how much money Congress allocates to each government program, agency, or account.

## How Appropriations Bills Are Structured

A typical appropriations bill is organized into:

- **Divisions** (lettered A, B, C...) covering broad areas like "Military Construction" or "Agriculture"
- **Titles** (numbered I, II, III...) covering departments or agencies within each division
- **Accounts** (named items like "Military construction, army" or "Medical Services") that receive specific dollar amounts

Each account section contains prose text that specifies the amount and conditions. For example:

> For acquisition, construction, installation, and equipment of temporary or permanent public works, military installations, facilities, and real property for the Army as currently authorized by law, **$2,022,775,000**, to remain available until September 30, 2028: *Provided*, That, of this amount, not to exceed $398,145,000 shall be available for study, planning, design...

In this example, $2,022,775,000 is the **primary allocation**. The $398,145,000 is a **sub-allocation** (a ceiling on how much of the primary amount can go to a specific purpose).

## How We Identify the Primary Allocation

The XML text for each account is divided into two parts:

1. **The main sentence** - States the primary dollar amount and what it's for
2. **Proviso clauses** - Begin with "Provided, That" and contain sub-allocations, conditions, and restrictions

We extract amounts only from the main sentence (before the first "Provided" clause). This structural approach avoids relying on specific word patterns to distinguish primary amounts from sub-allocations.

When multiple amounts appear in the main sentence, we keep:

- **The largest amount** - This is the primary allocation in the vast majority of cases. Smaller amounts that precede it are typically incidental limits (e.g., "$2,250 for official reception expenses").
- **Advance appropriations** - Amounts followed by "shall become available on October 1" of a future year. These are funds for the next fiscal year, included alongside current-year amounts in some accounts.
- **Additions to prior year** - Amounts described as "in addition to funds previously appropriated." These supplement funding from a prior year's bill.

## Amount Types

Each extracted amount is classified as one of three types:

| Type | What It Means |
|------|---------------|
| **appropriation** | New budget authority for the current fiscal year |
| **advance_appropriation** | Funds that become available in a future fiscal year |
| **addition_to_prior** | A supplement to amounts previously appropriated |

To calculate total new funding, sum all three types. They do not overlap.

## What Is Excluded

The primary-only export deliberately excludes:

- **Sub-allocation ceilings** ("not to exceed $X shall be available for...") - These are limits within the primary amount, not additional money
- **Directed spending** ("of which $X shall be for...") - These specify how parts of the primary amount must be used
- **Rescissions** ("$X is hereby rescinded") - These cancel previously appropriated funds and appear inside proviso clauses
- **Threshold references** ("cost estimates exceed $25,000") - Dollar amounts in restriction language, not funding
- **Prior-year references** ("of the $74,004,000,000 that became available on October 1, 2023") - References to amounts from prior bills, not new funding

The full (non-primary) export includes all of these for detailed analysis.

## Known Limitations

1. **Fee-funded accounts** - Some accounts are funded from collected fees rather than general appropriations. These may use language like "not to exceed $X (from fees collected)" where the amount IS the primary allocation, not a sub-allocation. These accounts typically involve smaller dollar amounts.

2. **Amendment markup** - Intermediate bill versions (engrossed-in-house, engrossed-amendment-senate) sometimes contain amendment change markers like "(increased by $103,000,000) (reduced by $103,000,000)." These are procedural markup, not actual funding amounts, and may appear in the output.

3. **Explanatory statement references** - Some accounts reference detailed project-level allocations in an accompanying "explanatory statement" that is printed separately in the Congressional Record. Those project-level details are not in the bill XML and cannot be extracted by this tool.

4. **Multiple text elements** - A small number of accounts have more than one `<text>` block. The tool extracts from the first one, which may miss amounts in subsequent blocks.

## How to Verify Results

1. **Spot-check against the bill text.** The CSV includes an `element_id` column that maps back to specific XML elements. Search the XML file for that ID to find the source text.

2. **Compare against CRS reports.** The Congressional Research Service publishes per-bill reports (e.g., "Department of Veterans Affairs FY2024 Appropriations") with account-level tables. These are available at [crsreports.congress.gov](https://crsreports.congress.gov/).

3. **Compare against USAspending.gov.** For enacted bills, account-level budget authority data is available as CSV downloads from [USAspending.gov/download_center/custom_account_data](https://www.usaspending.gov/download_center/custom_account_data). Select "File A (Account Balances)" for the relevant fiscal year.

## Data Source

All bill text is downloaded from the official [Congress.gov](https://www.congress.gov/) bulk data repository in XML format (Bill DTD schema). The XML files are public domain per 17 U.S.C. 105.
