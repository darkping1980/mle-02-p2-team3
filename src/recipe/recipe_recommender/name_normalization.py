"""적재와 추천 Service가 공유하는 식재료명 비교 규칙."""


def normalize_name(value: str) -> str:
    """식재료명 매칭과 중복 제거에 쓸 비교 문자열로 정규화한다.

    Args:
        value (str): 사용자 입력 또는 DB의 식재료·별칭.

    Returns:
        str: 앞뒤 공백을 제거하고 소문자로 바꾼 이름.
    """
    return value.strip().lower()
