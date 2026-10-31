"""Streamlit chat front end for the HNS consumer signal agent API."""

import html
import os
import re
import time

import requests
import streamlit as st

DEFAULT_API_URL = "https://hns-agent-887686014711.asia-northeast3.run.app"
REPO_URL = "https://github.com/ChangyeolAidenOh/consumer-signal-agentic-platform"

SESSION_QUESTION_LIMIT = 10
MAX_QUERY_CHARS = 300
ANALYZE_TIMEOUT = (10, 120)  # (connect, read) seconds; the first call may hit a cold start
HEALTH_TIMEOUT = (5, 8)  # kept short so the page never blocks on a cold start
ANSWER_CACHE_TTL = 60 * 60 * 24  # identical questions reuse the answer for one day

EXAMPLE_QUESTIONS = [
    "안티트로가 헤드앤숄더를 역전한 시점은 언제야?",
    "소비자들이 헤드앤숄더에서 이탈하는 주된 이유는 뭐야?",
    "At-risk 세그먼트의 특징과 대응 전략은 뭐야?",
    "안티트로와 헤드앤숄더를 직접 비교한 후기의 주요 내용은 뭐야?",
    "Loyal이 19.8%인데 리스크 0.068이면 안전한 거야?",
]

ROUTE_LABELS = {
    "trend": ("검색 트렌드", "네이버 검색량 시계열을 조회했습니다"),
    "voc": ("소비자 후기", "VoC 문서를 의미 기반으로 검색했습니다"),
    "switching": ("이탈 세그먼트", "세그먼트별 전환 확률과 대응 전략을 조회했습니다"),
    "mixed": ("후기와 수치 결합", "VoC 검색과 SQL 집계를 함께 사용했습니다"),
    "methodology": ("분석 방법론", "토픽 모델과 예측 모델 결과를 조회했습니다"),
}

STYLE = """
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
.stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3,
.stApp button, .stApp textarea, .stApp input, .stApp label {
    font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
}
.stApp h1 {
    font-weight: 700;
    letter-spacing: -0.02em;
}
.route-badge {
    display: inline-block;
    padding: 0.1rem 0.65rem;
    border: 1px solid #1F5E8C;
    border-radius: 999px;
    color: #1F5E8C;
    font-size: 0.8rem;
    font-weight: 600;
}
.route-desc {
    margin-left: 0.5rem;
    color: #5B6B78;
    font-size: 0.8rem;
}
</style>
"""


def get_api_url() -> str:
    """Resolve the API base URL from Streamlit secrets, an env var, or the default."""
    try:
        url = st.secrets["API_URL"]
    except Exception:
        url = os.getenv("API_URL", DEFAULT_API_URL)
    return url.rstrip("/")


@st.cache_data(ttl=ANSWER_CACHE_TTL, show_spinner=False)
def ask_agent(api_url: str, query: str) -> dict:
    """Call the analyze endpoint. Only successful responses are cached."""
    response = requests.post(
        f"{api_url}/api/v1/analyze",
        json={"query": query},
        timeout=ANALYZE_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60, show_spinner=False)
def check_health(api_url: str) -> dict | None:
    """Return the health payload, or None if the service is not ready yet."""
    try:
        response = requests.get(f"{api_url}/health", timeout=HEALTH_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def describe_error(exc: requests.RequestException) -> str:
    """Translate a request failure into a message that tells the user what to do."""
    if isinstance(exc, requests.Timeout):
        return "응답 시간이 초과되었습니다. 서버가 막 시작된 경우일 수 있으니 같은 질문을 다시 보내 주세요."
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        if exc.response.status_code == 429:
            return "서버가 다른 요청을 처리하고 있습니다. 잠시 후 다시 보내 주세요."
        return f"서버가 오류를 반환했습니다 (HTTP {exc.response.status_code}). 잠시 후 다시 시도해 주세요."
    return "API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."


def format_answer(text: str) -> str:
    """Demote markdown headings to bold text and prevent LaTeX rendering of dollar signs."""
    text = re.sub(r"^#{1,6}\s*(.+)$", r"**\1**", text, flags=re.MULTILINE)
    return text.replace("$", "\\$")


def render_route(route: str, elapsed: float) -> None:
    """Show which data path the agent used for this answer."""
    label, description = ROUTE_LABELS.get(
        route, (route or "알 수 없음", "라우팅 정보를 확인할 수 없습니다")
    )
    st.markdown(
        f'<span class="route-badge">{html.escape(label)}</span>'
        f'<span class="route-desc">{html.escape(description)} ({elapsed:.1f}초)</span>',
        unsafe_allow_html=True,
    )


def render_message(message: dict) -> None:
    """Render one chat message from session history."""
    with st.chat_message(message["role"]):
        if message.get("is_error"):
            st.error(message["content"])
            return
        st.markdown(format_answer(message["content"]))
        if message.get("route") is not None:
            render_route(message["route"], message["elapsed"])


def render_sidebar(api_url: str, remaining: int) -> None:
    """Service status, example questions, remaining quota, and project links."""
    with st.sidebar:
        st.subheader("서비스 상태")
        health = check_health(api_url)
        if health and health.get("status") == "ok":
            voc_count = health.get("voc_count", 0)
            st.success(f"정상 운영 중입니다. VoC 문서 {voc_count:,}건이 연결되어 있습니다.")
        else:
            st.warning("서버를 준비하는 중입니다. 첫 질문은 평소보다 오래 걸릴 수 있습니다.")

        st.subheader("예시 질문")
        for index, question in enumerate(EXAMPLE_QUESTIONS):
            if st.button(question, key=f"sidebar_example_{index}"):
                st.session_state.pending = question

        st.caption(f"이 세션에서 남은 질문: {remaining}개")
        st.markdown(f"[GitHub 저장소]({REPO_URL})  \n[API 문서]({api_url}/docs)")


def main() -> None:
    st.set_page_config(page_title="헤드앤숄더 소비자 신호 에이전트")
    st.markdown(STYLE, unsafe_allow_html=True)

    api_url = get_api_url()
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("question_count", 0)
    st.session_state.setdefault("pending", None)

    remaining = SESSION_QUESTION_LIMIT - st.session_state.question_count
    render_sidebar(api_url, remaining)

    st.title("헤드앤숄더 소비자 신호 에이전트")
    st.markdown(
        "소비자 후기 발췌 1,744건, 네이버 검색 트렌드 76개월, 이탈 세그먼트 분석 결과를 근거로 답합니다. "
        "질문 유형에 따라 필요한 데이터를 골라 조회하고, 답변마다 어떤 데이터를 사용했는지 표시합니다. "
        "질문은 하나씩 독립적으로 처리되므로, '그거'나 '1번'처럼 앞선 답변을 가리키기보다 대상을 질문에 직접 적어 주세요."
    )

    if not st.session_state.messages:
        st.markdown("아래 질문 중 하나를 눌러 시작하거나 직접 입력하세요.")
        for index, question in enumerate(EXAMPLE_QUESTIONS):
            if st.button(question, key=f"empty_example_{index}"):
                st.session_state.pending = question

    for message in st.session_state.messages:
        render_message(message)

    limit_reached = remaining <= 0
    prompt = st.chat_input(
        "헤드앤숄더 소비자 신호에 대해 질문하세요",
        max_chars=MAX_QUERY_CHARS,
        disabled=limit_reached,
    )
    if limit_reached:
        st.info(f"이 세션의 질문 한도({SESSION_QUESTION_LIMIT}개)에 도달했습니다.")

    pending = st.session_state.pending
    st.session_state.pending = None
    if pending and not limit_reached:
        prompt = pending

    if not prompt or not prompt.strip():
        return

    query = prompt.strip()
    st.session_state.messages.append({"role": "user", "content": query})
    render_message(st.session_state.messages[-1])

    with st.chat_message("assistant"):
        started = time.perf_counter()
        with st.spinner("데이터를 조회하고 답변을 작성하는 중입니다"):
            try:
                result = ask_agent(api_url, query)
                error_message = None
            except requests.RequestException as exc:
                result = None
                error_message = describe_error(exc)
        elapsed = time.perf_counter() - started

    if result is not None:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.get("answer", ""),
                "route": result.get("query_type", ""),
                "elapsed": elapsed,
            }
        )
        st.session_state.question_count += 1
    else:
        st.session_state.messages.append(
            {"role": "assistant", "content": error_message, "is_error": True}
        )

    st.rerun()


if __name__ == "__main__":
    main()
