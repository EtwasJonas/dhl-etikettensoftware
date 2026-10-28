#!/usr/bin/env bash
# install.sh – Installer für die DHL-Etikettensoftware
# Ziel: Ubuntu / Debian / Linux Mint (apt + systemd + CUPS)
#
# Zwei Betriebsarten:
#   1) Interaktiv (kein Argument): fragt alles per Terminal ab – Fallback
#   2) Nicht-interaktiv (Flags): wird vom GUI-Setup (setup_gui.py) aufgerufen
#
# Flags:
#   --printer NAME        CUPS-Druckername (USB oder WLAN)
#   --media NAME          CUPS-Mediengröße (z.B. 4x6)
#   --target SIZEXSIZE    Etikettengröße in mm (z.B. 100x150); leer = nur croppen
#   --watch-mode MODE     downloads | custom
#   --watch-dir PFAD      zu überwachender Ordner
#   --pattern REGEX       Namensfilter (downloads-Modus)
#   --side top|bottom     wo sitzt die Marke im A4-PDF
#   --no-calibrate        Kalibrierungs-Prompt am Ende überspringen (GUI macht das selbst)
#   --pkexec              apt über pkexec (GUI-Passwortdialog statt sudo-Terminal)
#   --non-interactive     keine Rückfragen; fehlende Pflicht-Flags = Fehler
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

FLAG_PRINTER="" FLAG_MEDIA="" FLAG_TARGET="" FLAG_WATCH_MODE="" FLAG_WATCH_DIR="" FLAG_PATTERN="" FLAG_SIDE=""
NO_CALIBRATE=0 USE_PKEXEC=0 NONINTERACTIVE=0

usage() {
  grep '^#   --' "$0" | sed 's/^#   //'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --printer)        FLAG_PRINTER="${2:-}";   shift 2 ;;
    --media)          FLAG_MEDIA="${2:-}";     shift 2 ;;
    --target)         FLAG_TARGET="${2:-}";    shift 2 ;;
    --watch-mode)     FLAG_WATCH_MODE="${2:-}"; shift 2 ;;
    --watch-dir)      FLAG_WATCH_DIR="${2:-}"; shift 2 ;;
    --pattern)        FLAG_PATTERN="${2:-}";   shift 2 ;;
    --side)           FLAG_SIDE="${2:-}";      shift 2 ;;
    --no-calibrate)   NO_CALIBRATE=1;          shift ;;
    --pkexec)         USE_PKEXEC=1;            shift ;;
    --non-interactive) NONINTERACTIVE=1;       shift ;;
    --help|-h)        usage; exit 0 ;;
    *) die "Unbekannte Option: $1 (siehe --help)" ;;
  esac
done

# Im nicht-interaktiven Modus (GUI) müssen die Pflicht-Flags gesetzt sein,
# sonst würde das Skript auf eine Terminal-Eingabe warten und ewig hängen.
if [ "$NONINTERACTIVE" -eq 1 ]; then
  MISSING=""
  [ -n "$FLAG_PRINTER" ]    || MISSING="${MISSING}--printer "
  [ -n "$FLAG_MEDIA" ]      || MISSING="${MISSING}--media "
  [ -n "$FLAG_WATCH_MODE" ] || MISSING="${MISSING}--watch-mode "
  [ -n "$FLAG_WATCH_DIR" ]  || MISSING="${MISSING}--watch-dir "
  [ -n "$FLAG_SIDE" ]       || MISSING="${MISSING}--side "
  if [ -n "$MISSING" ]; then
    die "Nicht-interaktiver Modus, es fehlen: $MISSING"
  fi
fi

# ---------------------------------------------------------------- Voraussetzungen
command -v apt-get >/dev/null 2>&1 || die "Diese Installation unterstützt Debian/Ubuntu/Mint (apt)."

if [ "$USE_PKEXEC" -eq 1 ]; then
  command -v pkexec >/dev/null 2>&1 || die "pkexec nicht gefunden (PolicyKit) – bitte --pkexec weglassen."
  APT="pkexec"
  info "Systempakete werden installiert – Bestätigungsdialog erscheint in Kürze…"
else
  APT=""
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || die "Bitte sudo installieren oder als root ausführen."
    APT="sudo"
  fi
  info "Systempakete installieren (python3-venv, cups-client)…"
fi
$APT apt-get update -qq
$APT apt-get install -y -qq python3-venv python3-pip cups-client ghostscript

# ---------------------------------------------------------------- Drucker wählen
if [ -n "$FLAG_PRINTER" ]; then
  PRINTER="$FLAG_PRINTER"
  lpstat -p "$PRINTER" >/dev/null 2>&1 || die "Drucker '$PRINTER' existiert nicht (lpstat)."
  info "Drucker (vorgegeben): $PRINTER"
else
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
if [ -n "$FLAG_MEDIA" ]; then
  MEDIA="$FLAG_MEDIA"
  info "Mediengröße (vorgegeben): $MEDIA"
else
  echo ""
  echo "Erklärung: Die 'Mediengröße' ist der interne Name, unter dem CUPS"
  echo "(das Drucksystem) die Papier-/Etikettengröße kennt – z.B. '4x6',"
  echo "'100x150mm' oder 'A4'. Beim Drucken wird sie automatisch mitgegeben."
  echo "Der Standard-Vorschlag entspricht bereits dem, was der Drucker meldet."
  info "Verfügbare Mediengrößen für '$PRINTER':"
  MEDIA_LIST="$(lpoptions -p "$PRINTER" -l 2>/dev/null | grep -iE 'pagesize|^media' | head -n1 || true)"
  [ -n "$MEDIA_LIST" ] || die "Konnte Mediengrößen nicht lesen (lpoptions)."
  echo "  $MEDIA_LIST"
  DEFAULT_MEDIA="$(echo "$MEDIA_LIST" | sed 's/.*://' | tr ' ' '\n' | grep '^\*' | tr -d '*' | head -n1 || true)"
  DEFAULT_MEDIA="${DEFAULT_MEDIA:-4x6}"
  read -r -p "Mediengröße übernehmen (Enter) oder anderen Namen eingeben [$DEFAULT_MEDIA]: " MEDIA
  MEDIA="${MEDIA:-$DEFAULT_MEDIA}"
fi
info "Gewählt: Drucker='$PRINTER' Medium='$MEDIA'"

# ---------------------------------------------------------------- Etikettengröße
if [ -n "$FLAG_TARGET" ] || [ "$NONINTERACTIVE" -eq 1 ]; then
  TARGET="$FLAG_TARGET"
else
  echo ""
  echo "Erklärung: Zusätzlich wird das gecroppte A4-Stück exakt auf die"
  echo "Etikettengröße der Rolle eingepasst (gedreht + skaliert, zentriert)."
  echo "Das sorgt dafür, dass die Marke das komplette Etikett füllt."
  echo "Der Vretti nutzt meist 100x150-mm-Rollen (synonym mit 4\"x6\")."
  read -r -p "Etikettengröße der Rolle in mm (Breite x Höhe) [100x150]: " TARGET
  TARGET="${TARGET:-100x150}"
  if [ "$TARGET" = "-" ]; then TARGET=""; fi
fi
info "Ziel-Etikettengröße: ${TARGET:-(nur croppen, Drucker skaliert selbst)}"

# ---------------------------------------------------------------- Watch-Modus wählen
if [ -n "$FLAG_WATCH_MODE" ]; then
  case "$FLAG_WATCH_MODE" in
    downloads|custom) WATCH_MODE="$FLAG_WATCH_MODE" ;;
    *) die "Ungültiger --watch-mode: $FLAG_WATCH_MODE (downloads|custom)" ;;
  esac
else
  echo ""
  echo "Wie sollen PDFs erkannt werden?"
  echo "  1) Downloads-Ordner überwachen – druckt nur PDFs mit Namensfilter (z.B. 'versand', 'dhl', 'paket')"
  echo "  2) Eigener Watch-Ordner – alle neuen PDFs dort werden gedruckt"
  read -r -p "Auswahl [1]: " WMODE
  WMODE="${WMODE:-1}"
  WATCH_MODE="downloads"
  [ "$WMODE" = "2" ] && WATCH_MODE="custom"
fi

WATCH_DIR=""
FILENAME_PATTERN=""
if [ "$WATCH_MODE" = "downloads" ]; then
  WATCH_DIR="${FLAG_WATCH_DIR:-$HOME/Downloads}"
  FILENAME_PATTERN="${FLAG_PATTERN:-versand|dhl|paket}"
else
  if [ -n "$FLAG_WATCH_DIR" ]; then
    WATCH_DIR="$FLAG_WATCH_DIR"
  else
    read -r -p "Pfad des Watch-Ordners [$HOME/DHL]: " WATCH_DIR
    WATCH_DIR="${WATCH_DIR:-$HOME/DHL}"
  fi
  mkdir -p "$WATCH_DIR"
fi

# ---------------------------------------------------------------- Crop-Einstellungen
if [ -n "$FLAG_SIDE" ]; then
  case "$FLAG_SIDE" in
    top)    SIDE="o" ;;
    bottom) SIDE="u" ;;
    *) die "Ungültiges --side: $FLAG_SIDE (top|bottom)" ;;
  esac
else
  echo ""
  read -r -p "Wo sitzt die Marke im A4-PDF? (o=obere Hälfte, u=untere Hälfte) [o]: " SIDE
  SIDE="${SIDE:-o}"
fi
CROP_SIDE="top"
[ "$SIDE" = "u" ] && CROP_SIDE="bottom"

# ---------------------------------------------------------------- Dateien installieren
info "Installiere nach $APP_DIR …"
mkdir -p "$APP_DIR" "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR" "$DESKTOP_DIR"
cp "$SRC_DIR/dhl_label.py" "$APP_DIR/"
cp "$SRC_DIR/gui_helpers.py" "$APP_DIR/"
cp "$SRC_DIR/setup_gui.py" "$APP_DIR/"
cp "$SRC_DIR/install.sh" "$APP_DIR/"   # damit dhl-label-setup (GUI) die GUI erneut ausführen kann
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

# GUI-Setup-Wrapper (benutzt System-Python mit GTK, NICHT das venv)
cat > "$BIN_DIR/dhl-label-setup" <<EOF
#!/bin/sh
exec /usr/bin/python3 "$APP_DIR/setup_gui.py" "\$@"
EOF
chmod +x "$BIN_DIR/dhl-label-setup"

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
target_size_mm = $TARGET
rotate = auto

[watch]
mode = $WATCH_MODE
dir = $WATCH_DIR
filename_pattern = $FILENAME_PATTERN
processed_dirname = gedruckt
poll_seconds = 2.0
process_existing = false
EOF

# ---------------------------------------------------------------- Desktop-Icons
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

cat > "$DESKTOP_DIR/dhl-label-setup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=DHL-Setup
Comment=Setup und Kalibrierung der DHL-Etikettensoftware
Exec=$BIN_DIR/dhl-label-setup
Icon=preferences-system
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
if [ "$NO_CALIBRATE" -eq 1 ]; then
  info "Kalibrierung wird vom GUI-Setup angeboten (Terminal-Kalibrierung übersprungen)."
else
  echo ""
  info "Installation abgeschlossen."
  read -r -p "Jetzt Kalibrierungsdruck starten? (braucht eine heruntergeladene DHL-PDF) [J/n]: " CAL
  CAL="${CAL:-J}"
  if [ "${CAL,,}" != "n" ]; then
    echo "Pfad zur DHL-PDF (leer = neueste passende PDF im Watch-Ordner):"
    read -r CALPDF
    "$BIN_DIR/dhl-label" calibrate ${CALPDF:+"$CALPDF"} || warn "Kalibrierung später starten: dhl-label calibrate PFAD/ZUR/PDF"
  fi
fi

echo ""
info "Fertig! Von jetzt an: DHL-PDF herunterladen → Marke druckt automatisch."
info "Hilfe & Befehle:  dhl-label --help   |   Log:  journalctl --user -u dhl-label -f"
