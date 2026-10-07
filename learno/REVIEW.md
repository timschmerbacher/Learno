# Leitfaden für das Code-Review

## Umfang

Dieser Stand fasst den Umbau des bisherigen Learno-Prototyps zusammen: gemeinsame Prüfungstermine und private Prüfungszustände, zwei Gruppenebenen, Datenerhaltung und explizite Migrationen V2 bis V5, gezielte Feedfreigaben, Antworten, unabhängige Rankingfreigaben, private Statistik und Feedback sowie die überarbeitete mobile Oberfläche. Eine Frameworkumstellung gehört nicht zum Umfang.

`groups.py` bleibt als Kompatibilitätsimport erhalten. Die alte Frontenddatei `static/groups.js` wird durch `static/v2.js` und `static/ui.js` ersetzt. Die alten Gruppentests werden durch umfangreichere V2-, Fach- und Berechtigungstests ersetzt; ihre Entfernung betrifft keine Nutzerdaten.

## Architektur und Einstiegspunkte

| Datei | Zuständigkeit |
|---|---|
| `app.py`, `wsgi.py` | HTTP/WSGI, Anmeldung, CSRF, Einstellungen, CSV, anfragenbezogene SQLite-Verbindungen |
| `v2.py` | Eigentum und Gruppenrechte, Prüfungstermine, persönliche Zustände, Lernsessionen, Dateizugriff, Freigaben und Archivierung |
| `insights.py` | Feedfilter vor Pagination, Hinweise, Wochenstatistik |
| `feedback.py` | Privates Feedback für Absender und explizit konfigurierte Verwaltung |
| `legacy_schema.py`, `migrate.py` | Ausgangsschema, additive versionierte Migrationen, Bestandsvergleich und Integritätsprüfung |
| `backup.py`, `preflight_update.py` | Konsistentes geprüftes Backup und Migrationstest auf einer Kopie |
| `prepare_release.py`, `install_update.py` | Quellpaket mit Dateihashes und Installation mit Programmstandsicherung |
| `static/app.js` | Gemeinsame Browserhilfen, Formulare, Navigation und Timerdarstellung |
| `static/v2.js` | Prüfungs-/Gruppenaktionen und zugehörige Dialoge |
| `static/ui.js` | Aktuelle Ansichten, Diagramme, Feed, Entwürfe, Statistik und Feedback |

Ein HTTP-Schreibaufruf durchläuft Anmeldung, Origin-/CSRF-Prüfung und eine kurze `BEGIN IMMEDIATE`-Transaktion. Fachliche Eigentums- und Sichtbarkeitsprüfungen erfolgen im Backend. Die Oberfläche übernimmt keine Sicherheitsentscheidung. Fremdschlüssel sind pro Verbindung aktiviert; Fehler rollen die Transaktion zurück.

Die Skripte werden in der Reihenfolge `app.js` → `v2.js` → `ui.js` geladen. Einige Präsentationsfunktionen des bisherigen Prototyps werden durch die letzte Datei ersetzt. Das ist funktional getestet, bleibt aber ein Ansatzpunkt für eine spätere Modulaufteilung. Eine umfangreiche Umformatierung wurde nicht mit den funktionalen Änderungen vermischt.

## Datenmodell und Schutzregeln

- `study_groups.parent_id` bildet Haupt- und Untergruppen ab. `members.left_at` dokumentiert Austritte. Es gibt keine dritte Ebene und keinen Zugriff auf Geschwistergruppen allein durch Hauptgruppenmitgliedschaft.
- `exam_events` speichert einen Termin einmal. `user_exam_states` speichert Schwierigkeit, Note, Abschluss und persönliche Archivierung getrennt je Benutzer und Termin.
- `sessions` und `active` erhalten zusätzliche V2-Zuordnungen. Historische Fachtexte, Inhalte und Zeitwerte bleiben unabhängig von späteren Terminänderungen.
- `exam_event_history` und `exam_grade_history` erhalten Änderungen. `exam_attachments` erhält Dateiinhalte oder verweist auf unveränderte alte BLOBs.
- `posts` enthält Momentaufnahmen mit Zielgruppe, ausgewählten Kennzahlen und optionaler tatsächlicher Sessionreferenz. `comments.parent_comment_id` bildet Antworten ab. Ranking verwendet gesondert freigegebene Sessions.
- `users.weekly_goal_minutes`, `notices.read_at` und die Feedbacktabellen ergänzen private Ziele, Lesestatus und Nachrichten. `schema_migrations` protokolliert explizite Migrationen.
- Alte Prüfungs-/Dateitabellen bleiben als Altbestand erhalten. Keine Migration beim Start oder WSGI-Import; kein Ersetzen bestehender Datenbanken.

Benutzte Prüfungen und Dateien werden archiviert. Sessioninhalte werden durch Prüfungsänderungen nicht rückwirkend überschrieben. Eine ausdrücklich bestätigte Ausnahme ist `POST /api/v2/post-delete`: Der Autor kann seinen Beitrag samt allen Kommentaren und Antworten endgültig entfernen. Ursprüngliche Sessions, Prüfungen, Noten, Dateien, Feedback und Rankingfreigaben bleiben dabei erhalten. Es gibt keinen Papierkorb; alte Backups können frühere Inhalte enthalten.

## Lokal nachvollziehen

Python 3.10 oder neuer genügt für Anwendung und Backendtests. Im Ordner `learno/`:

```text
python -B -m unittest discover -v
python -B migrate.py --workers-stopped
python -B app.py
```

Die Migration in diesem Beispiel ist für eine eigene lokale Installation gedacht. Eine vorhandene Datenbank nur mit gestoppten Schreibprozessen und vorheriger Sicherung migrieren. Standardadresse: `http://127.0.0.1:8000/`. Ein eigenes Testkonto registrieren. Feedback ist zunächst deaktiviert; optional ein vorhandenes Testkonto explizit mit `python -B feedback.py --reviewer review-admin` zuweisen.

Backendtests erstellen ihre eigenen temporären Datenbanken. Der zusätzliche Bestandsmigrationstest kopiert einen vorhandenen lokalen Bestand ausschließlich lesend; ohne diesen Bestand wird genau dieser Test übersprungen. Reale Kontopasswörter werden für das Review nicht benötigt. Passwörter wie `ExamplePassword123!` sind ausschließlich Testfixtures.

Für die optionalen Browserprüfungen Node.js und Playwright bereitstellen. Der geprüfte Stand verwendet Playwright 1.62.1:

```text
npm install --no-save playwright@1.62.1
npx playwright install chromium
node test_browser.cjs
node test_browser_v4.cjs
node test_browser_extended.cjs
node test_browser_feedback.cjs
node test_browser_feed_stats.cjs
```

Alternativ kann `LEARNO_BROWSER_EXECUTABLE` auf einen vorhandenen Chromium-/Edge-Browser zeigen. `LEARNO_TEST_PYTHON` benennt bei Bedarf den Pythonpfad. `LEARNO_BROWSER_TEMP_ROOT` wählt den isolierten Test-/Screenshotordner. Browsertests starten eigene Serverports, Datenbanken und Browserprofile. Sie sind keine Tests gegen die Online-Nutzerdatenbank.

## Empfohlene Review-Reihenfolge

1. Migration und Backup: Originalspaltenvergleich, Wiederholbarkeit, Integrität und Abbruch ohne automatische Datenkorrektur.
2. Backendrechte: Mehrfachmitgliedschaft, Zugriffsentzug nach Austritt, private Ergebnisse/Dateien/Feedback und nicht freigegebene Kennzahlen im JSON.
3. Transaktionen: konkurrierende Änderungen, Timerabschluss, Archivprüfung und Beitragslöschung einschließlich Fremdschlüssel-Rollback.
4. Feed und Ranking: Momentaufnahmen, Filter vor Pagination, Bezugskommentare und unabhängige Freigabemetadaten.
5. Oberfläche: Formularzuständigkeit, Entwurfserhalt, Tastaturmenüs, mobile Breiten 320/390/700 und Timererhalt.

Die Tests sind nach diesen Bereichen benannt. `test_post_delete.py` prüft gezielt Löschung und Datenerhalt; `test_release.py` prüft Paketinhalt und sichere Installation. Details stehen in `TEST_REPORT.md`.

## Bekannte Grenzen

Kein Passwort-Reset und kein Offlinebetrieb. Erinnerungen benötigen einen geöffneten Browser und ein waches Gerät. Die Anzeige wertet Lernzeit aus und bewertet damit keinen Wissensstand. Dateisignaturen werden geprüft, aber es gibt keinen Virenscanner.

Manuelle historische Nachträge können auch benoteten oder archivierten Prüfungen zugeordnet werden, während neue Timerstarts dafür gesperrt sind. Unberechtigte Annahme-/Ablehnungsversuche bei Freundschaften verändern keine Daten, melden derzeit aber Erfolg. Beides ist im Testbericht ausdrücklich dokumentiert.

Die bisherige Prüfung erfolgte mit Edge/Chromium und emulierten Viewports, teilweise mit Touch-Emulation. Echte Smartphones, Safari, native Bildschirmtastaturen, Screenreader, größere Last und Prozess-/Stromausfälle bleiben gesonderte Prüfungen. Die kompakte Python-/JavaScript-Struktur und globale Frontendfunktionen sind weitere Wartbarkeitsthemen für das Review.
