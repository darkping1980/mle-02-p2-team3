# 하나카드 공식 상품설명서 PDF 10종 독립 재검증

- 검증일: 2026-10-30 (Asia/Seoul). 공식 서버에서 직접 다운로드한 바이트와 기존 Claude 사본을 비교했다.
- 저장: `src/card_benefit/data/raw/hanacard/{credit,debit}/`; 상세 URL·HTTP 응답·페이지·텍스트·해시: `src/card_benefit/data/metadata/manifest.json`.
- 공식 원본 10개, 브라우저 인쇄본 0개, 다운로드 실패 0개. SHA-256 일치 10개. 기존 PDF 10개 모두 열기·텍스트 추출 확인.
- 상품 페이지에서 해당 PDF를 제공하는 것과 해당 문서가 모든 시점에 법적으로 유효한 최신판이라는 것은 다르다. 공식 링크 미확인 상품의 최신판 여부는 미확인이다.

| 카드명 | 카드 종류 | 다운로드 방법 | 공식 PDF 확보 | 기존 파일과 동일 | 최신판 확인 | 특이사항 |
|---|---|---|---|---|---|---|
| ONE PICK STYLE 하나 체크카드 | 체크 | 공식 URL 직접 | 예 | 해시 일치 | 미확인 | 상품 페이지에서 PDF 링크 미확인 |
| ONE PICK PLAY 하나 체크카드 | 체크 | 공식 URL 직접 | 예 | 해시 일치 | 미확인 | 상품 페이지에서 PDF 링크 미확인 |
| K-패스 하나 체크카드 | 체크 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| 더 심플 체크카드 | 체크 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| MULTI Any 체크카드 | 체크 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| BT 카드 | 신용 | 공식 URL 직접 | 예 | 해시 일치 | 미확인 | 기존 BT의 독립 상품 페이지 미확인; 제휴 BT 별도 |
| 에너지 더블 카드 | 신용 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| K-패스 하나 신용카드 | 신용 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| 더 심플 하나카드 | 신용 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |
| 하나 원큐 카드 | 신용 | 공식 URL 직접 | 예 | 해시 일치 | 페이지 제공본 확인 | 상품 페이지 직접 링크 확인 |

## 문서와 비교 결과

| 카드명 | 공식 상품 페이지 | 공식 PDF 및 다운로드 파일명 | 크기 | 페이지 | SHA-256 |
|---|---|---|---:|---:|---|
| ONE PICK STYLE 하나 체크카드 | [상품 페이지](https://m.hanacard.co.kr/MKCDCM1000M.web?CD_PD_SEQ=18899) | [15650_20260429.pdf](https://m.hanacard.co.kr/leaflet/15/15650_20260429.pdf) | 360,659 | 2 | `6ec9641c2e318ce9429a916f5d01c0468ccc3cffb238eb1162a43b280e25c6d2` |
| ONE PICK PLAY 하나 체크카드 | [상품 페이지](https://m.hanacard.co.kr/MKCDCM1000M.web?CD_PD_SEQ=18901) | [15651_20260429.pdf](https://m.hanacard.co.kr/leaflet/15/15651_20260429.pdf) | 327,746 | 2 | `228260b213e52c65fdf1e0123482c6c35bfa844cf673969db14129721ec320ee` |
| K-패스 하나 체크카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41017033P&CD_PD_SEQ=17033) | [14474_20251224.pdf](https://m.hanacard.co.kr/leaflet/14/14474_20251224.pdf) | 266,251 | 1 | `819395701e3d49075b5a3d653cbce44d460e6a84d6a35cd522a6c3217d6b2eec` |
| 더 심플 체크카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41018271P&CD_PD_SEQ=18271) | [15245_20250703.pdf](https://m.hanacard.co.kr/leaflet/15/15245_20250703.pdf) | 197,362 | 1 | `f63efee1e0250cfcc6d7a2219004262d8d2f81688b5d73c61ecdac98a20505c0` |
| MULTI Any 체크카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41013823P&CD_PD_SEQ=13823) | [13278_20260306.pdf](https://m.hanacard.co.kr/leaflet/13/13278_20260306.pdf) | 1,906,890 | 2 | `72177812c926a711bb30c275afb2baaf65fdf115e28758c3316b8df281eb9ee3` |
| BT 카드 | 기본 BT 페이지 미확인 | [14324_20260310.pdf](https://m.hanacard.co.kr/leaflet/14/14324_20260310.pdf) | 543,780 | 1 | `520d635dd26e1d370e4d1ca85105ddfa140023098fcd36e914b13ea2df70577e` |
| 에너지 더블 카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41016772P&CD_PD_SEQ=16772) | [14422_20251224.pdf](https://m.hanacard.co.kr/leaflet/14/14422_20251224.pdf) | 1,398,539 | 1 | `1b938dd04b54116a9c56b715f291e345c529b56a3505603baf16f2d0b55a0198` |
| K-패스 하나 신용카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41017016P&CD_PD_SEQ=17016) | [14472_20251224.pdf](https://m.hanacard.co.kr/leaflet/14/14472_20251224.pdf) | 216,784 | 1 | `d461b07b93f01b0009075be904b22d89eda9bdfbcad1379c6fbc31e5e61d4da4` |
| 더 심플 하나카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41016952P&CD_PD_SEQ=16952) | [14527_20260929.pdf](https://m.hanacard.co.kr/leaflet/14/14527_20260929.pdf) | 206,617 | 1 | `5e6417c7f693ff44e90c7c570e081618d8dfd189d7e9ba9e014d74716723520a` |
| 하나 원큐 카드 | [상품 페이지](https://www.hanacard.co.kr/OPI41000000D.web?schID=pcd&mID=PI41012942P&CD_PD_SEQ=12942) | [13066_20251224.pdf](https://m.hanacard.co.kr/leaflet/13/13066_20251224.pdf) | 320,949 | 1 | `f6dbd8445a219a00bfbda5d32f0e36ef9961df25c44bcecf062cfd9397de4d89` |

- 10개 모두 HTTP 200, `application/pdf`, PDF 서명 확인 및 PyMuPDF 열기 성공. 각 파일에서 텍스트가 추출됐으며 상품명 확인용 문자열도 확인했다. 단 BT는 원문 BIG TICKET 및 PDF 제목으로 상품을 확인했다.
- 기존 파일명·공식 다운로드 URL·실제 바이트 해시 10개 모두 일치하고 기존 manifest 해시도 일치한다. 다운로드한 파일과 기존 파일의 페이지 수는 같다. 각 사본을 열고 텍스트를 읽었으며 확인된 손상은 없다. 이 검사는 모든 내용의 무결성·조건의 정확성을 보증하지 않는다.
- 파일명 날짜와 PDF 생성일은 다를 수 있으며, 각각 메타데이터에 별도 기록했다. 날짜만으로 시행일이나 법적 유효성을 확정하지 않는다.
- 새 버전 발견: 없음. STYLE·PLAY·BT는 실제 공식 상품 페이지의 원본 PDF 링크를 확인하지 못해 최신판 여부를 확정할 수 없다. 나머지 7종은 접근한 공식 상품 페이지 HTML에서 동일 PDF 링크를 직접 확인했으나, 그 사실만으로 유효한 모든 버전을 확정하지 않는다.
- BT: 기본 BT 상품 페이지와 신규 발급 가능 여부 미확인. [휴베이스 약사 대상 BT 제휴 페이지](https://m.hanacard.co.kr/MKCDCM1010M.web?CD_PD_SEQ=18256)에서 BIG TICKET과 신청 문구가 보이나 제휴 상품이므로 기본 BT의 발급 가능성이나 PDF 최신성을 입증하지 않는다.
- 텍스트 추출은 표의 행·열이나 혜택·조건 관계가 정확히 추출됐음을 의미하지 않는다. 원문과 표 구조는 별도 검증해야 한다.
- 브라우저 인쇄 파일은 만들지 않았다. 기존 Claude 파일은 수정하지 않았다. PDF 저장 경로는 Git ignore 대상으로 설정했다.
