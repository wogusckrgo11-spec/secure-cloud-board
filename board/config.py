"""애플리케이션 설정 로드 모듈.

DB 접속 정보 등 민감한 값은 오직 환경변수에서만 읽어온다.
(운영: systemd EnvironmentFile / 로컬: 셸 export 또는 .env 로드 래퍼)
하드코딩을 금지하며, 필수 값이 없으면 기동 시점에 즉시 실패시킨다(fail-fast).
"""

import os


class ConfigError(RuntimeError):
  """필수 환경변수 누락 시 발생."""


def _require(key):
  """필수 환경변수를 읽고, 없으면 예외."""
  value = os.environ.get(key)
  if not value:
    raise ConfigError(f"필수 환경변수가 설정되지 않았습니다: {key}")
  return value


class Config:
  # --- DB 접속 정보 (전부 환경변수 주입, 하드코딩 금지) ---
  DB_HOST = _require("DB_HOST")
  DB_PORT = int(os.environ.get("DB_PORT", "3306"))
  DB_USER = _require("DB_USER")
  DB_PASSWORD = _require("DB_PASSWORD")
  DB_NAME = _require("DB_NAME")

  # --- Flask ---
  # flash 메시지에 세션 쿠키 서명이 필요하므로 운영에서는 반드시 설정한다.
  SECRET_KEY = os.environ.get("SECRET_KEY", "")

  # --- 목록 페이지네이션 ---
  PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "10"))

  # --- 입력값 길이 제한 ---
  MAX_TITLE_LEN = 200
  MAX_WRITER_LEN = 50
  MAX_CONTENT_LEN = 10000
