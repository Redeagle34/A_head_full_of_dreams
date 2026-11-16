# Video A Head Full of Dreams (37 s, 1920×1080, 60 fps)

La animación es una página web donde cada fotograma depende solo del tiempo (`window.seek(t)`), y se renderiza a MP4 con Chrome sin ventana + ffmpeg.

- `index.html`, `main.js`: la animación (escenas de gis, globo 3D, satélites, mapa, interfaz de la app).
- `GUION.md`: guión con tiempos y texto para grabar la voz.
- `out/video_1080p60.mp4`: el video renderizado.

## Fotos de las personas

Ya están puestas: `assets/people/persona1.png` … `persona4.png`, recortadas sin fondo con `tools/cutout.py` (sin modelos de IA: superpíxeles + color de la pared). Para cambiar una foto, recórtala con

```bash
python A_head_full_of_dreams/video/tools/cutout.py foto.jpg A_head_full_of_dreams/video/assets/people/persona1.png
```

Posición, tamaño, lado de entrada y color del papel de cada persona: `PEOPLE`, al inicio de `main.js`.

## Ver y renderizar

Vista previa con controles (Play y barra de tiempo): sirve la carpeta y abre `http://localhost:8767/` (`?t=12.5` salta a un segundo).

```bash
python -m http.server 8767 --directory A_head_full_of_dreams/video
```

Renderizar (con el servidor anterior corriendo):

```bash
node A_head_full_of_dreams/video/tools/render.mjs
```

Opciones: `--fps 30`, `--from 10 --to 15` (un tramo), `--stills 3.5,12,26` (imágenes PNG sueltas en `out/stills`).

`tools/prep_assets.py` y `tools/globe_patches.py` vuelven a generar los datos y las imágenes de `data/` y `assets/` (ya están generados).

## Fuentes

- Detecciones: NASA FIRMS (MODIS C6.1, VIIRS S-NPP y NOAA-20), del archivo Parquet del proyecto; 8 sep 2020, California.
- Imagen satelital del mapa: Esri World Imagery (Esri, Maxar, Earthstar Geographics).
- Textura de la Tierra: NASA Blue Marble (vía three-globe); contornos: Natural Earth (world-atlas).
- Modelos 3D: NASA 3D Resources (Terra, Aqua, Suomi NPP; este último también se usa para NOAA-20).
