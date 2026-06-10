#!/usr/bin/env python3
"""
ONPE Scraper - Segunda Vuelta 2026
Extracts national totals from ONPE using Playwright + BeautifulSoup.
Saves to docs/data.json for the HTML dashboard to consume.
Includes original date/time from ONPE API.
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

data_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
DATA_FILE = os.path.join(data_dir, "data.json")
PERU_TZ = timezone(timedelta(hours=-5))

def scrape_onpe():
    """Scrapes ONPE results page using Playwright headless + BeautifulSoup."""
    from playwright.sync_api import sync_playwright
    
    BASE = "https://resultadosegundavuelta.onpe.gob.pe"
    URL = f"{BASE}/main/resumen"
    
    print("[SCRAPER] Iniciando scrape con Playwright...")
    
    data = None
    timestamp_onpe = None
    html = ""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(8000)  # wait for JS to fully render
            html = page.content()
        finally:
            browser.close()
    
    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    
    print("[PARSER] HTML recibido, buscando datos...")
    print(f"[PARSER] Longitud HTML: {len(html)} chars")
    
    # 1. Extract timestamp - look for "ACTUALIZADO AL"
    for el in soup.find_all(string=True):
        if "ACTUALIZADO AL" in str(el).upper():
            ts_text = str(el).strip()
            timestamp_onpe = ts_text
            print(f" [API ONPE] Timestamp original: {timestamp_onpe}")
            break
    
    # 2. Extract advance percentage - look for pattern like "X.X %"
    pct_avance = "0"
    text = soup.get_text()
    m = re.search(r"(\d+\.\d+)\s*%", text)
    if m:
        pct_avance = m.group(1)
    
    # 3. Extract total actas
    total_actas = 0
    m = re.search(r"Total de actas:\s*([\d,]+)", text)
    if m:
        total_actas = int(m.group(1).replace(",", ""))
    
    # 4. Extract Sanchez votes and percentage
    sanchez_votos = 0
    sanchez_pct = 0.0
    
    # Look for Sanchez percentage in text (should be ~5X.X%)
    # ONPE shows it as percentage like 50.X%
    for el in soup.find_all(string=True):
        s = str(el).strip()
        m_pct = re.search(r"(5\d\.\d+)\s*%", s)
        if m_pct:
            sanchez_pct = float(m_pct.group(1))
            break
    
    # Look for Sanchez votes
    for el in soup.find_all(string=True):
        s = str(el)
        if "ROBERTO" in s.upper() or "SANCHEZ" in s.upper():
            m_v = re.search(r"(\d[\d\',\u2019]+(?:\.\d+)?)", s)
            if m_v:
                num_str = m_v.group(1).replace("'", "").replace(",", "").replace("\u2019", "")
                sanchez_votos = int(re.sub(r"[^0-9]", "", num_str))
                break
    
    # 5. Extract Fujimori votes and percentage  
    fujimori_votos = 0
    fujimori_pct = 0.0
    
    for el in soup.find_all(string=True):
        s = str(el).strip()
        m_pct = re.search(r"(4\d\.\d+)\s*%", s)
        if m_pct:
            fujimori_pct = float(m_pct.group(1))
            break
    
    for el in soup.find_all(string=True):
        s = str(el)
        if "KEIKO" in s.upper() or "FUJIMORI" in s.upper():
            m_v = re.search(r"(\d[\d\',\u2019]+(?:\.\d+)?)", s)
            if m_v:
                num_str = m_v.group(1).replace("'", "").replace(",", "").replace("\u2019", "")
                fujimori_votos = int(re.sub(r"[^0-9]", "", num_str))
                break
    
    print(f" [NACIONAL] Sanchez: {sanchez_votos} ({sanchez_pct}%)")
    print(f" [NACIONAL] Fujimori: {fujimori_votos} ({fujimori_pct}%)")
    print(f" [NACIONAL] Actas: {total_actas} ({pct_avance}%)")
    
    data = {
        "sanchez": {"votos": sanchez_votos, "pct_validos": sanchez_pct},
        "fujimori": {"votos": fujimori_votos, "pct_validos": fujimori_pct},
        "meta": {"total_actas": total_actas, "pct_avance": pct_avance},
    }
    
    return data, timestamp_onpe

def build_timestamp(ts_onpe):
    """Builds the final timestamp for data.json."""
    if ts_onpe:
        m = re.search(r"ACTUALIZADO AL (\d+/\d+/\d{4}) A LAS (\d+:\d+:\d+)\s*(a\.?\s*m\.?|p\.?\s*m\.?)", ts_onpe, re.IGNORECASE)
        if m:
            fecha, hora, ampm = m.groups()
            return f"{fecha} {hora} {ampm.strip().upper()}"
        m2 = re.search(r"(\d+/\d+/\d{4}).*?(\d+:\d+:\d+)", ts_onpe)
        if m2:
            return f"{m2.group(1)} {m2.group(2)}"
        return ts_onpe.strip()
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
