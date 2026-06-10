# ONPE 2026 — Scraper Automático + Dashboard en la Nube

Sistema 100% en la nube que **scrapea ONPE cada hora** y muestra los resultados
en un **dashboard HTML** auto-actualizable. Todo gratis con GitHub.

## Cómo funciona

```
GitHub Actions (cada hora)
   → corre scraper/onpe_scraper.py (con Chrome fingerprint)
   → consulta la API interna de ONPE
   → guarda docs/data.json
   → hace commit automático

GitHub Pages
   → sirve docs/index.html (el dashboard)
   → lee data.json y se autorefresca cada 5 min
```

## Despliegue (10 minutos, una sola vez)

### 1. Crear el repositorio
- Entra a https://github.com/new
- Nombre: `onpe-2026` · Marca **Public** · Crea el repo.

### 2. Subir los archivos
Sube TODO el contenido de esta carpeta manteniendo la estructura:
```
.github/workflows/scraper.yml
scraper/onpe_scraper.py
scraper/requirements.txt
docs/index.html
docs/data.json
```
(Puedes arrastrarlos en GitHub → "Add file" → "Upload files", subiendo carpeta por carpeta.)

### 3. Activar GitHub Pages
- Repo → **Settings** → **Pages**
- Source: **Deploy from a branch**
- Branch: **main** · Folder: **/docs** → **Save**
- En 1-2 min tu dashboard estará en:
  `https://TU_USUARIO.github.io/onpe-2026/`

### 4. Activar GitHub Actions
- Repo → pestaña **Actions** → si pide confirmación, **Enable**
- Para probar ya: Actions → "ONPE Scraper Horario" → **Run workflow**
- A partir de ahí corre solo cada hora.

## ¿Y si ONPE bloquea o cambia la API?

El scraper ya usa `curl_cffi` con `impersonate=chrome124` (el truco que
descubrió la comunidad para pasar el filtro anti-bot de ONPE).
Si ONPE cambia los endpoints, edita las URLs en `scraper/onpe_scraper.py`
(sección de funciones `get_*`). Los endpoints actuales:

| Endpoint | Uso |
|----------|-----|
| `/presentacion-backend/proceso/proceso-electoral-activo` | Detecta la elección activa |
| `/presentacion-backend/candidatos/totales?...` | Totales por candidato |
| `tipoFiltro=ubigeo_nivel_01&ubigeo=15` | Lima |
| `tipoFiltro=ambito_geografico&idAmbitoGeografico=2` | Extranjero |

## Datos iniciales

`docs/data.json` ya viene cargado con 18 cortes históricos (7-10 junio)
recopilados de prensa, para que el dashboard muestre datos desde el minuto cero.
El scraper irá añadiendo los cortes nuevos automáticamente.
