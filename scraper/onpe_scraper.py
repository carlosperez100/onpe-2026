#!/usr/bin/env python3
"""
ONPE Scraper v2 - Segunda Vuelta 2026
Motor: Playwright + intercepción de API ONPE + BeautifulSoup (fallback).
Extrae: Nacional, Lima, Extranjero; deriva Resto = Nacional - Lima - Extranjero.
Calcula: proyección OLS univariado + estratificado + Monte Carlo 20 000 sims.
Guarda: docs/data.json con esquema completo.
"""
import json, os, re, math, random
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────
DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "docs")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
PERU_TZ   = timezone(timedelta(hours=-5))
BASE      = "https://resultadosegundavuelta.onpe.gob.pe"
API_BASE  = f"{BASE}/presentacion-backend"

STRAT_PARAMS = {
    "lima":       "tipoFiltro=ubigeo_nivel_01&ubigeo=15",
    "extranjero": "tipoFiltro=ambito_geografico&idAmbitoGeografico=2",
}

# ─── HELPERS ──────────────────────────────────────────────────────────────
def clean_num(v):
    return re.sub(r"[', ]", "", str(v))

def to_int(v):
    try:    return int(clean_num(v))
    except: return 0

def to_float(v):
    try:    return float(clean_num(v))
    except: return 0.0

# ─── PARSE API JSON ───────────────────────────────────────────────────────
def parse_api(data):
    """Parsea JSON de la API de ONPE. Retorna dict con sanchez/fujimori o None."""
    if not data:
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return None

    candidatos = (data.get("candidatos") or data.get("lista") or
                  data.get("data") or data.get("items") or [])
    if not candidatos:
        return None

    r = {
        "pct_avance":           to_float(data.get("porcentajeActas")          or data.get("pctActas")              or 0),
        "actas_contabilizadas": to_int  (data.get("actasContabilizadas")       or data.get("totalActasContabilizadas") or 0),
        "actas_totales":        to_int  (data.get("totalActas")                or 0),
        "votos_validos":        to_int  (data.get("totalVotosValidos")         or 0),
        "sanchez":  None,
        "fujimori": None,
    }

    for c in candidatos:
        nombre = str(c.get("nombre") or c.get("candidato") or "").upper()
        votos  = to_int  (c.get("totalVotosValidos") or c.get("votos") or 0)
        pct    = to_float(c.get("porcentajeVotosValidos") or c.get("pct") or 0)
        if "SANCHEZ" in nombre or "SÁNCHEZ" in nombre:
            r["sanchez"]  = {"votos": votos, "pct_validos": pct}
        elif "FUJIMORI" in nombre or "KEIKO" in nombre:
            r["fujimori"] = {"votos": votos, "pct_validos": pct}

    return r if (r["sanchez"] and r["fujimori"]) else None

# ─── PARSE HTML FALLBACK ──────────────────────────────────────────────────
def parse_html(html):
    """Extrae datos nacionales del HTML renderizado (fallback si la API falla)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    ts_m    = re.search(r"ACTUALIZADO AL\s+(.+?)(?:\n|$)", text, re.IGNORECASE)
    ts_text = ts_m.group(1).strip() if ts_m else None

    # Avance de actas: porcentaje entre 50 y 100 con 3 decimales
    avance = 0.0
    for m in re.finditer(r"(\d{2,3}\.\d{3})\s*%", text):
        v = float(m.group(1))
        if 50 <= v <= 100:
            avance = v
            break

    def find_near_candidate(name_re):
        """Sube el árbol DOM desde el nodo del nombre buscando pct y votos."""
        el = soup.find(string=re.compile(name_re, re.IGNORECASE))
        if not el:
            return 0.0, 0
        node = el.parent
        for _ in range(8):
            if node is None:
                break
            t  = node.get_text()
            # Porcentajes de votos válidos (30-70%)
            ps = [float(m) for m in re.findall(r"(\d{1,2}\.\d{3})\s*%", t)
                  if 30 <= float(m) <= 70]
            # Conteos de votos (>100 000)
            vs = [to_int(m) for m in re.findall(r"([\d][\d',]+)\s*(?:votos)", t)
                  if to_int(m) > 100_000]
            if ps and vs:
                return ps[0], vs[0]
            node = node.parent
        return 0.0, 0

    s_pct,  s_voto = find_near_candidate(r"SANCHEZ|SÁNCHEZ")
    f_pct,  f_voto = find_near_candidate(r"FUJIMORI")

    # Fallback posicional
    if not s_pct:
        pcts = [float(m) for m in re.findall(r"(\d{1,2}\.\d{3})\s*%", text)
                if 30 <= float(m) <= 70]
        if len(pcts) >= 2:
            s_pct, f_pct = pcts[0], pcts[1]

    if not s_voto:
        vts = [to_int(m) for m in re.findall(r"([\d][\d',]+)\s*votos", text)
               if to_int(m) > 100_000]
        if len(vts) >= 2:
            s_voto, f_voto = vts[0], vts[1]

    if not s_pct:
        return None

    return {
        "pct_avance":           avance,
        "actas_contabilizadas": 0,
        "actas_totales":        0,
        "votos_validos":        s_voto + f_voto,
        "sanchez":  {"votos": s_voto, "pct_validos": s_pct},
        "fujimori": {"votos": f_voto, "pct_validos": f_pct},
        "_ts_text": ts_text,
    }

# ─── SCRAPE CON PLAYWRIGHT ───────────────────────────────────────────────
def scrape():
    from playwright.sync_api import sync_playwright

    api_data = {}
    html     = ""

    print("[SCRAPER] Iniciando Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="es-PE",
            timezone_id="America/Lima",
            # Ocultar que somos Playwright
            extra_http_headers={"Accept-Language": "es-PE,es;q=0.9"},
        )
        # Remover la propiedad webdriver que delata automatización
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()

        def on_response(resp):
            if "candidatos/totales" not in resp.url:
                return
            try:
                body = resp.json()
                url  = resp.url
                if "ubigeo=15" in url:
                    api_data["lima"] = body
                    print("  [API-INTERCEPT] Lima capturado")
                elif "idAmbitoGeografico=2" in url:
                    api_data["extranjero"] = body
                    print("  [API-INTERCEPT] Extranjero capturado")
                else:
                    api_data["nacional"] = body
                    print("  [API-INTERCEPT] Nacional capturado")
            except:
                pass

        page.on("response", on_response)

        # Primer intento: página principal con espera larga
        try:
            page.goto(f"{BASE}/main/resumen", timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(12000)  # Más tiempo para que Angular renderice
        except Exception as e:
            print(f"  [WARN] Carga página /resumen: {e}")

        # Si no capturamos nada, probar URL alternativa
        if not api_data:
            try:
                page.goto(f"{BASE}/", timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(10000)
            except Exception as e:
                print(f"  [WARN] Carga página /: {e}")

        # Llamadas directas usando la sesión del navegador (hereda cookies/TLS)
        for strat, params in STRAT_PARAMS.items():
            if strat not in api_data:
                try:
                    resp = page.request.get(
                        f"{API_BASE}/candidatos/totales?{params}", timeout=30000
                    )
                    if resp.ok:
                        body = resp.json()
                        if body:
                            api_data[strat] = body
                            print(f"  [API-DIRECT] {strat} OK")
                        else:
                            print(f"  [API-DIRECT] {strat} respuesta vacía")
                    else:
                        print(f"  [API-DIRECT] {strat} HTTP {resp.status}")
                except Exception as e:
                    print(f"  [API-DIRECT] {strat} error: {e}")

        if "nacional" not in api_data:
            for endpoint in [
                f"{API_BASE}/candidatos/totales",
                f"{API_BASE}/candidatos/totales?tipoFiltro=ambito_geografico&idAmbitoGeografico=1",
            ]:
                try:
                    resp = page.request.get(endpoint, timeout=30000)
                    if resp.ok:
                        body = resp.json()
                        if body:
                            api_data["nacional"] = body
                            print(f"  [API-DIRECT] Nacional OK ({endpoint})")
                            break
                except Exception as e:
                    print(f"  [API-DIRECT] Nacional error ({endpoint}): {e}")

        html = page.content()
        browser.close()

    print(f"[SCRAPER] HTML: {len(html)} chars | API obtenidos: {list(api_data)}")

    nacional = parse_api(api_data.get("nacional")) or parse_html(html)
    lima     = parse_api(api_data.get("lima"))
    extran   = parse_api(api_data.get("extranjero"))
    ts_onpe  = nacional.pop("_ts_text", None) if nacional else None

    return nacional, lima, extran, ts_onpe

# ─── CALCULAR RESTO = "Fuera de Lima" = Nacional − Lima − Extranjero ─────
def calcular_resto(nacional, lima, extran=None):
    """Fuera de Lima = Nacional - Lima - Extranjero (3 estratos independientes)."""
    if not (lima and nacional and nacional.get("votos_validos")):
        return None
    vv_n = nacional["votos_validos"]
    vv_l = lima.get("votos_validos") or 0
    vv_e = (extran.get("votos_validos") or 0) if extran else 0
    vv_r = vv_n - vv_l - vv_e
    if vv_r <= 0:
        return None
    s_n = nacional["sanchez"]["votos"]  or 0
    f_n = nacional["fujimori"]["votos"] or 0
    s_l = (lima["sanchez"]["votos"]    or 0)
    f_l = (lima["fujimori"]["votos"]   or 0)
    s_e = ((extran["sanchez"]["votos"]  or 0) if extran else 0)
    f_e = ((extran["fujimori"]["votos"] or 0) if extran else 0)
    s_r = s_n - s_l - s_e
    f_r = f_n - f_l - f_e
    tot_r = s_r + f_r
    if tot_r <= 0:
        return None
    # Avance derivado: (actas nac - actas Lima - actas Extran) / VV_resto
    a_n  = nacional.get("pct_avance", 0) / 100
    a_l  = lima.get("pct_avance",     0) / 100
    a_e  = (extran.get("pct_avance",  0) / 100) if extran else 0
    num_r = a_n * vv_n - a_l * vv_l - a_e * vv_e
    av_r  = max(0.0, min(100.0, (num_r / vv_r) * 100)) if vv_r else 0.0
    return {
        "sanchez":       {"votos": s_r, "pct_validos": round(100 * s_r / tot_r, 3)},
        "fujimori":      {"votos": f_r, "pct_validos": round(100 * f_r / tot_r, 3)},
        "votos_validos": tot_r,
        "pct_avance":    round(av_r, 3),
    }

# ─── PROYECCIÓN UNIVARIADA ────────────────────────────────────────────────
def proyeccion_univariado(historial):
    pts = [(h["actas"], h["sanchez_pct"]) for h in historial
           if h.get("actas") and h.get("sanchez_pct")]
    if len(pts) < 3:
        return None
    n  = len(pts)
    ma = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - ma) * (p[1] - my) for p in pts)
    sxx = sum((p[0] - ma) ** 2           for p in pts)
    if sxx == 0:
        return None
    b1   = sxy / sxx
    b0   = my - b1 * ma
    y100 = b0 + b1 * 100
    ss_res = sum((p[1] - (b0 + b1 * p[0])) ** 2 for p in pts)
    s2     = ss_res / (n - 2) if n > 2 else 1.0
    se     = math.sqrt(s2) * math.sqrt(1 + 1/n + (100 - ma) ** 2 / sxx)
    ss_tot = sum((p[1] - my) ** 2 for p in pts) or 1
    return {
        "sanchez_pct":  round(y100, 3),
        "fujimori_pct": round(100 - y100, 3),
        "ic_inf":       round(y100 - 2.0 * se, 3),
        "ic_sup":       round(y100 + 2.0 * se, 3),
        "r2":           round(1 - ss_res / ss_tot, 3),
    }

# ─── PROYECCIÓN ESTRATIFICADA + MONTE CARLO ───────────────────────────────
# Modelo 3 estratos: Lima · Fuera de Lima · Internacional
# Lima + FDL + Internacional = 100% del Nacional
def proyeccion_estratificada(lima, resto, extran=None, pesos_ref=None):
    if not (lima and resto):
        return None

    def vv_proj(strat):
        vv = strat.get("votos_validos") or 0
        av = strat.get("pct_avance", 0) / 100
        return vv / av if av > 0 else 0

    vv_l = vv_proj(lima)
    vv_r = vv_proj(resto)
    vv_e = vv_proj(extran) if extran else 0
    total = vv_l + vv_r + vv_e

    if total == 0:
        ref = pesos_ref or {"lima": 34.82, "resto": 63.53, "extranjero": 1.65}
        wL  = ref.get("lima",       34.82) / 100
        wR  = ref.get("resto",      63.53) / 100
        wE  = ref.get("extranjero",  1.65) / 100
        print(f"  [ESTRAT] votos_validos no disponibles — usando pesos referencia: "
              f"Lima {wL*100:.2f}% FDL {wR*100:.2f}% Intl {wE*100:.2f}%")
    else:
        wL = vv_l / total
        wR = vv_r / total
        wE = vv_e / total

    pL = lima["sanchez"]["pct_validos"]  / 100
    pR = resto["sanchez"]["pct_validos"] / 100
    pE = (extran["sanchez"]["pct_validos"] / 100) if extran else pL

    sf_central = wL * pL + wR * pR + wE * pE

    N      = 20_000
    sigma  = {"L": 0.003, "R": 0.004, "E": 0.005}
    count_s = 0
    sims    = []
    for _ in range(N):
        pl = random.gauss(pL, sigma["L"])
        pr = random.gauss(pR, sigma["R"])
        pe = random.gauss(pE, sigma["E"])
        sf = wL * pl + wR * pr + wE * pe
        sims.append(sf)
        if sf > 0.5:
            count_s += 1

    sims.sort()
    return {
        "sanchez_pct":   round(sf_central * 100, 3),
        "fujimori_pct":  round((1 - sf_central) * 100, 3),
        "ic_inf":        round(sims[int(0.025 * N)] * 100, 3),
        "ic_sup":        round(sims[int(0.975 * N)] * 100, 3),
        "prob_sanchez":  round(100 * count_s / N, 1),
        "prob_fujimori": round(100 * (N - count_s) / N, 1),
        "pesos": {
            "lima":       round(wL * 100, 2),
            "resto":      round(wR * 100, 2),
            "extranjero": round(wE * 100, 2),
        },
        "n_sim": N,
    }

# ─── TIMESTAMP ────────────────────────────────────────────────────────────
def build_ts(ts_onpe):
    if ts_onpe:
        m = re.search(
            r"(\d{1,2}/\d{1,2}/\d{4})\s+[Aa]\s+[Ll][Aa][Ss]\s+(\d{1,2}:\d{2}:\d{2})"
            r"\s*(a\.?\s*m\.?|p\.?\s*m\.?)?",
            ts_onpe, re.IGNORECASE,
        )
        if m:
            ampm = (m.group(3) or "").strip().upper()
            return f"{m.group(1)} {m.group(2)}{' ' + ampm if ampm else ''}"
        m2 = re.search(r"(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2}:\d{2})", ts_onpe)
        if m2:
            return f"{m2.group(1)} {m2.group(2)}"
        return ts_onpe.strip()
    return datetime.now(PERU_TZ).strftime("%d/%m/%Y %H:%M:%S")

# ─── CARGAR / GUARDAR ─────────────────────────────────────────────────────
def load_existing():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            # Filtrar entradas de historial inválidas (votos=0 o sin ts)
            hist = [h for h in d.get("historial", [])
                    if h.get("sanchez_pct") or h.get("sanchez_votos")]
            d["historial"] = hist
            return d
        except:
            pass
    return {
        "meta": {"ultima_actualizacion": None, "pct_avance": 0,
                 "actas_contabilizadas": 0, "actas_totales": 0, "fuente": None},
        "nacional": None, "lima": None, "resto": None, "extranjero": None,
        "proyeccion": None, "historial": [],
    }

def save_data(nacional, lima, resto, extran, ts_onpe):
    existing  = load_existing()
    historial = existing.get("historial", [])
    ts        = build_ts(ts_onpe)

    s_votos  = nacional["sanchez"]["votos"]
    f_votos  = nacional["fujimori"]["votos"]
    s_pct    = nacional["sanchez"]["pct_validos"]
    f_pct    = nacional["fujimori"]["pct_validos"]
    avance   = nacional.get("pct_avance", 0)

    nuevo = True
    if historial and s_votos and f_votos:
        ult = historial[-1]
        if (ult.get("sanchez_votos") == s_votos and
                ult.get("fujimori_votos") == f_votos):
            nuevo = False
            print(f"  [HIST] Sin cambios desde {ult.get('hora') or ult.get('ts')}")

    if nuevo:
        historial.append({
            "ts":             datetime.now(PERU_TZ).strftime("%Y-%m-%dT%H:%M:%S"),
            "hora":           datetime.now(PERU_TZ).strftime("%d/%m %H:%M"),
            "actas":          round(float(avance), 3),
            "sanchez_votos":  s_votos,
            "sanchez_pct":    s_pct,
            "fujimori_votos": f_votos,
            "fujimori_pct":   f_pct,
            "brecha":         s_votos - f_votos,
        })
        print(f"  [HIST] Nuevo snapshot (total: {len(historial)})")

    # Resolver estratos: datos frescos o último valor guardado
    lima_f   = lima   or existing.get("lima")
    resto_f  = resto  or existing.get("resto")
    extran_f = extran or existing.get("extranjero")
    if lima   is None and lima_f:   print("  [ESTRAT] Lima: usando datos preservados")
    if extran is None and extran_f: print("  [ESTRAT] Extranjero: usando datos preservados")

    # Pesos de referencia del último cómputo estratificado (3 estratos)
    ex_pesos = None
    try:
        ex_pesos = existing["proyeccion"]["estratificado"]["pesos"]
    except (KeyError, TypeError):
        pass
    # Asegurar que ex_pesos tiene clave "extranjero"
    if ex_pesos and "extranjero" not in ex_pesos:
        ex_pesos = None

    proy_univ   = proyeccion_univariado(historial)
    # Modelo 3 estratos: Lima · Fuera de Lima · Internacional
    proy_estrat = proyeccion_estratificada(lima_f, resto_f, extran_f, ex_pesos)

    out = {
        "meta": {
            "ultima_actualizacion":  ts,
            "pct_avance":            round(float(avance), 3),
            "actas_contabilizadas":  nacional.get("actas_contabilizadas") or existing.get("meta", {}).get("actas_contabilizadas", 0),
            "actas_totales":         nacional.get("actas_totales")        or existing.get("meta", {}).get("actas_totales",        0),
            "fuente":                "onpe_html" if ts_onpe else "local_time",
        },
        "nacional": {**nacional,
            "actas_contabilizadas": nacional.get("actas_contabilizadas") or existing.get("nacional", {}).get("actas_contabilizadas", 0),
            "actas_totales":        nacional.get("actas_totales")        or existing.get("nacional", {}).get("actas_totales",        0),
        },
        "lima":       lima_f,
        "resto":      resto_f,
        "extranjero": extran_f,
        "proyeccion": {
            "univariado":    proy_univ,
            "estratificado": proy_estrat,
        },
        "historial": historial,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[GUARDADO] {DATA_FILE}")

# ─── MAIN ─────────────────────────────────────────────────────────────────
def main():
    nacional, lima, extran, ts_onpe = scrape()
    if nacional is None:
        print("[ERROR] No se pudo extraer datos de ONPE. Abortando.")
        return
    resto = calcular_resto(nacional, lima, extran)

    print(f"\n[NACIONAL] Sánchez:  {nacional['sanchez']['votos']:,} ({nacional['sanchez']['pct_validos']}%)")
    print(f"[NACIONAL] Fujimori: {nacional['fujimori']['votos']:,} ({nacional['fujimori']['pct_validos']}%)")
    avance = nacional.get("pct_avance", 0)
    print(f"[NACIONAL] Actas:    {float(avance):.3f}%")
    for tag, strat in [("LIMA   ", lima), ("EXTRAN ", extran), ("RESTO  ", resto)]:
        if strat:
            print(f"[{tag}] S {strat['sanchez']['pct_validos']}% "
                  f"F {strat['fujimori']['pct_validos']}% "
                  f"Avance {strat.get('pct_avance', '?')}%")

    save_data(nacional, lima, resto, extran, ts_onpe)
    print("[SCRAPER] Finalizado OK.")

if __name__ == "__main__":
    main()
