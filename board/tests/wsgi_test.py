"""Gunicorn 기동 스모크 테스트용 WSGI 진입점 (DB 불필요).

harness 를 먼저 import 해 db.get_db 를 SQLite 로 교체한 뒤 실제 app 을 노출한다.
운영에서는 deploy/gunicorn-board.service 가 'app:app' 을 그대로 사용한다.

실행 예:
  cd tests
  PYTHONPATH=. gunicorn --workers 1 --bind 127.0.0.1:5056 wsgi_test:app
"""

import harness

harness.seed(3)

from app import app  # noqa: E402,F401
