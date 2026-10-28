"""PDF/CSV 문서를 읽어 페이지별 텍스트 목록으로 만드는 도우미 모듈.

차량 매뉴얼 등록(``CarManualRegisterService``)과 샘플 스크립트가
PDF 페이지 텍스트를 ``doc_list`` 로 얻기 위해 사용한다.
"""

from typing import Any

from pathlib import Path
import sys

#=========================================================
# 문서 파일 읽기 및 전처리 관리
#=========================================================
class DocumentReader:
    """
    문서 파일 읽기 및 전처리 관리

    파일 경로만 받아 두고, 실제 읽기는 ``set_pdf_reader()`` / ``set_csv_reader()`` 를
    호출할 때 수행한다. 사용 순서(PDF):

        reader = DocumentReader(file_path)
        reader.set_pdf_reader()      # self.reader = pypdf.PdfReader
        reader.set_pdf_doc_list()    # self.doc_list 에 페이지별 dict 추가

    Attributes:
        file_path: 읽을 파일 경로(``Path``).
        reader: ``pypdf.PdfReader`` 또는 ``pandas.DataFrame``. 읽기 전에는 ``None``.
        doc_list: ``{"page_no": 1부터 시작, "text": 추출 텍스트}`` dict 목록.
    """

    file_path :str          # 파일경로
    doc_list : list[Any]    # 문서 리스트
    reader : Any            # 문서 리더 객체

    #=========================================================
    # 생성자 읽을 파일 설정
    #=========================================================
    def __init__(self, file_path):
        """
        읽을 파일 경로를 ``Path`` 로 저장하고 reader와 doc_list를 빈 상태로 초기화한다.

        파일은 이 시점에 열지 않으며, 상대 경로는 현재 작업 디렉터리 기준으로 해석된다.
        """
        self.file_path = Path(file_path)
        self.reader = None
        self.doc_list = []


    #=========================================================
    # pdf 읽어서 설정
    #=========================================================
    def set_pdf_reader(self):
        """
        pdf 읽어서 설정

        ``pypdf.PdfReader`` 로 ``self.file_path`` 를 열어 ``self.reader`` 에 보관한다.
        """
        # region [Python 설명] 함수 안의 import
        # import를 함수 본문에 두면 이 메서드를 실제로 호출할 때만 모듈을 불러온다.
        # PDF를 읽지 않는 코드에서는 pypdf/pandas를 불러오지 않아 import 시간과 의존성을 줄인다.
        # endregion
        from pypdf import PdfReader

        self.reader = PdfReader(self.file_path)

    #=========================================================
    # csv 읽어서 설정
    #=========================================================
    def set_csv_reader(self):
        """
        csv 읽어서 설정

        ``pandas.read_csv()`` 결과 ``DataFrame`` 을 ``self.reader`` 에 보관한다.
        """
        import pandas as pd

        self.reader = pd.read_csv(self.file_path)


    #=========================================================
    # 읽은 pdf 내용 doc_list 로 설정
    #=========================================================
    def set_pdf_doc_list(self):
        """
        읽은 pdf 내용 doc_list 로 설정

        ``set_pdf_reader()`` 를 먼저 호출해야 한다. 기존 ``doc_list`` 를 비우지 않고 뒤에 추가하므로
        두 번 호출하면 페이지가 중복된다.
        """

        # 페이지를 순서대로 돌며 텍스트를 추출한다.
        # region [Python 설명] enumerate()
        # `enumerate(items)`는 `(index, item)` 쌍을 0부터 순서대로 돌려준다.
        # Java의 `for (int i = 0; ...)`와 향상된 for문을 합친 형태로 생각하면 된다.
        # endregion
        for i, page in enumerate(self.reader.pages):
            text = page.extract_text()

            self.doc_list.append({              # 현재 페이지 번호와 추출 텍스트를 하나의 딕셔너리로 목록에 추가
                "page_no": i + 1,               # 사용자에게 보이는 실제 페이지 순서처럼 1부터 시작하도록 페이지 번호 저장
                "text": text                    # 현재 페이지에서 추출된 전체 텍스트 저장
            })

    #=========================================================
    # doc_list 청크 설정후 재저장
    #=========================================================
    def set_pdf_chunk_doc_list(selft):
        """
        doc_list 청크 설정후 재저장

        아직 구현되지 않았다. 호출하면 안내 문구만 출력한다.
        (첫 매개변수 이름이 ``self`` 가 아닌 ``selft`` 지만 Python은 첫 인자를 이름과 무관하게 인스턴스로 전달한다.)
        """
        print("구현 예정")

