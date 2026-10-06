# Learno kostenlos mit eurer Gruppe testen

## Empfohlene Lösung: PythonAnywhere Beginner

Stand der Prüfung: 3. Oktober 2026. Für einen kleinen Gruppentest eignet sich die kostenlose PythonAnywhere-Web-App mit SQLite. Sie bietet **eine Web-App, einen Web-Worker und 512 MiB Speicher**. Die Web-App hat **eine Laufzeit von einem Monat**, die im Anbieter-Dashboard regelmäßig verlängert werden muss. Die 100 täglichen CPU-Sekunden des Gratis-Kontos betreffen Konsolen und Hintergrundaufgaben, nicht die normalen Web-Anfragen.

Keine Kreditkarte oder ein kostenpflichtiges Paket für dieses Projekt auswählen. Die jeweils im Registrierungsdialog angezeigten Bedingungen gelten. Ein Providerkonto wird benötigt; eure Mitstudierenden brauchen anschließend nur ein eigenes Learno-Konto.

Die App ist vorbereitet, aber noch nicht online veröffentlicht. Der getestete WSGI-Einstieg ist `wsgi.py`. `python app.py` wird nur für den lokalen Start verwendet, nicht zum Hosten auf PythonAnywhere.

## Schritt für Schritt

1. Unter **https://eu.pythonanywhere.com/** ein kostenloses **Beginner-Konto** anlegen. Falls dort kein kostenloses Konto angeboten wird, den kostenlosen Tarif unter **https://www.pythonanywhere.com/pricing/** prüfen. Im EU-System liegt die Installation näher an eurer Gruppe in Österreich.
2. Im Bereich **Files** die Datei `Learno_VSCode.zip` in dein Home-Verzeichnis hochladen.
3. Unter **Consoles → Bash** folgende Befehle ausführen:

   ```bash
   cd ~
   python3 -m zipfile -e Learno_VSCode.zip .
   cd ~/learno
   python3 -m unittest -v
   ```

   Es werden keine zusätzlichen Python-Pakete benötigt. Die Tests verwenden temporäre Datenbanken und benötigen keinen Netzwerkport.

4. Unter **Web → Add a new web app** die angebotene kostenlose Subdomain auswählen. Danach **Manual configuration** und **Python 3.10 oder neuer** wählen. Kein Django-/Flask-Starterprojekt erstellen.
5. Als Source code und Working directory `/home/DEIN_BENUTZERNAME/learno` eintragen. `DEIN_BENUTZERNAME` durch deinen tatsächlichen PythonAnywhere-Benutzernamen ersetzen.
6. Den Link zur **WSGI configuration file** öffnen. Den Vorlageninhalt durch den Inhalt der mitgelieferten Datei `pythonanywhere_wsgi.py` ersetzen und speichern. Diese Vorlage bestimmt deinen Home-Pfad automatisch; sie enthält keine zu ersetzenden Zugangsdaten.
7. Im Web-Bereich **Force HTTPS** einschalten. Keine statische Zuordnung zum gesamten Projektordner oder zu `data/` anlegen: Unterlagen dürfen nur über die geschützte Downloadroute erreichbar sein. Die App liefert ihre Oberflächendateien selbst aus.
8. **Reload** drücken und anschließend den vom Dashboard angegebenen **HTTPS-Link** öffnen. Den tatsächlichen Link aus dem Dashboard verwenden; die Subdomain unterscheidet sich zwischen EU- und US-System.
9. In Learno registrieren, eure Lerngruppe erstellen und eine gemeinsame Prüfung anlegen.
10. Den HTTPS-Link an die Gruppe weitergeben. Alle registrieren sich selbst, suchen die Gruppe, treten direkt bei und übernehmen gewünschte Prüfungen bewusst.

Der eigene Computer kann danach ausgeschaltet sein. App und Daten liegen auf dem gemeinsamen Server.

## Vor dem Gruppentest prüfen

- Zwei verschiedene Konten auf zwei Geräten verwenden.
- Eine Person erstellt eine Gruppe; die andere tritt bei.
- Eine Gruppenprüfung bleibt bei der zweiten Person zunächst außerhalb der eigenen Prüfungsliste. Erst nach **Zu meinen Prüfungen hinzufügen** erscheint sie dort.
- Die erstellende Person ändert den Termin. Die andere Person öffnet erneut **Prüfungen** oder lädt die Seite neu: Terminänderung und Hinweis müssen sichtbar sein.
- Eine PDF hochladen und als Mitglied herunterladen. Ein Konto außerhalb der Gruppe darf denselben Downloadlink nicht öffnen können.
- Eine persönliche Prüfung entfernen: Lernsessions bleiben erhalten, Gruppenprüfung bleibt bestehen.
- App im Anbieter-Dashboard neu laden und erneut anmelden bzw. Sitzung weiterverwenden: Die gespeicherten Daten müssen erhalten bleiben.

## Gratis-Grenzen und Betrieb

- Kostenloser Tarif: 512 MiB gesamter Speicher und ein Web-Worker. SQLite ist dort verfügbar, wird vom Anbieter aber nicht für größere Produktionssysteme empfohlen. Für eure kleine Testgruppe ist das eine praktikable erste Lösung, kein unbegrenzt skalierbarer Dienst.
- Die App begrenzt Dateien auf **5 MiB pro Datei** und insgesamt **200 MiB aktive Dateiinhalte**. Der übrige Platz bleibt für Datenbankverwaltung, Programm und Providerdateien. Große Skriptensammlungen benötigen mehr Speicher.
- PDF, PNG und JPEG werden akzeptiert. Endung und Dateisignatur werden geprüft. Keine Virenprüfung und keine automatische Bild-/Textmoderation der Unterlagen.
- Gruppen sind offen. Mitgliedschaft schützt Dateien vor unangemeldeten Personen und Nichtmitgliedern, aber jeder registrierte Benutzer kann beitreten.
- Erinnerungen benötigen weiterhin einen geöffneten Browser und ein waches Gerät; keine Push-Erinnerungen bei geschlossener App.
- Im **Web**-Dashboard das Ablaufdatum im Blick behalten und die Laufzeit spätestens vor Ablauf des Monats verlängern. Es wird hier keine automatische Verlängerung eingerichtet.
- Im Handy-Browser lässt sich der Link als Lesezeichen bzw. auf dem Homescreen ablegen. Eine native App oder Offline-App ist nicht enthalten.

## Update einer bestehenden Installation

Die Datenbank wird beim Start automatisch um die neuen Tabellen und die Gruppenverknüpfung erweitert. Bestehende Konten und Lernsessions bleiben erhalten. Lokal vorher die App beenden und `data/learno.db` sichern. Danach die neuen Programmdateien in den bisherigen `learno`-Ordner kopieren. `data/` nicht löschen oder mit einer leeren Datenbank ersetzen.

Online vor einem Update ein Datenbank-Backup herunterladen. Die neue ZIP enthält bewusst keine Benutzer-Datenbank. Nach dem Entpacken im Web-Dashboard **Reload** drücken.

## Backup

Für ein konsistentes Backup in der PythonAnywhere-Bash-Konsole im Ordner `~/learno` ausführen:

```bash
python3 -c "import sqlite3; source=sqlite3.connect('data/learno.db'); target=sqlite3.connect('learno-backup.db'); source.backup(target); target.close(); source.close()"
```

Danach `learno-backup.db` unter **Files** herunterladen und die Serverkopie bei knappem Speicher entfernen. Die Datenbank enthält auch hochgeladene Unterlagen. Ein CSV-Export allein ist kein vollständiges Backup.

## Offizielle Quellen

- Gratis-Funktionen: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- Preise: https://www.pythonanywhere.com/pricing/
- Datenbanken und SQLite-Einschränkungen: https://help.pythonanywhere.com/pages/KindsOfDatabases/
- Web-App und manuelle Konfiguration: https://help.pythonanywhere.com/pages/WebAppBasics/
- HTTPS erzwingen: https://help.pythonanywhere.com/pages/ForcingHTTPS
