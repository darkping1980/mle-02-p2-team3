import pytest

from card_benefit.payment_card.file_pipeline.graph.normalize_values import (
    parse_amount, parse_condition, parse_per_unit, parse_range, parse_rate,
)


@pytest.mark.parametrize("raw,want", [
    ("5만원", 50000), ("3천원", 3000), ("1억", 100000000),
    ("10,000원", 10000), ("1만 5천원", 15000), ("0원", 0),
    ("12원", 12), ("2만원", 20000), ("1천 2백원", None),
    ("5만원 이상", None), ("", None), ("5%", None),
])
def test_amount_boundaries(raw, want):
    result = parse_amount(raw)
    if want is None:
        assert result is not None and "unparsed" in result
    else:
        assert result["raw"] == raw and result["amount"] == want and result["unit"] == "원"


@pytest.mark.parametrize("raw,want", [("5%", .05), ("0.5%", .005), ("100%", 1), ("0%", 0), ("1,5%", None), ("5", None), ("-5%", None)])
def test_rate_boundaries(raw, want):
    result = parse_rate(raw)
    if want is None:
        assert "unparsed" in result
    else:
        assert result["rate"] == want and result["raw"] == raw


@pytest.mark.parametrize("raw,amount,unit,per", [
    ("리터당 50원", 50, "원", "리터"), ("건당 2%", 2, "%", "건"),
    ("회당 1,000원", 1000, "원", "회"), ("매당 0.5포인트", .5, "포인트", "매"),
])
def test_per_unit(raw, amount, unit, per):
    assert parse_per_unit(raw) == {"raw": raw, "amount": amount, "unit": unit, "per": per}


@pytest.mark.parametrize("raw,key,want", [
    ("3만원 이상", "min", 30000), ("5만원 이하", "max", 50000),
    ("1만원 이상", "min", 10000), ("0원 이상", "min", 0),
    ("월 1회", "count", 1), ("월 6회", "count", 6),
    ("연 4회", "count", 4), ("일 2회", "count", 2),
])
def test_condition(raw, key, want):
    result = parse_condition(raw)
    assert result["raw"] == raw and result[key] == want


@pytest.mark.parametrize("raw,want", [("1~3%", (.01, .03)), ("0.5~1.5%", (.005, .015)), ("3-5%", (.03, .05))])
def test_ranges(raw, want):
    result = parse_range(raw)
    assert (result["min_rate"], result["max_rate"]) == want
    assert result["raw"] == raw


@pytest.mark.parametrize("fn,raw", [
    (parse_amount, "약 5만원"), (parse_amount, "5만원 초과"),
    (parse_rate, "최대 5%"), (parse_range, "3~1%"),
    (parse_condition, "월 2~3회"), (parse_condition, "전월실적"),
    (parse_per_unit, "리터 50원"), (parse_per_unit, "리터당 50"),
])
def test_unparsed_is_explained(fn, raw):
    result = fn(raw)
    assert result["raw"] == raw and result["unparsed"]


def test_none_and_non_string_inputs_are_not_guessed():
    for fn in (parse_amount, parse_rate, parse_condition, parse_range, parse_per_unit):
        assert fn(None) is None
        assert fn(5)["unparsed"] == "empty_or_non_string"


def test_expands_unambiguous_reverse_per_unit_and_embedded_condition_thresholds():
    assert parse_per_unit("1,000원당 2마일") == {
        "raw": "1,000원당 2마일", "amount": 2, "unit": "마일", "per": "1000원"
    }
    assert parse_condition("지난달 실적 30만원 이상")["min"] == 300000
    assert parse_condition("전월 이용금액 30만원 이상")["min"] == 300000


def test_range_parser_accepts_numeric_bounds_with_amount_units():
    assert parse_range("30만원 이상 ~ 50만원 미만") == {
        "raw": "30만원 이상 ~ 50만원 미만", "min_amount": 300000, "max_amount": 500000, "unit": "원"
    }


def test_amount_parser_accepts_clear_monetary_value_labels():
    assert parse_amount("3만원 할인") == {"raw": "3만원 할인", "amount": 30000, "unit": "원"}
    assert parse_amount("1만 5천원 교환권") == {
        "raw": "1만 5천원 교환권", "amount": 15000, "unit": "원"
    }
    assert "unparsed" in parse_amount("최대 3만원 할인")


def test_ambiguous_ranges_and_upper_bound_rate_remain_unparsed():
    assert "unparsed" in parse_rate("최대 5%")
    assert "unparsed" in parse_condition("월 2~3회")
    assert "unparsed" in parse_range("숙박 1.0~2.0 / 예약 2.0~3.0")
