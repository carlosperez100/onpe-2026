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

def get_text_by_regex(soup, pattern):
    """Finds text in soup that matches a regex pattern."""
    matches = soup.find_all(string=re.compile(pattern))
    for m in matches:
        return str(m).strip()
    return None

def extract_number(text, pattern):
    """Extracts a number from text matching pattern, returns int or float."""
    m = re.search(pattern, text)
    if m:
        val = m.group(1).replace("'", "").replace(",", "").replace(".", "")
        return int(val) if re.match(r"^\d+$", val) else float(val)
    return 0

def extract_decimal(text, pattern):
    """Extracts a decimal number from text matching pattern."""
    m = re.search(pattern, text)
    if m:
        return float(m.group(1))
    return 0.0

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
            page.wait_for_timeout(10000)
            html = page.content()
        finally:
            browser.close()
    
    soup = BeautifulSoup(html, "html.parser")
    text_all = soup.get_text(separator="\n")
    
    print("[PARSER] HTML recibido, buscando datos...")
    print(f"[PARSER] Longitud HTML: {len(html)} chars")
    
    # 1. Timestamp: ACTUALIZADO AL
    ts_text = get_text_by_regex(soup, r"ACTUALIZADO AL")
    if ts_text:
        timestamp_onpe = ts_text
        print(f" [ONPE] Timestamp: {timestamp_onpe}")
    
    # 2. % actas (e.g. "97.910 %")
    pct_text = get_text_by_regex(soup, r"\d+\.\d{3}\s+%")
    pct_avance = "0"
    if pct_text:
        m = re.search(r"(\d+\.\d{3})\s*%", pct_text)
        if m:
            pct_avance = m.group(1)
        print(f" [ONPE] Avance actas: {pct_avance}%")
    
    # 3. Total actas
    actas_text = get_text_by_regex(soup, r"Total de actas")
    total_actas = 0
    if actas_text:
        m = re.search(r"Total de actas:\s*([\d,]+)", actas_text)
        if m:
            total_actas = int(m.group(1).replace(",", ""))
        print(f" [ONPE] Total actas: {total_actas}")
    
    # 4. Sanchez: nombre y votos
    sanchez_votos = 0
    sanchez_pct = 0.0
    s_nome = get_text_by_regex(soup, r"ROBERTO.*SANCHEZ")
    if s_nome:
        print(f" [ONPE] Sanchez nombre: {s_nome}")
    s_voto = get_text_by_regex(soup, r"\d[\d\',]+\s+votos")
    if s_voto:
        sanchez_votos = extract_number(s_voto, r"(\d[\d\',]+)")
        print(f" [ONPE] Sanchez votos texto: {s_voto}")
    # Buscar porcentaje de Sanchez ( empieza con 5X.XXX%)
    for el in soup.find_all(string=True):
        s = str(el).strip()
        m = re.search(r"(5[0-9]\.\d{3})\s*%", s)
        if m:
            sanchez_pct = float(m.group(1))
            print(f" [ONPE] Sanchez pct: {sanchez_pct}%")
            break
    
    # 5. Fujimori: nombre y votos
    fujimori_votos = 0
    fujimori_pct = 0.0
    f_nome = get_text_by_regex(soup, r"KEIKO.*FUJIMORI")
    if f_nome:
        print(f" [ONPE] Fujimori nombre: {f_nome}")
    # Fujimori votos: el texto "X'XXX,XXX votos" seguido de Fujimori
    f_voto = get_text_by_regex(soup, r"\d[\d\',]+\s+votos")
    # Ya extrajimos el primero como Sanchez, necesitamos el segundo que es Fujimori
    votos_all = soup.find_all(string=re.compile(r"\d[\d\',]+\s+votos"))
    if len(votos_all) >= 2:
        f_voto = str(votos_all[1]).strip()
        fujimori_votos = extract_number(f_voto, r"(\d[\d\',]+)")
        print(f" [ONPE] Fujimori votos texto: {f_voto}")
    elif len(votos_all) == 1:
        # Solo hay un match, es el segundo candidato
        f_voto = str(votos_all[0]).strip()
        fujimori_votos = extract_number(f_voto, r"(\d[\d\',]+)")
        print(f" [ONPE] Fujimori votos texto: {f_voto}")
    # Porcentaje Fujimori (empieza con 4X.XXX%)
    for el in soup.find_all(string=True):
        s = str(el).strip()
        m = re.search(r"(4[0-9]\.\d{3})\s*%", s)
        if m:
            fujimori_pct = float(m.group(1))
            print(f" [ONPE] Fujimori pct: {fujimori_pct}%")
            break
    
    print(f"\n [NACIONAL] Sanchez: {sanchez_votos} ({sanchez_pct}%)")
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
    """Saves data.json with history and deduplication."""
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
        hist_entry = {
            "timestamp": ts_final,
            "sanchez_votos": sanchez_votos,
            "fujimori_votos": fujimori_votos,
        }
        historial.append(hist_entry)
        snapshot = {
            "nacional": nacional_data,
            "peru": existing.get("peru"),
            "lima": existing.get("lima"),
            "extranjero": existing.get("extranjero"),
            "timestamp_iso": ts_final,
        }
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
