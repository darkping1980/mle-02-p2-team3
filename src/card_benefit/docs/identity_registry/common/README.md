# 공통(BRAND_SERVICE) 문서·혜택 목록

> 2026-11-05 PostgreSQL `db_pipeline` 읽기 전용 조회로 생성했다. 실제 테이블: `card_ai_run`, `card_common`, `card_common_bnft`, `card_common_bnft_apply`, `card_common_doc`, `card_doc`, `card_doc_chunk`, `card_doc_page`, `card_extr_stg`, `card_source_evidence`.
> 공통 혜택은 `card_common_bnft`, 카드 적용은 `card_common_bnft_apply`에 있다. 카드별 상품 혜택(`card_product_item`)과는 별개다.

상세 문서는 우리카드 문서만 있다. 하나카드 기존 자료(`../HANA_MP004.json`, `../README.md`)는 수정하지 않았다.

## 우리카드 요약

| card_doc_id | 공통서비스 | 추출 후보 | 등록 | 보류 | 카드 적용 | 상세 |
|---|---|---:|---:|---:|---:|---|
| `20261104_000024` | `WOORI_MASTERCARD_WORLD` | 40 | 1 | 39 | 0 | [README](20261104_000024/README.md) |
| `20261104_000025` | `WOORI_MASTERCARD_PLATINUM` | 34 | 23 | 11 | 0 | [README](20261104_000025/README.md) |
| `20261104_000026` | `WOORI_VISA_INFINITE` | 34 | 0 | 34 | 0 | [README](20261104_000026/README.md) |
| `20261104_000027` | `WOORI_VISA_PLATINUM` | 25 | 6 | 19 | 0 | [README](20261104_000027/README.md) |
| `20261104_000028` | `WOORI_UPI_PLATINUM` | 21 | 13 | 8 | 0 | [README](20261104_000028/README.md) |
| **합계** | | **154** | **43** | **111** | **0** | |

## 전체 공통 문서(DB 기준)

| card_doc_id | 카드사 | doc_cd | card_common | 브랜드·등급 | 쪽 | 등록 공통 혜택(공통서비스 기준) | 카드 적용 | 원문 Markdown | 상세 |
|---|---|---|---|---|---:|---:|---:|---|---|
| `20261102_000004` | 하나카드 | `HANA_VS002_20260317` | `1` VISA_SIGNATURE | VISA / SIGNATURE | 2 | 1 | 1 | [md](../../../data/markdown/common/20261102_000004/manifest.json) | — |
| `20261103_000009` | 하나카드 | `HANA_AE001_20260305` | `6` AMEX_PLATINUM_ELITE | AMEX / PLATINUM_ELITE | 3 | 0 | 0 | [md](../../../data/markdown/common/20261103_000009/manifest.json) | — |
| `20261103_000010` | 하나카드 | `HANA_AP002_20260305` | `7` AMEX_PLATINUM | AMEX / PLATINUM | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000010/manifest.json) | — |
| `20261103_000011` | 하나카드 | `HANA_AP003_20260609` | `7` AMEX_PLATINUM | AMEX / PLATINUM | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000011/manifest.json) | — |
| `20261103_000012` | 하나카드 | `HANA_JP002_20260326` | `None` None | None / None | 1 | 0 | 0 | [md](../../../data/markdown/common/20261103_000012/manifest.json) | — |
| `20261103_000013` | 하나카드 | `HANA_MP001_20260209` | `9` MASTERCARD_PLATINUM | MASTERCARD / PLATINUM | 2 | 33 | 0 | [md](../../../data/markdown/common/20261103_000013/manifest.json) | — |
| `20261103_000014` | 하나카드 | `HANA_MP004_20260209` | `9` MASTERCARD_PLATINUM | MASTERCARD / PLATINUM | 2 | 33 | 0 | [md](../../../data/markdown/common/20261103_000014/manifest.json) | — |
| `20261103_000015` | 하나카드 | `HANA_MW002_20260209` | `11` MASTERCARD_WORLD | MASTERCARD / WORLD | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000015/manifest.json) | — |
| `20261103_000016` | 하나카드 | `HANA_MW003_20260209` | `11` MASTERCARD_WORLD | MASTERCARD / WORLD | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000016/manifest.json) | — |
| `20261103_000017` | 하나카드 | `HANA_UD001_20260324` | `13` UPI_DIAMOND | UPI / DIAMOND | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000017/manifest.json) | — |
| `20261103_000018` | 하나카드 | `HANA_UD002_20260618` | `13` UPI_DIAMOND | UPI / DIAMOND | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000018/manifest.json) | — |
| `20261103_000019` | 하나카드 | `HANA_UP001_20260324` | `15` UPI_PLATINUM | UPI / PLATINUM | 1 | 5 | 0 | [md](../../../data/markdown/common/20261103_000019/manifest.json) | — |
| `20261103_000020` | 하나카드 | `HANA_VI001_20260317` | `16` VISA_INFINITE | VISA / INFINITE | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000020/manifest.json) | — |
| `20261103_000021` | 하나카드 | `HANA_VP001_20230727` | `17` VISA_PLATINUM | VISA / PLATINUM | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000021/manifest.json) | — |
| `20261103_000022` | 하나카드 | `HANA_VP001_20260317` | `17` VISA_PLATINUM | VISA / PLATINUM | 2 | 0 | 0 | [md](../../../data/markdown/common/20261103_000022/manifest.json) | — |
| `20261104_000024` | 우리카드 | `WOORI_BRAND_260225_346dbaa50ad5` | `20` WOORI_MASTERCARD_WORLD | MASTERCARD / WORLD | 2 | 1 | 0 | [md](../../../data/markdown/common/20261104_000024/manifest.json) | [README](20261104_000024/README.md) |
| `20261104_000025` | 우리카드 | `WOORI_BRAND_260225_b05e4c64ec0b` | `21` WOORI_MASTERCARD_PLATINUM | MASTERCARD / PLATINUM | 2 | 23 | 0 | [md](../../../data/markdown/common/20261104_000025/manifest.json) | [README](20261104_000025/README.md) |
| `20261104_000026` | 우리카드 | `WOORI_BRAND_260313_2039d0154f17` | `22` WOORI_VISA_INFINITE | VISA / INFINITE | 2 | 0 | 0 | [md](../../../data/markdown/common/20261104_000026/manifest.json) | [README](20261104_000026/README.md) |
| `20261104_000027` | 우리카드 | `WOORI_BRAND_260313_65f1ddecc9b2` | `23` WOORI_VISA_PLATINUM | VISA / PLATINUM | 2 | 6 | 0 | [md](../../../data/markdown/common/20261104_000027/manifest.json) | [README](20261104_000027/README.md) |
| `20261104_000028` | 우리카드 | `WOORI_BRAND_260316_40819705fc4c` | `24` WOORI_UPI_PLATINUM | UPI / PLATINUM | 2 | 13 | 0 | [md](../../../data/markdown/common/20261104_000028/manifest.json) | [README](20261104_000028/README.md) |

- 등록 공통 혜택 수는 공통서비스(`card_common_id`) 단위다. 같은 공통서비스에 문서가 둘 이상이면 같은 숫자가 반복된다.
- 상태 정의: **등록 완료** = `card_common_bnft` 행 있음. **검토 보류** = 후보만 있고 등록 안 함(기존 규칙 REVIEW, 추가 안전 게이트, OCR 문구 오류). **카드 적용** = `card_common_bnft_apply` 행.