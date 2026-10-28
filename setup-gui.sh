#!/bin/sh
# setup-gui.sh – Doppelklick-Einstieg für die GTK-Setup-GUI (kein Terminal nötig).
# Startet setup_gui.py mit dem System-Python (GTK ist dort vorinstalliert,
# im venv nicht). Aus einem ZIP kann das Ausführungsrecht fehlen – dann
# einmalig: Rechtsklick → Eigenschaften → Berechtigungen → "Ausführen erlauben"
# (siehe README, Schritt 3).
exec /usr/bin/python3 "$(dirname "$0")/setup_gui.py"
