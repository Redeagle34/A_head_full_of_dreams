"""Aggregate US FIRMS yearly archives (MODIS C6.1 SP, VIIRS C2 SP) into small tables.
Per file -> data/derived/us/agg_<sensor>_<year>.parquet (cached). Never loads >1 file at a time.
Filters recorded as flags so experiments can compare raw vs filtered.
"""
import pandas as pd, numpy as np, pathlib, sys, glob, re
SRC = pathlib.Path("data/country"); OUT = pathlib.Path("data/derived/us"); OUT.mkdir(parents=True, exist_ok=True)

def region(lat, lon):
    r = np.full(len(lat), "East", dtype=object)
    r[lon < -90] = "Central"; r[lon < -104] = "West"
    r[(lat > 51) & (lon < -129)] = "Alaska"; r[(lat < 23) & (lon < -150)] = "Hawaii"
    return r

def load(f):
    sensor = "MODIS" if "modis" in f.name else "VIIRS"
    d = pd.read_csv(f, usecols=["latitude","longitude","acq_date","acq_time","satellite","confidence","frp","daynight","type"],
                    dtype={"satellite": str, "confidence": str, "daynight": str})
    d["sensor"] = sensor
    d["sat"] = d.satellite.replace({"N": "SNPP", "N20": "NOAA20", "1": "NOAA20", "N21": "NOAA21"})
    if sensor == "MODIS": good_conf = pd.to_numeric(d.confidence, errors="coerce") >= 30
    else: good_conf = d.confidence.isin(["n", "h", "nominal", "high"])
    d["veg"] = d["type"] == 0
    d["keep"] = d.veg & good_conf
    d["region"] = region(d.latitude.values, d.longitude.values)
    d["date"] = pd.to_datetime(d.acq_date)
    d["c01"] = (np.floor(d.latitude*10).astype(int)*10000 + np.floor(d.longitude*10).astype(int))
    d["c001"] = (np.floor(d.latitude*100).astype(np.int64)*100000 + np.floor(d.longitude*100).astype(np.int64))
    d["c025"] = (np.floor(d.latitude*4).astype(int)*10000 + np.floor(d.longitude*4).astype(int))
    hh = d.acq_time // 100 + (d.acq_time % 100)/60
    d["lst"] = (hh + d.longitude/15) % 24  # local solar time (approx)
    return d

def agg(f):
    o = OUT / ("agg_" + f.stem.replace("_United_States", "") + ".parquet")
    if o.exists(): return
    d = load(f)
    tabs = {}
    for flt in ["all", "keep"]:
        x = d if flt == "all" else d[d.keep]
        g = x.groupby(["date","sat","sensor","region","daynight"])
        t = g.agg(n_det=("frp","size"), frp_sum=("frp","sum"), n_c01=("c01","nunique"), n_c001=("c001","nunique")).reset_index()
        t["filter"] = flt; tabs[flt] = t
    daily = pd.concat(tabs.values())
    daily.to_parquet(o)
    k = d[d.keep]
    k.groupby([k.date.dt.year.rename("year"), k.date.dt.month.rename("month"), "sat", "sensor", "c025"]).agg(
        n_det=("frp","size"), n_celldays01=("c01", "size")).reset_index().to_parquet(o.with_name(o.name.replace("agg_","cell025_")))
    # cell-days at 0.1 deg for cell025 maps: count unique (date,c01)
    cd = k.drop_duplicates(["date","c01","sat"]).groupby([k.date.dt.year.rename("year"), k.date.dt.month.rename("month"), "sat","c025"]).size().rename("celldays01")
    cd.reset_index().to_parquet(o.with_name(o.name.replace("agg_","cd025_")))
    # FRP + local time distributions
    bins = np.r_[0, np.logspace(-1, 4, 51)]
    rows = []
    for (sat, dn), x in k.groupby(["sat","daynight"]):
        h, _ = np.histogram(x.frp.clip(0, 9999), bins)
        rows.append({"sat": sat, "daynight": dn, "frp_hist": h.tolist(), "frp_q": x.frp.quantile([.1,.25,.5,.75,.9,.99]).tolist(),
                     "lst_median": float(x.lst.median()), "lst_q": x.lst.quantile([.1,.5,.9]).tolist(), "n": len(x)})
    pd.DataFrame(rows).assign(year=int(re.search(r"_(\d{4})", f.name).group(1))).to_parquet(o.with_name(o.name.replace("agg_","dist_")))
    print("done", f.name, len(d), flush=True)

if __name__ == "__main__":
    for f in sorted(SRC.glob("*_United_States.csv")):
        try: agg(f)
        except Exception as e: print("FAIL", f.name, e, flush=True)
