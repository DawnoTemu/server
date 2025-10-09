import pytest

from utils.credits import calculate_required_credits, get_credit_config


@pytest.mark.parametrize(
    "length, expected",
    [
        (0, 1),
        (1, 1),
        (999, 1),
        (1000, 1),
        (1001, 2),
        (1999, 2),
        (2000, 2),
        (2001, 3),
        (10_000, 10),
    ],
)
def test_calculate_required_credits_boundaries(length, expected):
    text = "x" * length
    assert calculate_required_credits(text, unit_size=1000) == expected


def test_calculate_required_credits_unicode_and_config(monkeypatch):
    # Set unit size via config to 500
    from config import Config
    monkeypatch.setattr(Config, "CREDITS_UNIT_SIZE", 500, raising=False)

    # 500 unicode characters -> 1 credit
    txt = "ą" * 250 + "🙂" * 250
    assert len(txt) == 500
    assert calculate_required_credits(txt, unit_size=None) == 1

    # 501 -> 2 credits
    txt2 = txt + "ż"
    assert len(txt2) == 501
    assert calculate_required_credits(txt2, unit_size=None) == 2


def test_minimum_one_credit_with_empty_text():
    assert calculate_required_credits("") == 1
    assert calculate_required_credits(None) == 1


def test_invalid_config_unit_size_falls_back(monkeypatch):
    from config import Config
    # Misconfigure to 0 -> should fall back to 1000 and not crash
    monkeypatch.setattr(Config, "CREDITS_UNIT_SIZE", 0, raising=False)
    assert calculate_required_credits("x" * 1500, unit_size=None) == 2
