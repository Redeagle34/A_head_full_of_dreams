# Script: A Head Full of Dreams presentation video

Format: 16:9 landscape, 1920×1080, 60 fps, 30 s.
English voice-over, brisk (about 3 words per second). Times mark where each line starts; once your recordings are in, the animation will be retimed to your voices (see "Recording the voices").

| Time | Voice-over | On screen |
|---|---|---|
| 0:00 – 0:05.0 | "In a world with more and more fires, we need to predict them, prevent them, and take action." | NASA Space Apps Challenge logo on top. **MORE AND MORE FIRES** in textured fire-coloured chalk, flames growing on the letters; **PREDICT · PREVENT · TAKE ACTION** pop in under it. |
| 0:05.0 – 0:06.1 | *(music hit)* | The letters flatten into a line, the line curls into a rainbow circle, the circle becomes a colourful chalk Earth. |
| 0:06.1 – 0:08.3 | "We are A Head Full of Dreams, and this is our proposal." | The 5 teammates slide in, alternating left and right, cut out with colour-cycling outlines, heads aligned, all pointing at the Earth. **A HEAD FULL OF DREAMS** in shifting colours. |
| 0:08.3 – 0:10.6 | *(music rises)* | A 3D satellite rises without stopping and glides into orbit; the chalkboard opens into space and the Earth becomes real. |
| 0:10.6 – 0:12.0 | "Our webpage," | The picture freezes, **OUR WEBPAGE**, straight zoom out: it was a laptop screen. |
| 0:12.0 – 0:14.9 | "built on open NASA data…" | The laptop slides right; **DATASETS** slides in from the left: 9 sources. |
| 0:14.9 – 0:17.9 | "…and our own algorithms." | DATASETS leaves left, the laptop slides past the centre, **ALGORITHMS** arrives from the right: 8 methods. |
| 0:17.9 – 0:18.4 | | ALGORITHMS leaves right and the laptop comes back to the centre, close and head-on. |
| 0:18.4 – 0:21.2 | "Search any place and analyse its fires," | **ANALYSING FIRES IN A GIVEN AREA**: typing "Paradise, California", then the result card zooms in: the Camp Fire, 171,251 acres, rated Extreme. |
| 0:21.2 – 0:23.9 | "watch any period play out," | **ANALYSING FIRES ACROSS A PERIOD**: Play is clicked and California's 2020 fire season runs month by month. |
| 0:23.9 – 0:26.6 | "and compare satellite pictures before and after a fire." | **BEFORE AND AFTER A FIRE PICTURES**: the Camp Fire's Landsat pictures before and after, and its burn-severity map, zoomed in. |
| 0:26.6 – 0:30.0 | *(no voice, big hit)* | The laptop is flung away, a wall of fire rises, white flash, **A HEAD FULL OF DREAMS** slams in with a shockwave, NASA Space Apps logo, embers, fade to black. |

## Full text to record (about 21 seconds of speech)

> In a world with more and more fires, we need to predict them, prevent them, and take action.
>
> We are A Head Full of Dreams, and this is our proposal.
>
> Our webpage, built on open NASA data and our own algorithms. Search any place and analyse its fires, watch any period play out, and compare satellite pictures before and after a fire.

## Recording the voices

**Already recorded** (`audio/voice_raw.mp4`, used in `audio/voice_clean.wav`): the intro (sped up 1.25×, pitch kept), the team line, and
"Our solution is an interactive app, where you can see all the fires that are active, and which ones were detected by MODIS or by VIIRS".
The clause "which are aboard Terra and Aqua, Suomi NPP and NOAA-20" was cut: it repeats the DATASETS panel and kept the video from fitting in 30 s.

**Second recording** (`audio/voice2_raw.mp4`): the five lines below, each placed on its slide at normal speed (final voice track: `audio/voice_full.wav`):

| Line in the take | Line | Slide | Placed at |
|---|---|---|---|
| 2.0–4.4 s | "Our algorithms rate every fire's danger." | ALGORITHMS | 18.95 s |
| 5.1–6.5 s | "Search any place," | Analysing fires in a given area | 21.2 s |
| 6.8–8.5 s | "replay any period," | Analysing fires across a period | 23.25 s |
| 9.0–11.5 s | "and see each fire, before and after." | Before and after a fire pictures | 25.1 s |
| 12.7–13.6 s | "Burning Calendar." | Title slam | 28.6 s |

Music and sound effects are synthesized by `tools/make_audio.py` (royalty-free, timed to the film's events); the music ducks under the voice in the final mix.

## What is on screen is real

- The laptop shows the real Burning Calendar page (the Guide map design), captured from the app with `tools/capture_features.mjs`: the Paradise search and its fire card, a Play run over 2020, and the Camp Fire (event 1564960) with its Landsat before/after pictures and burn severity from Earth Engine.
- The fire dots on the globe are FIRMS detections from September 2020.
- The script says "any place", but coverage is the contiguous United States and Hawaii (see `PRODUCT.md`), and data ends on 31 December 2025. If the jury may try other countries, say "any place in the U.S.".

## Credits to include

NASA Space Apps Challenge logo; Earth texture NASA Blue Marble; 3D models from NASA 3D Resources; fire detections from NASA FIRMS; Landsat imagery (USGS/NASA) via Google Earth Engine; map imagery inside the webpage from Esri World Imagery.
