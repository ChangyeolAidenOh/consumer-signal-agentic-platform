"""LangGraph agent with Router -> Retriever -> Reporter nodes."""

from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

from agent.state import AgentState
from agent.tools import search_voc, query_canned, query_trend


LLM = ChatOllama(model="llama3.1:8b", temperature=0)


def router(state: AgentState) -> AgentState:
    """Classify query into type: voc, trend, switching, or mixed."""
    prompt = f"""Classify this query into one category. Read the rules carefully.

    Categories:
    - voc: consumer reviews, complaints, opinions, product experience, VoC data, document counts
    - trend: search volume numbers, market share over time, Antitro vs HNS ratio, forecast, timeline
    - switching: segments (Active Switcher, At-risk, Passive User, Loyal), switching probability, risk score, intervention strategy
    - mixed: needs BOTH consumer data AND trend/segment data, strategic recommendations, cross-layer analysis
    - methodology: about analysis methods (LDA, BERTopic, Chronos, KMeans, preprocessing, coherence, model selection)

    Query: {state['query']}

    Classification rules (apply in order):
    1. If query contains VoC, 후기, 리뷰, 소비자, 불만, 성분, 반응, 채널, 블로그, 유튜브, 수집, 문서 수, 건수 → "voc"
    2. If query contains 세그먼트, segment, At-risk, Active Switcher, Loyal, Passive, 이탈 확률, switching, probability, 리스크 스코어, risk score, 대응 전략, intervention, 가중치, multiplier, Logistic → "switching"
    3. If query contains 검색량, 역전, ratio, 추이, trend, 모멘텀, forecast, 예측, 카테고리 클릭 → "trend"
    4. If query contains LDA, BERTopic, coherence, 토픽, KMeans, Chronos, 전처리, 불용어, 모드, 방법론 → "methodology"
    5. If query asks for strategic conclusion, 대응 과제, 시사점, 한계, limitations, 종합, 요약 → "mixed"
    6. Default: "mixed"

    Answer with ONE word only:"""

    response = LLM.invoke(prompt)
    query_type = response.content.strip().lower().strip('"')

    # Validate
    if query_type not in ("voc", "trend", "switching", "mixed"):
        query_type = "mixed"

    return {**state, "query_type": query_type}


def retriever(state: AgentState) -> AgentState:
    """Retrieve relevant data based on query type and content."""
    query = state["query"]
    query_type = state["query_type"]

    retrieved_docs = ""
    sql_result = ""

    # VoC retrieval for voc or mixed types
    if query_type in ("voc", "mixed"):
        retrieved_docs = search_voc(query, n_results=5)

    # SQL query selection based on query type and keywords
    if query_type == "switching":
        sql_result = query_canned("segment_summary")

    elif query_type == "trend":
        sql_result = query_canned("antitro_timeline")

    elif query_type == "mixed":
        # Pick SQL based on query keywords
        q = query.lower()
        if any(kw in q for kw in ["이탈", "불만", "churn", "왜", "이유", "원인"]):
            sql_result = query_canned("churn_reasons")
        elif any(kw in q for kw in ["역전", "트렌드", "추이", "검색량", "안티트로"]):
            sql_result = query_canned("antitro_timeline")
        elif any(kw in q for kw in ["세그먼트", "segment", "at-risk", "위험"]):
            sql_result = query_canned("segment_summary")
        elif any(kw in q for kw in ["월별", "월간", "추세"]):
            sql_result = query_canned("monthly_churn")
        else:
            sql_result = query_canned("churn_reasons")

    elif query_type == "voc":
        # Pure VoC can also benefit from churn stats
        q = query.lower()
        if any(kw in q for kw in ["이탈", "불만", "이유", "원인"]):
            sql_result = query_canned("churn_reasons")

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