# Script: A Head Full of Dreams presentation video

Format: 16:9 landscape, 1920×1080, 60 fps, 37 s.
English voice-over. Pace: about 2.8 words per second (brisk but clear).
Times mark where each line starts; the animation is currently synced to them. Once your recordings are in, the animation will be retimed to your voices (see "Recording the voices" below).

| Time | Voice-over | On screen |
|---|---|---|
| 0:00 – 0:03.5 | "In a world with more and more fires…" | Green chalkboard. **MORE AND MORE FIRES** is written in the centre in textured, fire-coloured chalk, and hand-drawn flames grow on top of the letters. |
| 0:03.5 – 0:05.6 | "…today more than ever we need to predict them," | A forecast chart pops in with **PREDICT** under it. |
| 0:05.6 – 0:07.6 | "…prevent them…" | A shield with **PREVENT**. |
| 0:07.6 – 0:09.6 | "…and take action in time when they are already burning." | A lightning bolt with **TAKE ACTION**. |
| 0:09.6 – 0:11.4 | *(no voice, music hit)* | Zoom out on the letters: they flatten into one line, both ends curl down into a rainbow circle, and the circle becomes a colourful chalk Earth. |
| 0:11.0 – 0:14.0 | "We are team A Head Full of Dreams, and this is our proposal." | The 5 teammates slide in, upright and at the same scale, cut out with a colour-cycling outline that follows each silhouette, all pointing at the Earth. **A HEAD FULL OF DREAMS** in shifting colours, with "this is our proposal" underneath. |
| 0:14.0 – 0:17.4 | *(no voice, music rises)* | The team slides out. A 3D satellite (Suomi NPP) rises from below without stopping while the Earth shrinks a little, and glides into orbit. The chalkboard opens into space and the chalk Earth becomes the real Earth. Terra and Aqua circle on their own orbits. |
| 0:17.4 – 0:18.0 | "Our solution…" | The satellite settles into orbit and the Earth starts turning toward North America. |
| 0:18.0 – 0:20.0 | "…is an interactive app, our webpage,…" | The picture freezes and **OUR WEBPAGE** appears. Straight zoom out: what we were watching was the screen of a laptop, seen head-on. |
| 0:20.0 – 0:25.2 | "…where you can see fires on the map, when the satellites pass overhead, and the fire history of any area." | On the screen the frozen picture turns into the real Burning Calendar page (the Guide map design), big and head-on: the cover with the Earth and play. A cursor presses *Play* and the map opens on the United States; it zooms out until the satellites show, picks one (its card opens on the left), then opens *Settings* → *Area numbers* for the fire history. |
| 0:25.2 – 0:30.2 | "We built it on open data: NASA FIRMS detections from MODIS and VIIRS, gridMET weather, LANDFIRE, MODIS and Landsat imagery, and NIFC fire reports." | The laptop slides right and steps back; a **DATASETS** panel slides in from the left and lists the 9 sources, one by one. |
| 0:30.2 – 0:37.0 | "And these algorithms: a satellite observation operator that makes VIIRS and MODIS comparable, fire grouping, and a LightGBM model that rates the danger of each fire." | DATASETS leaves to the left the way it came, the laptop keeps sliding left past the centre, and an **ALGORITHMS** panel arrives from the right to the centre, listing the 8 methods. |

## Full text to record

> In a world with more and more fires, today more than ever we need to predict them, prevent them, and take action in time when they are already burning.
>
> We are team A Head Full of Dreams, and this is our proposal.
>
> Our solution is an interactive app, our webpage, where you can see fires on the map, when the satellites pass overhead, and the fire history of any area.
>
> We built it on open data: NASA FIRMS detections from MODIS and VIIRS, gridMET weather, LANDFIRE, MODIS and Landsat imagery, and NIFC fire reports.
>
> And these algorithms: a satellite observation operator that makes VIIRS and MODIS comparable, fire grouping, and a LightGBM model that rates the danger of each fire.

## Recording the voices

Put the recordings in `video/audio/` (WAV, MP3 or M4A all work). Two ways, pick one:

- **One file per line** (easiest to retime): `01_fires.wav`, `02_team.wav`, `03_solution.wav`, each starting right when the person starts speaking.
- **One continuous take**: `voice.wav`, with a short pause (about half a second) between the three blocks above.

What happens next: the start and end of every phrase are measured from the audio itself (silence detection with ffmpeg), the scenes are stretched or shortened so each animation beat lands on its words (title on "fires", the three icons on "predict / prevent / take action", the team on "A Head Full of Dreams", the freeze on "our webpage", the clicks on "satellites" and "history", the DATASETS panel on "open data", ALGORITHMS on "algorithms"), and the voice is mixed into the final MP4.

## Check before recording

- **"see fires on the map", not "around the world" or "live".** According to `PRODUCT.md`, Burning Calendar covers only the contiguous United States and Hawaii, and its data ends on 31 December 2025 (live detections need a FIRMS key and are not wired in). The script avoids promising worldwide or real-time coverage.
- **What is on screen is real**: the fire dots on the globe are FIRMS detections from September 2020, and the laptop screens are captures of the real page (`assets/web/`, made with `tools/capture_web.mjs`).
- **Credits to include** (in the description or at the end of the full video): Earth texture NASA Blue Marble; 3D models from NASA 3D Resources; fire detections from NASA FIRMS; map imagery inside the webpage from Esri World Imagery.
