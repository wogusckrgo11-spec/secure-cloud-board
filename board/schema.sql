-- 게시판 스키마 및 애플리케이션 전용 계정 생성
-- DB 서버(프라이빗 서브넷)에서 관리자 계정으로 1회 실행한다.
--   mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS board
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE board;

CREATE TABLE IF NOT EXISTS posts (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title      VARCHAR(200) NOT NULL,
  content    TEXT         NOT NULL,
  writer     VARCHAR(50)  NOT NULL DEFAULT '익명',
  -- created_at 은 애플리케이션이 아닌 DB 가 채운다.
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 애플리케이션 전용 계정: 웹서버의 사설 IP 에서만 접속 허용.
-- 아래 10.0.1.10 을 실제 웹서버 프라이빗 IP 로, 비밀번호를 강력한 값으로 교체할 것.
CREATE USER IF NOT EXISTS 'board_app'@'10.0.1.10'
  IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';

-- 필요한 최소 권한만 부여 (게시판은 조회/작성만 하므로 SELECT, INSERT)
GRANT SELECT, INSERT ON board.posts TO 'board_app'@'10.0.1.10';

FLUSH PRIVILEGES;
