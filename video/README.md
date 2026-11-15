# Video A Head Full of Dreams (30 s, 1920×1080, 60 fps)

La animación es una página web donde cada fotograma depende solo del tiempo (`window.seek(t)`), y se renderiza a MP4 con Chrome sin ventana + ffmpeg.

- `index.html`, `main.js`: la animación (escenas de gis, globo 3D, satélites, mapa, interfaz de la app).
- `GUION.md`: guión con tiempos y texto para grabar la voz.
- `out/video_1080p60.mp4`: el video renderizado.

## Poner las fotos de las 5 personas

1. Guarda las fotos como `assets/people/persona1.png` … `persona5.png` (también sirve `.jpg`). Se recortan solas para llenar el marco; conviene que sean verticales.
2. Cambia los nombres en `PEOPLE`, al inicio de `main.js` (`'Integrante 1'`, etc.). Ahí también están la posición, el tamaño y el lado por el que entra cada persona.

| # | Entra por | Lugar |
|---|---|---|
| 1 | derecha | abajo a la derecha (al frente) |
| 2 | derecha | detrás de la 1, más arriba |
| 3 | izquierda | abajo a la izquierda (al frente) |
| 4 | izquierda | detrás de la 3, más arriba |
| 5 | abajo | centro, delante de la Tierra |

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
