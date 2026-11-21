import io
import zipfile
from datetime import date, datetime, timezone

from bgfin.connectors.ameco import parse_ameco
from bgfin.connectors.base import forecast_cutoff_type, parse_number
from bgfin.connectors.eurostat import parse_jsonstat
from bgfin.connectors.imf import parse_imf_csv, weo_vintage
from bgfin.connectors.nsi import parse_nsi
from bgfin.connectors.sdmx import parse_sdmx_csv
from bgfin.periods import parse_period, period_label, shift


def test_periods():
    assert parse_period("2026-Q3") == (date(2026, 7, 1), "Q")
    assert parse_period("2019Q2") == (date(2019, 4, 1), "Q")
    assert parse_period("2026-10") == (date(2026, 10, 1), "M")
    assert parse_period("2026") == (date(2026, 1, 1), "A")
    assert parse_period("2026-09-16") == (date(2026, 9, 16), "D")
    assert period_label(date(2026, 7, 1), "Q") == "2026-Q3"
    assert shift(date(2026, 1, 1), "Q", -1) == date(2025, 10, 1)


def test_parse_number_flags():
    assert parse_number("(2.2)") == (2.2, "low_reliability")
    assert parse_number("4.1") == (4.1, None)
    assert parse_number("..") == (None, None)
    assert parse_number(3) == (3.0, None)


EUROSTAT_DOC = {
    "label": "test", "updated": "2026-11-20T23:00:00+0100",
    "id": ["freq", "unit", "geo", "time"], "size": [1, 1, 2, 3],
    "dimension": {
        "freq": {"category": {"index": {"Q": 0}, "label": {"Q": "Quarterly"}}},
        "unit": {"category": {"index": {"PCH": 0}, "label": {"PCH": "Percentage change"}}},
        "geo": {"category": {"index": {"BG": 0, "EL": 1}, "label": {"BG": "Bulgaria", "EL": "Greece"}}},
        "time": {"category": {"index": {"2026-Q1": 0, "2026-Q2": 1, "2026-Q3": 2}}},
    },
    "value": {"0": 0.6, "1": 0.6, "2": 0.5, "4": 0.3},
    "status": {"2": "p", "5": "c"},
}


def test_eurostat_jsonstat():
    series = {s.geo: s for s in parse_jsonstat(EUROSTAT_DOC, "namq_10_gdp")}
    assert set(series) == {"BG", "GR"}                 # EL mapped back to GR
    bg = series["BG"]
    assert bg.frequency == "Q" and bg.unit == "Percentage change"
    assert [o.value for o in bg.observations] == [0.6, 0.6, 0.5]
    assert bg.observations[-1].obs_type == "preliminary"
    gr = series["GR"]
    assert [(o.period_label, o.value, o.obs_type) for o in gr.observations] == [
        ("2026-Q2", 0.3, "actual"), ("2026-Q3", None, "missing")]
    assert bg.source_key == "namq_10_gdp:freq=Q.unit=PCH.geo=BG"


ECB_CSV = """KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT,UNIT_MULT,TITLE
BSI.M.BG.X,M,BG,2026-08,21.4,A,PCCH,0,Loans
BSI.M.BG.X,M,BG,2026-09,21.3,P,PCCH,0,Loans
BSI.M.U2.X,M,U2,2026-09,,M,PCCH,0,Loans
"""


def test_sdmx_csv_ecb():
    series = {s.geo: s for s in parse_sdmx_csv(ECB_CSV, "BSI", geo_map={"U2": "EA"})}
    assert series["BG"].observations[1].obs_type == "preliminary"
    assert series["EA"].observations[0].obs_type == "missing"
    assert series["EA"].attrs["raw_geo"] == "U2"


BIS_CSV = """FREQ,REF_AREA,VALUE,UNIT_MEASURE,UNIT_MULT,TIME_PERIOD,OBS_VALUE,OBS_STATUS
Q,BG,N,771,0,2026-Q1,14.77,A
Q,BG,N,771,0,2026-Q2,15.47,A
"""


def test_sdmx_csv_bis_uses_key_length():
    (s,) = parse_sdmx_csv(BIS_CSV, "WS_SPP", n_dims=4)
    assert s.source_key == "WS_SPP.Q.BG.N.771"
    assert len(s.observations) == 2


IMF_CSV = """STRUCTURE,STRUCTURE_ID,ACTION,COUNTRY,INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE,SCALE,UNIT,COUNTRY_UPDATE_DATE
dataflow,IMF.RES:WEO(9.0.0),R,BGR,NGDP_RPCH,A,2025,3.0,0,PT,9/24/2026
dataflow,IMF.RES:WEO(9.0.0),R,BGR,NGDP_RPCH,A,2026,2.55,0,PT,9/24/2026
"""


def test_imf_vintage_and_forecast_flag():
    (s,) = parse_imf_csv(IMF_CSV, "WEO")
    assert s.geo == "BG"
    assert [o.vintage for o in s.observations] == ["WEO-2026-10"] * 2
    assert [o.obs_type for o in s.observations] == ["actual", "forecast"]
    assert weo_vintage("WEO", datetime(2027, 3, 30))[0] == "WEO-2027-04"
    assert forecast_cutoff_type(2026, 2026) == "forecast"


def _ameco_zip():
    text = ("CODE;COUNTRY;SUB-CHAPTER;TITLE;UNIT;2025;2026;2027;\n"
            "BGR.1.0.319.0.UDGG;Bulgaria;03;Gross debt;(Percentage of GDP);29.9;33.0;35.0;\n"
            "ROM.1.0.319.0.UDGG;Romania;03;Gross debt;(Percentage of GDP);NA;60.1;62.0;\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AMECO1.TXT", text)
    return buf.getvalue()


def test_ameco():
    release = datetime(2026, 11, 17, tzinfo=timezone.utc)
    parsed = parse_ameco(_ameco_zip(), {"BGR": {"1.0.319.0.UDGG"}, "ROM": {"1.0.319.0.UDGG"}}, release)
    bg = parsed[("BGR", "1.0.319.0.UDGG")]
    assert bg.unit == "Percentage of GDP"
    assert [(o.period_label, o.obs_type, o.vintage) for o in bg.observations] == [
        ("2025", "actual", "AMECO-2026-11"), ("2026", "forecast", "AMECO-2026-11"),
        ("2027", "forecast", "AMECO-2026-11")]
    assert len(parsed[("ROM", "1.0.319.0.UDGG")].observations) == 2


NSI_DOC = {
    "label": "UNEMPLOYMENT RATES", "updated": "2026-09-15T11:00:00",
    "id": ["periods", "Units", "Age"], "size": [2, 1, 2],
    "role": {"time": ["periods"], "metric": ["Units"]},
    "dimension": {
        "periods": {"category": {"label": {"2026Q2": "2026Q2", "2026Q1": "2026Q1"}}},
        "Units": {"category": {"label": {"perc": "Per cent"}}},
        "Age": {"category": {"label": {"0": "Total", "15 - 24": "15 - 24"}}},
    },
    "value": [3.5, 13.1, 3.2, "(11.1)"],
}


def test_nsi_without_index():
    series = {s.attrs["dimensions"]["Age"]: s for s in parse_nsi(NSI_DOC, "1103")}
    youth = series["15 - 24"]
    assert [(o.period_label, o.value, o.status) for o in youth.observations] == [
        ("2026Q2", 13.1, None), ("2026Q1", 11.1, "low_reliability")]
    assert series["0"].unit == "Per cent"
