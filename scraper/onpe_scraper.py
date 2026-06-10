#!/usr/bin/env python3
"""
ONPE Scraper - Segunda Vuelta 2026
Extrae totales nacionales, Lima, Peru, extranjero desde ONPE.
Usa: (1) scraping HTML cuando API falla, (2) API con Referer como fallback.
Guarda en docs/data.json para que el dashboard HTML lo consuma.
Incluye fecha/hora original del API ONPE.
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as cffi

BASE = "https://resultadosegundavuelta.onpe.gob.pe"
REFERER = f"{BASE}/main/resumen"
IMPERSONATE = "chrome124"
TIMEOUT = 30
PERU_TZ = timezone(timedelta(hours=-5))
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

def get_raw(url, referer=True):
    hdrs = {"Accept": "application/json", "Referer": REFERER} if referer else {}
    r = cffi.get(url, impersonate=IMPERSONATE, timeout=TIMEOUT, headers=hdrs)
    return r.status_code, r.text

def get_html_status():
    """Llama a la SPA de ONPE y devuelve el HTML renderizado."""
    return get_raw(f"{BASE}/main/resumen", referer=False)

def try_json_api(base_path, params):
    """Llama a un endpoint de la API de ONPE."""
    url = f"{BASE}{base_path}"
    if params:
        qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        url += qs
    status, text = get_raw(url)
    if status != 200 or not text:
        raise RuntimeError(f"HTTP {status} en {url}")
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"No JSON en {url}")
    return body.get("data", body) if isinstance(body, dict) else body

def scrape_html(html):
    """Extrae datos desde el HTML de la SPA de ONPE."""
    # Porcentaje avance
    m = re.search(r">97\.\d+\s*%" if "97" in html else r"(\d+\.?\d*)\s*%", html)
    pct_avance = "0"
    if m:
        # Buscar especificamente el porcentaje de actas contabilizadas
        pct_pat = re.search(r"Actas contabilizadas.*?>(\d+\.?\d*\s*%)", html)
        if pct_pat:
            pct_avance = pct_pat.group(1)
        else:
            pct_avance = m.group(0) if m else "0"
    # Total actas
    m = re.search(r"Total de actas:\s*([\d,]+)", html)
    total_actas = int(m.group(1).replace(",", "")) if m else 0
    # Sanchez votos
    m = re.search(r"9[\u2019']?([\d,]*)\s*votos", html)
    sanchez = 0
    fujimori = 0
    # Buscar votos por candidato mas especificamente
    pat_s = re.search(r"ROBERTO.*?(9[\u2019']?\d{1,3}(?:,\d{3})*(?:,\d{1,3})?)\s*votos", html, re.DOTALL)
    pat_f = re.search(r"KEIKO.*?(9[\u2019']?\d{1,3}(?:,\d{3})*(?:,\d{1,3})?)\s*votos", html, re.DOTALL)
    if pat_s:
        sanchez = int(pat_s.group(1).replace("'", "").replace(",", ""))
    if pat_f:
        fujimori = int(pat_f.group(1).replace("'", "").replace(",", ""))
    # Votos conjuntos
    votos = pat_s or pat_f
    if not pat_s or not pat_f:
        # Fallback: buscar cualquier patron de votos
        votos_pat = re.findall(r"(\d[\d\u2019\,,]*)\s*votos", html)
        if votos_pat:
            nums = [int(v.replace("'", "").replace(",", "")) for v in votos_pat]
            nums = [n for n in nums if n > 100000]  # Solo numeros grandes
            if len(nums) >= 2:
                sanchez, fujimori = nums[0], nums[1]
    # Porcentajes candidatos
    pct_s = pct_f = 0
    pct_pat_s = re.search(r"5\d\.\d+\s*%", html)
    pct_pat_f = re.search(r"4\d\.\d+\s*%", html)
    if pct_pat_s:
        pct_s = float(pct_pat_s.group().replace("%", "").strip())
    if pct_pat_f:
        pct_f = float(pct_pat_f.group().replace("%", "").strip())
    return {
        "pct_avance": pct_avance,
        "total_actas": total_actas,
        "sanchez": {"votos": sanchez, "pct_validos": pct_s},
        "fujimori": {"votos": fujimori, "pct_validos": pct_f},
    }

def get_original_timestamp(html=None):
    """Extrae la fecha/hora original del API ONPE desde el HTML."""
    if not html:
        status, html = get_html_status()
        if status != 200 or not html:
            return None
    patron = r"ACTUALIZADO AL (\d{2}/\d{2}/\d{4}) A LAS (\d{1,2}:\d{2}:\d{2}) (a\.?m\.?|p\.?m\.?)" if "ACTUALIZADO AL" in html else r"(\d{2}/\d{2}/\d{4}).*?(\d{1,2}:\d{2}:\d{2}).*?(a\.?m\.?|p\.?m\.?)"
    match = re.search(patron, html)
    if match:
        fecha, hora, ampm = match.groups()
        ampm = ampm.strip().lower().replace(".", "")
        return f"{fecha} {hora} {ampm}"
    return None

def fetch_region(ambito, label):
    """Obtiene datos de una region desde API o HTML."""
    # Intentar API primero
    bases = [
        "/presentacion-backend/candidatos/totales",
        "/presentacion-backend/resumen-general/totales",
        "/api/candidatos/totales",
    ]
    params = {"idEleccion": "162", "ambitoGeografico": ambito} if ambito else {}
    for b in bases:
        try:
            data = try_json_api(b, params if ambito else {"idEleccion": "162"})
            return parse_api(data), "api"
        except Exception as e:
            print(f"  [API {label}] {b}{f' params={params}' if params else ''} -> {e}")
    return None, "fallo_api"

def parse_api(data):
    """Parsea respuesta API de ONPE a formato comun."""
    if not data:
        return None
    cands = data if isinstance(data, list) else data.get("candidatos", [])
    sanchez = fujimori = None
    total_actas = 0
    for c in cands:
        nombre = (c.get("nombreAgrupacionPolitica") or "").upper()
        registro = {
            "votos": c.get("totalVotosValidos") or c.get("votos"),
            "pct_validos": c.get("porcentajeVotosValidos") or c.get("pct_votos_validos"),
            "pct_emitidos": c.get("porcentajeVotosEmitidos"),
        }
        if "JUNTOS" in nombre or "SANCHEZ" in nombre:
            sanchez = registro
        elif "FUERZA" in nombre or "FUJIMORI" in nombre:
            fujimori = registro
        if c.get("totalActas") and not total_actas:
            total_actas = c["totalActas"]
    return {"sanchez": sanchez, "fujimori": fujimori, "total_actas": total_actas}

def load_existing():
    """Carga data.json existente o devuelve estructura base."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"nacional": None, "peru": None, "lima": None, "extranjero": None,
            "historial": [], "meta": {"ultima_actualizacion": None, "fuente": None},
            "snapshots": []}

def save_data(data):
    """Guarda data.json con historial para evitar perder datos."""
    existing = load_existing()
    historial = existing.get("historial", [])
    snapshots = existing.get("snapshots", [])
    sanchez_votos = data["nacional"].get("sanchez", {}).get("votos") if data["nacional"] else None
    fujimori_votos = data["nacional"].get("fujimori", {}).get("votos") if data["nacional"] else None
    nuevo = True
    if historial and sanchez_votos and fujimori_votos:
        ultimo = historial[-1]
        if (ultimo.get("sanchez_votos") == sanchez_votos and
            ultimo.get("fujimori_votos") == fujimori_votos):
            nuevo = False
            print(f"  [HISTORIAL] Sin cambios: {ultimo.get('timestamp')}")
    if nuevo:
        snapshot = {
            "nacional": data["nacional"],
            "peru": data.get("peru"),
            "lima": data.get("lima"),
            "extranjero": data.get("extranjero"),
            "timestamp_iso": data["meta"]["ultima_actualizacion"],
        }
        historial.append({
            "timestamp": data["meta"]["ultima_actualizacion"],
            "sanchez_votos": sanchez_votos,
            "fujimori_votos": fujimori_votos,
        })
        snapshots.append(snapshot)
        print(f"  [HISTORIAL] Nuevo snapshot guardado ({len(historial)} en historial)")
    out = {
        "nacional": data["nacional"],
        "peru": data.get("peru") or existing.get("peru"),
        "lima": data.get("lima") or existing.get("lima"),
        "extranjero": data.get("extranjero") or existing.get("extranjero"),
        "historial": historial,
        "meta": {"ultima_actualizacion": data["meta"]["ultima_actualizacion"], "fuente": data["meta"].get("fuente")},
        "snapshots": snapshots if nuevo else snapshots,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    if not nuevo:
        print(f"  [WARN] No se escribieron cambios en data.json")

def main():
    # Paso 1: Obtener HTML de ONPE (la SPA renderiza los datos)
    print("[SCRAPER] Iniciando...")
    status, html = get_html_status()
    if status != 200 or not html:
        print(f"  [ERROR] No se pudo obtener HTML: HTTP {status}")
        return
    ts_onpe = get_original_timestamp(html)
    print(f"  [API ONPE] Timestamp original: {ts_onpe or '(no detectado)'}")
    ahora = datetime.now(PERU_TZ)
    ts_iso = ahora.isoformat()
    ts_legible = ahora.strftime("%d/%m/%Y %H:%M:%S")
    ts_final = ts_onpe if ts_onpe else ts_legible
    print(f"[{ts_final}] Iniciando captura ONPE...")
    # Paso 2: Extraer datos nacionales del HTML
    scraped = scrape_html(html)
    total_actas = scraped.get("total_actas", 0)
    pct_avance = scraped.get("pct_avance", "0")
    nacional = {
        "sanchez": {"votos": scraped["sanchez"]["votos"], "pct_validos": scraped["sanchez"]["pct_validos"]},
        "fujimori": {"votos": scraped["fujimori"]["votos"], "pct_validos": scraped["fujimori"]["pct_validos"]},
        "meta": {"total_actas": total_actas, "pct_avance": pct_avance},
    }
    print(f"  [NACIONAL] Sanchez: {nacional['sanchez']['votos']} ({nacional['sanchez']['pct_validos']}%)")
    print(f"  [NACIONAL] Fujimori: {nacional['fujimori']['votos']} ({nacional['fujimori']['pct_validos']}%)")
    print(f"  [NACIONAL] Actas: {total_actas} ({pct_avance})")
    # Paso 3: Intentar obtener datos de regiones via API
    lima, lima_src = fetch_region(None, "Lima")
    peru, peru_src = fetch_region("1", "Peru")
    ext, ext_src = fetch_region("2", "Extranjero")
    # Paso 4: Guardar datos
    data = {
        "nacional": nacional,
        "peru": peru,
        "lima": lima,
        "extranjero": ext,
        "meta": {"ultima_actualizacion": ts_final, "fuente": "onpe_html"},
    }
    save_data(data)
    print(f"[SCRAPER] Finalizado. Fuente: html")

if __name__ == "__main__":
    main()
