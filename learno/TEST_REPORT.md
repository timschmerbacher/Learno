# Funktionsprüfung V5 – 7. Oktober 2026

Getestet wurde der aktuelle lokale Repository-Stand. Schreibende Prüfungen verwenden ausschließlich separate Testdatenbanken, Serverports und Browserprofile. Die Prüfung erfolgt nach Umsetzung der V4-Funktionen. Schreibende Tests verwenden keine bestehenden Nutzerdaten. Die explizite lokale Migration erhält sämtliche ursprünglichen Spaltenwerte; reproduzierbare Tests wurden ergänzt.

## Ergebnis

Nachprüfung am 7. Oktober: Feedback zeigt „Admins“ statt eines Kontonamens. Drei Feedback-Szenariogruppen erneut bestanden, darunter Touch-Emulation mit mobilem Viewport und doppelter Pixeldichte. Auf 320, 390 und 700 Pixeln wurden Feedback gesendet, Entwürfe geprüft und sämtliche Ansichten über die untere Navigation beziehungsweise „Mehr“ geöffnet. Kein horizontaler Überlauf. Bestehender Browsertest und sechs V4-Szenariogruppen ebenfalls erneut bestanden, einschließlich gefüllter Prüfungs-/Feedansichten und unverändertem Timer. Keine echten Geräte, Safari oder native Bildschirmtastatur emuliert.

- Python: aktuell 65 Tests bestanden, kein erwarteter Fehlschlag; die vier neuen Löschtests sind im Nachtrag beschrieben.
- Bestehender Edge-Browsertest: bestanden; zwei Konten und Ansichten auf 320, 390 und 700 Pixel Breite.
- Erweiterter Edge-Browsertest: acht Szenariogruppen bestanden. V4-Browsertest: sechs weitere Szenariogruppen bestanden; Entwürfe, direkte Freigaben, unabhängiges Ranking, Prüfungssuche, Timerleiste, gespeicherte Sessionbestätigung und mobiles Layout.

- Feedback: fünf Backendtests und drei Browser-Szenariogruppen; Absender-/Empfängerrechte, CSRF, unveränderliche Inhalte, Entwürfe und mobiles Layout.
- Updatewerkzeuge: vier Tests für Quellpaket-Hashes, additive Installation, unveränderte Originaldaten und Backups ohne Überschreiben.

## Funktionsabdeckung

| Bereich | Geprüfte Abläufe |
|---|---|
| Konten und Anmeldung | Registrierung, ungültige und doppelte Konten, falsches Passwort, Login, Logout, mehrere Anmeldungen, abgelaufene Tokens, Passwort-/Tokenhashes, persistente Anmeldelimits |
| Profil und Freunde | Einstellungen und Zeitzone, Validierung, Speicherung und Benutzertrennung, Anfragen, Annahme, Ablehnung, Duplikate und unberechtigte Anfragen |
| Haupt- und Untergruppen | Erstellen, Beitreten, erforderliche Hauptmitgliedschaft, Verwaltung, Austritt/Wiedereintritt, Geschwistergruppen ohne Zugriff, keine dritte Ebene |
| Prüfungen und Ergebnisse | Persönliche und gemeinsame Termine, Übernahme ohne Terminkopie, Noten 1–5, Notenhistorie, Versionskonflikte, Archiv/Wiederherstellung, Löschen unbenutzter Prüfungen, drei Ansichten |
| Timer | Start, Abbruch des Startdialogs, Pause, Fortsetzen, Stoppen, Speichern, Verwerfen, wiederholte Steueraktionen, exakte Pausenzeit, Reload/Neuanmeldung, ungültiges Speichern erhält Timer |
| Lernsessionen | Nachtragen, Validierung und Grenzen, Lernorte, Hilfsmittel, Zuordnung und Eigentum, unveränderte historische Inhalte, Sessionabschluss nach Benotung |
| Dateien | PDF/PNG/JPEG-Signaturen, ungültige Namen und Übertragung, Eigentums-/Gruppenrechte, Archiv und Wiederherstellung, Speicherlimit einschließlich Archiv, echter 5-MiB-Upload und bytegenauer Download, Ablehnung bei 5 MiB + 1 Byte |
| Feed und Diskussionen | Filter vor Pagination, ältere passende Beiträge, alle Freigabekombinationen ohne versteckte JSON-Kennzahlen, private Momentaufnahmen, Rücknahme, Gruppen-/Freundschaftsrechte, Antworten auf Antworten, Bezug zum richtigen Beitrag, 500-Zeichen-Regel und Sperrwortprüfung |
| Statistik und Ranking | Fach-/Datumsfilter, private Wochenziele und Grenzen, Jahreswechsel, sechs Wochen und vergleichbare Vorwoche, gespeicherte/private Lernzeit, kein aktiver Timer im Ziel, öffentliche Zeit nur einmal trotz mehrerer Beiträge |
| Hinweise | Vollständiger ungelesener Zähler, Pagination, Einzelmarkierung und Alle gelesen, Erhalt der Hinweisdatensätze |
| Import und Export | Echter Browserdownload, BOM/Umlaute/Anführungszeichen, Sechs-Spalten-Vertrag, CSV-Rundlauf, ungültige Zeilen/Datumswerte/Spalten, leere Daten und vollständiger Rollback bei mehr als 5000 Zeilen |
| HTTP und Sicherheit | Authentifizierung, CSRF, fremder Origin, ungültiges JSON und Anfragegrößen, unbekannte Routen, verbotene Methoden, HEAD, Cache-/Sicherheitsheader, kein direkter Datenbankdownload |
| Migration und Parallelität | Additive V2/V3-Schritte, geprüfte Backups ohne Überschreiben, Bestandsvergleich und Fremdschlüssel, Wiederholbarkeit und Rollback, keine Startup-Migration, konkurrierendes Übernehmen/Benoten/Speichern/Archivieren |
| Bedienung | Desktop/mobile Navigation, Filterwechsel, Dialogabbruch und Formularvalidierung, Menüs per Tastatur, kein horizontaler Dokumentüberlauf in geprüften Ansichten, laufender Timer bei Navigation erhalten |

## Behobene Befunde und V4-Abnahme

- Überlange Datei-IDs werden vor SQLite kontrolliert mit HTTP 404 abgelehnt.
- Kommentar-/Antwortentwürfe bleiben bei Aufklappen, Filterwechsel, Navigation und fehlgeschlagenem Senden erhalten; erfolgreiches Senden und Abmelden löschen den jeweiligen Entwurf. Andere Diskussionen werden beim Aufklappen nicht neu aufgebaut.
- Beitragssichtbarkeit und Rankingfreigabe werden ausdrücklich getrennt verwaltet. Rücknahme eines Beitrags lässt eine bewusst aktive Rankingfreigabe erhalten und erklärt das.
- Dialogüberschriften sind mit `aria-labelledby` verknüpft; Formularfehler besitzen einen Alert-Bereich.
- Neue Sessionbeiträge haben eine echte Sessionreferenz, beginnen privat und enthalten keine nicht gewählten Kennzahlen im JSON. Altbeiträge bleiben ohne geratene Referenz.
- V3→V4-Migration erhält öffentliche Sessions, Originalwerte und laufende Timer exakt; wiederholte Migration ändert nichts.

Weitere beobachtete Verhaltensweisen: Manuelle historische Nachträge sind auch für benotete oder archivierte Prüfungen möglich, während neue Timerstarts gesperrt sind. Unberechtigte Annahme-/Ablehnungsversuche für Freundschaften verändern keine Daten, melden aber Erfolg statt eines Fehlers. Diese Punkte brauchen eine Produktentscheidung, keine automatische Datenkorrektur.

## Wiederholen

```text
python -B -m unittest discover -v
node test_browser.cjs
node test_browser_extended.cjs
node test_browser_v4.cjs
node test_browser_feedback.cjs
```

Die Browserprüfungen benötigen Playwright und gegebenenfalls die Umgebungsvariablen `NODE_PATH`, `LEARNO_TEST_PYTHON`, `LEARNO_BROWSER_EXECUTABLE` und `LEARNO_BROWSER_TEMP_ROOT`. Alle Befehle werden im Ordner `learno/` ausgeführt.

## Grenzen

Die Matrix deckt die vorhandenen Funktionsbereiche und viele Fehlerpfade ab, beweist aber nicht sämtliche denkbaren Eingaben und Ausfälle. Nicht praktisch geprüft wurden echte Handytastaturen, Safari/iOS, Screenreader, tatsächliche Browserbenachrichtigungen auf einem schlafenden Gerät, größere Last sowie Prozess-/Stromausfall während einer SQLite-Schreibtransaktion. Die angemeldeten Schreibabläufe wurden bewusst auf isolierten Datenbanken durchgeführt.



## Statistik, Feed und endgültige Beitragslöschung – 7. Oktober 2026

65 Python-Tests bestanden. Neue Löschtests prüfen Eigentum, Anmeldung, CSRF, private/zurückgenommene/alte Beiträge, verschachtelte fremde Antworten, konkurrierende Kommentare und vollständigen Rollback bei einer unerwarteten Fremdschlüsselbeziehung. Originalspalten aller übrigen fachlichen Tabellen werden verglichen, einschließlich gespeicherter Datei-BLOBs, Noten, Feedback und Rankingfreigaben.

Browser: bestehender V2-Ablauf sowie 5 neue Statistik-/Feed-Szenarien, 6 V4-, 8 erweiterte und 3 Feedback-Szenarien bestanden. Touch-/Viewportprüfungen bei 320, 390 und 700 Pixeln, gemeinsame Diagrammskala, 6/3 Fachsäulen pro Reihe, Filter, leere Statistik, optionales/deaktiviertes Ziel, mehrzeiliger Text, Tastaturmenü, Löschabbruch und Bestätigung, andere Entwürfe und Timererhalt. Ein alter V4-Test erwartete die ersetzte Rankingbeschriftung und scheiterte daran; mit der neuen Formulierung besteht er. Ein tatsächlicher Formularfehler beim Deaktivieren wurde behoben: Aktionsbuttons verwenden explizit `type="button"`.

Zusätzlicher Aufruf: `node test_browser_feed_stats.cjs`. Schreibende Tests ausschließlich gegen isolierte Testdatenbanken. Kein neues Schema und keine Migration. Keine Löschtests mit bestehenden Online-Beiträgen. Echte Smartphones, Safari und native Bildschirmtastaturen bleiben gesonderte Geräteprüfungen.
