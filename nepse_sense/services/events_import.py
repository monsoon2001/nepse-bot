from pathlib import Path

from nepse_sense.services.csv_import import CSVImporter


def import_events_from_default():
    """Import events from data/events.csv"""
    importer = CSVImporter()
    events_file = Path("data/events.csv")
    if events_file.exists():
        return importer.import_events_csv(events_file)
    return 0
