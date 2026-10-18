from nepse_sense.db.engine import engine
from nepse_sense.db.models import Base
from nepse_sense.services.csv_import import CSVImporter


def test_csv_import_prices():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    importer = CSVImporter()
    count = importer.import_prices_csv("tests/fixtures/sample_prices.csv")
    assert count == 2
    importer.db.close()


def test_csv_import_fundamentals():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    importer = CSVImporter()
    count = importer.import_fundamentals_csv("tests/fixtures/sample_fundamentals.csv")
    assert count == 1
    importer.db.close()
