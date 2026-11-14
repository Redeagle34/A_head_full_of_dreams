"""What is typical for a week of the year, and which weeks are unusual.

"Typical" for a week = the same week, one week before and one week after, over
all other years.
  unusual (flag 1) = value above 90% of those reference weeks, and at least `min_activity`
  record  (flag 2) = value above every reference week, and at least `min_activity`
  critical         = weeks of the year whose long-term mean is at least half of
                     the peak week (the recurring fire season)
"""
import statistics

UNUSUAL_RANK = 0.90


def quantile(sorted_values, q):
    if not sorted_values:
        return 0.0
    i = q * (len(sorted_values) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (i - lo)


def analyse(weeks, values, min_activity):
    """Flags and ranks per week, and climatology per week of the year.

    weeks: list of datetime.date (Mondays); values: list of numbers or None.
    """
    iso = [w.isocalendar() for w in weeks]          # (year, week, weekday)
    by_woy = {}
    for (yr, wk, _), v in zip(iso, values):
        if v is not None:
            by_woy.setdefault(wk, []).append((yr, v))

    def reference(wk, skip_year=None):
        out = []
        for d in (-1, 0, 1):
            w = (wk - 1 + d) % 52 + 1 if wk <= 52 else (52 if d < 0 else 53 if d == 0 else 1)
            out += [v for y, v in by_woy.get(w, []) if y != skip_year]
        return out

    flags, ranks = [], []
    for (yr, wk, _), v in zip(iso, values):
        ref = reference(wk, skip_year=yr)
        if v is None or not ref:
            flags.append(0), ranks.append(None)
            continue
        rank = sum(r < v for r in ref) / len(ref)
        ranks.append(round(rank, 2))
        flag = 0
        if v >= min_activity:
            flag = 2 if v > max(ref) else 1 if rank >= UNUSUAL_RANK else 0
        flags.append(flag)
    clim = {"p10": [], "p50": [], "p90": [], "mean": []}
    for wk in range(1, 54):
        ref = sorted(reference(wk))
        clim["p10"].append(round(quantile(ref, 0.10), 1))
        clim["p50"].append(round(quantile(ref, 0.50), 1))
        clim["p90"].append(round(quantile(ref, 0.90), 1))
        clim["mean"].append(round(statistics.fmean(ref), 1) if ref else 0.0)
    peak = max(clim["mean"])
    clim["critical"] = [int(peak >= 1 and m >= 0.5 * peak) for m in clim["mean"]]
    return flags, ranks, clim


def self_check():
    import datetime
    weeks = [datetime.date(2001, 1, 1) + datetime.timedelta(weeks=i) for i in range(52 * 10)]
    values = [1.0] * len(weeks)
    values[52 * 9 + 30] = 50.0                      # one extreme week in the last year
    flags, ranks, clim = analyse(weeks, values, min_activity=5)
    assert flags[52 * 9 + 30] == 2 and sum(flags) == 2, sum(flags)
    assert quantile([0, 10], 0.5) == 5


if __name__ == "__main__":
    self_check()
    print("stats ok")
