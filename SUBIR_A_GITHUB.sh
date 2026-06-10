#!/bin/bash
# ============================================================
#  SUBIR PROYECTO ONPE A GITHUB · Git Bash
#  Autor: asistido para Carlos Pérez Pérez
# ============================================================
#  INSTRUCCIONES:
#  1. Descomprime ONPE_Cloud_Sistema.zip (tendrás la carpeta onpe-cloud)
#  2. Abre Git Bash DENTRO de la carpeta onpe-cloud
#     (clic derecho dentro de la carpeta -> "Git Bash Here")
#  3. Copia y pega TODO este bloque en Git Bash y presiona Enter
# ============================================================

# --- CONFIGURACIÓN (ya puesta para tu usuario) ---
GH_USER="carlosperez100"
REPO="onpe-2026"

echo "==> Verificando que estás en la carpeta correcta..."
if [ ! -d "docs" ] || [ ! -d "scraper" ]; then
  echo "❌ ERROR: no veo las carpetas docs/ y scraper/."
  echo "   Abre Git Bash DENTRO de la carpeta onpe-cloud y repite."
  exit 1
fi
echo "✓ Carpeta correcta."

# --- Inicializar git (si no existe) ---
if [ ! -d ".git" ]; then
  echo "==> Inicializando repositorio git..."
  git init
  git branch -M main
fi

# --- Conectar con tu repo de GitHub ---
echo "==> Conectando con GitHub ($GH_USER/$REPO)..."
git remote remove origin 2>/dev/null
git remote add origin "https://github.com/$GH_USER/$REPO.git"

# --- Traer lo que ya está en GitHub para no chocar ---
echo "==> Sincronizando con lo que ya subiste..."
git fetch origin main 2>/dev/null
git reset --soft origin/main 2>/dev/null

# --- Agregar TODOS los archivos (incluida la carpeta .github) ---
echo "==> Agregando archivos (incluye .github/workflows)..."
git add -A
git add -f .github/workflows/scraper.yml

# --- Confirmar y subir ---
echo "==> Creando commit..."
git commit -m "Sistema completo: scraper 15min + dashboard TV + modelo GEMSES + ETA"

echo "==> Subiendo a GitHub..."
git push -u origin main

echo ""
echo "============================================================"
echo "✅ LISTO. Si te pidió usuario/contraseña, usa tu usuario de"
echo "   GitHub y un TOKEN (no la contraseña normal)."
echo ""
echo "   Ahora ve a tu repo -> pestaña ACTIONS -> habilita los"
echo "   workflows -> Run workflow para probar el scraper."
echo ""
echo "   Tu dashboard: https://$GH_USER.github.io/$REPO/"
echo "============================================================"
