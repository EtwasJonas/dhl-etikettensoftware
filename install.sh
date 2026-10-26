#!/usr/bin/env bash
# install.sh – Ein-Klick-Installer für die DHL-Etikettensoftware
# Ziel: Ubuntu / Debian / Linux Mint (apt + systemd + CUPS)
set -euo pipefail

APP_DIR="$HOME/.local/share/dhl-label"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/dhl-label"
CONFIG_FILE="$CONFIG_DIR/config.conf"
SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- Voraussetzungen
command -v apt-get >/dev/null 2>&1 || die "Diese Installation unterstützt Debian/Ubuntu/Mint (apt)."
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "Bitte sudo installieren oder als root ausführen."
  SUDO="sudo"
fi

info "Systempakete installieren (python3-venv, cups-client)…"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3-venv python3-pip cups-client

# ---------------------------------------------------------------- Drucker wählen
info "Verfügbare Drucker (USB und WLAN/Netzwerk):"
lpstat -p 2>/dev/null || die "Keine Drucker gefunden – ist der Vretti (USB oder WLAN) mit dem PC verbunden und in CUPS eingerichtet?"
mapfile -t PRINTERS < <(lpstat -p 2>/dev/null | awk '{print $2}')
mapfile -t PRINTER_STATE < <(lpstat -p 2>/dev/null | awk '{$1="";$2="";print;sub(/^ +/,"")}')
[ "${#PRINTERS[@]}" -ge 1 ] || die "Keine Drucker in CUPS gefunden."

if [ "${#PRINTERS[@]}" -eq 1 ]; then
  PRINTER="${PRINTERS[0]}"
  info "Drucker automatisch gewählt: $PRINTER (${PRINTER_STATE[0]})"
else
  echo "Welchen Drucker soll die Versandmarke nutzen? (USB oder WLAN)"
  i=1
  for p in "${PRINTERS[@]}"; do
    echo "  $i) $p  –  ${PRINTER_STATE[$((i-1))]}"
    i=$((i+1))
  done
  while true; do
    read -r -p "Nummer [1]: " SEL
    SEL="${SEL:-1}"
    if [[ "$SEL" =~ ^[0-9]+$ ]] && [ "$SEL" -ge 1 ] && [ "$SEL" -le "${#PRINTERS[@]}" ]; then
      break
    fi
    echo "Ungültige Eingabe, bitte Zahl 1-${#PRINTERS[@]} eingeben."
  done
  PRINTER="${PRINTERS[$((SEL-1))]}"
fi

# Status prüfen (funktioniert für USB- und WLAN-Drucker gleich)
PSTATE="$(lpstat -p "$PRINTER" 2>/dev/null || true)"
case "$PSTATE" in
  *disabled*|*deaktiviert*|*"nicht bereit"*)
    warn "Drucker '$PRINTER' ist deaktiviert/nicht bereit: $PSTATE"
    warn "Aktivieren mit:  cupsenable '$PRINTER'   (oder Systemeinstellungen › Drucker)"
    ;;
esac

# ---------------------------------------------------------------- Mediengröße wählen
info "Verfügbare Mediengrößen für '$PRINTER':"
MEDIA_LIST="$(lpoptions -p "$PRINTER" -l 2>/dev/null | grep -iE 'pagesize|^media' | head -n1 || true)"
[ -n "$MEDIA_LIST" ] || die "Konnte Mediengrößen nicht lesen (lpoptions)."
echo "  $MEDIA_LIST"
DEFAULT_MEDIA="$(echo "$MEDIA_LIST" | sed 's/.*://' | tr ' ' '\n' | grep '^\*' | tr -d '*' | head -n1 || true)"
DEFAULT_MEDIA="${DEFAULT_MEDIA:-4x6}"
read -r -p "Mediengröße eingeben [$DEFAULT_MEDIA]: " MEDIA
MEDIA="${MEDIA:-$DEFAULT_MEDIA}"
info "Gewählt: Drucker='$PRINTER' Medium='$MEDIA'"

# ---------------------------------------------------------------- Watch-Modus wählen
echo ""
echo "Wie sollen PDFs erkannt werden?"
echo "  1) Downloads-Ordner überwachen – druckt nur PDFs mit Namensfilter (z.B. 'versand', 'dhl', 'paket')"
echo "  2) Eigener Watch-Ordner – alle neuen PDFs dort werden gedruckt"
read -r -p "Auswahl [1]: " WMODE
WMODE="${WMODE:-1}"

WATCH_MODE="downloads"
WATCH_DIR="$HOME/Downloads"
FILENAME_PATTERN="versand|dhl|paket"
if [ "$WMODE" = "2" ]; then
  WATCH_MODE="custom"
  read -r -p "Pfad des Watch-Ordners [$HOME/DHL]: " WATCH_DIR
  WATCH_DIR="${WATCH_DIR:-$HOME/DHL}"
  FILENAME_PATTERN=""
  mkdir -p "$WATCH_DIR"
fi

# ---------------------------------------------------------------- Crop-Einstellungen
echo ""
read -r -p "Wo sitzt die Marke im A4-PDF? (o=obere Hälfte, u=untere Hälfte) [o]: " SIDE
SIDE="${SIDE:-o}"
CROP_SIDE="top"
[ "$SIDE" = "u" ] && CROP_SIDE="bottom"

# ---------------------------------------------------------------- Dateien installieren
info "Installiere nach $APP_DIR …"
mkdir -p "$APP_DIR" "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR" "$DESKTOP_DIR"
cp "$SRC_DIR/dhl_label.py" "$APP_DIR/"
cp "$SRC_DIR/dhl-label.service" "$SYSTEMD_DIR/"

info "Python-virtualenv anlegen und pypdf installieren…"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet pypdf

# Kommandozeilen-Wrapper
cat > "$BIN_DIR/dhl-label" <<EOF
#!/bin/sh
exec "$APP_DIR/venv/bin/python" "$APP_DIR/dhl_label.py" "\$@"
EOF
chmod +x "$BIN_DIR/dhl-label"

# ---------------------------------------------------------------- Konfiguration schreiben
cat > "$CONFIG_FILE" <<EOF
# dhl-label Konfiguration (erzeugt von install.sh)
[printer]
name = $PRINTER
media = $MEDIA
extra_options =

[crop]
side = $CROP_SIDE
trim_top_mm = 0.0
trim_bottom_mm = 0.0
page_index = 0
use_ghostscript = false

[watch]
mode = $WATCH_MODE
dir = $WATCH_DIR
filename_pattern = $FILENAME_PATTERN
processed_dirname = gedruckt
poll_seconds = 2.0
process_existing = false
EOF

# ---------------------------------------------------------------- Desktop-Icon
cat > "$DESKTOP_DIR/dhl-label-print.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=DHL-Marke drucken
Comment=Druckt die neueste DHL-PDF als Versandmarke
Exec=$BIN_DIR/dhl-label print-latest
Icon=printer
Terminal=false
Categories=Utility;
EOF

# ---------------------------------------------------------------- systemd-Service
info "systemd-User-Service aktivieren…"
systemctl --user daemon-reload
systemctl --user enable --now dhl-label.service
sleep 1
if systemctl --user is-active --quiet dhl-label.service; then
  info "Watcher läuft."
else
  warn "Watcher-Status prüfen:  systemctl --user status dhl-label"
fi

# ---------------------------------------------------------------- Kalibrierung
echo ""
info "Installation abgeschlossen."
read -r -p "Jetzt Kalibrierungsdruck starten? (braucht eine heruntergeladene DHL-PDF) [J/n]: " CAL
CAL="${CAL:-J}"
if [ "${CAL,,}" != "n" ]; then
  echo "Pfad zur DHL-PDF (leer = neueste passende PDF im Watch-Ordner):"
  read -r CALPDF
  "$BIN_DIR/dhl-label" calibrate ${CALPDF:+"$CALPDF"} || warn "Kalibrierung später starten: dhl-label calibrate PFAD/ZUR/PDF"
fi

echo ""
info "Fertig! Von jetzt an: DHL-PDF herunterladen → Marke druckt automatisch."
info "Hilfe & Befehle:  dhl-label --help   |   Log:  journalctl --user -u dhl-label -f"
