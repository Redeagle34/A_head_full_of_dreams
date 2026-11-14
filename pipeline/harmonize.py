"""Step 4: express VIIRS detections in MODIS-equivalent units.

Run:  python pipeline/harmonize.py     (after pipeline/calendar_table.py)
Output: data/calendar/harmonized.parquet, one row per state and week.

Method: the fire-radiative-power observation operator of M. Sofiev (Finnish
Meteorological Institute, IS4FIRES v3.0, https://github.com/fmidev/FRP_OOp).
This file re-implements the published formula; no code is copied.

A sensor detects a fire when its power exceeds a detection limit that grows with
pixel area. For each VIIRS S-NPP fire we compute the probability that MODIS on
Aqua (same overpass time, about 13:30 and 01:30 local) would have detected it,
then sum probabilities instead of drawing random numbers, so results repeat.

Steps
  1. Merge VIIRS 375 m pixels into clusters about the size of one MODIS pixel
     and add up their power (MODIS sees the sum).
  2. Probability that MODIS detects each cluster, averaged over the MODIS pixel
     sizes that occur across its swath (1 km2 at nadir to about 10 km2 at the edge).
  3. Per 0.1 degree cell and day: probability of at least one MODIS detection.
  4. Sum per state and week -> expected MODIS active cell-days, with a standard
     deviation.

The check compares the result with real Aqua detections on withheld years.
"""
import math
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAL = ROOT / "data" / "calendar"
CELL = 0.1                      # same grid as calendar_table.py
TRAIN = (2013, 2020)            # used only to fit the multiplier baselines
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


def build(con):
    swath = modis_pixel_areas()
    rows = [("swath", a) for a in swath] + [("mean", MEAN_PIXEL_KM2)]
    con.execute("CREATE TABLE areas (variant VARCHAR, area DOUBLE)")
    con.executemany("INSERT INTO areas VALUES (?, ?)", rows)
    # 1. clusters: sum power per overpass, keep the strongest overpass per day part
    #    (VIIRS swaths overlap at U.S. latitudes; Aqua mostly gets one look).
    con.execute(f"""
        CREATE TABLE clusters AS
        WITH looks AS (
            SELECT state, acq_date, daynight, acq_time,
                   floor(latitude / {CLUSTER_LAT})::INT AS cy,
                   floor(longitude / {CLUSTER_LON})::INT AS cx,
                   sum(frp) AS frp
            FROM '{(CAL / "detections.parquet").as_posix()}'
            WHERE sensor = 'viirs-snpp' GROUP BY ALL)
        SELECT state, acq_date, daynight, cy, cx, round(max(frp), 1) AS frp
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
    # 3 + 4. cell-day probability, then state-week sums.
    con.execute(f"""
        CREATE TABLE viirs_as_modis AS
        WITH cell_day AS (
            SELECT state, acq_date, variant,
                   floor((cy + 0.5) * {CLUSTER_LAT} / {CELL})::INT AS gy,
                   floor((cx + 0.5) * {CLUSTER_LON} / {CELL})::INT AS gx,
                   1 - exp(sum(ln(greatest(1 - p, 1e-12)))) AS q, sum(p) AS n
            FROM prob GROUP BY ALL)
        SELECT state, date_trunc('week', acq_date)::DATE AS week_start, variant,
               sum(q) AS cell_days, sqrt(sum(q * (1 - q))) AS cell_days_sd, sum(n) AS detections
        FROM cell_day GROUP BY ALL
    """)
    cal = f"'{(CAL / 'calendar.parquet').as_posix()}'"
    con.execute(f"""
        CREATE TABLE harmonized AS
        WITH keys AS (SELECT DISTINCT state, week_start FROM {cal}
                      WHERE series IN ('aqua', 'viirs-snpp') AND week_start >= DATE '2012-01-23')
        SELECT k.state, k.week_start,
               coalesce(a.active_cell_days, 0) AS aqua_cell_days,
               coalesce(a.detections, 0) AS aqua_detections,
               coalesce(v.active_cell_days, 0) AS viirs_cell_days,
               coalesce(v.detections, 0) AS viirs_detections,
               round(coalesce(s.cell_days, 0), 2) AS viirs_as_modis_cell_days,
               round(coalesce(s.cell_days_sd, 0), 2) AS viirs_as_modis_cell_days_sd,
               round(coalesce(s.detections, 0), 2) AS viirs_as_modis_detections,
               round(coalesce(m.cell_days, 0), 2) AS viirs_as_modis_meanpixel_cell_days,
               round(coalesce(m.cell_days_sd, 0), 2) AS viirs_as_modis_meanpixel_cell_days_sd
        FROM keys k
        LEFT JOIN {cal} a ON a.state = k.state AND a.week_start = k.week_start AND a.series = 'aqua'
        LEFT JOIN {cal} v ON v.state = k.state AND v.week_start = k.week_start AND v.series = 'viirs-snpp'
        LEFT JOIN viirs_as_modis s ON s.state = k.state AND s.week_start = k.week_start AND s.variant = 'swath'
        LEFT JOIN viirs_as_modis m ON m.state = k.state AND m.week_start = k.week_start AND m.variant = 'mean'
        ORDER BY ALL
    """)


def score(con):
    """Compare every method with real Aqua cell-days on the withheld years."""
    tr = f"year(week_start) BETWEEN {TRAIN[0]} AND {TRAIN[1]}"
    te = f"year(week_start) BETWEEN {TEST[0]} AND {TEST[1]}"
    season = "CASE WHEN month(week_start) IN (12,1,2) THEN 'winter' WHEN month(week_start) IN (3,4,5) " \
             "THEN 'spring' WHEN month(week_start) IN (6,7,8) THEN 'summer' ELSE 'autumn' END"
    con.execute(f"CREATE VIEW h AS SELECT *, {season} AS season FROM harmonized")
    g = con.execute(f"SELECT sum(aqua_cell_days) / sum(viirs_cell_days) FROM h WHERE {tr}").fetchone()[0]
    # Choose the pixel-size variant on the training years only, never on the withheld ones.
    variants = ["viirs_as_modis_cell_days", "viirs_as_modis_meanpixel_cell_days"]
    train_err = {c: con.execute(f"SELECT sum(abs({c} - aqua_cell_days)) / sum(aqua_cell_days) "
                                f"FROM h WHERE {tr}").fetchone()[0] for c in variants}
    best = min(train_err, key=train_err.get)
    print("training-year error per variant:", {k: round(v, 3) for k, v in train_err.items()})
    print("chosen on training years:", best)
    con.execute(f"""CREATE TABLE factors AS SELECT state, season,
        sum(aqua_cell_days) / nullif(sum(viirs_cell_days), 0) AS f_raw,
        sum(aqua_cell_days) / nullif(sum({best}), 0) AS f_op
        FROM h WHERE {tr} GROUP BY ALL""")
    con.execute(f"""CREATE TABLE scored AS SELECT h.*,
        viirs_cell_days * {g} AS m_global,
        viirs_cell_days * coalesce(f_raw, {g}) AS m_state_season,
        {best} * coalesce(f_op, 1) AS m_op_cal
        FROM h LEFT JOIN factors USING (state, season) WHERE {te}""")
    methods = {"raw VIIRS": "viirs_cell_days",
               "one multiplier": "m_global",
               "multiplier per state and season": "m_state_season",
               "operator, mean pixel": "viirs_as_modis_meanpixel_cell_days",
               "operator, swath pixels": "viirs_as_modis_cell_days",
               "operator + state-season factor": "m_op_cal"}

    def line(where="true"):
        cols = ", ".join(f"sum(abs({c} - aqua_cell_days)) / sum(aqua_cell_days), "
                         f"sum({c}) / sum(aqua_cell_days)" for c in methods.values())
        return con.execute(f"SELECT {cols} FROM scored WHERE {where}").fetchone()

    print(f"one multiplier fit on {TRAIN[0]}-{TRAIN[1]}: {g:.3f}")
    print(f"\nWithheld years {TEST[0]}-{TEST[1]}, state-week active cell-days against Aqua")
    print(f"{'method':34s} {'error':>7s} {'total/Aqua':>11s}")
    r = line()
    for i, name in enumerate(methods):
        print(f"{name:34s} {r[2 * i]:7.3f} {r[2 * i + 1]:11.3f}")
    print("\nerror by season (same column order: " + " | ".join(methods) + ")")
    for s in ["winter", "spring", "summer", "autumn"]:
        r = line(f"season = '{s}'")
        print(f"{s:8s}", " ".join(f"{r[2 * i]:6.3f}" for i in range(len(methods))))
    print("\nchosen operator, total/Aqua by state, 8 lowest and 8 highest, states with >2000 Aqua cell-days")
    rows = con.execute(f"""SELECT state, sum(aqua_cell_days) a,
        round(sum({best}) / sum(aqua_cell_days), 2) r
        FROM scored GROUP BY ALL HAVING a > 2000 ORDER BY r""").fetchall()
    print(" low:", [(s, r) for s, _, r in rows[:8]])
    print(" high:", [(s, r) for s, _, r in rows[-8:]])
    print(" Hawaii (Aqua, operator, raw VIIRS):", con.execute(
        f"SELECT sum(aqua_cell_days), round(sum({best}), 1), sum(viirs_cell_days) "
        "FROM scored WHERE state = 'HI'").fetchone())
    op = con.execute(f"SELECT sum(abs({best} - aqua_cell_days)) / sum(aqua_cell_days) FROM scored").fetchone()[0]
    raw = con.execute("SELECT sum(abs(viirs_cell_days - aqua_cell_days)) / sum(aqua_cell_days) FROM scored").fetchone()[0]
    one = con.execute("SELECT sum(abs(m_global - aqua_cell_days)) / sum(aqua_cell_days) FROM scored").fetchone()[0]
    return op, raw, one, best


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
    build(con)
    print("harmonized rows:", con.execute("SELECT count(*) FROM harmonized").fetchone()[0])
    op, raw, one, best = score(con)
    # Final product: chosen variant times a state-season factor fit on all full overlap years.
    con.execute(f"""
        COPY (
            WITH f AS (SELECT state, season, sum(aqua_cell_days) / nullif(sum({best}), 0) AS factor
                       FROM h WHERE year(week_start) BETWEEN {TRAIN[0]} AND {TEST[1]} GROUP BY ALL)
            SELECT h.* EXCLUDE (season),
                   round({best} * coalesce(factor, 1), 2) AS modis_equivalent_cell_days,
                   round({best}_sd * coalesce(factor, 1), 2) AS modis_equivalent_cell_days_sd
            FROM h LEFT JOIN f USING (state, season) ORDER BY state, week_start
        ) TO '{(CAL / 'harmonized.parquet').as_posix()}' (FORMAT parquet)
    """)
    print(f"\nSTEP 4 CHECK: operator error {op:.3f} vs raw {raw:.3f} vs one multiplier {one:.3f} ->",
          "PASS" if op < raw and op < one else "FAIL")


if __name__ == "__main__":
    main()
