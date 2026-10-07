# Learno – Fortschritt und Gemeinschaft

Mobile Lern-Web-App mit Python 3.10+, SQLite und WSGI. Keine zusätzlichen Python-Pakete und kein Node.js für den App-Betrieb erforderlich.

Für die Studiengruppe: [Review-Leitfaden](REVIEW.md) mit Architektur, Datenmodell, Testaufrufen und bekannten Grenzen. Die aktuellen Testergebnisse stehen in [TEST_REPORT.md](TEST_REPORT.md).

## Start und Update

Im Ordner `learno` arbeiten. Vor der Migration alle lokalen und WSGI-Worker stoppen.

```text
python migrate.py --workers-stopped
python app.py
```

Dann http://127.0.0.1:8000 öffnen. Unter Windows muss eine echte Python-Installation verfügbar sein; ein nicht eingerichteter Microsoft-Store-Alias genügt nicht. Gegebenenfalls `python` durch den Pfad zur Python-Installation ersetzen.

Die aktuelle Migration ergänzt Version 5 (privates Feedback). Ältere Bestände durchlaufen V2 bis V5 der Reihe nach, ohne erneute Prüfungsübernahme. Altbeiträge bleiben unverändert und erhalten keine geratene Sessionreferenz. Die Migration legt für eine vorhandene Datenbank automatisch ein neues, geprüftes Backup unter `data/backups/` an. Sie ist additiv, transaktional und wiederholbar. Alle ursprünglichen Spaltenwerte werden vor dem Commit verglichen. Eine bereits migrierte Datenbank wird nicht erneut verändert. Für eine neue Installation erstellt derselbe explizite Befehl das Schema.

## Privates Feedback

„Feedback“ ist über die Navigation und mobil unter „Mehr“ erreichbar. Nachrichten (bis 2000 Zeichen) sehen ausschließlich der Absender und der ausdrücklich konfigurierte Empfänger. Sie erscheinen weder im Feed noch in Gruppen. Der Empfänger kann alle Nachrichten und ungelesene Nachrichten anzeigen und als gelesen markieren; Nachrichteninhalte werden nicht überschrieben oder gelöscht.

Nach der Migration einmal bewusst ein bestehendes Konto zuweisen: `python feedback.py --reviewer Tim`. Ohne Zuweisung bleibt das Senden gesperrt. Es gibt keine automatische Berechtigung für das erste Konto und keine API zur Rollenvergabe. Ein automatischer Wechsel zu einem anderen Empfänger wird verweigert.

**Niemals `data/` löschen, eine leere Datenbank darüberkopieren oder ein altes Backup über neue V2-Nutzerdaten zurückspielen.** Der Server migriert beim Start oder WSGI-Import nicht automatisch. Ohne abgeschlossene Migration verweigert er den Betrieb mit einer erklärenden Meldung.

Andere Datenbank: `LEARNO_DB` setzen oder bei der Migration `--db PFAD` angeben. Anderer lokaler Port: `LEARNO_PORT` setzen. Der lokale Server bindet ausschließlich an 127.0.0.1; gemeinsamer Online-Betrieb erfolgt über WSGI und HTTPS gemäß `ONLINE_START.md`.

## Gruppen und Prüfungen

- Hauptgruppen und genau eine Ebene Untergruppen. Hauptgruppenverwaltung legt Untergruppen an.
- Offener Beitritt; für eine Untergruppe zuerst der Hauptgruppe beitreten. Hauptgruppenmitgliedschaft gewährt keinen Zugriff auf Geschwister-Untergruppen.
- Mehrere Mitgliedschaften pro Person möglich. Vor dem Hauptgruppenaustritt zuerst Untergruppen verlassen. Die Verwaltung kann ihre eigene Gruppe nicht verlassen.
- Ein Prüfungstermin gehört entweder einer Person oder genau einer Gruppe. Gemeinsame Termine liegen nur einmal in `exam_events`.
- „Zu meinen Prüfungen hinzufügen“ erzeugt einen privaten Zustand in `user_exam_states`, keine Terminkopie. Schwierigkeit, Note, Abschluss und persönliche Archivierung sind pro Person getrennt.
- Lernzeit und Sessionanzahl werden aus den eigenen Sessions berechnet. Priorität berücksichtigt Zeitdruck, persönliche Schwierigkeit und zugeordnete Lernzeit.
- Nach einer Note erscheint die Prüfung nicht mehr beim Timerstart. Die API prüft dies ebenfalls. Ein bereits laufender Timer darf weiterhin beendet und gespeichert werden.
- Im Startdialog kann unmittelbar eine neue persönliche oder gemeinsame Prüfung angelegt und ausgewählt werden. Anlage startet den Timer nicht automatisch.
- Lernorte: Standardliste, bisher verwendete eigene Orte und Freitext.

## Datenerhalt und Archiv

Unbenutzte persönliche Prüfungen können endgültig aus dem V2-Modell entfernt werden. Sobald Sessions, Timer, Dateien, Ergebnisse, Freigaben oder Änderungen vorhanden sind, wird archiviert. Gemeinsame Termine mit persönlichen Übernahmen werden ebenfalls archiviert. Die persönliche Archivierung eines Gruppentermins betrifft nur die eigene Liste.

Archiv und Wiederherstellung sind in „Prüfungen“ erreichbar; globale Gruppentermine werden in der Gruppe verwaltet. Dateien werden einzeln archiviert und können wiederhergestellt werden. Archivieren löscht weder Sessionzuordnungen noch Noten, Dateiinhalte oder Veröffentlichungen.

Titel-, Fach- und Datumsänderungen verändern niemals gespeicherte Sessions oder den Fachwert eines gestarteten Timers. Noten- und Terminänderungen besitzen eine Historie. Konflikte gleichzeitiger Änderungen verlangen erneutes Laden statt stillen Überschreibens.

Beim Gruppenaustritt bleiben eigene Ergebnisse und Sessions erhalten. Der zuletzt zugängliche Terminstand wird für die eigene Historie eingefroren; neue Gruppenänderungen und Gruppenunterlagen sind nicht mehr zugänglich. Nach Wiedereintritt ist der aktuelle Termin wieder verfügbar. Gruppenfreigaben des austretenden Autors werden zurückgenommen.

Alttabellen `exams`, `group_exams` und `exam_files` bleiben unverändert als schreibgeschützter Bestand bestehen. Sie werden nicht mehr als aktive V2-Datenquelle beschrieben. Bestehende Privatdateien bleiben privat, auch wenn ihre Prüfung einen Gruppentermin referenziert.

## Teilen, Feed und Dateien

Prüfungsergebnisse sind zunächst privat. Beim freiwilligen Teilen eine konkrete Haupt- oder Untergruppe wählen. Note, gesamte Lernzeit und Sessionanzahl sind unabhängig auswählbar und zunächst abgewählt. Die Vorschau zeigt die Auswahl.

Beiträge sind Momentaufnahmen; spätere Änderungen aktualisieren sie nicht. Nicht ausgewählte Kennzahlen fehlen in der Serverantwort. Freigaben können ohne Löschen der Historie zurückgenommen werden. Bei Gruppenbeiträgen dürfen alle aktuell berechtigten Gruppenmitglieder kommentieren und antworten. Öffentliche Beiträge erfordern weiterhin eine bestätigte Freundschaft oder den eigenen Beitrag. Antworten beziehen sich auf den konkreten Kommentar, auch bei Antworten auf Antworten. Die Anzeige bleibt flach und aufklappbar; es werden keine Texte automatisch eingefügt.

Alte bewusst veröffentlichte Beiträge behalten ihre bisherige Sichtbarkeit für alle angemeldeten Personen. Sessionbeiträge beginnen privat und können bewusst mit einer Gruppe oder öffentlich geteilt werden. Das Teilen ändert keine Rankingfreigabe. In den Sessiondetails kann die Lernzeit unabhängig im Ranking veröffentlicht oder zurückgenommen werden; jede Session zählt einmal. Ergebnisfreigaben für Gruppen veröffentlichen keine Sessions und verändern das globale Ranking nicht. Das Ausblenden eines Sessionbeitrags nimmt die bereits veröffentlichte Sessionzeit nicht aus dem Ranking.

PDF, PNG und JPEG: 5 MiB je Datei, 200 MiB insgesamt einschließlich Dateiarchiv. Signatur und Endung werden geprüft. Downloads sind geschützt; eine Ergebnisfreigabe erteilt keinen Dateizugriff. Keine Viren- oder Inhaltsanalyse. Altdatei-URLs bleiben geschützt erreichbar.

## Übersicht, Feed und persönliches Wochenziel

- Prüfungen: Anstehend, Abgeschlossen und Archiv mit Anzahl. Archivstatus hat Vorrang. Eine Hauptaktion je Karte; Zusatzaktionen im Menü. Offene vergangene Termine bleiben gekennzeichnet anstehend.
- Startseite: zuerst laufender Timer, sonst die wichtigste startbare Prüfung oder eine freie Session; darunter Kennzahlen und Historie.
- Gruppen: Meine Gruppen und Entdecken, Hauptgruppen mit aufklappbaren Untergruppen. Die Darstellung ändert keine Zugriffsrechte.
- Änderungen: vollständige Anzahl in der Kopfzeile; Details und weitere Seiten im Dialog. Gelesen und Alle gelesen markieren bestehende Hinweise, ohne sie zu löschen.
- Handy bis 700 Pixel: feste untere Navigation mit Start, Lernen, Prüfungen, Feed und Mehr. Unter Mehr liegen Gruppen, Statistik, Ranking und Profil.
- Feed: Alle, Meine Gruppen (optional eine Gruppe), Freunde und Öffentlich. Serverseitige Filterung vor 50 Beiträgen je Seite; Weitere Beiträge lädt ältere passende Einträge. Auswahl bleibt innerhalb der Anmeldung erhalten.
- Kommentare: zunächst die letzten drei Hauptkommentare und zwei Antworten je Diskussion; ältere Einträge aufklappbar. Antworteditor startet leer. Austritt und Freigaberücknahme entziehen auch Antwortzugriff, ohne Diskussionen zu löschen.
- Statistik: freiwilliges privates Wochenziel in Viertelstunden (0,25–168 Stunden), sechs Wochen Lernzeit und Vergleich mit denselben Wochentagen der Vorwoche. Nur gespeicherte Sessions zählen, einschließlich privater und archivierter Prüfungen; laufende Timer zählen erst nach Speichern. Wochenwerte sind unabhängig vom Detailfilter.

API-Ergänzungen: `GET /api/v2/feed?filter=all|groups|friends|public`, optional `group_id` und `before_id`; `GET /api/v2/statistics`; `GET /api/v2/notices`, optional `before_id`; POST `weekly-goal` mit `weekly_goal_minutes` oder `null`, `notices-read-all` und `comment` mit optionalem `parent_comment_id`. Alle Routen verwenden weiterhin Anmeldung und bei Änderungen CSRF-Schutz.

## Backup und Tests

Ein vollständiges Backup ist eine konsistente SQLite-Sicherung; die Datenbank enthält auch Datei-BLOBs. CSV ist kein vollständiges Backup: nur die ursprünglichen sechs Sessionattribute, ganze Minuten, keine Konten/Prüfungen/Zuordnungen/Dateien. Ein erneuter Import erzeugt zusätzliche Sessions. Sessions unter einer Minute werden als 0 Minuten exportiert und sind mit diesem ursprünglichen CSV-Vertrag nicht wieder importierbar.

```text
python -m unittest discover -v
```

Tests erstellen separate temporäre Datenbanken unter `data/` und entfernen ausschließlich ihre eigenen Testverzeichnisse. Migrationstests verwenden synthetische Altbestände sowie eine rein lesend erstellte Kopie des vorhandenen Bestands.

Optionaler echter Browsertest mit Node.js und Playwright (nur Testwerkzeuge):

```text
node test_browser.cjs
node test_browser_extended.cjs
node test_browser_v4.cjs
```

Optional `LEARNO_TEST_PYTHON`, `LEARNO_BROWSER_EXECUTABLE`, `LEARNO_BROWSER_TEMP_ROOT` und `LEARNO_BROWSER_SCREENSHOT` setzen. Der Test startet einen eigenen Server mit separater Datenbank, zwei Browserkonten und mobilem Viewport. Er prüft Noten 1–5, Timer, Archiv, Gruppen, Dateien, Freigaben, Antworten, Filter, Wochenziel, Hinweise und die Bedienung auf 320/390/700 Pixel Breite.

## Struktur und Grenzen

- `app.py`: HTTP, Authentifizierung, CSV und persönliche Einstellungen.
- `insights.py`: Feedpagination, Hinweise und private Wochenstatistik.
- `v2.py`: Fachregeln, Berechtigungen, Termine, Ergebnisse, Archiv und Feed.
- `migrate.py` / `legacy_schema.py`: explizite Migration und unverändertes Ausgangsschema.
- `static/app.js` / `static/v2.js` / `static/ui.js`: Ansichten mit einer gemeinsamen Formular- und Aktionssteuerung.
- `wsgi.py` / `pythonanywhere_wsgi.py`: Hosting-Einstieg ohne automatische Migration.
- `test_app.py`, `test_v2.py`, `test_migration.py`, `test_community.py`, `test_browser.cjs`: Regressionen und Datenerhalt.

Erinnerungen benötigen einen geöffneten Browser und ein waches Gerät. Die Timeranzeige bietet Zehntelsekunden, aber keine messtechnisch garantierte Genauigkeit; Systemuhränderungen können die Dauer beeinflussen. Eine Session über Mitternacht gehört ihrem Startdatum. Serverdatum und Browserdatum sollten dieselbe Zeitzone verwenden. Kein Passwort-Reset, keine Streaks und kein Offlinebetrieb.

## Aktivitätsablauf und Freigaben (V4)

Der Feed bietet direkt Beitrag verfassen und Meine Beiträge. Quelle ist eine eigene gespeicherte Session oder ein benotetes Prüfungsergebnis. Texte bleiben frei; es gibt keine Vorlagen. Sessionlernzeit und Ergebniskennzahlen sind zunächst abgewählt. Die Rankingfreigabe wird gesondert in Sessiondetails verwaltet; die Profilübersicht zeigt beide Freigabearten.

Kommentar-/Antwortentwürfe werden nur im Arbeitsspeicher pro Konto, Beitrag und Antwortbezug gehalten. Navigation, Aufklappen und Fehler erhalten sie; erfolgreiches Senden oder Abmelden entfernt sie. Ein Browserneustart erhält diese Entwürfe nicht. Diskussionen werden gezielt aktualisiert und Antworten verweisen auf den Bezugskommentar.

Eine Timerleiste bleibt auf allen Ansichten erreichbar. Nach dem Speichern erscheint eine freiwillige Teilen-Aktion. Prüfungen lassen sich nach Fach/Titel suchen und nach Termin/Fach sortieren; Gesamtanzahlen bleiben unverändert. Auf dem Handy erscheinen Sessions als Karten.

API: POST `session-ranking` mit `session_id` und booleschem `public`; POST `post` für Sessions mit `session_id`, optionalem `audience` (Standard `private`), `target_group_id` bei `group` und `show_seconds` (0/1). Ergebnisfreigaben unterstützen weiterhin ausschließlich privat oder Gruppe. GET `feed?filter=mine` filtert eigene Beiträge vor Pagination. Neue Sessionantworten liefern `session_id`, Prüfungszustände `deletion_mode`, Zustandsantworten zusätzlich `own_posts`.


## Statistik und bestätigte Beitragslöschung

Die Statistik beginnt mit Fach-/Datumsfiltern und Kennzahlen. Lernzeit nach Fach und sechs Kalenderwochen erscheinen als stehende Säulen mit gemeinsamer Skala; Wochen bleiben vom Filter unabhängig. Das freiwillige Wochenziel steht unten in einem eingeklappten Bereich.

Eigene Feedbeiträge bieten ein Drei-Punkte-Menü. Rücknahme erhält den Beitrag privat. POST `/api/v2/post-delete` mit `post_id` löscht nach ausdrücklicher Bestätigung einen eigenen Beitrag einschließlich aller Kommentare und Antworten endgültig. Anmeldung, CSRF und Eigentumsprüfung sind erforderlich; die Löschung erfolgt innerhalb einer `BEGIN IMMEDIATE`-Transaktion mit aktivierten Fremdschlüsseln. Sessions, Ergebnisse, Dateien, Feedback und Rankingfreigaben bleiben erhalten. Es gibt keinen Papierkorb; bestehende Backups können frühere Inhalte enthalten. Alte Beiträge erhalten keine erratene Sessionreferenz. Kein neues Schema oder Migration nötig.
