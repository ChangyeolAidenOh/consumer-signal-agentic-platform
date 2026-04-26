"""LangGraph agent with Router -> Retriever -> Reporter nodes."""

import os

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from agent.state import AgentState
from agent.tools import query_canned, query_trend, search_voc

LLM = ChatOllama(
    model="llama3.1:8b",
    temperature=0,
    base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
)

def router(state: AgentState) -> AgentState:
    """Hybrid router: keyword match first, LLM fallback for ambiguous queries."""
    q = state["query"].lower()

    # methodology: analysis method questions
    # But NOT if asking about results (e.g. "Chronos 예측 결과" = trend)
    methodology_kw = ["lda", "bertopic", "coherence", "토픽 모델", "kmeans", "k-means",
                      "클러스터링", "전처리", "불용어", "stopword", "adj_noun",
                      "logistic regression", "cv 정확도", "방법론",
                      "ft-transformer", "rocket", "모드가 실패"]
    result_kw = ["결과", "예측 결과", "forecast", "12개월"]
    is_method_question = any(kw in q for kw in methodology_kw)
    is_result_question = any(kw in q for kw in result_kw)

    if is_method_question and not is_result_question:
        # Check if asking about method selection vs method results
        if "chronos" in q and any(kw in q for kw in ["선택", "이유", "대안", "왜"]):
            return {**state, "query_type": "methodology"}
        elif "chronos" in q:
            return {**state, "query_type": "trend"}
        return {**state, "query_type": "methodology"}

    # switching: segment and probability questions
    switching_kw = ["세그먼트", "segment", "at-risk", "at risk", "active switcher",
                    "loyal", "passive user", "switching", "이탈 확률", "리스크 스코어",
                    "risk score", "대응 전략", "intervention", "trend_multiplier",
                    "가중치", "weight", "p_switch"]
    if any(kw in q for kw in switching_kw):
        return {**state, "query_type": "switching"}

    # trend: search volume and timeline questions
    trend_kw = ["검색량", "역전", "ratio", "비율", "추이", "모멘텀", "momentum",
                "forecast", "예측", "카테고리 클릭", "닥터그루트", "케라시스", "팬틴",
                "클리니컬 스트렝스", "clinical strength", "처음 등장", "시점",
                "chronos"]
    if any(kw in q for kw in trend_kw):
        return {**state, "query_type": "trend"}

    # voc: consumer review questions
    voc_kw = ["후기", "리뷰", "소비자 반응", "성분", "가려움", "자극", "뾰루지",
              "불만", "만족", "차콜", "프로페셔널", "채널", "블로그", "유튜브",
              "수집", "문서 수", "몇 건", "경쟁사를 언급", "이탈률"]
    if any(kw in q for kw in voc_kw):
        return {**state, "query_type": "voc"}

    # Slow path: LLM fallback for ambiguous queries
    prompt = f"""Classify this query into one category.
Categories: voc, trend, switching, mixed, methodology
Query: {q}
Answer with ONE word:"""

    response = LLM.invoke(prompt)
    query_type = response.content.strip().lower().strip('"')

    if query_type not in ("voc", "trend", "switching", "mixed", "methodology"):
        query_type = "mixed"

    return {**state, "query_type": query_type}

def retriever(state: AgentState) -> AgentState:
    """Retrieve relevant data based on query type and content."""
    query = state["query"]
    query_type = state["query_type"]

    retrieved_docs = ""
    sql_result = ""

    if query_type in ("voc", "mixed"):
        retrieved_docs = search_voc(query, n_results=5)

    if query_type == "switching":
        sql_result = query_canned("segment_summary")

    elif query_type == "trend":
        sql_result = query_canned("antitro_timeline")

    elif query_type == "methodology":
        q = query.lower()
        if any(kw in q for kw in ["lda", "coherence", "토픽 모델"]):
            sql_result = query_canned("lda_coherence")
        elif any(kw in q for kw in ["bertopic", "bert"]):
            sql_result = query_canned("bertopic_summary")
        elif any(kw in q for kw in ["합의", "consensus", "교차"]):
            sql_result = query_canned("consensus_signals")
        else:
            sql_result = query_canned("lda_coherence")

    elif query_type == "mixed":
        q = query.lower()
        if any(kw in q for kw in ["이탈", "불만", "churn", "왜", "이유", "원인"]):
            sql_result = query_canned("churn_reasons")
        elif any(kw in q for kw in ["역전", "트렌드", "추이", "검색량", "안티트로", "성장"]):
            sql_result = query_canned("antitro_timeline")
        elif any(kw in q for kw in ["세그먼트", "segment", "at-risk", "위험"]):
            sql_result = query_canned("segment_summary")
        elif any(kw in q for kw in ["월별", "월간", "추세"]):
            sql_result = query_canned("monthly_churn")
        elif any(kw in q for kw in ["대응", "과제", "전략", "시급", "시사점"]):
            sql_result = (
                query_canned("segment_summary") + "\n\n" +
                query_canned("antitro_timeline")
            )
        elif any(kw in q for kw in ["한계", "limitation", "확인할 수 없"]):
            sql_result = query_canned("antitro_timeline")
        else:
            sql_result = (
                query_canned("churn_reasons") + "\n\n" +
                query_canned("antitro_timeline")
            )

    elif query_type == "voc":
        q = query.lower()
        if any(kw in q for kw in ["이탈", "불만", "이유", "원인"]):
            sql_result = query_canned("churn_reasons")

    return {**state, "retrieved_docs": retrieved_docs, "sql_result": sql_result}


def reporter(state: AgentState) -> AgentState:
    """Generate final answer using retrieved context."""
    context_parts = []

    if state.get("retrieved_docs"):
        context_parts.append(
            f"=== VoC Documents ===\n{state['retrieved_docs']}"
        )
    if state.get("sql_result"):
        context_parts.append(
            f"=== Data from Database ===\n{state['sql_result']}"
        )

    context = "\n\n".join(context_parts) if context_parts else "No data retrieved."

    prompt = f"""You are an analyst for Head & Shoulders (P&G Korea).
    Answer the user's question based ONLY on the provided data.
    Answer in Korean.

    Critical rules for interpreting the data:
    - The "ratio" column = Antitro / HNS. When ratio > 1.0, Antitro has SURPASSED HNS. When ratio < 1.0, HNS is still ahead.
    - Dates in the data use month-end format (e.g. "2025-06-30" means June 2025, NOT a specific day). Never say "X월 30일 현재". Say "X월 기준" instead.
    - In VoC documents, signal=이탈위험 means the consumer is showing churn risk. churn_score > 0 means churn signals detected. competitor=True means they mentioned a competing brand.
    - Do NOT contradict the data. If VoC documents show complaints, report them as complaints.

    Format rules:
    - Cite specific numbers and months from the data
    - Keep the answer concise (3-5 sentences)

    Data:
    {context}

    Question: {state['query']}

    Answer:"""

    response = LLM.invoke(prompt)
    return {**state, "final_answer": response.content}


def build_graph():
    """Construct the LangGraph agent."""
    graph = StateGraph(AgentState)

    graph.add_node("router", router)
    graph.add_node("retriever", retriever)
    graph.add_node("reporter", reporter)

    graph.set_entry_point("router")
    graph.add_edge("router", "retriever")
    graph.add_edge("retriever", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()