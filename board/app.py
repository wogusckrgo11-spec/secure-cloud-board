"""게시판 Flask 애플리케이션 (애플리케이션 팩토리).

라우트:
  GET  /            게시글 목록 (페이지네이션)
  GET  /write       작성 폼
  POST /write       작성 처리 (검증 후 INSERT)
  GET  /posts/<id>  상세 보기
  POST /posts/<id>/delete  삭제 처리 (인증 없음 - 누구나 삭제)

Gunicorn 진입점: gunicorn "app:app"
"""

from flask import (
  Flask, render_template, request, redirect, url_for, abort, flash
)

import db
from config import Config


def create_app():
  app = Flask(__name__)
  app.config.from_object(Config)

  if not app.config["SECRET_KEY"]:
    # flash 메시지에 세션이 필요하다. 운영에서는 .env 의 SECRET_KEY 를 채울 것.
    app.logger.warning("SECRET_KEY 미설정 - 개발용 임시 키 사용 중")
    app.config["SECRET_KEY"] = "dev-only-change-me"

  db.init_app(app)

  @app.get("/")
  def index():
    # 페이지 번호 파싱 (음수/문자 방어)
    page = request.args.get("page", 1, type=int) or 1
    if page < 1:
      page = 1
    size = app.config["PAGE_SIZE"]
    offset = (page - 1) * size

    conn = db.get_db()
    with conn.cursor() as cur:
      cur.execute("SELECT COUNT(*) AS cnt FROM posts")
      total = cur.fetchone()["cnt"]
      # 파라미터 바인딩 사용
      cur.execute(
        "SELECT id, title, writer, created_at "
        "FROM posts ORDER BY id DESC LIMIT %s OFFSET %s",
        (size, offset),
      )
      posts = cur.fetchall()

    total_pages = max(1, (total + size - 1) // size)
    return render_template(
      "list.html", posts=posts, page=page, total_pages=total_pages
    )

  @app.route("/write", methods=["GET", "POST"])
  def write():
    if request.method == "GET":
      return render_template("write.html", form={})

    # --- 입력값 수집 ---
    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    writer = (request.form.get("writer") or "").strip() or "익명"

    # --- 최소 입력값 검증 ---
    errors = []
    if not title:
      errors.append("제목을 입력하세요.")
    if not content:
      errors.append("내용을 입력하세요.")
    if len(title) > app.config["MAX_TITLE_LEN"]:
      errors.append(f"제목은 {app.config['MAX_TITLE_LEN']}자 이하여야 합니다.")
    if len(writer) > app.config["MAX_WRITER_LEN"]:
      errors.append(f"작성자는 {app.config['MAX_WRITER_LEN']}자 이하여야 합니다.")
    if len(content) > app.config["MAX_CONTENT_LEN"]:
      errors.append(f"내용은 {app.config['MAX_CONTENT_LEN']}자 이하여야 합니다.")

    if errors:
      for msg in errors:
        flash(msg, "error")
      # 입력했던 값을 유지한 채 폼 재표시
      return render_template(
        "write.html",
        form={"title": title, "content": content, "writer": writer},
      ), 400

    # --- 저장 (파라미터 바인딩) ---
    conn = db.get_db()
    with conn.cursor() as cur:
      cur.execute(
        "INSERT INTO posts (title, content, writer) VALUES (%s, %s, %s)",
        (title, content, writer),
      )
      new_id = cur.lastrowid
    conn.commit()

    return redirect(url_for("detail", post_id=new_id))

  @app.get("/posts/<int:post_id>")
  def detail(post_id):
    conn = db.get_db()
    with conn.cursor() as cur:
      cur.execute(
        "SELECT id, title, content, writer, created_at "
        "FROM posts WHERE id = %s",
        (post_id,),
      )
      post = cur.fetchone()

    if post is None:
      abort(404)
    return render_template("detail.html", post=post)

  @app.post("/posts/<int:post_id>/delete")
  def delete(post_id):
    # 인증 없는 익명 게시판 - 누구나 삭제 가능 (정책상 확정)
    conn = db.get_db()
    with conn.cursor() as cur:
      # 존재 여부 확인 (detail() 과 동일한 패턴)
      cur.execute("SELECT id FROM posts WHERE id = %s", (post_id,))
      if cur.fetchone() is None:
        abort(404)
      cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    conn.commit()

    flash("게시글을 삭제했습니다.", "info")
    return redirect(url_for("index"))

  return app


# Gunicorn / flask run 공통 진입점
app = create_app()
