"""T2.1 — 승인 문서 4개를 documents 테이블에 등록한다 (지식베이스 시딩).

한 번만 하는 관리 작업이라 앱 코드가 아니라 스크립트로 둔다.
여러 번 실행해도 같은 문서가 중복 등록되지 않는다(database.register_document가 멱등).

실행: .venv/bin/python scripts/seed_documents.py
"""

import os
import sys

# src/ 모듈(database, config)을 불러오기 위해 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import database  # noqa: E402
import ingest_db  # 시딩 전용 DB 쓰기 (코어 밖)  # noqa: E402

# ── 등록할 문서 4개 ─────────────────────────────────────────────
# published_at은 확실한 것만 채운다(추측 금지). 65세용 자료는 발행정보 미상.
# source_location은 data/source_docs 안의 실제 PDF 파일명.
# (참고: 표준교육자료는 청크에는 'DMhmenu180514.pdf', 실제 PDF는 'DMmenu180514.pdf'로
#  파일명이 조금 다르다 — T2.4에서 청크를 문서에 연결할 때 이 점을 고려한다.)
DOCUMENTS = [
    {
        "title": "일차 의료용 근거기반 당뇨병 권고 요약 정보",
        "publisher": "대한당뇨병학회 외 6개 학회",
        "published_at": "2018-12-31",
        "source_version": "2020-rev",
        "source_location": "[당뇨병]권고 요약정보_전자.pdf",
    },
    {
        "title": "근거기반 당뇨병 환자 관리 정보",
        "publisher": "대한의학회·질병관리본부",
        "published_at": "2014-12-01",
        "source_version": "2016-rev",
        "source_location": "근거기반 당뇨병 환자 관리 정보.pdf",
    },
    {
        "title": "노년 당뇨병 환자에게 필요한 정보 (65세 이상)",
        "publisher": None,          # 미상 — 추후 확인
        "published_at": None,       # 미상
        "source_version": None,
        "source_location": "당뇨병 환자에게 필요한 정보_65세 이상.pdf",
    },
    {
        "title": "고혈압·당뇨병 표준교육자료: 당뇨병 고급실습과정 교육지침서",
        "publisher": "질병관리본부·아주대학교 의과대학",
        "published_at": None,       # 연도(2012)만 확인 → source_version에 기록
        "source_version": "2012",
        "source_location": "DMmenu180514.pdf",
    },
]


def main() -> int:
    ok, msg = database.check_connection()
    print(f"DB 연결: {msg}")
    if not ok:
        return 1

    print(f"\n문서 {len(DOCUMENTS)}개 등록 시도 (멱등 — 이미 있으면 건너뜀)\n")
    for doc in DOCUMENTS:
        row = ingest_db.register_document(**doc)
        pub = row.get("publisher") or "발행정보 미상"
        print(f"  ✅ [{row['approval_status']}] {row['title']}")
        print(f"      {pub} · 버전={row.get('source_version')} · id={row['document_id'][:8]}…")

    # 최종 확인
    total = database.get_client().table("documents").select("document_id").execute().data
    print(f"\ndocuments 테이블 총 {len(total)}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
