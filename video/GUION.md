# Guión: video de presentación, equipo A Head Full of Dreams

Formato: horizontal 16:9, 1920×1080, 60 fps, 27 s.
Voz en off en español. Ritmo: unas 2,8 palabras por segundo (rápido pero claro).
Los tiempos marcan cuándo empieza cada frase; la animación ya está sincronizada con ellos.

| Tiempo | Voz en off | Lo que se ve |
|---|---|---|
| 0:00 – 0:03.5 | «En un mundo con cada vez más incendios…» | Pizarrón verde. Al centro se escribe **CADA VEZ MÁS INCENDIOS** con letras de gis texturizadas en tonos de fuego, y encima de las letras brotan fuegos dibujados que se mueven como animación a mano. |
| 0:03.5 – 0:05.6 | «…hoy más que nunca es importante predecirlos,» | Aparece rápido una gráfica de pronóstico y debajo **PREDECIR**. |
| 0:05.6 – 0:07.6 | «…prevenirlos…» | Escudo y debajo **PREVENIR**. |
| 0:07.6 – 0:09.6 | «…y actuar a tiempo cuando ya están activos.» | Rayo y debajo **ACTUAR**. |
| 0:09.6 – 0:11.4 | *(sin voz, golpe de música)* | Zoom out sobre las letras: se aplastan hasta volverse una línea; los dos extremos de la línea se curvan hacia abajo y forman un círculo, que se convierte en la Tierra dibujada con gis. |
| 0:11.0 – 0:14.0 | «Somos el equipo A Head Full of Dreams, y esta es nuestra propuesta.» | Entran los 4 integrantes, derechos y a la misma escala, recortados sin fondo con un contorno de colores que sigue su silueta y cambia de color; todos señalan la Tierra: dos por la izquierda, una por la derecha y uno al centro sosteniéndola. Título **A HEAD FULL OF DREAMS** en colores que cambian, y debajo «esta es nuestra propuesta». |
| 0:14.0 – 0:17.4 | *(sin voz, música sube)* | Las personas salen. Un satélite 3D (Suomi NPP) sube desde abajo sin detenerse mientras la Tierra se hace un poco más chica, y se desliza hasta su órbita. El pizarrón se abre al espacio y la Tierra de gis se vuelve la Tierra real. En las órbitas giran los modelos 3D de Terra y Aqua. |
| 0:17.4 – 0:18.0 | «Nuestra solución…» | El satélite termina de entrar en órbita y la Tierra empieza a girar hacia Norteamérica. |
| 0:18.0 – 0:20.0 | «…es una aplicación interactiva, nuestra página web,…» | La imagen se congela y aparece **OUR WEBPAGE**. Zoom out recto: lo que veíamos era la pantalla de una laptop, vista de frente. |
| 0:20.0 – 0:27.0 | «…donde puedes ver los incendios en el mapa, cuándo pasan los satélites y la historia de cada zona.» | En la pantalla, la imagen congelada se convierte en la página real de Burning Calendar, grande y de frente. Un cursor hace clic en *Satellites* y luego en *Area history*. |

## Texto corrido para grabar

> En un mundo con cada vez más incendios, hoy más que nunca es importante predecirlos, prevenirlos y actuar a tiempo cuando ya están activos.
>
> Somos el equipo A Head Full of Dreams, y esta es nuestra propuesta.
>
> Nuestra solución es una aplicación interactiva, nuestra página web, donde puedes ver los incendios en el mapa, cuándo pasan los satélites y la historia de cada zona.

## Cosas que conviene revisar antes de grabar

- **«en el mundo» vs. lo que hace la app.** Tu idea original dice «puede ver en el mundo los incendios activos». Según `PRODUCT.md`, Burning Calendar cubre solo Estados Unidos continental y Hawái, y los datos terminan el 31 de diciembre de 2025 (las detecciones en vivo necesitan una llave de FIRMS y no están conectadas). Por eso el guión dice «en el mapa». Si el jurado ve la app, conviene no prometer cobertura mundial ni tiempo real. Si sí quieren decirlo, una versión honesta es: «…donde puedes ver los incendios detectados por satélite desde el año 2000».
- **Lo que se ve es real**: los puntos de fuego del globo son detecciones FIRMS de septiembre de 2020, y las pantallas de la laptop son capturas de la página real (`assets/web/`, hechas con `tools/capture_web.mjs`).
- **Créditos que hay que poner** (en la descripción o al final del video completo): imágenes satelitales de Esri World Imagery (Esri, Maxar, Earthstar Geographics); textura de la Tierra NASA Blue Marble; modelos 3D de NASA 3D Resources; detecciones de NASA FIRMS.
