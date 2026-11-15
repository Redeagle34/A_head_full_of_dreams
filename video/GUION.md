# Guión: video de presentación, equipo A Head Full of Dreams

Formato: horizontal 16:9, 1920×1080, 60 fps, 30 s.
Voz en off en español. Ritmo: unas 2,8 palabras por segundo (rápido pero claro).
Los tiempos marcan cuándo empieza cada frase; la animación ya está sincronizada con ellos.

| Tiempo | Voz en off | Lo que se ve |
|---|---|---|
| 0:00 – 0:03.5 | «En un mundo con cada vez más incendios…» | Pizarrón verde. Entran fuegos dibujados con gis desde los bordes, se mueven y tiemblan como animación a mano. Se escribe con gis **CADA VEZ MÁS INCENDIOS**. Aparecen más fueguitos. |
| 0:03.5 – 0:05.6 | «…hoy más que nunca es importante prevenirlos,» | Se dibuja un escudo y la palabra **PREVENIR**. |
| 0:05.6 – 0:07.6 | «…poder controlarlos cuando están activos…» | Mira de control y **CONTROLAR**. |
| 0:07.6 – 0:09.6 | «…y analizar sus causas y sus consecuencias.» | Lupa con gráfica y **ANALIZAR**. |
| 0:09.6 – 0:10.6 | *(sin voz, golpe de música)* | Zoom out: todo el pizarrón se encoge y aparece la Tierra dibujada con gis, girando, con fueguitos sobre ella. |
| 0:10.2 – 0:14.0 | «Somos el equipo A Head Full of Dreams, y esta es nuestra propuesta.» | Entran las 5 personas: una por la derecha abajo, otra detrás y más arriba, otra por la izquierda abajo, otra detrás y más arriba a la izquierda, y la quinta sube desde abajo al centro. Título **A HEAD FULL OF DREAMS** y debajo «esta es nuestra propuesta». |
| 0:14.0 – 0:17.4 | *(sin voz, música sube)* | Las personas salen. Un satélite 3D (Suomi NPP) sube desde abajo hasta el centro, se aleja y se hace chiquito hasta quedar en órbita. El pizarrón se abre al espacio y la Tierra de gis se vuelve la Tierra real. Aparecen las órbitas y los haces de los satélites. |
| 0:17.4 – 0:22.6 | «Nuestra solución es una aplicación interactiva donde puedes ver los incendios activos en el mapa…» | La Tierra gira a Norteamérica, se encienden miles de puntos de fuego (datos reales, septiembre 2020) y la cámara entra a California hasta el mapa satelital en alta definición, con la interfaz de la app. |
| 0:22.6 – 0:25.0 | «…y distinguir los que detecta MODIS…» | Una línea de barrido cruza el mapa y aparecen los cuadritos de detección sobre el August Complex. |
| 0:25.0 – 0:30.0 | «…en Terra y Aqua, y los que detecta VIIRS, en Suomi NPP y NOAA-20.» | Pantalla dividida: izquierda solo MODIS (píxel ≈ 1 km) con Terra y Aqua en 3D; derecha solo VIIRS (píxel ≈ 375 m) con Suomi NPP y NOAA-20. Mismo lugar, distinta resolución. |

## Texto corrido para grabar

> En un mundo con cada vez más incendios, hoy más que nunca es importante prevenirlos, poder controlarlos cuando están activos y analizar sus causas y sus consecuencias.
>
> Somos el equipo A Head Full of Dreams, y esta es nuestra propuesta.
>
> Nuestra solución es una aplicación interactiva donde puedes ver los incendios activos en el mapa, y distinguir los que detecta MODIS, en Terra y Aqua, y los que detecta VIIRS, en Suomi NPP y NOAA-20.

## Cosas que conviene revisar antes de grabar

- **«en el mundo» vs. lo que hace la app.** Tu idea original dice «puede ver en el mundo los incendios activos». Según `PRODUCT.md`, Burning Calendar cubre solo Estados Unidos continental y Hawái, y los datos terminan el 31 de diciembre de 2025 (las detecciones en vivo necesitan una llave de FIRMS y no están conectadas). Por eso el guión dice «en el mapa». Si el jurado ve la app, conviene no prometer cobertura mundial ni tiempo real. Si sí quieren decirlo, una versión honesta es: «…donde puedes ver los incendios detectados por satélite desde el año 2000».
- **Lo que se ve en el mapa es real**: detecciones FIRMS del 8 de septiembre de 2020 sobre el August Complex (California), sacadas de los Parquet del proyecto. El tamaño de cada cuadrito es el tamaño real del píxel (`scan` × `track`).
- **Créditos que hay que poner** (en la descripción o al final del video completo): imágenes satelitales de Esri World Imagery (Esri, Maxar, Earthstar Geographics); textura de la Tierra NASA Blue Marble; modelos 3D de NASA 3D Resources; detecciones de NASA FIRMS.
