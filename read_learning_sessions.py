import csv


def read_learning_sessions(file_path):
    """Read learning sessions and return a list of dictionaries."""
    expected_columns = [
        "date",
        "duration_minutes",
        "learning_resources",
        "learning_location",
        "interruptions",
        "subject",
    ]
    sessions = []

    try:
        # utf-8-sig supports UTF-8 files with or without a BOM.
        with open(file_path, mode="r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)

            if reader.fieldnames != expected_columns:
                raise ValueError("Die CSV-Spalten fehlen oder sind falsch angeordnet.")

            for row in reader:
                line = reader.line_num

                # Reject missing fields, extra fields and empty values.
                if None in row or any(
                    value is None or not value.strip()
                    for value in row.values()
                ):
                    raise ValueError(f"Zeile {line}: Fehlende oder zusätzliche Daten.")

                # Convert the two numeric fields.
                try:
                    row["duration_minutes"] = int(row["duration_minutes"])
                    row["interruptions"] = int(row["interruptions"])
                except ValueError as error:
                    raise ValueError(
                        f"Zeile {line}: Dauer und Unterbrechungen "
                        "müssen ganze Zahlen sein."
                    ) from error

                if row["duration_minutes"] <= 0:
                    raise ValueError(f"Zeile {line}: Die Dauer muss positiv sein.")

                if row["interruptions"] < 0:
                    raise ValueError(
                        f"Zeile {line}: Unterbrechungen dürfen nicht negativ sein."
                    )

                # Validate the ISO date without importing another module.
                date = row["date"]
                if (
                    len(date) != 10
                    or date[4] != "-"
                    or date[7] != "-"
                    or any(
                        character not in "0123456789"
                        for character in date[:4] + date[5:7] + date[8:]
                    )
                ):
                    raise ValueError(
                        f"Zeile {line}: Das Datum muss das Format YYYY-MM-DD haben."
                    )

                year = int(date[:4])
                month = int(date[5:7])
                day = int(date[8:])
                leap_year = year % 4 == 0 and (
                    year % 100 != 0 or year % 400 == 0
                )
                days_per_month = [
                    31, 29 if leap_year else 28, 31, 30, 31, 30,
                    31, 31, 30, 31, 30, 31,
                ]

                if (
                    year < 1
                    or not 1 <= month <= 12
                    or not 1 <= day <= days_per_month[month - 1]
                ):
                    raise ValueError(f"Zeile {line}: Ungültiges Kalenderdatum.")

                sessions.append(row)

    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Die Datei '{file_path}' wurde nicht gefunden."
        ) from error
    except (csv.Error, UnicodeError) as error:
        raise ValueError(
            f"Die Datei enthält ungültige CSV- oder UTF-8-Daten: {error}"
        ) from error

    return sessions


if __name__ == "__main__":
    try:
        learning_sessions = read_learning_sessions("learning_sessions.csv")

        if not learning_sessions:
            print("Keine Lernsessions vorhanden.")

        for number, session in enumerate(learning_sessions, start=1):
            print(f"\nLernsession {number}")
            print(f"  Datum:           {session['date']}")
            print(f"  Fach:            {session['subject']}")
            print(f"  Lerndauer:       {session['duration_minutes']} Minuten")
            print(f"  Lernhilfsmittel: {session['learning_resources']}")
            print(f"  Lernort:         {session['learning_location']}")
            print(f"  Unterbrechungen: {session['interruptions']}")

    except (OSError, ValueError) as error:
        print(f"Fehler: {error}")