# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Confirmed by the owner on 2026-11-15: the page serves the **general public first**: someone with
no fire or satellite knowledge who wants to know whether there is fire near them, whether that
is normal for the time of year, and how bad it is.

Other audiences named in the NASA Space Apps challenge and the README, served second:
early-warning and emergency responders, land managers, scientists.

## Product Purpose

Burning Calendar shows where and when vegetation fires burned in the contiguous United States and
Hawaii since 2000, as seen by satellite, in one comparable unit across the MODIS and VIIRS sensors.
Success for a member of the public: they find their place, see whether fire is there now or was
there, understand whether it is unusual, and trust what they read.

## Positioning

One harmonized record: VIIRS detections are converted to MODIS-equivalent units with a published
observation operator, so 2002 and 2025 can be compared. Fires are grouped into single events with
duration, area, vegetation and a danger level measured on years the model never saw.

## Operating Context

A static web front end (`web/`) served by a FastAPI server (`server/`) that reads a local DuckDB
file and Parquet files built by `pipeline/`. Data ends on 2025-12-31 (the yearly FIRMS archive);
live detections need a FIRMS key and are not wired into the page.

## Capabilities and Constraints

Must keep working in every design (confirmed by the owner):

- **Fire map and time**: the fire layer on the map and moving through time (time bar, Play).
- **Burning calendar**: weekly history of an area, with unusual and record weeks and the usual season.
- **Fires near me**: fires around a place with their danger level.
- **Satellites**: the satellites in orbit and what each one sees.

Also present: fires one by one (duration, area, vegetation, before/after pictures, agency reports),
missed fires, a scientific report page, a state overview page, CSV download.

Constraints: no build step (plain HTML, CSS, JavaScript; MapLibre, D3, Observable Plot, three.js from
CDNs). Coverage is the contiguous U.S. and Hawaii only. The danger level is an experiment, not an
operational forecast.

Language: English (confirmed).

## Brand Commitments

Name: Burning Calendar. Repository and team name: A head full of dreams. No logo or binding visual
identity was given; the owner asked for three experimental directions to compare.

## Evidence on Hand

Real data behind every number (FIRMS archive 2000–2025, 11.3 million detections, 2.0 million fires).
NASA 3D models of Terra, Aqua, Suomi NPP and Landsat 8 in `web/models/`. NASA Worldview pictures on
request. No testimonials, users or usage numbers exist; none may be invented.

## Product Principles

1. Answer the visitor's question in plain words before showing the instrument.
2. Say what is not known: no detection is not the same as no fire; the record ends in 2025.
3. Every number can be traced to its source and method.
4. The same fire means the same thing everywhere on the page.

## Accessibility & Inclusion

The challenge asks for accessible color ramps. No formal standard was set by the owner; treat WCAG
2.2 AA contrast, keyboard reach and color-independent meaning as the working floor.
