"""검색된 근거를 Prompt로 전달하고 Mock 또는 OpenAI 답변을 만드는 Service입니다."""

import os
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI


# region [LangChain 설명] RAG(Retrieval-Augmented Generation) 흐름
# 1) 검색(Retrieval): PostgreSQL 키워드/벡터 검색과 Neo4j 그래프 조회로 근거 데이터를 모은다(이 클래스 밖).
# 2) Context 구성: `build_context()`가 검색 결과를 출처 제목이 붙은 문자열로 만든다.
# 3) 생성(Generation): Prompt에 질문과 Context를 넣어 ChatModel을 호출하고, Parser가 문자열 답변을 꺼낸다.
# GraphRAG는 이 중 검색 단계에 그래프 관계(Neo4j) 조회를 포함하는 방식이다.
# endregion
class GraphRagSampleLlmService:
    """검색 데이터에서 Context를 만들고 Prompt → ChatModel → Parser를 실행합니다.

    ``chat_model`` 을 주입하면 그 모델을, ``use_openai=True`` 면 ChatOpenAI를, 둘 다 아니면
    외부 호출 없는 Mock 모델을 사용한다. 어떤 모델이든 같은 chain 구조로 실행된다.
    """

    # =========================================================
    # 01. 생성자와 기본 Mock 모델
    # =========================================================
    # region [01. 생성자와 기본 Mock 모델]
    def __init__(self, chat_model: Runnable | None = None, use_openai: bool = False):
        """기본은 외부 호출이 없는 Mock이며, use_openai=True일 때만 실제 모델을 씁니다.

        Raises:
            RuntimeError: ``use_openai=True`` 인데 ``OPENAI_API_KEY`` 환경변수가 없는 경우.
        """
        # system/human 두 메시지로 된 prompt template. `{question}`, `{context}`는 실행 시 채워진다.
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "질문에 답할 때 제공된 Context만 근거로 사용하세요. "
                    "Context가 비어 있으면 근거가 없다고 말하고 사실을 추측하지 마세요.",
                ),
                ("human", "질문: {question}\n\n검색 근거:\n{context}"),
            ]
        )
        # 사용할 모델을 고른다: 주입한 모델 > 실제 OpenAI(명시적으로 요청한 경우) > Mock.
        # region [LangChain 설명] Runnable과 RunnableLambda
        # LangChain의 prompt, model, parser는 모두 `invoke()`를 가진 Runnable이라 `|`로 이어 chain을 만들 수 있다.
        # `RunnableLambda(함수)`는 일반 Python 함수를 Runnable로 감싼다.
        # 여기서는 `_mock_answer`를 모델 자리에 넣어, 실제 API 없이도 같은 chain을 실행·테스트할 수 있게 한다.
        # 실제 모델이 받는 것과 같은 prompt 값(ChatPromptValue)을 받아 AIMessage를 돌려주므로 Parser도 그대로 동작한다.
        # endregion
        if chat_model is not None:
            self.chat_model = chat_model
            self.model_mode = "injected"
        elif use_openai:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("실제 LLM 모드에는 OPENAI_API_KEY가 필요합니다.")
            self.chat_model = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                max_tokens=256,
                api_key=api_key,
            )
            self.model_mode = "openai"
        else:
            self.chat_model = RunnableLambda(self._mock_answer)
            self.model_mode = "mock"
        self.chain = self.prompt | self.chat_model | StrOutputParser()
    # endregion

    # =========================================================
    # 02. 검색 결과를 Context 문장으로 변환
    # =========================================================
    # region [02. 검색 결과를 Context 문장으로 변환]
    @staticmethod
    def build_context(search_results: Mapping[str, Any]) -> str:
        """각 검색 경로의 dict/list 결과를 출처가 보이는 문자열로 바꿉니다.

        Returns:
            ``[PostgreSQL - Keyword]``, ``[PostgreSQL - Vector]``, ``[Neo4j - Graph]`` 세 구역을 빈 줄로 이은 문자열.
            세 경로 모두 결과가 없으면 ``"No retrieved evidence."``.
        """
        # region [Python 설명] `"\n".join(lines) or "No results."`
        # 결과 줄이 없으면 join 결과가 빈 문자열("")이고, 빈 문자열은 falsy이므로 `or` 오른쪽 값이 선택된다.
        # `row.get("a", row.get("b", "기본값"))`은 key a → b → 기본값 순으로 값을 찾는다.
        # endregion
        sections = []
        postgres = search_results.get("postgres", {})
        neo4j = search_results.get("neo4j", {})

        keyword_rows = postgres.get("keyword_rows", [])
        keyword_lines = [str(row.get("content", "")) for row in keyword_rows]
        sections.append("[PostgreSQL - Keyword]\n" + ("\n".join(keyword_lines) or "No results."))

        vector_rows = postgres.get("vector_rows", [])
        vector_lines = []
        for row in vector_rows:
            vector_lines.append(
                f"{row.get('item_name', row.get('item_id', 'item'))} "
                f"(similarity={row.get('similarity', 'n/a')})"
            )
        sections.append("[PostgreSQL - Vector]\n" + ("\n".join(vector_lines) or "No results."))

        graph_rows = neo4j.get("relationships", [])
        graph_lines = []
        for row in graph_rows:
            graph_lines.append(
                f"{row.get('project', row.get('from_project', 'Project'))} "
                f"→ {row.get('relationship', 'USES')} → "
                f"{row.get('to_technology', row.get('technology', 'Technology'))}"
            )
        sections.append("[Neo4j - Graph]\n" + ("\n".join(graph_lines) or "No results."))

        has_evidence = bool(keyword_rows or vector_rows or graph_rows)
        if not has_evidence:
            return "No retrieved evidence."
        return "\n\n".join(sections)

    @staticmethod
    def _mock_answer(prompt_value) -> AIMessage:
        """실제 API 대신 Prompt 내용을 확인하는 고정 응답을 돌려줍니다.

        prompt의 검색 근거 부분에 "Python"/"Neo4j" 문자열이 있으면 그 기술 이름으로 답변 문장을 만든다.
        """
        # `prompt_value`는 ChatPromptValue다. `to_string()`은 전체 메시지를 문자열로,
        # `messages[-1].content`는 마지막(human) 메시지 본문을 준다.
        prompt_text = prompt_value.to_string()
        if "No retrieved evidence." in prompt_text:
            return AIMessage(content="검색 근거가 없어 답변할 수 없습니다.")
        # 출처 제목([Neo4j - Graph])은 기술 검색 결과로 오인하지 않도록 제외한다.
        user_message = prompt_value.messages[-1].content
        context_text = user_message.split("검색 근거:\n", maxsplit=1)[-1]
        evidence_lines = [
            line for line in context_text.splitlines()
            if line and not line.startswith("[") and line != "No results."
        ]
        technologies = []
        for technology in ("Python", "Neo4j"):
            if any(technology in line for line in evidence_lines):
                technologies.append(technology)
        if not technologies:
            return AIMessage(content="검색 근거에서 사용 기술을 찾지 못했습니다.")
        technology_text = "과 ".join(technologies)
        return AIMessage(
            content=f"Mock 답변: 검색 근거에서 Project A가 {technology_text}를 사용하는 것을 확인했습니다."
        )
    # endregion

    # =========================================================
    # 03. Context와 Prompt를 기록하고 답변 생성
    # =========================================================
    # region [03. 답변 생성]
    def generate_answer(
        self, question: str, search_results: Mapping[str, Any]
    ) -> dict[str, str]:
        """질문과 검색 결과를 입력해 Context, Prompt, 최종 문자열 답변을 반환합니다.

        Returns:
            ``question``, ``context``, ``prompt`` (확인용 문자열), ``answer``, ``model_mode`` 를 담은 dict.
        """
        # `prompt.format()`은 모델에 보낼 내용을 사람이 확인할 수 있는 문자열로만 만든다(모델 호출 없음).
        # 실제 답변은 `chain.invoke()`가 prompt → model → parser 순서로 실행해 만든다.
        context = self.build_context(search_results)
        prompt_text = self.prompt.format(question=question, context=context)
        answer = self.chain.invoke({"question": question, "context": context})
        return {
            "question": question,
            "context": context,
            "prompt": prompt_text,
            "answer": answer,
            "model_mode": self.model_mode,
        }
    # endregion
