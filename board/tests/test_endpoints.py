"""app.py 엔드포인트 통합 검증 (Flask test_client, DB 불필요).

실행:  python tests/test_endpoints.py
"""

import re
import sys

import harness

harness.seed(13)  # 페이지네이션 테스트용 (PAGE_SIZE=10 → 2페이지)

from app import app  # noqa: E402

app.config.update(TESTING=True)
c = app.test_client()

passed = 0
failed = 0


def check(name, cond, extra=""):
  global passed, failed
  if cond:
    passed += 1
    print(f"  PASS  {name}")
  else:
    failed += 1
    print(f"  FAIL  {name}  {extra}")


print("\n[1] GET / (목록 1페이지)")
r = c.get("/")
body = r.get_data(as_text=True)
check("200 응답", r.status_code == 200, r.status_code)
check("최신글(13번) 노출", "테스트 게시글 13" in body)
check("11번째 글은 다음 페이지로", "테스트 게시글 3" not in body)
check("페이지 표시 '1 / 2'", "1 / 2" in body)
check("글쓰기 링크 존재", 'href="/write"' in body)

print("\n[2] GET /?page=2")
r = c.get("/?page=2")
body = r.get_data(as_text=True)
check("200 응답", r.status_code == 200, r.status_code)
check("남은 글(1번) 노출", "테스트 게시글 1" in body)
check("페이지 표시 '2 / 2'", "2 / 2" in body)

print("\n[3] GET /?page=-5 (음수 방어)")
r = c.get("/?page=-5")
check("200 으로 클램프", r.status_code == 200, r.status_code)

print("\n[4] GET /?page=abc (문자 방어)")
r = c.get("/?page=abc")
check("200 (기본 1페이지)", r.status_code == 200, r.status_code)

print("\n[5] GET /write (작성 폼)")
r = c.get("/write")
body = r.get_data(as_text=True)
check("200 응답", r.status_code == 200, r.status_code)
check("title 입력 필드", 'name="title"' in body)
check("content 입력 필드", 'name="content"' in body)

print("\n[6] POST /write (정상 등록)")
before = harness.count()
r = c.post("/write", data={"title": "새 글", "content": "새 본문", "writer": "홍길동"})
check("302 리다이렉트", r.status_code == 302, r.status_code)
m = re.search(r"/posts/(\d+)", r.headers.get("Location", ""))
check("Location 이 /posts/<id>", m is not None, r.headers.get("Location"))
check("DB 행 1개 증가", harness.count() == before + 1)
new_id = int(m.group(1)) if m else None
row = harness.get_row(new_id)
check("저장된 값 일치", row and row["title"] == "새 글" and row["writer"] == "홍길동")
check("created_at 자동 생성", row and row["created_at"] is not None)

print("\n[7] GET /posts/<id> (상세, 방금 등록글)")
r = c.get(f"/posts/{new_id}")
body = r.get_data(as_text=True)
check("200 응답", r.status_code == 200, r.status_code)
check("본문 노출", "새 본문" in body)
check("작성자 노출", "홍길동" in body)

print("\n[8] POST /write (제목 빈 값)")
before = harness.count()
r = c.post("/write", data={"title": "  ", "content": "내용만"})
body = r.get_data(as_text=True)
check("400 응답", r.status_code == 400, r.status_code)
check("에러 메시지 노출", "제목을 입력하세요" in body)
check("DB 미변경", harness.count() == before)
check("입력값 유지(내용)", "내용만" in body)

print("\n[9] POST /write (내용 빈 값)")
r = c.post("/write", data={"title": "제목만", "content": ""})
body = r.get_data(as_text=True)
check("400 응답", r.status_code == 400, r.status_code)
check("에러 메시지 노출", "내용을 입력하세요" in body)

print("\n[10] POST /write (writer 빈 값 → '익명')")
r = c.post("/write", data={"title": "익명글", "content": "내용", "writer": ""})
m = re.search(r"/posts/(\d+)", r.headers.get("Location", ""))
row = harness.get_row(int(m.group(1)))
check("writer 가 '익명'", row["writer"] == "익명", row["writer"] if row else None)

print("\n[11] POST /write (제목 200자 초과)")
before = harness.count()
r = c.post("/write", data={"title": "가" * 201, "content": "내용"})
body = r.get_data(as_text=True)
check("400 응답", r.status_code == 400, r.status_code)
check("길이 초과 메시지", "200자 이하" in body)
check("DB 미변경", harness.count() == before)

print("\n[12] GET /posts/99999 (없는 글)")
r = c.get("/posts/99999")
check("404 응답", r.status_code == 404, r.status_code)

print("\n[13] GET /posts/abc (숫자 아님)")
r = c.get("/posts/abc")
check("404 (int 컨버터)", r.status_code == 404, r.status_code)

print("\n[14] XSS 방어 (Jinja autoescape)")
payload = "<script>alert('xss')</script>"
r = c.post("/write", data={"title": "xss테스트", "content": payload, "writer": "x"})
m = re.search(r"/posts/(\d+)", r.headers.get("Location", ""))
r = c.get(f"/posts/{m.group(1)}")
body = r.get_data(as_text=True)
check("원본 <script> 미포함", payload not in body)
check("이스케이프된 형태 포함", "&lt;script&gt;" in body)

print("\n[15] SQL Injection 방어 (파라미터 바인딩)")
evil = "'; DROP TABLE posts; --"
before = harness.count()
r = c.post("/write", data={"title": evil, "content": "sqli", "writer": "x"})
check("302 (정상 저장)", r.status_code == 302, r.status_code)
check("posts 테이블 생존", harness.count() == before + 1)
m = re.search(r"/posts/(\d+)", r.headers.get("Location", ""))
row = harness.get_row(int(m.group(1)))
check("제목이 리터럴로 저장됨", row["title"] == evil, row["title"] if row else None)
r = c.get("/")
check("목록 정상 동작", r.status_code == 200, r.status_code)

print(f"\n{'=' * 40}\n결과: {passed} PASS / {failed} FAIL\n{'=' * 40}")
sys.exit(1 if failed else 0)
