"""카드사별 어댑터. 원본 manifest를 공통 항목(entry) 목록으로 바꾸는 일만 한다."""

from . import hana, woori

ADAPTERS = {"hana": hana, "woori": woori}
