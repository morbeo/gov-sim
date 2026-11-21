# Indicator catalogue

Generated from `config/indicators.yaml` and `config/derived.yaml` by `bgfin catalogue`. Do not edit by hand.

Roles: **primary** feeds dashboards and alerts; **secondary** is the same concept from another source for cross-checks; **benchmark** is the actual outcome used to score forecasts; **forecast** is stored per vintage; **input** only feeds derived metrics.

## Economic activity

### `gdp_growth`: Real GDP growth, year on year (priority)

- Unit: % change on same period of previous year
- Canonical frequency: Q
- Definition: Growth of GDP at chain-linked volumes. Quarterly series compare with the same quarter a year earlier (seasonally and calendar adjusted); annual series compare with the previous year.
- Sources:
  - eurostat (primary, Q): `namq_10_gdp na_item=B1GQ, unit=CLV_PCH_SM, s_adj=SCA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (benchmark, A): `nama_10_gdp na_item=B1GQ, unit=CLV_PCH_PRE`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - imf (forecast, A): `WEO key {geo}.NGDP_RPCH.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - worldbank (secondary, A): `WDI NY.GDP.MKTP.KD.ZG`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - derived `ameco_gdp_growth` (yoy_pct): level = ameco:gdp_real_level

### `gdp_growth_qoq`: Real GDP growth, quarter on quarter (priority)

- Unit: % change on previous quarter
- Canonical frequency: Q
- Sources:
  - eurostat (primary, Q): `namq_10_gdp na_item=B1GQ, unit=CLV_PCH_PRE, s_adj=SCA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `gdp_real_level`: Real GDP level (AMECO, 2020 reference levels)

- Unit: bn EUR (2020 reference levels)
- Canonical frequency: A
- Definition: Used to derive AMECO GDP growth forecasts.
- Sources:
  - ameco (input, A): `AMECO 1.1.0.0.OVGD`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

## Inflation and purchasing power

### `hicp_inflation`: HICP inflation, annual rate (priority)

- Unit: % change on same month of previous year
- Canonical frequency: M
- Definition: Harmonised index of consumer prices, all items. From 2026 Eurostat publishes HICP under ECOICOP version 2 (dataset prc_hicp_minr, base 2025=100); the old prc_hicp_manr ends in December 2025.
- Sources:
  - eurostat (primary, M): `prc_hicp_minr unit=RCH_A, coicop18=TOTAL`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (benchmark, A): `prc_hicp_ainr unit=RCH_A_AVG, coicop18=TOTAL`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - imf (forecast, A): `WEO key {geo}.PCPIPCH.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - derived `ameco_hicp_inflation` (yoy_pct): level = ameco:hicp_index_annual

### `core_inflation`: Core inflation (HICP excluding energy, food, alcohol and tobacco) (priority)

- Unit: % change on same month of previous year
- Canonical frequency: M
- Sources:
  - eurostat (primary, M): `prc_hicp_minr unit=RCH_A, coicop18=TOT_X_NRG_FOOD`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `food_inflation`: HICP food including alcohol and tobacco, annual rate

- Unit: % change on same month of previous year
- Canonical frequency: M
- Sources:
  - eurostat (primary, M): `prc_hicp_minr unit=RCH_A, coicop18=FOOD`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `energy_inflation`: HICP energy, annual rate

- Unit: % change on same month of previous year
- Canonical frequency: M
- Sources:
  - eurostat (primary, M): `prc_hicp_minr unit=RCH_A, coicop18=NRG`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `hicp_index`: HICP all-items index

- Unit: index 2025=100
- Canonical frequency: M
- Definition: Price deflator for real wage growth.
- Sources:
  - eurostat (input, M): `prc_hicp_minr unit=I25, coicop18=TOTAL`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `hicp_index_annual`: HICP all-items index, annual (AMECO)

- Unit: index 2015=100
- Canonical frequency: A
- Definition: Used to derive AMECO inflation forecasts.
- Sources:
  - ameco (input, A): `AMECO 1.0.0.0.ZCPIH`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `wage_growth_nominal`: Nominal wage growth (labour cost index, wages and salaries) (priority)

- Unit: % change on same quarter of previous year
- Canonical frequency: Q
- Definition: Hourly wages and salaries component (D11) of the labour cost index, business economy and services (NACE B-S), not adjusted.
- Sources:
  - eurostat (primary, Q): `lc_lci_r2_q lcstruct=D11, nace_r2=B-S, s_adj=NSA, unit=PCH_SM`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `real_wage_growth`: Real wage growth (priority)

- Unit: % change on same quarter of previous year
- Canonical frequency: Q
- Definition: Derived: nominal wage growth deflated by HICP, (1 + w) / (1 + p) - 1, where p is the year-on-year change of the quarterly average HICP index. See config/derived.yaml.
  - derived `real_wage_growth` (real_growth): nominal = eurostat:wage_growth_nominal; price_index = eurostat:hicp_index

## Labour market

### `unemployment_rate`: Unemployment rate (priority)

- Unit: % of labour force
- Canonical frequency: M
- Sources:
  - eurostat (primary, M): `une_rt_m s_adj=SA, age=TOTAL, sex=T, unit=PC_ACT`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (benchmark, A): `une_rt_a age=Y15-74, sex=T, unit=PC_ACT`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - nsi (secondary, Q): `1103 Age10_LFS=0, GenderID=0`; BG
  - imf (forecast, A): `WEO key {geo}.LUR.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - ameco (forecast, A): `AMECO 1.0.0.0.ZUTN`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `youth_unemployment_rate`: Youth unemployment rate (15-24)

- Unit: % of labour force aged 15-24
- Canonical frequency: Q
- Sources:
  - nsi (primary, Q): `1103 Age10_LFS=15 - 24, GenderID=0`; BG

## Government finances

### `gov_balance`: General government deficit (-) / surplus (+) (priority)

- Unit: % of GDP
- Canonical frequency: A
- Sources:
  - eurostat (benchmark, A): `gov_10dd_edpt1 na_item=B9, sector=S13, unit=PC_GDP`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (secondary, Q): `gov_10q_ggnfa na_item=B9, sector=S13, unit=PC_GDP, s_adj=NSA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - imf (forecast, A): `WEO key {geo}.GGXCNL_NGDP.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - ameco (forecast, A): `AMECO 1.0.319.0.UBLGE`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

### `gov_debt`: General government gross debt (priority)

- Unit: % of GDP
- Canonical frequency: A
- Sources:
  - eurostat (benchmark, A): `gov_10dd_edpt1 na_item=GD, sector=S13, unit=PC_GDP`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (secondary, Q): `gov_10q_ggdebt na_item=GD, sector=S13, unit=PC_GDP`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - imf (forecast, A): `WEO key {geo}.GGXWDG_NGDP.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - ameco (forecast, A): `AMECO 1.0.319.0.UDGG`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

## Monetary and financial conditions

### `household_credit_growth`: Loans to households, annual growth rate (priority)

- Unit: % change on same month of previous year
- Canonical frequency: M
- Definition: MFI loans to euro-area households, growth adjusted for reclassifications and write-offs. ECB BSI coverage for Bulgaria starts in January 2023 (euro adoption reporting); earlier history is on bnb.bg only.
- Sources:
  - ecb (primary, M): `BSI key M.{geo}.N.A.A20.A.I.U2.2250.Z01.A`; BG, U2

### `corporate_credit_growth`: Loans to non-financial corporations, annual growth rate

- Unit: % change on same month of previous year
- Canonical frequency: M
- Sources:
  - ecb (primary, M): `BSI key M.{geo}.N.A.A20.A.I.U2.2240.Z01.A`; BG, U2

### `mortgage_rate`: Cost of borrowing for households for house purchase

- Unit: % per annum
- Canonical frequency: M
- Sources:
  - ecb (primary, M): `MIR key M.{geo}.B.A2C.AM.R.A.2250.EUR.N`; BG, U2

### `ecb_deposit_rate`: ECB deposit facility rate

- Unit: % per annum
- Canonical frequency: B
- Sources:
  - ecb (primary, B): `FM key B.U2.EUR.4F.KR.DFR.LEV`; U2

## External sector

### `current_account`: Current account balance (priority)

- Unit: % of GDP
- Canonical frequency: Q
- Sources:
  - eurostat (primary, Q): `bop_gdp6_q freq=Q, bop_item=CA, stk_flow=BAL, partner=WRL_REST, unit=PC_GDP, s_adj=NSA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - eurostat (benchmark, A): `bop_gdp6_q freq=A, bop_item=CA, stk_flow=BAL, partner=WRL_REST, unit=PC_GDP, s_adj=NSA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - imf (forecast, A): `WEO key {geo}.BCA_NGDPD.A`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
  - ameco (forecast, A): `AMECO 1.0.310.0.UBCA`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI

## Real estate and household debt

### `house_price_growth`: Residential property prices, annual growth (priority)

- Unit: % change on same quarter of previous year
- Canonical frequency: Q
- Sources:
  - eurostat (primary, Q): `prc_hpi_q purchase=TOTAL, unit=RCH_A`; BG, EU27_2020, EA21, RO, HR, GR, HU, PL, CZ, SK, SI
  - bis (secondary, Q): `WS_SPP key Q.{geo}.N.771`; BG

### `house_price_growth_real`: Residential property prices, real annual growth

- Unit: % change on same quarter of previous year
- Canonical frequency: Q
- Sources:
  - bis (primary, Q): `WS_SPP key Q.{geo}.R.771`; BG, RO, HR, GR, HU, PL, CZ, SK, SI

## Forecasts and international comparisons

### `gdp_per_capita_usd`: GDP per capita, current US dollars

- Unit: current USD
- Canonical frequency: A
- Sources:
  - worldbank (primary, A): `WDI NY.GDP.PCAP.CD`; BG, RO, HR, GR, HU, PL, CZ, SK, SI
