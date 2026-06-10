#!/usr/bin/env python3
"""
ONPE Scraper - Segunda Vuelta 2026
Extrae totales nacionales, Lima y extranjero desde la API interna de ONPE.
Requiere curl_cffi con impersonate de Chrome (ONPE bloquea requests normales).
Guarda en docs/data.json para que el dashboard HTML lo consuma.
"""
import json
import os
from datetime import datetime, timezone, timedelta

from curl_cffi import requests as cffi

BASE = "https://resultadosegundavuelta.onpe.gob.pe"
IMPERSONATE = "chrome124"
TIMEOUT = 30

# Zona horaria Perú (UTC-5)
PERU_TZ = timezone(timedelta(hours=-5))

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")


def get(url):
    """GET con fingerprint de Chrome. Devuelve el payload dentro de 'data'."""
    r = cffi.get(url, impersonate=IMPERSONATE, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    return body.get("data", body)


def get_id_eleccion():
    """Detecta automáticamente la elección activa (segunda vuelta)."""
    url = f"{BASE}/presentacion-backend/proceso/proceso-electoral-activo"
    data = get(url)
    # El payload puede ser dict con idEleccion o lista
    if isinstance(data, dict):
        return data.get("idEleccion") or data.get("id_eleccion")
    if isinstance(data, list) and data:
        return data[0].get("idEleccion") or data[0].get("id_eleccion")
    raise RuntimeError("No se pudo detectar idEleccion")


def get_totales(id_eleccion, tipo_filtro="eleccion", ubigeo=None, ambito=None):
    """
    Obtiene totales por candidato segun filtro geografico.
    tipo_filtro: eleccion | ubigeo_nivel_01 | ambito_geografico
    """
    url = f"{BASE}/presentacion-backend/candidatos/totales"
    params = [f"idEleccion={id_eleccion}", f"tipoFiltro={tipo_filtro}"]
    if ubigeo:
        params.append(f"ubigeo={ubigeo}")
    if ambito:
        params.append(f"idAmbitoGeografico={ambito}")
    full_url = url + "?" + "&".join(params)
    try:
        return get(full_url)
    except Exception as e:
        print(f"  [warn] fallo totales {tipo_filtro}: {e}")
        return None


def parse_candidatos(data):
    """Normaliza la respuesta de candidatos a {sanchez, fujimori, meta}."""
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
        if "JUNTOS" in nombre or "SANCHEZ" in nombre or "SÁNCHEZ" in nombre:
            out["sanchez"] = registro
        elif "FUERZA" in nombre or "FUJIMORI" in nombre:
            out["fujimori"] = registro
        # Metadatos comunes
        if c.get("actasContabilizadas"):
            meta["actas_contabilizadas"] = c.get("actasContabilizadas")
        if c.get("totalActas"):
            meta["total_actas"] = c.get("totalActas")
        if c.get("participacionCiudadana"):
            meta["participacion"] = c.get("participacionCiudadana")
    out["meta"] = meta
    return out


def main():
    ahora = datetime.now(PERU_TZ)
    ts_iso = ahora.isoformat()
    ts_legible = ahora.strftime("%d/%m/%Y %H:%M:%S")

    print(f"[{ts_legible}] Iniciando captura ONPE...")
    id_eleccion = get_id_eleccion()
    print(f"  idEleccion = {id_eleccion}")

    # Nacional
    nacional = parse_candidatos(get_totales(id_eleccion, "eleccion"))
    # Lima (ubigeo departamento = 15)
    lima = parse_candidatos(get_totales(id_eleccion, "ubigeo_nivel_01", ubigeo="15"))
    # Extranjero (ambito geografico = 2)
    extranjero = parse_candidatos(get_totales(id_eleccion, "ambito_geografico", ambito="2"))
    # Peru (ambito = 1) y Lima -> derivar "resto" (fuera de Lima)
    peru = parse_candidatos(get_totales(id_eleccion, "ambito_geografico", ambito="1"))

    # Estimar "resto" = Peru nacional - Lima (en votos), para el modelo estratificado
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
        print(f"  [warn] no se pudo derivar resto: {e}")

    snapshot = {
        "timestamp_iso": ts_iso,
        "timestamp_legible": ts_legible,
        "id_eleccion": id_eleccion,
        "nacional": nacional,
        "lima": lima,
        "extranjero": extranjero,
        "peru": peru,
        "resto": resto,
    }

    # Cargar historial existente
    historial = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                prev = json.load(f)
                historial = prev.get("historial", [])
        except Exception:
            historial = []

    # Agregar snapshot al historial (nacional resumido)
    if nacional and nacional.get("sanchez") and nacional.get("fujimori"):
        s = nacional["sanchez"]
        fj = nacional["fujimori"]
        brecha = None
        if s.get("votos") is not None and fj.get("votos") is not None:
            brecha = s["votos"] - fj["votos"]
        historial.append({
            "ts": ts_iso,
            "hora": ts_legible,
            "actas": nacional.get("meta", {}).get("actas_contabilizadas"),
            "sanchez_votos": s.get("votos"),
            "sanchez_pct": s.get("pct_validos"),
            "fujimori_votos": fj.get("votos"),
            "fujimori_pct": fj.get("pct_validos"),
            "brecha": brecha,
        })

    salida = {
        "ultima_actualizacion": ts_legible,
        "actual": snapshot,
        "historial": historial,
    }

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"  Guardado en {DATA_FILE} ({len(historial)} registros historicos)")
    print("  OK")


if __name__ == "__main__":
    main()
