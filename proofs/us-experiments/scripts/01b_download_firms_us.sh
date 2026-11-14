#!/usr/bin/env bash
# US yearly FIRMS country archives (public, no key). Cached; never re-downloads.
B=https://firms.modaps.eosdis.nasa.gov/data/country
OUT=data/country; mkdir -p $OUT
get(){ s=$1; y=$2; c=$3; f=$OUT/${s}_${y}_${c}.csv; [ -s "$f" ] && return; curl -sf --retry 3 -o "$f.part" "$B/$s/$y/${s}_${y}_${c}.csv" && mv "$f.part" "$f" && echo "ok $s $y" || { rm -f "$f.part"; echo "miss $s $y $c"; }; }
for y in $(seq 2012 2025); do get viirs-snpp $y United_States; done
for y in $(seq 2000 2025); do get modis $y United_States; done
for y in $(seq 2018 2025); do get viirs-jpss1 $y United_States; done
echo DONE
