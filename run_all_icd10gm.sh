#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# run_all_icd10gm.sh
# Bash-Skript zur Ausführung aller Funktionen des ICD-10-GM-Toolkits
#
# VORAUSSETZUNGEN:
# - Python3 (>=3.7) im PATH unter python3
# - icd10gm_tools.py im aktuellen Verzeichnis
#
# USAGE:
#   chmod +x run_all_icd10gm.sh
#   ./run_all_icd10gm.sh
#
set -euo pipefail

# -- Konfiguration -------------------------------------------------------------
ICD_XML="icd10gm2025.xml"         # Pfad zur Ausgangs-ClaML-XML
OLD_XML="icd10gm2024.xml"         # Für Versions-Diff: alte Version
NEW_XML="icd10gm2025.xml"         # Für Versions-Diff: neue Version
OUT_DIR="out"                     # Zielverzeichnis für hierarchischen Export
SINGLE_JSON="icd10gm.json"       # Dateiname für Gesamt-JSON
SQLITE_DB="icd10gm.db"            # Dateiname für SQLite-DB

# -- 1) Hierarchischer JSON-Export ---------------------------------------------
echo "[1/5] Hierarchischer JSON-Export → $OUT_DIR"
python3 icd10gm_tools.py export "$ICD_XML" "$OUT_DIR" --pretty

echo
# -- 2) Kompaktes Gesamt-JSON --------------------------------------------------
echo "[2/5] Einzel-JSON-Export → $SINGLE_JSON"
python3 icd10gm_tools.py single "$ICD_XML" "$SINGLE_JSON" --pretty

echo
# -- 3) SQLite-Export ----------------------------------------------------------
echo "[3/5] SQLite-DB erzeugen → $SQLITE_DB"
python3 icd10gm_tools.py sqlite "$ICD_XML" "$SQLITE_DB"

echo
# -- 4) Strukturvalidierung -----------------------------------------------------
echo "[4/5] Strukturvalidierung"
python3 icd10gm_tools.py validate "$ICD_XML"

echo
# -- 5) Versions-Diff ---------------------------------------------------------
echo "[5/5] Diff zwischen $OLD_XML und $NEW_XML"
python3 icd10gm_tools.py diff "$OLD_XML" "$NEW_XML"

echo
# Alle Befehle abgeschlossen
echo "Fertig."

