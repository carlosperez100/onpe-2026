# ONPE 2026 — Dashboard Electoral · CLAUDE.md

Contexto permanente para no re-explorar el proyecto en cada sesión.

## Repositorio y despliegue

- **Local**: `C:\Users\infor\onpe-edit`
- **GitHub**: https://github.com/carlosperez100/onpe-2026
- **Sitio público**: https://carlosperez100.github.io/onpe-2026/
- **Rama principal**: `main` → GitHub Pages sirve `docs/`

## Estructura de archivos

```
scraper/
  onpe_scraper.py        # scraper principal (Playwright + BeautifulSoup)
  merge_historial.py     # helper: unifica historial en rebase conflict
  requirements.txt
docs/
  index.html             # dashboard (Chart.js 4.4.1, sin bundler)
  data.json              # datos actuales + historial acumulativo
  data.csv               # exportación CSV del historial
.github/workflows/
  scraper.yml            # GitHub Actions cron */15 min UTC
```

## Regla crítica: historial ADITIVO

El campo `historial` en `data.json` es **acumulativo** — NUNCA reemplazar.
Flujo correcto: leer data.json → añadir entradas nuevas → escribir.
`load_existing()` + `historial.append(...)` ya lo maneja correctamente.
**Nunca usar `git checkout --ours docs/data.json`** en conflictos de merge.
El workflow hace `git pull` ANTES de correr el scraper y usa `merge_historial.py`
para resolver conflictos de push (rebase → merge historial por ts).

## Modelo estadístico (3 estratos)

```
Nacional TODOS = Perú doméstico + Internacional
Fuera de Lima  = Nacional − Lima − Internacional  (calcular_resto())
Pesos: wL + wR + wE = 100%  (VV_k/avance_k / suma)
```

**Monte Carlo**: N=20 000, σL=0.003, σR=0.004, σE=0.005  
**OLS univariado**: y=β0+β1·actas%, proyectado a actas=100  
**Por estrato**: σN=0.002, σL=0.003, σR=0.004, σE=0.005 (N=10 000)

## data.json — estructura

```json
{
  "meta": { "ultima_actualizacion", "pct_avance", "actas_contabilizadas", "actas_totales" },
  "nacional": { "pct_avance", "votos_validos", "sanchez": {votos, pct_validos}, "fujimori": {...} },
  "lima":     { igual que nacional },
  "resto":    { derivado: Nacional − Lima − Internacional },
  "extranjero": { igual que nacional },
  "proyeccion": {
    "univariado":    { sanchez_pct, fujimori_pct, ic_inf, ic_sup, r2 },
    "estratificado": { sanchez_pct, fujimori_pct, ic_inf, ic_sup, prob_sanchez, prob_fujimori, pesos, n_sim },
    "por_estrato":   { nacional, lima, resto, extranjero }  ← proyecciones individuales
  },
  "historial": [ { ts, hora, actas, sanchez_votos, sanchez_pct, fujimori_votos, fujimori_pct, brecha } ]
}
```

## Fuentes ONPE

- **TODOS (Nacional)**: filtro "TODOS" en la SPA de ONPE
- **Perú doméstico**: filtro "PERÚ" (≠ TODOS; incluye Lima + FDL, excluye Extranjero)
- **Lima**: filtro por departamento Lima
- **Internacional**: filtro Extranjero / Internacional
- `calcular_resto()` deriva FDL = Nacional − Lima − Internacional

## Zona horaria

Perú: UTC-5. El scraper usa `PERU_TZ = pytz.timezone("America/Lima")`.  
Timestamps en `historial.ts` en formato ISO 8601 local Perú.

## GitHub Actions

- Cron: `*/15 * * * *` (cada 15 min UTC)
- El workflow hace `git pull` ANTES de correr el scraper
- Push con retry: si falla, hace rebase + `merge_historial.py`
- `continue-on-error: true` en el paso del scraper (bot-detection puede fallar)

## Candidatos

- **Roberto Sánchez** — Juntos por el Perú N.° 16 — color: `#2ecc71` (verde)
- **Keiko Fujimori** — Fuerza Popular N.° 10 — color: `#ff8c42` (naranja)

## Contexto académico

Autor: Mg. Carlos Pérez Pérez · RENACYT · CIIDEG SAC  
Modelo GEMSES (Patente WIPO PE324096539)  
Email: informes.ciideg@gmail.com
