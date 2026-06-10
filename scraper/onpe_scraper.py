#!/usr/bin/env python3
"""
ONPE Scraper - Segunda Vuelta 2026
Extracts national totals from ONPE using Playwright (headless Chrome).
Saves to docs/data.json for the HTML dashboard to consume.
Includes original date/time from ONPE API.
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

data_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
DATA_FILE = os.path.join(data_dir, "data.json")
PERU_TZ = timezone(timedelta(hours=-5))


def scrape_onpe():
    """Scrapes ONPE results page using Playwright headless browser."""
    from playwright.sync_api import sync_playwright
    
    BASE = "https://resultadosegundavuelta.onpe.gob.pe"
    URL = f"{BASE}/main/resumen"
    
    print("[SCRAPER] Iniciando scrape con Playwright...")
    
    data = None
    timestamp_onpe = None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)  # wait for JS to fully render
            
            # Extract timestamp
            ts_el = page.query_selector("text=ACTUALIZADO AL")
            if ts_el:
                ts_text = ts_el.text_content().strip()
                timestamp_onpe = ts_text
                print(f" [API ONPE] Timestamp original: {timestamp_onpe}")
            
            # Extract advance percentage
            pct_el = page.query_selector("text=/\\d+\\.\\d+ \\%/")
            pct_avance = "0"
            if pct_el:
                pct_text = pct_el.text_content().strip()
                m = re.search(r"(\d+\.\d+)\\s*\\%", pct_text)
                if m:
                    pct_avance = m.group(1)
            
            # Extract total actas
            actas_el = page.query_selector("text=/Total de actas:/")
            total_actas = 0
            if actas_el:
                actas_text = actas_el.text_content().strip()
                m = re.search(r"Total de actas:\\s*([\\d,]+)", actas_text)
                if m:
                    total_actas = int(m.group(1).replace(",", ""))
            
            # Extract Sanchez data
            sanchez_votos = 0
            sanchez_pct = 0
            s_pct_el = page.query_selector("text=/5\\d\\.\\d+\\s*\\%/")
            if s_pct_el:
                s_text = s_pct_el.text_content().strip()
                m = re.search(r"(\d+\.\d+)", s_text)
                if m:
                    sanchez_pct = float(m.group(1))
            s_votos_el = page.query_selector("text=/ROBERTO.*votos/i")
            if s_votos_el:
                s_text = s_votos_el.text_content().strip()
                m = re.search(r"(\\d[\\d'\\u2019,]+)\\s*votos", s_text, re.DOTALL)
                if m:
                    num_str = m.group(1).replace("\'", "").replace(",", "")
                    sanchez_votos = int(re.sub(r"[^0-9]", "", num_str))
            
            # Extract Fujimori data
            fujimori_votos = 0
            fujimori_pct = 0
            f_pct_el = page.query_selector("text=/4\\d\\.\\d+\\s*\\%/")
            if f_pct_el:
                f_text = f_pct_el.text_content().strip()
                m = re.search(r"(\d+\.\d+)", f_text)
                if m:
                    fujimori_pct = float(m.group(1))
            f_votos_el = page.query_selector("text=/KEIKO.*votos/i")
            if f_votos_el:
                f_text = f_votos_el.text_content().strip()
                m = re.search(r"(\\d[\\d'\\u2019,]+)\\s*votos", f_text, re.DOTALL)
                if m:
                    num_str = m.group(1).replace("\'", "").replace(",", "")
                    fujimori_votos = int(re.sub(r"[^0-9]", "", num_str))
            
            print(f" [NACIONAL] Sanchez: {sanchez_votos} ({sanchez_pct}%)")
            print(f" [NACIONAL] Fujimori: {fujimori_votos} ({fujimori_pct}%)")
            print(f" [NACIONAL] Actas: {total_actas} ({pct_avance}%)")
            
            data = {
                "sanchez": {"votos": sanchez_votos, "pct_validos": sanchez_pct},
                "fujimori": {"votos": fujimori_votos, "pct_validos": fujimori_pct},
                "meta": {"total_actas": total_actas, "pct_avance": pct_avance},
            }
            
        finally:
            browser.close()
    
    return data, timestamp_onpe


def build_timestamp(ts_onpe):
    """Builds the final timestamp for data.json."""
    if ts_onpe:
        # Try to normalize: "ACTUALIZADO AL DD/MM/YYYY A LAS HH:MM:SS a. m."
        m = re.search(r"ACTUALIZADO AL (\\d+/\\d+/\\d{4}) A LAS (\\d+:\\d+:\\d+)\\s+(a\\.?m\\.?|p\\.?m\\.?|am|pm)", ts_onpe)
        if m:
            fecha, hora, ampm = m.groups()
            return f"{fecha} {hora} {ampm.strip()}"
        return ts_onpe.strip().replace("ACTUALIZADO AL ", "")
    ahora = datetime.now(PERU_TZ)
    return ahora.strftime("%d/%m/%Y %H:%M:%S")


def load_existing():
    """Loads existing data.json or returns base structure."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "nacional": None, "peru": None, "lima": None, "extranjero": None,
        "historial": [], "meta": {"ultima_actualizacion": None, "fuente": None},
        "snapshots": [],
    }


def save_data(nacional_data, ts_onpe):
    """Saves data.json with history, deduplication."""
    existing = load_existing()
    historial = existing.get("historial", [])
    snapshots = existing.get("snapshots", [])
    
    ts_final = build_timestamp(ts_onpe)
    
    sanchez_votos = nacional_data["sanchez"]["votos"]
    fujimori_votos = nacional_data["fujimori"]["votos"]
    
    nuevo = True
    if historial and sanchez_votos and fujimori_votos:
        ultimo = historial[-1]
        if (ultimo.get("sanchez_votos") == sanchez_votos and
            ultimo.get("fujimori_votos") == fujimori_votos):
            nuevo = False
            print(f" [HISTORIAL] Sin cambios: {ultimo.get('timestamp')}")
    
    if nuevo:
        snapshot = {
            "nacional": nacional_data,
            "peru": existing.get("peru"),
            "lima": existing.get("lima"),
            "extranjero": existing.get("extranjero"),
            "timestamp_iso": ts_final,
        }
        historial.append({
            "timestamp": ts_final,
            "sanchez_votos": sanchez_votos,
            "fujimori_votos": fujimori_votos,
        })
        snapshots.append(snapshot)
        print(f" [HISTORIAL] Nuevo snapshot guardado ({len(historial)} en historial)")
    
    out = {
        "nacional": nacional_data,
        "peru": existing.get("peru"),
        "lima": existing.get("lima"),
        "extranjero": existing.get("extranjero"),
        "historial": historial,
        "meta": {"ultima_actualizacion": ts_final, "fuente": ts_onpe and "onpe_html" or "local_time"},
        "snapshots": snapshots,
    }
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    if not nuevo:
        print(" [WARN] No se escribieron cambios en data.json")


def main():
    nacional, ts_onpe = scrape_onpe()
    
    if nacional is None:
        print(" [ERROR] No se pudo extraer datos de ONPE")
        return
    
    save_data(nacional, ts_onpe)
    print("[SCRAPER] Finalizado.")


if __name__ == "__main__":
    main()
