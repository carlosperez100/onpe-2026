#!/usr/bin/env python3
"""
ONPE Scraper - Segunda Vuelta 2026
Extrae totales nacionales, Lima y extranjero desde la API interna de ONPE.
Requiere curl_cffi con impersonate de Chrome (ONPE bloquea requests normales).
Guarda en docs/data.json para que el dashboard HTML lo consuma.
Incluye fecha/hora original del API ONPE (NO del momento del scrape).
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as cffi

BASE = "https://resultadosegundavuelta.onpe.gob.pe"
IMPERSONATE = "chrome124"
TIMEOUT = 30
PERU_TZ = timezone(timedelta(hours=-5))
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

def get_raw(url):
    r = cffi.get(url, impersonate=IMPERSONATE, timeout=TIMEOUT,
                 headers={"Accept": "application/json, text/plain, */*"})
    return r.status_code, r.text

def get(url):
    status, text = get_raw(url)
    snippet = (text or "")[:200].replace("\n", " ")
    if status != 200:
        raise RuntimeError(f"HTTP {status} en {url} | inicio: {snippet}")
    if not text or not text.strip():
        raise RuntimeError(f"Respuesta VACIA en {url}")
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"No es JSON ({url}). ONPE devolvio: {snippet}")
    return body.get("data", body) if isinstance(body, dict) else body

def get_original_timestamp():
    """Extrae la fecha/hora original del API ONPE desde el HTML.
    La pagina muestra 'ACTUALIZADO AL DD/MM/YYYY A LAS HH:MM:SS p.m.'
    Devuelve la fecha original en formato legible, o None si falla.
    """
    resumen_url = f"{BASE}/main/resumen"
    status, text = get_raw(resumen_url)
    if status != 200 or not text:
        return None
    # Buscar patron: ACTUALIZADO AL DD/MM/YYYY A LAS HH:MM:SS a./p. m.
    patron = r"ACTUALIZADO AL (\d{2}/\d{2}/\d{4}) A LAS (\d{1,2}:\d{2}:\d{2}) (a\.?m\.?|p\.?m\.?)"
    match = re.search(patron, text)
    if match:
        fecha, hora, ampm = match.groups()
        ampm = ampm.strip().lower().replace(".", "")
        return f"{fecha} {hora} {ampm}"
    return None

def get_id_eleccion():
    candidatos_url = [
        f"{BASE}/presentacion-backend/proceso/proceso-electoral-activo",
        f"{BASE}/presentacion-backend/proceso/activo",
        f"{BASE}/presentacion-backend/procesos/activo",
        f"{BASE}/api/proceso/proceso-electoral-activo",
    ]
    ultimo_error = None
    for url in candidatos_url:
        try:
            data = get(url)
            idv = None
            if isinstance(data, dict):
                idv = data.get("idEleccion") or data.get("id_eleccion") or data.get("id")
            elif isinstance(data, list) and data:
                idv = data[0].get("idEleccion") or data[0].get("id_eleccion") or data[0].get("id")
            if idv:
                print(f" [ok] idEleccion={idv} via {url}")
                return idv
        except Exception as e:
            ultimo_error = e
            print(f" [intento] {url} -> {e}")
    raise RuntimeError(f"No se pudo detectar idEleccion. Ultimo error: {ultimo_error}")

def get_totales(id_eleccion, tipo_filtro="eleccion", ubigeo=None, ambito=None):
    bases = [
        f"{BASE}/presentacion-backend/candidatos/totales",
        f"{BASE}/presentacion-backend/resumen-general/totales",
        f"{BASE}/presentacion-backend/totales/candidatos",
        f"{BASE}/api/candidatos/totales",
    ]
    params = [f"idEleccion={id_eleccion}", f"tipoFiltro={tipo_filtro}"]
    if ubigeo:
        params.append(f"ubigeo={ubigeo}")
    if ambito:
        params.append(f"idAmbitoGeografico={ambito}")
    qs = "?" + "&".join(params)
    for b in bases:
        try:
            return get(b + qs)
        except Exception as e:
            print(f" [intento totales {tipo_filtro}] {b} -> {e}")
    print(f" [warn] sin datos para {tipo_filtro}")
    return None

def parse_candidatos(data):
    if not data:
        return None
    candidatos = data if isinstance(data, list) else data.get("candidatos", [])
    out = {"sanchez": None, "fujimori": None}
    meta = {}
    for c in candidatos:
        nombre = (c.get("nombreAgrupacionPolitica") or c.get("nombre") or "").upper()
        registro = {
            "votos": c.get("totalVotosValidos") or c.get("votos"),
            "pct_validos": c.get("porcentajeVotosValidos") or c.get("pct_votos_validos"),
            "pct_emitidos": c.get("porcentajeVotosEmitidos"),
            "candidato": c.get("nombreCandidato") or c.get("candidato"),
        }
        if "JUNTOS" in nombre or "SANCHEZ" in nombre or "SANCHEZ" in nombre:
            out["sanchez"] = registro
        elif "FUERZA" in nombre or "FUJIMORI" in nombre:
            out["fujimori"] = registro
        if c.get("actasContabilizadas"):
            meta["actas_contabilizadas"] = c.get("actasContabilizadas")
        if c.get("totalActas"):
            meta["total_actas"] = c.get("totalActas")
        if c.get("participacionCiudadana"):
            meta["participacion"] = c.get("participacionCiudadana")
    out["meta"] = meta
    return out

def main():
    # Primera tarea: obtener la fecha/hora ORIGINAL del API
    ts_onpe_original = get_original_timestamp()
    print(f"[API ONPE] Timestamp original: {ts_onpe_original or '(no detectado)'}")

    ahora = datetime.now(PERU_TZ)
    ts_iso = ahora.isoformat()
    ts_legible = ahora.strftime("%d/%m/%Y %H:%M:%S")

    # Si ONPE tiene timestamp original, usarlo; sino, usar el del scrape
    if ts_onpe_original:
        ts_final = ts_onpe_original
    else:
        ts_final = ts_legible

    print(f"[{ts_final}] Iniciando captura ONPE...")

    try:
        id_eleccion = get_id_eleccion()
    except Exception as e:
        print(f" [AVISO] ONPE no entrego datos: {e}")
        print(" [AVISO] Se conserva el data.json actual.")
        return

    print(f" idEleccion = {id_eleccion}")

    nacional = parse_candidatos(get_totales(id_eleccion, "eleccion"))
    lima = parse_candidatos(get_totales(id_eleccion, "ubigeo_nivel_01", ubigeo="15"))
    extranjero = parse_candidatos(get_totales(id_eleccion, "ambito_geografico", ambito="2"))
    peru = parse_candidatos(get_totales(id_eleccion, "ambito_geografico", ambito="1"))

    resto = None
    try:
        if peru and lima and peru.get("sanchez") and lima.get("sanchez"):
            ps, pf = peru["sanchez"], peru["fujimori"]
            ls, lf = lima["sanchez"], lima["fujimori"]
            rs_v = (ps.get("votos") or 0) - (ls.get("votos") or 0)
            rf_v = (pf.get("votos") or 0) - (lf.get("votos") or 0)
            tot = rs_v + rf_v
            if tot > 0:
                resto = {
                    "sanchez": {"votos": rs_v, "pct_validos": round(100*rs_v/tot, 3)},
                    "fujimori": {"votos": rf_v, "pct_validos": round(100*rf_v/tot, 3)},
                }
    except Exception as e:
        print(f" [warn] no se pudo derivar resto: {e}")

    snapshot = {
        "timestamp_iso": ts_iso,
        "timestamp_legible": ts_legible,
        "timestamp_original_onpe": ts_onpe_original,
        "id_eleccion": id_eleccion,
        "nacional": nacional,
        "lima": lima,
        "extranjero": extranjero,
        "peru": peru,
        "resto": resto,
    }

    historial = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                prev = json.load(f)
                historial = prev.get("historial", [])
        except Exception:
            historial = []

    # Evitar duplicados consecutivos con los mismos votos
    skip_historial = False
    if historial and nacional and nacional.get("sanchez") and nacional.get("fujimori"):
        ultimo = historial[-1]
        s_v = nacional["sanchez"].get("votos")
        f_v = nacional["fujimori"].get("votos")
        if (ultimo.get("sanchez_votos") == s_v and ultimo.get("fujimori_votos") == f_v):
            skip_historial = True
            print(" [info] Datos sin cambios respecto al ultimo registro. No se agrega al historial.")

    if nacional and nacional.get("sanchez") and nacional.get("fujimori") and not skip_historial:
        s = nacional["sanchez"]
        fj = nacional["fujimori"]
        brecha = None
        if s.get("votos") is not None and fj.get("votos") is not None:
            brecha = s["votos"] - fj["votos"]
        historial.append({
            "ts": ts_iso,
            "hora": ts_final,
            "actas": nacional.get("meta", {}).get("actas_contabilizadas"),
            "sanchez_votos": s.get("votos"),
            "sanchez_pct": s.get("pct_validos"),
            "fujimori_votos": fj.get("votos"),
            "fujimori_pct": fj.get("pct_validos"),
            "brecha": brecha,
        })
    elif not skip_historial:
        print(" [warn] no se pudo parsear candidatos nacionales")

    salida = {
        "ultima_actualizacion": ts_final,
        "actual": snapshot,
        "historial": historial,
    }
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f" Guardado en {DATA_FILE} ({len(historial)} registros historicos)")
    print(" OK")

if __name__ == "__main__":
    main()
