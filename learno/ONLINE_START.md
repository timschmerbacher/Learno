# Bestehende Learno-Installation sicher aktualisieren

Für https://timbox.eu.pythonanywhere.com/ liegt das Projekt unter `/home/Timbox/learno`, die Datenbank unter `/home/Timbox/learno/data/learno.db`. Den tatsächlich konfigurierten Pfad vor jedem Update prüfen.

1. Lokal alle Tests ausführen und mit `python prepare_release.py` ein neues Quellpaket erstellen. Das Paket enthält keine Datenbanken, Unterlagen, Logs oder Zugangsdaten.
2. ZIP unter PythonAnywhere Files hochladen und in einen neuen Stagingordner entpacken. Niemals direkt über die laufende Installation entpacken.
3. Im Stagingordner `learno` zunächst `python3 preflight_update.py --db /home/Timbox/learno/data/learno.db` ausführen. Die echte Datenbank wird ausschließlich lesend geöffnet; die Migration läuft auf einer separaten Kopie mit Vergleich sämtlicher Originalwerte.
4. Vollständige Regressionen lokal ausführen. Auf Hosting mit knappem Konsolen-CPU-Budget die Bestandsvorprüfung und gezielte Bereitstellungsprüfungen verwenden. Falls die vollständigen Backendtests zusätzlich im datenfreien Stagingpaket laufen, wird der Test mit lokalem Originalbestand übersprungen; die Vorprüfung übernimmt den tatsächlichen Online-Bestand.
5. Im Web-Dashboard die Web-App vorübergehend deaktivieren und das Ende der Worker abwarten. Keine alte Version parallel schreibend betreiben.
6. Aus dem Stagingordner zunächst ein neues geprüftes Datenbankbackup erstellen, auch wenn keine Migration erforderlich ist. Danach installieren:

```bash
python3 -B backup.py --db /home/Timbox/learno/data/learno.db
python3 -B install_update.py --target /home/Timbox/learno --db /home/Timbox/learno/data/learno.db --reviewer Tim --workers-stopped
```

Der Installer prüft sämtliche Quellhashes und das bestehende Empfängerkonto und sichert bestehende Programmdateien unter einem neuen Namen. Falls eine Migration erforderlich ist, erstellt sie zusätzlich ein neues Datenbankbackup und durchläuft V2 bis V5 additiv. Bei bereits aktuellem Schema ersetzt das ausdrücklich ausgeführte Backup diese Sicherung. Alle ursprünglichen Spaltenwerte werden verglichen. `data/`, hochgeladene Dateien, bestehende CSVs und lokale Sperrwortlisten bleiben erhalten. Die externe WSGI-Konfiguration bleibt bestehen. Bei einem Fehler die App deaktiviert lassen und kompatibel korrigieren; kein altes Backup über neue Nutzerdaten zurückspielen.

7. Integrität, Fremdschlüssel, Migrationsversionen und Empfängerzuordnung prüfen. Force HTTPS einschalten; keine statische Zuordnung zu `data/` oder dem gesamten Projekt.
8. Web-App wieder aktivieren und neu laden. Anmeldung, bestehende Sessions/Timer und Feedback prüfen. Andere Konten dürfen nur eigene Feedbacknachrichten sehen.

## Zusätzliches Backup

```bash
python3 -B backup.py --db /home/Timbox/learno/data/learno.db
```

Das Werkzeug erstellt einen neuen Zeitstempelnamen unter `data/backups/`, prüft Integrität und sämtliche Originalwerte und überschreibt kein vorhandenes Backup. Die ausgegebene Datei bei Bedarf über Files herunterladen. Ein CSV-Export ist kein vollständiges Backup; die SQLite-Datei enthält auch Unterlagen.

Der WSGI-Import und der Serverstart migrieren nicht automatisch. Online-Datenbanken dürfen niemals durch lokale Datenbanken ersetzt werden.
