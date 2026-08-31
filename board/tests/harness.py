"""로컬 테스트 하네스 (DB 불필요).

실제 app.py 를 그대로 import 하되 db.get_db() 만 인메모리 SQLite 로 교체한다.
db.py / schema.sql 원본은 수정하지 않는다(런타임 몽키패치).
PyMySQL 과의 차이(%s 플레이스홀더, DictCursor, lastrowid, cursor 컨텍스트매니저)는
얇은 shim 으로 흡수한다.
"""

import datetime
import os
import sqlite3
import sys

# 저장소 루트(= board/) 를 import 경로에 추가
BOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOARD_DIR)

# config.py 는 import 시점에 필수 환경변수를 검증한다 → 더미 값으로 채운다(실제로는 미사용).
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PAGE_SIZE", "10")

# 'timestamp' 선언 컬럼 → datetime 자동 변환 (Jinja 의 created_at.strftime 대비)
sqlite3.register_converter(
  "timestamp", lambda b: datetime.datetime.fromisoformat(b.decode())
)

_conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
_conn.row_factory = sqlite3.Row
_conn.executescript(
  """
  CREATE TABLE posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      VARCHAR(200) NOT NULL,
    content    TEXT         NOT NULL,
    writer     VARCHAR(50)  NOT NULL DEFAULT '익명',
    created_at timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  """
)


class _DictCursor:
  """PyMySQL DictCursor + 컨텍스트매니저 흉내."""

  def __init__(self, conn):
    self._cur = conn.cursor()

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    self._cur.close()
    return False

  def execute(self, sql, params=()):
    # PyMySQL 은 %s, sqlite3 는 ? — SQL 문자열은 코드 리터럴이므로 안전하게 치환 가능
    self._cur.execute(sql.replace("%s", "?"), params)
    return self

  def fetchone(self):
    row = self._cur.fetchone()
    return dict(row) if row is not None else None

  def fetchall(self):
    return [dict(r) for r in self._cur.fetchall()]

  @property
  def lastrowid(self):
    return self._cur.lastrowid


class _ConnShim:
  def __init__(self, conn):
    self._conn = conn

  def cursor(self):
    return _DictCursor(self._conn)

  def commit(self):
    self._conn.commit()


_shim = _ConnShim(_conn)

import db  # noqa: E402

db.get_db = lambda: _shim  # 몽키패치


def seed(n):
  """테스트용 게시글 n개 삽입."""
  cur = _conn.cursor()
  for i in range(1, n + 1):
    cur.execute(
      "INSERT INTO posts (title, content, writer) VALUES (?, ?, ?)",
      (f"테스트 게시글 {i}", f"본문 내용 {i}\n둘째 줄", f"작성자{i}"),
    )
  _conn.commit()


def count():
  return _conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]


def get_row(post_id):
  r = _conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
  return dict(r) if r else None
