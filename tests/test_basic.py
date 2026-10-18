def test_imports():
    from nepse_sense import __version__

    assert __version__ == "0.1.0"


def test_config():
    from nepse_sense.config import settings

    assert settings.timezone == "Asia/Kathmandu"


def test_doctor_runs():
    # Just ensure doctor module is importable
    from nepse_sense import doctor

    assert doctor is not None
