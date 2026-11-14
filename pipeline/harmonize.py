"""Step 4: express VIIRS detections in MODIS-equivalent units.

Run:  python pipeline/harmonize.py     (after pipeline/calendar_table.py)
Output: data/calendar/harmonized.parquet, one row per state and week.

Method: the fire-radiative-power observation operator of M. Sofiev (Finnish
Meteorological Institute, IS4FIRES v3.0, https://github.com/fmidev/FRP_OOp).
This file re-implements the published formula; no code is copied.

A sensor detects a fire when its power exceeds a detection limit that grows with
pixel area. For each VIIRS fire (S-NPP and NOAA-20) we compute the probability
that MODIS on Aqua (similar overpass time, about 13:30 and 01:30 local) would
have detected it, then sum probabilities instead of drawing random numbers, so
results repeat.

Steps
  1. Merge VIIRS 375 m pixels into clusters about the size of one MODIS pixel
     and add up their power (MODIS sees the sum).
  2. Probability that MODIS detects each cluster, for two pixel-size choices:
     the mean MODIS pixel, and the range of pixel sizes across the MODIS swath.
     The better one is chosen on the training years.
  3. Per 0.1 degree cell and day: probability of at least one MODIS detection.
  4. Per state and day, average the VIIRS satellites that were working that day.
  5. Sum per state and week -> expected MODIS active cell-days, with a standard
     deviation and the number of days each sensor actually observed.

Outages: a day on which a satellite has no detection anywhere in the country is
treated as "not observed" (unknown), never as "no fire".

The check compares the result with real Aqua detections on withheld years.
"""
import math
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAL = ROOT / "data" / "calendar"
DET = f"'{(CAL / 'detections.parquet').as_posix()}'"
CELL = 0.1                      # same grid as calendar_table.py
TRAIN = (2013, 2020)            # used to fit multipliers and to choose the variant
TEST = (2021, 2025)             # withheld years

# MODIS coefficients of the operator (FRP_OOp_pixel.py, Sofiev).
# detection limit [MW] = slope * pixel_area_km2 + intercept
# sigmoid rate         = r0 + r1 / pixel_area_km2
MODIS = {"D": dict(slope=4.44, intercept=0.52, r0=0.07, r1=1.26),
         "N": dict(slope=4.43, intercept=1.01, r0=0.11, r1=1.06)}
CUT_OFF = 0.045
MEAN_PIXEL_KM2 = 2.45           # FRP-weighted mean MODIS pixel area (reference value)

# ponytail: clusters are fixed lat/lon boxes of about 2.4 km2 at 37 N, not real
# MODIS footprints. Upgrade: project onto actual Aqua granule geometry.
CLUSTER_LAT, CLUSTER_LON = 0.014, 0.0175

SAT = "CASE WHEN sensor = 'modis' THEN lower(satellite) ELSE sensor END"
SEASON = ("CASE WHEN month(week_start) IN (12,1,2) THEN 'winter' WHEN month(week_start) IN (3,4,5) "
          "THEN 'spring' WHEN month(week_start) IN (6,7,8) THEN 'summer' ELSE 'autumn' END")


def modis_pixel_areas(n=12):
    """MODIS pixel area [km2] at n scan angles evenly spread from nadir to 55 deg.

    Standard MODIS geometry (Ichoku & Kaufman 2005): the pixel grows away from nadir.
    """
    re, h, s = 6378.137, 705.0, 0.0014184397
    r = re + h
    areas = []
    for i in range(n):
        t = math.radians(55.0 * (i + 0.5) / n)
        root = math.sqrt((re / r) ** 2 - math.sin(t) ** 2)
        scan = re * s * (math.cos(t) / root - 1.0)
        track = r * s * (math.cos(t) - root)
        areas.append(scan * track)
    return areas


def define_operator(con):
    """SQL macro: probability that MODIS detects a fire of `frp` MW in a pixel of `area` km2."""
    d, n = MODIS["D"], MODIS["N"]
    con.execute(f"""
        CREATE MACRO detect_probability(frp, area, daynight) AS
        greatest(0, 1 / (1 + exp(-least(greatest(
            (CASE WHEN daynight = 'D' THEN {d["r0"]} + {d["r1"]} / area
                  ELSE {n["r0"]} + {n["r1"]} / area END)
            * (frp - (CASE WHEN daynight = 'D' THEN {d["slope"]} * area + {d["intercept"]}
                           ELSE {n["slope"]} * area + {n["intercept"]} END)),
            -50), 50))) - {CUT_OFF}) / (1 - {CUT_OFF})
    """)


def build_daily(con):
    """Table `daily`: one row per state and day with every series side by side."""
    con.execute("CREATE TABLE areas (variant VARCHAR, area DOUBLE)")
    con.executemany("INSERT INTO areas VALUES (?, ?)",
                    [("swath", a) for a in modis_pixel_areas()] + [("mean", MEAN_PIXEL_KM2)])
    # Days on which each satellite delivered at least one detection nationwide.
    # ponytail: whole-day outages only; a satellite down for part of a day still
    # counts as observed. Upgrade: use swath coverage masks (MYD14 / VJ114).
    con.execute(f"CREATE TABLE seen AS SELECT DISTINCT {SAT} AS sat, acq_date FROM {DET}")
    # 1. clusters: sum power per overpass, keep the strongest overpass per day part
    #    (VIIRS swaths overlap at U.S. latitudes; Aqua mostly gets one look).
    con.execute(f"""
        CREATE TABLE clusters AS
        WITH looks AS (
            SELECT sensor, state, acq_date, daynight, acq_time,
                   floor(latitude / {CLUSTER_LAT})::INT AS cy,
                   floor(longitude / {CLUSTER_LON})::INT AS cx,
                   sum(frp) AS frp
            FROM {DET} WHERE sensor LIKE 'viirs%' GROUP BY ALL)
        SELECT sensor, state, acq_date, daynight, cy, cx, round(max(frp), 1) AS frp
        FROM looks GROUP BY ALL
    """)
    # 2. detection probability per cluster, averaged over the pixel areas.
    con.execute("""
        CREATE TABLE prob AS
        WITH distinct_frp AS (SELECT DISTINCT frp, daynight FROM clusters),
        p AS (SELECT d.frp, d.daynight, a.variant,
                     avg(detect_probability(d.frp, a.area, d.daynight)) AS p
              FROM distinct_frp d, areas a GROUP BY ALL)
        SELECT c.*, p.variant, p.p FROM clusters c JOIN p USING (frp, daynight)
    """)
    # 3. cell-day probability, summed per state and day. Long format: name, value.
    con.execute(f"""
        CREATE TABLE long AS
        WITH cell_day AS (
            SELECT sensor, state, acq_date, variant,
                   floor((cy + 0.5) * {CLUSTER_LAT} / {CELL})::INT AS gy,
                   floor((cx + 0.5) * {CLUSTER_LON} / {CELL})::INT AS gx,
                   1 - exp(sum(ln(greatest(1 - p, 1e-12)))) AS q
            FROM prob GROUP BY ALL),
        op AS (SELECT sensor, state, acq_date, variant, sum(q) AS v, sum(q * (1 - q)) AS var
               FROM cell_day GROUP BY ALL)
        SELECT state, acq_date, sensor || '_' || variant AS name, v AS value FROM op
        UNION ALL
        SELECT state, acq_date, sensor || '_' || variant || '_var', var FROM op
        UNION ALL
        SELECT state, acq_date, {SAT} || '_raw',
               count(DISTINCT (floor(latitude / {CELL})::INT, floor(longitude / {CELL})::INT))
        FROM {DET} GROUP BY ALL
    """)
    names = ["aqua_raw", "viirs-snpp_raw", "viirs-jpss1_raw"] + [
        f"{s}_{v}{x}" for s in ("viirs-snpp", "viirs-jpss1") for v in ("swath", "mean") for x in ("", "_var")]
    pivot = ", ".join(f"coalesce(sum(value) FILTER (WHERE name = '{n}'), 0) AS \"{n}\"" for n in names)
    ok = ", ".join(f"EXISTS (SELECT 1 FROM seen s WHERE s.sat = '{s}' AND s.acq_date = k.acq_date) AS \"{s}_ok\""
                   for s in ("aqua", "viirs-snpp", "viirs-jpss1"))
    con.execute(f"""
        CREATE TABLE daily AS
        WITH k AS (SELECT state, acq_date FROM (SELECT DISTINCT state FROM {DET}),
                   (SELECT unnest(generate_series(DATE '2012-01-23',
                           (SELECT max(acq_date) FROM {DET}), INTERVAL 1 DAY))::DATE AS acq_date))
        SELECT k.state, k.acq_date, date_trunc('week', k.acq_date)::DATE AS week_start, {ok}, {pivot}
        FROM k LEFT JOIN long l USING (state, acq_date) GROUP BY ALL
    """)


def choose_variant(con):
    """Pick the pixel-size variant on the training years only, S-NPP against Aqua."""
    err = {}
    for v in ("mean", "swath"):
        err[v] = con.execute(f"""
            WITH w AS (SELECT state, week_start, sum(aqua_raw) a, sum("viirs-snpp_{v}") p FROM daily
                       WHERE aqua_ok AND "viirs-snpp_ok" AND year(acq_date) BETWEEN {TRAIN[0]} AND {TRAIN[1]}
                       GROUP BY ALL)
            SELECT sum(abs(p - a)) / sum(a) FROM w""").fetchone()[0]
    best = min(err, key=err.get)
    print("training-year error per pixel-size variant:", {k: round(x, 3) for k, x in err.items()},
          "-> using", best)
    return best


def build_weekly(con, v):
    """Tables `matched` (days where Aqua and VIIRS both observed) and `weekly` (final product)."""
    n_viirs = '("viirs-snpp_ok"::INT + "viirs-jpss1_ok"::INT)'
    con.execute(f"""
        CREATE VIEW d AS SELECT *, {n_viirs} AS n_viirs,
            ("viirs-snpp_ok"::INT * "viirs-snpp_{v}" + "viirs-jpss1_ok"::INT * "viirs-jpss1_{v}")
                / nullif({n_viirs}, 0) AS combined,
            ("viirs-snpp_ok"::INT * "viirs-snpp_{v}_var" + "viirs-jpss1_ok"::INT * "viirs-jpss1_{v}_var")
                / nullif({n_viirs} * {n_viirs}, 0) AS combined_var
        FROM daily
    """)
    # Day-matched weekly sums, used for fitting and scoring only.
    con.execute(f"""
        CREATE TABLE matched AS
        SELECT state, week_start, {SEASON} AS season, year(week_start) AS yr,
               sum(aqua_raw) FILTER (WHERE "viirs-snpp_ok") AS aqua_s,
               sum("viirs-snpp_raw") FILTER (WHERE "viirs-snpp_ok") AS snpp_raw,
               sum("viirs-snpp_{v}") FILTER (WHERE "viirs-snpp_ok") AS snpp_op,
               sum("viirs-snpp_{'swath' if v == 'mean' else 'mean'}") FILTER (WHERE "viirs-snpp_ok") AS snpp_op_other,
               sum(aqua_raw) FILTER (WHERE "viirs-jpss1_ok") AS aqua_j,
               sum("viirs-jpss1_{v}") FILTER (WHERE "viirs-jpss1_ok") AS jpss1_op,
               sum(aqua_raw) FILTER (WHERE n_viirs > 0) AS aqua_c,
               sum(combined) AS combined_op
        FROM d WHERE aqua_ok GROUP BY ALL
    """)
    # Final product. Factor: state-season ratio Aqua / operator on all full overlap years.
    con.execute(f"""
        CREATE TABLE weekly AS
        WITH f AS (SELECT state, season, sum(aqua_c) / nullif(sum(combined_op), 0) AS factor
                   FROM matched WHERE yr BETWEEN {TRAIN[0]} AND {TEST[1]} GROUP BY ALL),
        w AS (SELECT state, week_start, {SEASON} AS season,
                     sum(aqua_raw) FILTER (WHERE aqua_ok) AS aqua_cell_days,
                     count(*) FILTER (WHERE aqua_ok) AS aqua_days_observed,
                     sum("viirs-snpp_raw") AS viirs_snpp_cell_days,
                     sum("viirs-jpss1_raw") AS viirs_noaa20_cell_days,
                     count(*) FILTER (WHERE n_viirs > 0) AS viirs_days_observed,
                     sum(combined) AS op, sqrt(sum(combined_var)) AS op_sd
              FROM d GROUP BY ALL)
        SELECT w.state, w.week_start,
               coalesce(aqua_cell_days, 0)::INT AS aqua_cell_days, aqua_days_observed,
               viirs_snpp_cell_days::INT AS viirs_snpp_cell_days,
               viirs_noaa20_cell_days::INT AS viirs_noaa20_cell_days, viirs_days_observed,
               round(op, 2) AS viirs_as_modis_cell_days,
               round(op * coalesce(factor, 1), 2) AS modis_equivalent_cell_days,
               round(op_sd * coalesce(factor, 1), 2) AS modis_equivalent_cell_days_sd
        FROM w LEFT JOIN f USING (state, season) ORDER BY ALL
    """)


def score(con, v):
    """Compare every method with real Aqua cell-days on the withheld years."""
    tr, te = f"yr BETWEEN {TRAIN[0]} AND {TRAIN[1]}", f"yr BETWEEN {TEST[0]} AND {TEST[1]}"
    g = con.execute(f"SELECT sum(aqua_s) / sum(snpp_raw) FROM matched WHERE {tr}").fetchone()[0]
    con.execute(f"""CREATE TABLE factors AS SELECT state, season,
        sum(aqua_s) / nullif(sum(snpp_raw), 0) AS f_raw,
        sum(aqua_s) / nullif(sum(snpp_op), 0) AS f_op,
        sum(aqua_c) / nullif(sum(combined_op), 0) AS f_comb
        FROM matched WHERE {tr} GROUP BY ALL""")
    con.execute(f"""CREATE TABLE scored AS SELECT m.*,
        snpp_raw * {g} AS m_global, snpp_raw * coalesce(f_raw, {g}) AS m_state_season,
        snpp_op * coalesce(f_op, 1) AS m_op_cal, combined_op * coalesce(f_comb, 1) AS m_comb_cal
        FROM matched m LEFT JOIN factors USING (state, season) WHERE {te}""")
    other = "swath pixels" if v == "mean" else "mean pixel"
    methods = [("S-NPP raw", "snpp_raw", "aqua_s"),
               ("S-NPP x one multiplier", "m_global", "aqua_s"),
               ("S-NPP x state-season multiplier", "m_state_season", "aqua_s"),
               (f"S-NPP operator ({other}, rejected)", "snpp_op_other", "aqua_s"),
               ("S-NPP operator, no fitting", "snpp_op", "aqua_s"),
               ("S-NPP operator x state-season", "m_op_cal", "aqua_s"),
               ("NOAA-20 operator, no fitting", "jpss1_op", "aqua_j"),
               ("both VIIRS operator, no fitting", "combined_op", "aqua_c"),
               ("both VIIRS operator x state-season", "m_comb_cal", "aqua_c")]

    def line(where="true"):
        cols = ", ".join(f"sum(abs({c} - {a})) / sum({a}), sum({c}) / sum({a})" for _, c, a in methods)
        return con.execute(f"SELECT {cols} FROM scored WHERE {where}").fetchone()

    print(f"one multiplier fit on {TRAIN[0]}-{TRAIN[1]}: {g:.3f}")
    print(f"\nWithheld years {TEST[0]}-{TEST[1]}, state-week active cell-days against Aqua,")
    print("only days on which both sensors observed")
    print(f"{'method':38s} {'error':>7s} {'total/Aqua':>11s}")
    r = line()
    for i, (name, _, _) in enumerate(methods):
        print(f"{name:38s} {r[2 * i]:7.3f} {r[2 * i + 1]:11.3f}")
    print("\nerror by season: raw | one mult | state-season mult | S-NPP operator | both VIIRS operator x state-season")
    for s in ["winter", "spring", "summer", "autumn"]:
        r = line(f"season = '{s}'")
        print(f"{s:8s}", " ".join(f"{r[2 * i]:6.3f}" for i in (0, 1, 2, 4, 8)))
    rows = con.execute("""SELECT state, sum(aqua_c) a, round(sum(combined_op) / sum(aqua_c), 2) r
        FROM scored GROUP BY ALL HAVING a > 2000 ORDER BY r""").fetchall()
    print("\nboth VIIRS operator (no fitting), total/Aqua by state with >2000 Aqua cell-days")
    print(" lowest:", [(s, r) for s, _, r in rows[:6]])
    print(" highest:", [(s, r) for s, _, r in rows[-6:]])
    print(" Hawaii (Aqua, operator):", con.execute(
        "SELECT sum(aqua_c), round(sum(combined_op), 1) FROM scored WHERE state = 'HI'").fetchone())
    r = line()
    return r[8], r[0], r[2]      # S-NPP operator, raw, one multiplier


def self_check(con):
    # Operator limits: weak fire unseen, strong fire seen, bigger pixel sees less.
    p = lambda frp, area, dn: con.execute("SELECT detect_probability(?, ?, ?)", [frp, area, dn]).fetchone()[0]
    assert p(0.5, 1.0, "D") < 0.02
    assert p(500.0, 9.0, "D") > 0.99
    assert p(15.0, 1.0, "D") > p(15.0, 6.0, "D")
    a = modis_pixel_areas()
    assert 0.99 < a[0] < 1.05 and 6.0 < a[-1] < 11.0, a   # 1 km2 at nadir, 7 km2 at 53 deg


def main():
    con = duckdb.connect()
    define_operator(con)
    self_check(con)
    build_daily(con)
    for sat in ("aqua", "viirs-snpp", "viirs-jpss1"):
        first, n, missing = con.execute(f"""
            WITH s AS (SELECT min(acq_date) f, max(acq_date) l, count(*) n FROM seen WHERE sat = '{sat}')
            SELECT f, n, (l - f + 1) - n FROM s""").fetchone()
        print(f"{sat}: first day {first}, {n} days observed, {missing} outage days")
    v = choose_variant(con)
    build_weekly(con, v)
    op, raw, one = score(con, v)
    con.execute(f"COPY weekly TO '{(CAL / 'harmonized.parquet').as_posix()}' (FORMAT parquet)")
    print("\nharmonized rows:", con.execute("SELECT count(*) FROM weekly").fetchone()[0])
    print(f"STEP 4 CHECK: operator error {op:.3f} vs raw {raw:.3f} vs one multiplier {one:.3f} ->",
          "PASS" if op < raw and op < one else "FAIL")


if __name__ == "__main__":
    main()
