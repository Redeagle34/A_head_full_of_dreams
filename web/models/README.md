# Satellite 3D models

From NASA 3D Resources, https://github.com/nasa/NASA-3D-Resources (folder "3D Models"),
downloaded 2026-11-14. NASA media usage guidelines: https://www.nasa.gov/nasa-brand-center/images-and-media

| File | NASA model |
|---|---|
| `terra.glb` | Terra |
| `aqua.glb` | Aqua (A) |
| `suomi-npp.glb` | Suomi National Polar-orbiting Partnership (Suomi NPP); also used for NOAA-20 and NOAA-21, for which NASA publishes no model |
| `landsat-8.glb` | Landsat 8 |

## Terra's surface textures

NASA's `3D Models/Terra/Terra.glb` refers to two texture pictures (`Side_Panels_TERRA.tga`,
`solarpanels.tga`) that are not in the file or the folder, and it has no texture coordinates.
`terra.glb` here is that file with both repaired, using only NASA's own material from the same
repository, downloaded 2026-11-14:

- The two pictures come from the earlier version of the model, `3D Models/Terra/Terra_vFINAL.fbx`
  at commit `2b93e26d1b8705c97b39106b62e938144268cc81` ("From NASA 3D", 2015), which carries them
  inside the file. They are stored in `terra.glb` as PNG at their original size (346 x 313 and
  266 x 229 pixels), unchanged.
- The texture coordinates of the two meshes that use them ("Side Panels", "Main Solar Panels")
  come from the current `3D Models/Terra/Terra.fbx`, matched to the GLB's points by position.
- The base colour of those two materials is set to white, so the picture is shown as it is
  instead of being darkened by the blue that stood in for it.

The shapes and all other materials are NASA's, byte for byte.
