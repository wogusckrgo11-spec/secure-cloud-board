"""PyMySQL 기반 DB 커넥션 헬퍼.

- 요청마다 커넥션을 하나 열고 Flask 애플리케이션 컨텍스트(g)에 보관한다.
- 요청 종료 시 teardown 콜백에서 자동으로 닫는다.
- 모든 쿼리는 호출부에서 파라미터 바인딩 cursor.execute(sql, params) 로 실행한다.
  (문자열 포매팅/조합으로 SQL 을 만들지 않는다 → SQL Injection 방지)
"""

import pymysql
from flask import g, current_app


def get_db():
  """현재 요청에 연결된 DB 커넥션을 반환(없으면 생성)."""
  if "db" not in g:
    cfg = current_app.config
    g.db = pymysql.connect(
      host=cfg["DB_HOST"],
      port=cfg["DB_PORT"],
      user=cfg["DB_USER"],
      password=cfg["DB_PASSWORD"],
      database=cfg["DB_NAME"],
      charset="utf8mb4",
      autocommit=False,
      cursorclass=pymysql.cursors.DictCursor,
    )
  return g.db


def close_db(exc=None):
  """요청 종료 시 커넥션 정리."""
  db = g.pop("db", None)
  if db is not None:
    db.close()


def init_app(app):
  """앱에 teardown 콜백 등록."""
  app.teardown_appcontext(close_db)
