# Learno 2 – eure Lerndokumentationsapp

Neu: offene Lerngruppen, bewusst übernommene und synchronisierte Gruppentermine, geschützte PDF-/Bilddateien, Prüfungen bearbeiten und entfernen, Prüfung beim Timerstart anlegen und auswählbare Lernorte. Für den kostenlosen Online-Gruppentest siehe **ONLINE_START.md**.

Eine lokal und über WSGI online ausführbare Web-App für euer FH-Projekt. Python stellt die App bereit; die Oberfläche läuft im Browser. Es werden keine zusätzlichen Python-Pakete und kein Node.js benötigt.

## In VS Code starten

1. ZIP vollständig entpacken.
2. In VS Code **Datei → Ordner öffnen** wählen und den Ordner `learno` öffnen (darin liegt `app.py`).
3. **Terminal → Neues Terminal** öffnen.
4. `python app.py` ausführen. Falls der Befehl unter Windows nicht erkannt wird: `py app.py`. Unter macOS/Linux gegebenenfalls `python3 app.py` verwenden. Voraussetzung: Python 3.10 oder neuer.
5. **http://127.0.0.1:8000** im Browser öffnen.
6. Ein eigenes Konto anlegen. Passwortlänge: 12–128 Zeichen.

Das Terminal muss geöffnet bleiben. Mit **Strg+C** beenden. Unter Windows ist auch ein Doppelklick auf `START_WINDOWS.bat` möglich, wenn der Befehl `python` verfügbar ist.

Die mitgelieferte VS-Code-Startkonfiguration ermöglicht F5, wenn die Python- und Python-Debugger-Erweiterungen von Microsoft installiert sind. Für den normalen Terminalstart sind diese Erweiterungen nicht erforderlich.

## Erster Durchlauf

1. Unter **Profil & Freunde → CSV-Daten** die mitgelieferte `learning_sessions.csv` importieren. Sie enthält zehn erfundene Lernsessions aus September 2026. Deshalb erscheinen sie nur in den damaligen Wochenstatistiken, nicht automatisch in der aktuellen Woche.
2. Unter **Prüfungen** ein Fach, die Prüfungsbezeichnung, das Datum und eine Schwierigkeit von 1 bis 5 eingeben.
3. Unter **Lernsessions** die importierten Sessions über **Prüfung zuordnen** mit einer Prüfung desselben Fachs verbinden.
4. Eine neue Session starten, bei Bedarf pausieren und über **Beenden & speichern** mit Lernort und Hilfsmitteln abschließen.
5. Nach einer Prüfung eine Note von 1 bis 5 eintragen. Ihre Gesamtlernzeit wird aus den zugeordneten Sessions berechnet.
6. Über **Teilen** bewusst eine Session oder ein Prüfungsergebnis veröffentlichen.

## Enthaltene Funktionen

- Registrierung und Anmeldung; Passwörter werden mit Salt und PBKDF2-SHA256 gehasht.
- Pro Konto getrennte Prüfungen, Lernsessions und Einstellungen in einer SQLite-Datenbank.
- Timer mit Zehntelsekundenanzeige; Pausen werden abgezogen und als Unterbrechungen gezählt. Eine laufende Session bleibt nach Neuladen oder Serverneustart erhalten. Anmeldesitzungen bleiben bis zu ihrem Ablauf nach 24 Stunden erhalten.
- Manuelles Nachtragen von Sessions mit euren sechs Attributen und optionaler Prüfungszuordnung.
- CSV-Import mit vollständiger Validierung und atomarem Speichern: Bei ungültigen Zeilen wird nichts importiert.
- CSV-Export der eigenen Lernsessions. Der ursprüngliche CSV-Vertrag speichert ganze Minuten; beim Export werden Sekunden abgerundet.
- Prüfungsergebnisse, Gesamtlernzeit je Prüfung und Lernpriorität von 1 bis 10.
- Statistiken nach Fach und Datumsbereich, Wochenübersicht, getrennte Anzeige von Noten und Aufwand.
- Feed mit bewusst veröffentlichten Sessions und Ergebnissen; maximal 500 Textzeichen.
- Freundschaftsanfragen per genauem Benutzernamen, Annahme und Ablehnung. Kommentare auf eigenen Beiträgen und Beiträgen bestätigter Freunde.
- Vergleich zweier veröffentlichter Prüfungsergebnisse.
- Wöchentliches Top-100-Ranking nach veröffentlichter Lernzeit. Eine Session zählt auch bei mehrmaligem Teilen nur einmal. Bei Gleichstand wird alphabetisch nach Benutzernamen sortiert.
- Tägliche Erinnerung mit Uhrzeit und Zeitzone bei geöffneter App. Optionale Browserbenachrichtigung nach ausdrücklicher Erlaubnis.
- Beispielhafte Sperrwortprüfung für Text auf Basis von `blocked_words.json`.
- Responsive Oberfläche für Desktop und Smartphone.

## Lernpriorität

`Priorität = Zeitdruck + Schwierigkeit − Lernzeitabzug`, begrenzt auf 1–10.

| Tage bis zur Prüfung | Zeitdruckpunkte |
|---|---:|
| 0–3 | 6 |
| 4–7 | 5 |
| 8–14 | 3 |
| 15–30 | 2 |
| Mehr als 30 | 1 |

Pro voller Stunde der **dieser Prüfung zugeordneten Lernzeit** wird ein Punkt abgezogen, höchstens drei. Vergangene und abgeschlossene Prüfungen erhalten keine Priorität. Bei Gleichstand kommt die frühere Prüfung zuerst. Beispiel: in drei Tagen, 30 Minuten gelernt, Schwierigkeit 4 → Priorität 10/10.

Das ist eure Entwurfsheuristik. Lernzeit allein misst keinen Wissensstand.

## Mit mehreren Konten ausprobieren

Die App enthält keine erfundenen Freunde oder öffentlichen Fake-Beiträge. Erstelle ein zweites Konto in einem privaten Browserfenster. Beide Fenster greifen auf dieselbe App-Installation zu. Ihr könnt Anfragen senden, annehmen, Beiträge teilen und kommentieren. Bei Wechsel zurück zum App-Tab werden die Daten neu geladen; alternativ die Seite aktualisieren.

## Projektstruktur

- `app.py`: lokaler HTTP-Server, Datenbank, Authentifizierung, API und Prioritätsalgorithmus.
- `groups.py`: Gruppenrechte, übernommene Termine, Änderungsmeldungen und Prüfungsdateien.
- `wsgi.py`: Online-Einstieg für WSGI-Hosting.
- `pythonanywhere_wsgi.py`: kopierfertige Provider-Konfiguration.
- `static/groups.js`: Gruppenoberfläche und neue Prüfungsabläufe.
- `static/index.html`: Einstieg der Oberfläche.
- `static/style.css`: Gestaltung und responsive Layouts.
- `static/app.js`: Navigation, Formulare, Diagramme und Timeranzeige.
- `blocked_words.json`: erweiterbare Beispiel-Sperrwortliste.
- `learning_sessions.csv`: eure zehn Beispieldatensätze.
- `test_app.py`: automatisierte Tests mit eigener temporärer Datenbank.
- `data/learno.db`: entsteht beim ersten Start; enthält die tatsächlichen Konten und App-Daten.

## Daten aufbewahren

Die Daten bleiben nach dem Beenden bestehen. Für ein vollständiges Backup die App beenden und den Ordner `data` kopieren. Der CSV-Export ist kein vollständiges Backup: Er enthält weder Konten noch Prüfungen, Posts oder Zuordnungen. Ein erneuter CSV-Import erstellt zusätzliche Datensätze.

## Grenzen dieser lokalen Version

- `python app.py` ist der lokale Entwicklungsstart auf `127.0.0.1`. Für den kleinen Online-Gruppentest den vorbereiteten WSGI-Einstieg mit HTTPS gemäß ONLINE_START.md verwenden. Für größere öffentliche Nutzung sind weitergehende Betriebsmaßnahmen nötig.
- Die Wochenberechnung und Prüfungspriorität richten sich nach dem lokalen Datum des Python-Servers. Stellt euren Computer auf Europe/Vienna ein. Die Erinnerungszeitzone wird unabhängig davon im Browser ausgewertet.
- Erinnerungen funktionieren nur bei geöffneter App und wachem Computer. Browser können Hintergrundtabs verzögern. Es handelt sich nicht um einen Push-Dienst bei geschlossener App.
- Zehntelsekunden werden angezeigt und gespeichert. Eine garantierte Abweichung von höchstens 0,1 Sekunden über vier Stunden wurde nicht messtechnisch nachgewiesen. Änderungen der Systemuhr während der Session können die Messung beeinflussen.
- PDF-/PNG-/JPEG-Unterlagen sind implementiert. OCR-Inhaltsprüfung und Virenprüfung sind nicht enthalten. Die Textsperrwortliste prüft weiterhin nur Feed-Texte und Kommentare.
- Keine Streaks oder Abzeichen: Die zuletzt konkretisierten Anforderungen beschreiben eine Lernerinnerung.
- Geteilte Beiträge speichern eine Momentaufnahme. Eine spätere Notenänderung aktualisiert alte Beiträge nicht automatisch.
- Die 500-Zeichen-Regel zählt serverseitig Unicode-Codepunkte; Browser können komplexe Emojis bei der Eingabelänge strenger zählen.
- Kein Passwort-Reset, keine E-Mail-/Ausweis-Verifikation. Der Hosting-Einstieg ist vorbereitet; ein Providerkonto und die tatsächliche Bereitstellung sind noch erforderlich.

## Tests

Im Projektordner `python -m unittest -v` ausführen. Tests verwenden eine temporäre Datenbank und verändern eure Daten nicht.

Die automatisierten Tests prüfen den WSGI-Einstieg, Anmeldung, private Daten, CSV-Import, Timer, Gruppenbeitritt, Ersteller-/Verwaltungsrechte, Synchronisation, persönliche Noten, Datei-Zugriffsschutz und Löschverhalten. Die JavaScript-Syntax wird zusätzlich geprüft. Eine visuelle Browserprüfung ist in der Erstellungsumgebung weiterhin nicht erfolgt.

Wenn Port 8000 belegt ist, in PowerShell `$env:LEARNO_PORT=8001` und danach `python app.py` ausführen; anschließend http://127.0.0.1:8001 öffnen.


## Regeln für Gruppenprüfungen

Jeder registrierte Benutzer darf Gruppen erstellen und offen beitreten. Jedes Mitglied darf Termine anlegen. Ersteller und Gruppenverwaltung dürfen gemeinsame Termine bearbeiten oder löschen. Übernehmen erfolgt bewusst und nur einmal pro Person. Schwierigkeit, Noten und Lernzeiten gehören zur persönlichen Kopie. Änderungen gemeinsamer Felder aktualisieren übernommene Kopien und erscheinen als Hinweis beim nächsten Laden der App bzw. beim Wechsel einer Ansicht.

Eine persönliche Prüfung zu entfernen löscht deren private Dateien, aber keine Lernsessions. Der Gruppentermin und seine Dateien bleiben bestehen. Beim Löschen eines Gruppentermins werden dessen gemeinsame Dateien gelöscht; persönliche Kopien und Lernzeiten bleiben ohne weitere Synchronisation bestehen. Beim Verlassen einer Gruppe bleiben persönliche Kopien ebenfalls bestehen, der Zugriff auf Gruppenunterlagen endet sofort. Die Gruppenverwaltung kann in dieser Version die eigene Gruppe noch nicht verlassen oder übertragen.

Dateien privater Prüfungen sieht nur die jeweilige Person. Bei übernommenen Gruppenprüfungen sind Unterlagen immer gemeinsame Gruppenunterlagen. Die hochladende Person und die Gruppenverwaltung dürfen gemeinsame Dateien löschen.
