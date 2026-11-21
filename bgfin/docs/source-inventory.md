# Source inventory

Verified on 2026-11-21 by live requests from the collector. "Used for" lists what
the current configuration collects; everything else is available for expansion.

## Summary

| Source | Access | Format | Bulgaria coverage | Status |
|---|---|---|---|---|
| Eurostat | REST API, no key | JSON-stat 2.0 (also SDMX-ML/CSV) | Full ESA/HICP/LFS/GFS/BoP/HPI coverage, plus EU, EA21 and peers | Working, main source |
| ECB Data Portal | SDMX 2.1 REST, no key | SDMX-CSV | BSI and MIR for BG from 2023-01; policy rates; old ICP/EXR series end 2025-12 | Working |
| IMF | SDMX 3.0 REST (`api.imf.org`), no key | SDMX-CSV 2.0 | WEO: 145 indicators for BGR, history from 1980 and projections to +5 years | Working |
| World Bank | Indicators API v2, no key | JSON | WDI annual series | Working |
| BIS | SDMX 2.1 REST, no key | SDMX-CSV | Residential property prices only | Working |
| AMECO (EC) | Bulk ZIP download, no API | Semicolon TXT | ~740 variables per country, history from 1960 and forecast to +2 years | Working |
| NSI | Open data portal, no key | JSON-stat 2.0, CSV | ~140 datasets, mostly labour market and social | Working (limited scope) |
| BNB | Web pages with XLS/CSV files | Files, no API | Full national monetary and BoP history | Not automated (see below) |

## Eurostat

- Endpoint: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?geo=BG&...`
- Filtering by any dimension, `sinceTimePeriod` / `untilTimePeriod`, several `geo` values per request.
- Each response carries the dataset `updated` timestamp (stored as `published_at`) and per-value status
  flags (`p` provisional, `e` estimated, `b` break, `c` confidential, `u` low reliability).
- Publication: 11:00 CET on working days; the catalogue (`/catalogue/toc/txt`) lists last update per dataset.
- Limits: large extractions are queued asynchronously (not needed for these queries). No key, no published rate limit.
- **2026 changes found:**
  - HICP moved to ECOICOP version 2. The monthly datasets `prc_hicp_manr`, `prc_hicp_midx` etc. are frozen at
    December 2025. Current data is in `prc_hicp_minr` (dimension `coicop18`, index base 2025=100, units `RCH_A`,
    `RCH_M`, `I25`, `I15`). Annual averages are in `prc_hicp_ainr`; first releases in `prc_hicp_fpd`.
  - The euro area aggregate for comparisons is `EA21` (fixed composition, includes Bulgaria from 2026).
    `EA` is the changing composition; `EA20` stops at 2025.
- Used for: GDP growth (q/q, y/y, annual), HICP headline/core/food/energy and index, labour cost index (wages),
  unemployment (monthly and annual), government balance and debt (annual EDP and quarterly), current
  account, house price index.

## European Central Bank

- Endpoint: `https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata`
- Supports `startPeriod`, `endPeriod`, `lastNObservations`, and `updatedAfter`, which returns only values
  changed since a timestamp (used for incremental runs, so revisions to old periods are picked up).
  `Last-Modified` header per response.
- Euro adoption effects:
  - Bulgaria appears in BSI (MFI balance sheets) and MIR (interest rates) with history only from **January 2023**,
    reported in EUR. Longer history of these series is on bnb.bg only.
  - `EXR.D.BGN.EUR.SP00.A` ends 2025-12-31 at the fixed 1.95583 rate.
  - The ICP series key `ICP.M.BG.N.000000.4.ANR` ends 2025-12 (ECOICOP v2 transition); Eurostat is used for HICP.
- Used for: household and NFC loan growth (BG and euro area), mortgage rate, ECB deposit facility rate.

## International Monetary Fund

- Endpoint: `https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/{COUNTRY}.{INDICATOR}.A`
  with `Accept: application/vnd.sdmx.data+csv;version=2.0.0`. ISO3 country codes.
- The older DataMapper JSON API (`www.imf.org/external/datamapper/api`) returned 429 and Akamai 403 to
  automated requests and is not used.
- No per-value flag separates history from projections. Rule used: values for the year of the vintage and
  later are forecasts. Vintage labels: `WEO-YYYY-04` (country update dates January to June) or
  `WEO-YYYY-10` (July to December). Only the current WEO vintage is served; older vintages accumulate
  from the day collection starts.
- Used for: forecasts of GDP growth, inflation, unemployment, government balance and debt, current account.

## World Bank

- Endpoint: `https://api.worldbank.org/v2/country/BG;RO/indicator/{code}?format=json&per_page=20000`
- Paginated; `lastupdated` per indicator. Annual only, typically 6 to 18 months behind Eurostat for EU countries.
- Used for: GDP growth and GDP per capita (USD) for long-run international comparison.

## Bank for International Settlements

- Endpoint: `https://stats.bis.org/api/v1/data/{flow}/{key}/all?format=csv`
- **Bulgaria is not covered** by the credit-to-GDP gap (`WS_CREDIT_GAP`), total credit (`WS_TC`) or debt
  service ratio (`WS_DSR`) datasets. Only selected property prices (`WS_SPP`) include BG.
- Consequence: the credit-to-GDP gap has to be computed in-house (ECB BSI loans over Eurostat GDP with a
  one-sided HP filter). Not yet implemented because ECB BSI history for BG starts only in 2023; it needs
  the BNB history first.
- Used for: nominal and real residential property price growth.

## AMECO (European Commission, DG ECFIN)

- No query API. Full database as `https://ec.europa.eu/economy_finance/db_indicators/ameco/documents/ameco0.zip`
  (about 7 MB, 18 TXT files, wide format, years 1960 to forecast horizon). Per-chapter ZIPs and a CSV variant
  are linked from the AMECO download page.
- Series code `BGR.1.0.319.0.UBLGE` = country . transformation . aggregation . unit . reference . variable.
  Romania uses the legacy code `ROM`; aggregates `EU27`, `EA21`.
- Levels only; growth rates are computed in `derived_observation` (`ameco_gdp_growth`, `ameco_hicp_inflation`).
- Updated with the spring (May) and autumn (November) Commission forecasts; current file dated 2026-11-17.
  Vintage label `AMECO-YYYY-MM` from the file's Last-Modified date. Conditional GET (ETag/Last-Modified) avoids
  re-downloading an unchanged file.
- Units after euro adoption: national-currency series are shown as "Mrd EURO-BGN" (BGN history converted at
  1.95583).
- Used for: Commission forecasts of GDP, HICP, unemployment, government balance and debt, current account.

## National Statistical Institute (NSI)

- Open data portal `https://www.nsi.bg/opendata/getopendata_json.php?l=en&id={id}` (JSON-stat) and
  `getopendata.php` (CSV, includes a revision column).
- About 140 datasets, mainly labour force survey, wages (annual, to 2024), poverty and demography.
  **GDP, CPI, industrial production, retail trade are not on the open data portal**; they are in the
  interactive Infostat system (`infostat.nsi.bg`), which has no public API. The same NSI figures reach Eurostat,
  which is used for them.
- JSON-stat quirks handled: categories have labels but no `index`; values in parentheses, e.g. `(2.2)`, mark
  low-reliability estimates and are stored with status `low_reliability`.
- Used for: quarterly LFS unemployment rate (total and 15-24) as a cross-check and for youth unemployment.

## Bulgarian National Bank (BNB)

- No API. Statistics are published as XLS/CSV files on `www.bnb.bg/Statistics/...`.
- Requests from the collector were rejected by the site's web application firewall ("This page can't be
  displayed", incident id). This may differ from a residential or server IP in Bulgaria.
- Since euro adoption BNB monetary statistics are also reported through the Eurosystem, so the ECB Data
  Portal covers current BSI/MIR data. What only BNB has: pre-2023 monetary and credit history, NPL and bank
  capital/liquidity indicators, gross external debt and reserves detail in national presentation.
- Status: disabled in `config/sources.yaml`. A file-based connector can be added once file URLs are confirmed
  reachable from the production server.

## Gaps against the brief

| Brief item | Status |
|---|---|
| Credit-to-GDP gap | Not published for BG by BIS; derive in-house once BNB credit history is available |
| NPL ratio, bank capital and liquidity | BNB (blocked) or ECB Consolidated Banking Data (`CBD2` flow), next phase |
| External debt, reserves, NIIP | Eurostat `bop_gdp6_q` (NIIP), ECB `RAS`; next phase |
| Business and consumer confidence | EC business and consumer surveys (Eurostat `ei_bssi_m_r2`), next phase |
| Vacancies, participation, employment | Eurostat `jvs_q_nace2`, `lfsi_emp_q`; next phase |
| Building permits and completions | Eurostat `sts_cobp_q`; next phase |
| Historical forecast vintages | IMF and AMECO serve only the latest round; archives exist as files, next phase |
