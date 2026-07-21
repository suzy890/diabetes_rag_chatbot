"""연구자용 관리자 대시보드 — 참여자 앱과 완전 분리된 별도 앱 (PRD §8-1 · D22).

- **참여자 앱과 다른 URL로만** 접근한다. Streamlit Cloud에서 이 파일을 메인으로
  하는 별도 앱으로 배포하고, 비밀번호(`ADMIN_PASSWORD` 시크릿)로 보호한다.
- 연구 행동 데이터(messages·events·nudge_events·retrieval_logs)는 **읽기 전용**.
  수정·삭제 기능을 두지 않는다(데이터 무결성).
- 참여자는 **익명 ID로만** 표시한다(직접식별정보 없음).
- 이 앱은 참여자 앱의 핵심 500줄 로직에 포함되지 않는다(D22).
- 시각화는 Streamlit 기본 포함 라이브러리 Altair를 쓴다(추가 의존성 없음).
"""

import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import altair as alt
import pandas as pd
import streamlit as st

import database

st.set_page_config(page_title="연구자 대시보드", page_icon="📊", layout="wide")

GREEN = "#4d8b78"
# 초록을 기본으로, 범주형(도넛 등)엔 파스텔 팔레트를 쓴다(참여자 앱 톤과 맞춤).
PALETTE = ["#4d8b78", "#7cb7a1", "#f0b27a", "#d98c8c", "#9db8d2", "#c7a3d4"]


def check_password() -> bool:
    """비밀번호 게이트. 앱 시크릿 ADMIN_PASSWORD(또는 환경변수)와 일치해야 통과."""
    try:
        secret = str(st.secrets.get("ADMIN_PASSWORD", ""))
    except Exception:      # secrets.toml이 없으면(로컬 등) 접근만으로 예외가 난다
        secret = ""
    expected = secret or os.getenv("ADMIN_PASSWORD", "")
    if not expected:
        st.error("ADMIN_PASSWORD가 설정되지 않았습니다. 앱 시크릿에 추가해 주세요.")
        return False
    if st.session_state.get("admin_ok"):
        return True
    st.title("📊 연구자 대시보드")
    pw = st.text_input("관리자 비밀번호", type="password")
    if st.button("들어가기", type="primary") and pw:
        if pw == expected:
            st.session_state["admin_ok"] = True
            st.rerun()
        st.error("비밀번호가 올바르지 않습니다.")
    return False


@st.cache_data(ttl=60, show_spinner=False)
def load(table: str, cols: str = "*") -> pd.DataFrame:
    """테이블을 DataFrame으로 읽는다(60초 캐시). 대규모 연구에서는 페이지네이션 필요(현재 파일럿 규모)."""
    rows = database.get_client().table(table).select(cols).limit(10000).execute().data
    return pd.DataFrame(rows)


def col(df: pd.DataFrame, name: str) -> pd.Series:
    """빈 DataFrame·없는 컬럼에도 안전하게 열을 돌려준다(집계용)."""
    if df.empty or name not in df.columns:
        return pd.Series([], dtype=object)
    return df[name]


def rate(part: int, whole: int) -> str:
    """전환율 문자열. 분모가 0이면 '-'."""
    return f"{part / whole * 100:.0f}%  ({part}/{whole})" if whole else "-"


def kst_day(series: pd.Series) -> pd.Series:
    """ISO 타임스탬프 열을 한국시간 기준 '날짜(자정)'로 바꾼다(일자별 추이용)."""
    dt = pd.to_datetime(series, format="mixed", utc=True, errors="coerce")
    return dt.dt.tz_convert("Asia/Seoul").dt.normalize().dt.tz_localize(None)


def bar(df: pd.DataFrame, cat: str, val: str, horizontal: bool = True) -> alt.Chart:
    """막대 차트. 기본은 가로 막대(범주 이름이 길어도 잘 읽힌다)."""
    if horizontal:
        enc = {"y": alt.Y(f"{cat}:N", sort="-x", title=None), "x": alt.X(f"{val}:Q", title=None)}
    else:
        enc = {"x": alt.X(f"{cat}:N", sort="-y", title=None), "y": alt.Y(f"{val}:Q", title=None)}
    return (alt.Chart(df).mark_bar(color=GREEN, cornerRadius=3)
            .encode(tooltip=list(df.columns), **enc).properties(height=260))


def donut(df: pd.DataFrame, cat: str, val: str) -> alt.Chart:
    """도넛 차트(범주 비율)."""
    return (alt.Chart(df).mark_arc(innerRadius=62, stroke="white", strokeWidth=2)
            .encode(theta=alt.Theta(f"{val}:Q"),
                    color=alt.Color(f"{cat}:N", scale=alt.Scale(range=PALETTE),
                                    legend=alt.Legend(title=None, orient="bottom")),
                    tooltip=[cat, val]).properties(height=260))


def line(df: pd.DataFrame, x: str, y: str) -> alt.Chart:
    """꺾은선 차트(시간 추이)."""
    return (alt.Chart(df).mark_line(point=True, color=GREEN, strokeWidth=2)
            .encode(x=alt.X(x, title=None), y=alt.Y(f"{y}:Q", title=None), tooltip=list(df.columns))
            .properties(height=260))


def participant_table(parts, sessions, msgs) -> pd.DataFrame:
    """참여자별 요약: 세션 수·질문 수·넛지응답 수·마지막 활동."""
    rows = []
    for pid in col(parts, "participant_id"):
        m = msgs[col(msgs, "participant_id") == pid] if not msgs.empty else msgs
        s = sessions[col(sessions, "participant_id") == pid] if not sessions.empty else sessions
        status = parts.loc[parts.participant_id == pid, "status"].iloc[0] if "status" in parts else "-"
        rows.append({
            "참여자": pid,
            "상태": status,
            "세션수": len(s),
            "질문수": int(((col(m, "role") == "user") & (col(m, "message_type") == "rag_question")).sum()),
            "넛지응답": int((col(m, "message_type") == "nudge_response").sum()),
            "마지막 활동": (col(m, "created_at").max() or "-")[:16] if len(m) else "-",
        })
    return pd.DataFrame(rows)


def section_participation(parts, sessions, msgs) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("참여자 수", len(parts))
    c2.metric("총 세션 수", len(sessions))
    c3.metric("총 질문 수", int(((col(msgs, "role") == "user") &
                                (col(msgs, "message_type") == "rag_question")).sum()))
    pt = participant_table(parts, sessions, msgs)
    left, right = st.columns(2)
    if not pt.empty and pt["질문수"].sum():
        left.caption("참여자별 질문 수")
        left.altair_chart(bar(pt[["참여자", "질문수"]], "참여자", "질문수"), use_container_width=True)
    q = msgs[col(msgs, "message_type") == "rag_question"].copy()
    if not q.empty:
        q["날짜"] = kst_day(q["created_at"])
        daily = q.dropna(subset=["날짜"]).groupby("날짜").size().reset_index(name="질문수")
        right.caption("일자별 질문 추이")
        right.altair_chart(line(daily, "날짜:T", "질문수"), use_container_width=True)
    st.caption("참여자별 상세 (수치)")
    st.dataframe(pt, use_container_width=True, hide_index=True)


def nudge_by_participant(nudges) -> pd.DataFrame:
    """참여자별 넛지 노출·응답·응답률·행동약속."""
    if nudges.empty or "participant_id" not in nudges.columns:
        return pd.DataFrame()
    rows = []
    for pid, g in nudges.groupby("participant_id"):
        disp = len(g)
        ans = int((g["status"] == "answered").sum())
        rows.append({"참여자": pid, "노출": disp, "응답": ans,
                     "응답률(%)": round(ans / disp * 100) if disp else 0,
                     "행동약속": int(g["action_commitment"].notna().sum())})
    return pd.DataFrame(rows).sort_values("응답률(%)", ascending=False)


def section_nudge(nudges) -> None:
    displayed = len(nudges)
    answered = int((col(nudges, "status") == "answered").sum())
    committed = int(col(nudges, "action_commitment").notna().sum()) if not nudges.empty else 0
    n1, n2, n3 = st.columns(3)
    n1.metric("넛지 노출", displayed)
    n2.metric("응답 전환율", rate(answered, displayed))
    n3.metric("행동 약속(하겠다)", committed)
    left, right = st.columns(2)
    if displayed:
        resp = pd.DataFrame({"구분": ["응답", "무응답"], "수": [answered, displayed - answered]})
        left.caption("넛지 응답 전환")
        left.altair_chart(donut(resp, "구분", "수"), use_container_width=True)
    if not nudges.empty and "template_key" in nudges:
        by_tpl = nudges.groupby("template_key").size().reset_index(name="노출수")
        right.caption("넛지 종류별 노출")
        right.altair_chart(bar(by_tpl, "template_key", "노출수"), use_container_width=True)
        st.caption("넛지 종류별 노출 (수치)")
        st.dataframe(by_tpl, use_container_width=True, hide_index=True)
    per = nudge_by_participant(nudges)
    if not per.empty:
        st.markdown("**참여자별 넛지 반응**")
        pleft, pright = st.columns(2)
        pleft.caption("참여자별 응답률(%)")
        pleft.altair_chart(bar(per[["참여자", "응답률(%)"]], "참여자", "응답률(%)"), use_container_width=True)
        pright.caption("참여자별 상세 (노출·응답·응답률·행동약속)")
        pright.dataframe(per, use_container_width=True, hide_index=True)


def hist(df: pd.DataFrame, val: str, maxbins: int = 12) -> alt.Chart:
    """히스토그램(연속값 분포)."""
    return (alt.Chart(df).mark_bar(color=GREEN)
            .encode(x=alt.X(f"{val}:Q", bin=alt.Bin(maxbins=maxbins), title=None),
                    y=alt.Y("count()", title="건수"), tooltip=["count()"]).properties(height=260))


def rag_table(retr, rchunks) -> pd.DataFrame:
    """검색별 상세: 질문·근거수준·top유사도·검색/선택 청크 수·시각."""
    r = retr.rename(columns={"query_text": "질문", "evidence_level": "근거수준",
                             "knowledge_base_version": "KB버전"}).copy()
    if not rchunks.empty:
        top = rchunks.groupby("retrieval_id")["similarity_score"].max()
        ret = rchunks.groupby("retrieval_id").size()
        sel = rchunks[rchunks["was_selected"] == True].groupby("retrieval_id").size()
        r["top유사도"] = r["retrieval_id"].map(top).round(3)
        r["검색청크"] = r["retrieval_id"].map(ret).fillna(0).astype(int)
        r["선택청크"] = r["retrieval_id"].map(sel).fillna(0).astype(int)
    r["시각"] = r["retrieved_at"].astype(str).str[:16]
    return r


def doc_usage(rchunks, dchunks, docs) -> pd.DataFrame:
    """문서별 '근거로 선택된 청크 수'. 안 쓰인 문서는 0으로 함께 보여준다(커버리지 점검)."""
    if docs.empty:
        return pd.DataFrame()
    used = pd.Series(dtype="int64")
    if not rchunks.empty and not dchunks.empty:
        sel = rchunks[rchunks["was_selected"] == True].copy()
        sel["document_id"] = sel["chunk_id"].map(dict(zip(dchunks["chunk_id"], dchunks["document_id"])))
        used = sel.groupby("document_id").size()
    out = docs.copy()
    out["근거 선택 횟수"] = out["document_id"].map(used).fillna(0).astype(int)
    return (out[["title", "근거 선택 횟수"]].rename(columns={"title": "문서"})
            .sort_values("근거 선택 횟수", ascending=False))


# 질문을 큰 주제로 묶는 사전(부분 문자열 매칭). 연구팀이 자유롭게 수정 가능.
TOPICS = {
    "혈당/수치": ["혈당", "수치", "당화", "에이원", "a1c"],
    "저혈당": ["저혈당"],
    "식사/음식": ["식사", "음식", "먹", "밥", "탄수", "당지수", "간식"],
    "운동": ["운동", "걷", "산책", "활동"],
    "복약/약": ["약", "복용", "인슐린", "주사"],
    "합병증/발관리": ["합병증", "발", "상처", "신장", "저림", "눈", "혈관"],
    "혈압": ["혈압"],
    "체중": ["체중", "비만"],
}


def topic_analysis(retr) -> pd.DataFrame:
    """질문을 주제별로 분류해 '질문 수 + 근거 부족 비율'을 낸다(문서 보강 판단용)."""
    if retr.empty:
        return pd.DataFrame()
    q = retr["query_text"].fillna("")
    rows = []
    for topic, kws in TOPICS.items():
        mask = q.apply(lambda t: any(k in t for k in kws))
        n = int(mask.sum())
        if not n:
            continue
        insf = int((retr.loc[mask, "evidence_level"] == "insufficient").sum())
        rows.append({"주제": topic, "질문수": n, "근거부족": insf, "부족률(%)": round(insf / n * 100)})
    return pd.DataFrame(rows).sort_values("질문수", ascending=False)


def keyword_freq(retr, topn: int = 12) -> pd.DataFrame:
    """질문에서 자주 나온 단어(대략). 흔한 조사·의문사는 정리한다(형태소 분석은 아님)."""
    if retr.empty:
        return pd.DataFrame()
    josa = ("으로", "에서", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "도", "의", "로", "와", "과", "만")
    stop = {"어떻게", "무엇", "해도", "해야", "되나요", "인가요", "있나요", "하나요", "알려줘",
            "궁금", "무슨", "이건", "저는", "너는", "그리고", "지금", "그때"}
    c: Counter = Counter()
    for t in retr["query_text"].fillna(""):
        for w in re.findall(r"[가-힣]{2,}", t):
            for j in josa:
                if len(w) - len(j) >= 2 and w.endswith(j):
                    w = w[: -len(j)]
                    break
            if len(w) >= 2 and w not in stop:
                c[w] += 1
    return pd.DataFrame(c.most_common(topn), columns=["키워드", "횟수"])


def chunk_usage(rchunks, dchunks, docs, topn: int = 10) -> pd.DataFrame:
    """가장 많이 '근거로 선택된' 청크 top N — 내용 미리보기·문서·페이지와 함께."""
    if rchunks.empty or dchunks.empty:
        return pd.DataFrame()
    sel = rchunks[rchunks["was_selected"] == True]
    if sel.empty:
        return pd.DataFrame()
    m = sel.groupby("chunk_id").size().rename("선택횟수").reset_index().merge(dchunks, on="chunk_id", how="left")
    if not docs.empty:
        m = m.merge(docs, on="document_id", how="left")
    m["내용"] = m["content"].astype(str).str.slice(0, 60) + "…"
    out = m.sort_values("선택횟수", ascending=False).head(topn)
    cols = [c for c in ["선택횟수", "title", "page_number", "내용"] if c in out.columns]
    return out[cols].rename(columns={"title": "문서", "page_number": "쪽"})


def section_qa(events, retr, rchunks, dchunks, docs, calls) -> None:
    if retr.empty:
        st.caption("아직 RAG 검색 기록이 없습니다.")
        return
    total = len(retr)
    ev = retr["evidence_level"].value_counts()
    rt = rag_table(retr, rchunks)
    avg_top = rt["top유사도"].mean() if "top유사도" in rt.columns else float("nan")
    emb = col(calls, "call_type") == "query_embedding"
    ans = col(calls, "call_type") == "rag_answer"
    emb_lat = calls.loc[emb, "latency_ms"].mean() if emb.any() else float("nan")
    ans_lat = calls.loc[ans, "latency_ms"].mean() if ans.any() else float("nan")
    clicks = int((col(events, "event_type") == "source_clicked").sum())

    m = st.columns(3)
    m[0].metric("총 검색 수", total)
    m[1].metric("근거 충분", rate(int(ev.get("sufficient", 0)), total))
    m[2].metric("근거 부족 ⚠️", rate(int(ev.get("insufficient", 0)), total))
    m2 = st.columns(3)
    m2[0].metric("평균 top-1 유사도", f"{avg_top:.3f}" if avg_top == avg_top else "-")
    m2[1].metric("평균 검색 지연", f"{emb_lat:.0f} ms" if emb_lat == emb_lat else "-")
    m2[2].metric("평균 답변 생성", f"{ans_lat / 1000:.1f} 초" if ans_lat == ans_lat else "-")
    st.caption(f"‘근거 부족’ 비율이 높거나 top유사도가 낮으면 문서 보강·검색 개선이 필요하다는 신호입니다. (출처 클릭 {clicks}회)")

    lvl = ev.reset_index()
    lvl.columns = ["근거 충분성", "건수"]
    left, right = st.columns(2)
    left.caption("근거 충분성 분포 (충분/부분/부족)")
    left.altair_chart(donut(lvl, "근거 충분성", "건수"), use_container_width=True)
    if "top유사도" in rt.columns and rt["top유사도"].notna().any():
        right.caption("top-1 유사도 분포 (오른쪽일수록 근거가 강함)")
        right.altair_chart(hist(rt.dropna(subset=["top유사도"]), "top유사도"), use_container_width=True)

    usage = doc_usage(rchunks, dchunks, docs)
    if not usage.empty:
        st.markdown("**문서별 근거 활용** — 어떤 승인 문서가 실제 근거로 쓰였나 (0이면 한 번도 안 쓰임 → 커버리지 점검)")
        u1, u2 = st.columns(2)
        u1.altair_chart(bar(usage, "문서", "근거 선택 횟수"), use_container_width=True)
        u2.dataframe(usage, use_container_width=True, hide_index=True)

    ta = topic_analysis(retr)
    if not ta.empty:
        st.markdown("**질문 주제·키워드 분석** — 많이 묻는 주제인데 **근거 부족률이 높으면** 그 주제 문서를 보강하면 품질이 오릅니다")
        t1, t2 = st.columns(2)
        t1.caption("주제별 질문 수")
        t1.altair_chart(bar(ta[["주제", "질문수"]], "주제", "질문수"), use_container_width=True)
        t2.caption("주제별 질문 수 · 근거 부족률")
        t2.dataframe(ta, use_container_width=True, hide_index=True)
        kw = keyword_freq(retr)
        if not kw.empty:
            st.caption("자주 나온 키워드 (대략 — 형태소 분석 아님)")
            st.altair_chart(bar(kw, "키워드", "횟수"), use_container_width=True)
    cu = chunk_usage(rchunks, dchunks, docs)
    if not cu.empty:
        st.markdown("**많이 쓰인 근거 청크** — 어떤 문서 조각이 자주 근거로 선택되나 (활용 높은 지식 조각)")
        st.dataframe(cu, use_container_width=True, hide_index=True)

    st.markdown("**⚠️ 근거를 못 찾은 / 약한 질문** — 이 주제의 문서를 보강하면 정확도가 오릅니다")
    cond = rt["근거수준"] == "insufficient"
    if "top유사도" in rt.columns:
        cond = cond | (rt["top유사도"] < 0.30)
    weak = rt[cond]
    weak_cols = [c for c in ["질문", "근거수준", "top유사도", "시각"] if c in weak.columns]
    if weak.empty:
        st.caption("근거 부족·약한 질문이 없습니다. 👍")
    else:
        st.dataframe(weak[weak_cols].sort_values("top유사도"), use_container_width=True, hide_index=True)

    with st.expander("질문별 RAG 상세 전체 보기"):
        full = [c for c in ["질문", "근거수준", "top유사도", "검색청크", "선택청크", "KB버전", "시각"]
                if c in rt.columns]
        st.dataframe(rt[full].sort_values("시각", ascending=False),
                     use_container_width=True, hide_index=True)


def section_safety(events) -> None:
    safety = int((col(events, "event_type") == "safety_message_shown").sum())
    st.metric("안전 안내 노출(safety_message_shown)", safety)
    if safety == 0:
        st.caption("아직 안전 안내가 작동한 기록이 없습니다.")


def section_cost(calls, errors) -> None:
    if calls.empty:
        st.caption("API 호출 기록이 아직 없습니다.")
    else:
        agg = calls.groupby("call_type").agg(
            호출수=("call_type", "size"), 입력토큰=("input_tokens", "sum"),
            출력토큰=("output_tokens", "sum"), 평균지연ms=("latency_ms", "mean"),
        ).reset_index()
        agg["평균지연ms"] = agg["평균지연ms"].round(0)
        left, right = st.columns(2)
        left.caption("호출 유형별 횟수")
        left.altair_chart(bar(agg, "call_type", "호출수"), use_container_width=True)
        right.caption("유형별 토큰·지연 상세")
        right.dataframe(agg, use_container_width=True, hide_index=True)
        st.caption(f"API 실패 호출: {int((col(calls, 'status') != 'success').sum())}건")
    if not errors.empty:
        et = errors["error_type"].value_counts().reset_index()
        et.columns = ["오류 유형", "건수"]
        st.altair_chart(bar(et, "오류 유형", "건수"), use_container_width=True)


def section_csv() -> None:
    st.caption("분석용 원자료를 내려받습니다. 직접식별정보는 저장되지 않습니다. (내려받기 전 상단 새로고침으로 최신화)")
    cols = st.columns(4)
    for i, (label, table) in enumerate([
        ("참여자", "participants"), ("세션", "sessions"), ("메시지", "messages"),
        ("이벤트", "events"), ("넛지", "nudge_events"), ("검색로그", "retrieval_logs"),
        ("API호출", "model_calls"), ("기술오류", "technical_errors"),
    ]):
        df = load(table)
        cols[i % 4].download_button(
            f"⬇ {label}", df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{table}.csv", mime="text/csv", use_container_width=True,
            key=f"dl_{table}", disabled=df.empty)


def main() -> None:
    st.title("📊 연구자 대시보드")
    st.caption("참여자 앱과 분리된 읽기 전용 화면 · 참여자는 익명 ID로만 표시")
    if st.button("🔄 새로고침(캐시 비우기)"):
        st.cache_data.clear()
        st.rerun()

    parts = load("participants")
    sessions = load("sessions", "session_id, participant_id, started_at")
    msgs = load("messages", "participant_id, role, message_type, created_at")
    events = load("events", "event_type, participant_id")
    nudges = load("nudge_events", "participant_id, status, response, action_commitment, template_key")
    retr = load("retrieval_logs",
                "retrieval_id, question_message_id, query_text, evidence_level, knowledge_base_version, retrieved_at")
    rchunks = load("retrieval_chunks", "retrieval_id, chunk_id, similarity_score, was_selected")
    dchunks = load("document_chunks", "chunk_id, document_id, content, page_number")
    docs = load("documents", "document_id, title")
    calls = load("model_calls", "call_type, input_tokens, output_tokens, latency_ms, status")
    errors = load("technical_errors", "error_type")

    tabs = st.tabs(["👥 참여 현황", "🌱 넛지 성과", "💬 질문·근거",
                    "🛡️ 안전", "💰 비용·운영", "📁 데이터 추출"])
    with tabs[0]:
        section_participation(parts, sessions, msgs)
    with tabs[1]:
        section_nudge(nudges)
    with tabs[2]:
        section_qa(events, retr, rchunks, dchunks, docs, calls)
    with tabs[3]:
        section_safety(events)
    with tabs[4]:
        section_cost(calls, errors)
    with tabs[5]:
        section_csv()


if check_password():
    main()
