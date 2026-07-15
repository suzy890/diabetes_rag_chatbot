"""지식베이스 시딩(1회성 관리 작업) 전용 DB 쓰기 함수.

실행 앱은 이 모듈을 쓰지 않는다. 문서를 등록하거나 청크를 넣는 것은
연구자가 수동으로 돌리는 관리 작업이므로, 요청 경로의 코어(database.py)와
분리해 둔다. 실행 앱의 DB 접근은 여전히 database.py로만 이뤄진다.
(줄수 규칙: database.py는 실행 로직이 아니라 DB 배관 → 별도 관리)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import database  # get_client() 재사용  # noqa: E402


def register_document(
    title: str,
    publisher: str | None = None,
    published_at: str | None = None,
    source_version: str | None = None,
    approval_status: str = "approved",
    source_location: str | None = None,
) -> dict:
    """승인 문서를 documents에 등록한다 (멱등: 같은 제목·판버전이면 다시 안 넣음)."""
    client = database.get_client()
    existing = client.table("documents").select("*").eq("title", title).execute().data
    for row in existing:
        if row.get("source_version") == source_version:
            return row
    new_row = {
        "title": title,
        "publisher": publisher,
        "published_at": published_at,
        "source_version": source_version,
        "approval_status": approval_status,
        "source_location": source_location,
    }
    return client.table("documents").insert(new_row).execute().data[0]


def count_chunks(embedding_version: str) -> int:
    """해당 임베딩 버전으로 이미 저장된 청크 수 (재실행 시 중복 저장 방지 확인용)."""
    return (database.get_client().table("document_chunks")
            .select("chunk_id", count="exact")
            .eq("embedding_version", embedding_version).execute().count or 0)


def insert_document_chunks(rows: list[dict]) -> int:
    """청크+임베딩을 한꺼번에 저장한다. embedding은 pgvector 문자열 '[v1,...]'로 넣는다."""
    if not rows:
        return 0
    return len(database.get_client().table("document_chunks").insert(rows).execute().data)
