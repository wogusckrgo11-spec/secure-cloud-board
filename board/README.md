# 게시판 (Nginx + Flask + MySQL)

Amazon Linux 2023 기준. **웹서버(퍼블릭 서브넷)** 와 **DB서버(프라이빗 서브넷)** 를 분리한 EC2 2대 구성.

```
                  ┌───────────── 퍼블릭 서브넷 ─────────────┐   ┌──── 프라이빗 서브넷 ────┐
[인터넷] ──80──▶  │  Nginx  ──127.0.0.1:5000──▶  Gunicorn   │   │                        │
                  │  (:80)                       + Flask     │──3306──▶   MySQL           │
                  └────────────────────────────────────────┘   └────────────────────────┘
                     웹서버 EC2                                    DB서버 EC2
```

- 외부에 열리는 포트는 웹서버의 **80 하나**. Flask(5000)는 `127.0.0.1` 에만 바인딩되어 직접 접근 불가.
- DB는 프라이빗 서브넷에 있어 인터넷에서 도달 불가. **웹서버 보안그룹에서 오는 3306만** 허용.

---

## 0. 저장소 & 클론

저장소: <https://github.com/wogusckrgo11-spec/secure-cloud-board> (비공개)

```bash
# HTTPS
git clone https://github.com/wogusckrgo11-spec/secure-cloud-board.git

# SSH
git clone git@github.com:wogusckrgo11-spec/secure-cloud-board.git

# GitHub CLI
gh repo clone wogusckrgo11-spec/secure-cloud-board

cd secure-cloud-board/board   # 이 README 와 애플리케이션 코드가 있는 디렉터리
```

> 애플리케이션 코드는 저장소의 `board/` 하위에 있다. 서버 배포 시에는 `board/` 의
> **내용물** 을 `/opt/board` 에 배치한다 (4.4 참고).

---

## 1. 파일 구조와 역할

```
board/
├── app.py                      # Flask 애플리케이션 팩토리 + 라우트 4개(목록/작성/상세/삭제)
├── db.py                       # PyMySQL 커넥션 헬퍼 (요청 단위 연결/해제)
├── config.py                   # 환경변수에서 설정 로드 + 필수값 검증(fail-fast)
├── requirements.txt            # 운영 의존성 (Flask, PyMySQL, gunicorn) - 버전 고정
├── schema.sql                  # DB/테이블 생성 + 앱 전용 계정 GRANT
├── .env.example                # 실제 .env 템플릿 (이 파일만 커밋)
├── .gitignore                  # .env, __pycache__, .venv 제외
├── templates/                  # Jinja2 서버사이드 템플릿 (autoescape 로 XSS 방지)
│   ├── base.html               #   공통 레이아웃 + flash 메시지 출력
│   ├── list.html               #   목록 + 페이지네이션
│   ├── write.html              #   작성 폼 (검증 실패 시 입력값 유지)
│   └── detail.html             #   상세 보기 + 삭제 버튼(확인 대화 후 POST)
├── static/
│   └── style.css               # 최소 스타일 (Nginx 가 직접 서빙)
├── deploy/
│   ├── gunicorn-board.service  # systemd unit. EnvironmentFile 로 .env 주입, 127.0.0.1:5000 바인딩
│   └── nginx-board.conf        # 리버스 프록시 설정 (80 → 5000), /static 직접 서빙
└── tests/                      # DB 없이 도는 통합 테스트 (아래 3장)
    ├── harness.py              #   db.get_db() 를 인메모리 SQLite 로 교체하는 하네스
    ├── test_endpoints.py       #   Flask test_client 로 전 엔드포인트 검증
    └── wsgi_test.py            #   Gunicorn 기동 스모크 테스트용 WSGI 진입점
```

| 파일 | 왜 필요한가 |
|---|---|
| `config.py` | DB 접속 정보를 코드에서 분리. 환경변수만 읽고, 없으면 기동 즉시 실패시켜 잘못된 설정으로 뜨는 것을 막는다. |
| `db.py` | 커넥션 수명 관리를 한곳에 모음. 요청마다 열고 `teardown_appcontext` 에서 닫아 커넥션 누수 방지. 모든 쿼리는 호출부에서 파라미터 바인딩. |
| `app.py` | 라우팅 + 입력 검증 + 쿼리 실행. 팩토리 패턴이라 테스트/설정 교체가 쉬움. |
| `schema.sql` | 앱은 스키마를 만들지 않음(권한 최소화). DB 관리자가 1회 실행. 앱 계정은 `posts` 에 `SELECT, INSERT, DELETE` 만(UPDATE 없음). |
| `.env.example` | 실제 비밀값은 커밋 금지. 무엇을 채워야 하는지 문서 역할. |
| `gunicorn-board.service` | 부팅 시 자동 기동/장애 시 재시작. 민감값은 `EnvironmentFile` 로만 주입. |
| `nginx-board.conf` | 외부 노출은 Nginx 80 만. Flask 는 로컬 5000 에 갇혀 직접 접근 불가. 정적 파일은 Nginx 가 처리. |
| `tests/` | MySQL 없이도 라우팅·입력검증·페이지네이션·XSS·SQLi 방어를 CI/로컬에서 즉시 검증. |

---

## 2. 보안 요구사항이 코드에 반영된 지점

| 요구사항 | 반영 위치 |
|---|---|
| **SQL Injection 방지** | `app.py` 의 모든 `cur.execute(sql, params)` 는 `%s` 플레이스홀더 + 튜플 바인딩. 문자열 포매팅으로 SQL 을 만들지 않음. |
| **접속정보 분리** | `config.py` 는 `os.environ` 만 참조. 기본값/하드코딩 없음(포트 제외). 운영에선 systemd `EnvironmentFile=/etc/board/.env` 로 주입. |
| **입력 검증** | `app.py` `write()` — `title`/`content` strip 후 빈 값 차단, 길이 상한(제목 200 / 작성자 50 / 내용 10000), `writer` 빈 값은 `"익명"`. |
| **XSS** | Jinja2 기본 autoescape 유지. `|safe` 미사용. |
| **최소 권한** | DB 앱 계정은 `SELECT, INSERT, DELETE` 만(UPDATE 미부여). systemd 에 `NoNewPrivileges`, `ProtectSystem=full`, `ProtectHome` 적용. |
| **삭제 처리** | `app.py` `delete()` — `POST /posts/<id>/delete` 만 허용(GET 405), 없는 글은 404, `%s` 바인딩으로 `DELETE`. |

> **삭제 권한**: 로그인이 없는 익명 게시판이라 삭제는 **인증 없이 누구나 가능**하다(상세 페이지 확인 대화만 거침).
> 운영에서 통제가 필요하면 글별 삭제 비밀번호(작성 시 해시 저장) 또는 관리자 비밀번호(`ADMIN_PASSWORD` 환경변수) 방식으로 확장한다.
> 로그인/세션이 없어 CSRF 는 이번 범위에서 제외. 도입 시 `Flask-WTF` 로 폼 토큰 추가(작성·삭제 폼 공통).
> TLS 는 도메인·인증서 전제라 제외. `nginx-board.conf` 주석의 확장 지점 참고.

---

## 3. 로컬 개발 & 테스트

### 3.1 실제 MySQL 에 연결해서 실행

```bash
cd board
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 로컬 MySQL 에 스키마 적용 (schema.sql 의 host/비밀번호를 로컬용으로 수정)
mysql -u root -p < schema.sql

# 환경변수 주입
cp .env.example .env
vi .env                       # 로컬 DB 정보로 수정
export $(grep -v '^#' .env | grep -v '^$' | xargs)
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")

flask --app app run --debug   # http://127.0.0.1:5000
```

### 3.2 DB 없이 자동 테스트

`tests/harness.py` 가 실제 `app.py` 를 그대로 import 하되 `db.get_db()` 만 인메모리 SQLite 로 교체한다.
`db.py` / `schema.sql` 원본은 건드리지 않는다.

```bash
cd board
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (1) 엔드포인트 통합 테스트
cd tests
python test_endpoints.py

# (2) Gunicorn 기동 스모크 테스트 (실제 WSGI 경로)
PYTHONPATH=. gunicorn --workers 1 --bind 127.0.0.1:5056 wsgi_test:app &
curl -i -X POST -d "title=hello&content=world&writer=me" http://127.0.0.1:5056/write   # 302 → /posts/N
curl -s http://127.0.0.1:5056/posts/4                                                  # 상세 렌더 확인
kill %1
```

> 멀티워커(`--workers 2+`)로 스모크 테스트 시 인메모리 SQLite 가 프로세스별로 분리돼
> POST/GET 이 서로 다른 DB 를 볼 수 있다. 테스트 하네스만의 현상이며 실제 MySQL 에선 무관.
> 스모크 테스트는 `--workers 1` 로 실행할 것.

### 3.3 테스트 결과

`python tests/test_endpoints.py` → **46 PASS / 0 FAIL**

| # | 시나리오 | 검증 내용 | 결과 |
|---|---|---|---|
| 1 | `GET /` | 200, 최신순 정렬, 페이지네이션(13글 → "1 / 2"), 글쓰기 링크 | PASS |
| 2 | `GET /?page=2` | 남은 3글 노출, "2 / 2" | PASS |
| 3 | `GET /?page=-5` | 음수 → 1페이지로 클램프 (200) | PASS |
| 4 | `GET /?page=abc` | 문자 → 기본 1페이지 (200) | PASS |
| 5 | `GET /write` | 작성 폼 렌더 (title/content 필드) | PASS |
| 6 | `POST /write` 정상 | 302 → `/posts/<id>`, DB 행 +1, 값 일치, `created_at` 자동 생성 | PASS |
| 7 | `GET /posts/<id>` | 상세 200, 본문·작성자 노출 | PASS |
| 8 | `POST /write` 제목 빈 값 | 400, "제목을 입력하세요", DB 미변경, 입력값 유지 | PASS |
| 9 | `POST /write` 내용 빈 값 | 400, "내용을 입력하세요" | PASS |
| 10 | `POST /write` writer 빈 값 | `"익명"` 으로 저장 | PASS |
| 11 | `POST /write` 제목 201자 | 400, "200자 이하", DB 미변경 | PASS |
| 12 | `GET /posts/99999` | 404 | PASS |
| 13 | `GET /posts/abc` | 404 (`<int:post_id>` 컨버터) | PASS |
| 14 | **XSS** | `<script>` → `&lt;script&gt;` 이스케이프되어 렌더 | PASS |
| 15 | **SQL Injection** | `'; DROP TABLE posts; --` 를 리터럴로 저장, 테이블 생존, 목록 정상 | PASS |
| 16 | `POST /posts/<id>/delete` 정상 | 302 → `/`, DB 행 -1, 삭제 후 상세 404 | PASS |
| 17 | `POST /posts/99999/delete` | 없는 글 404, DB 미변경 | PASS |
| 18 | `GET /posts/<id>/delete` | 405 (POST 만 허용) | PASS |

Gunicorn 스모크 테스트: 정상 부팅(worker spawn) → `GET /` 200, `GET /write` 200, `POST /write` 302,
빈 제목 400, `/posts/<id>` 200(제목·본문·작성자·`created_at` 렌더 확인), `/posts/9999` 404.

> 참고: `CURRENT_TIMESTAMP` 는 보통 UTC 로 저장된다. KST 로 표시하려면 MySQL `time_zone`
> 설정 또는 템플릿에서 변환이 필요하다(현재 요구사항엔 없어 그대로 둠).

---

## 4. AWS 배포

### 4.1 네트워크 구성 (VPC)

| 리소스 | 설정 |
|---|---|
| VPC | 예: `10.0.0.0/16` |
| 퍼블릭 서브넷 | 예: `10.0.1.0/24` — 라우팅 테이블에 **인터넷 게이트웨이(IGW)** 기본 경로 |
| 프라이빗 서브넷 | 예: `10.0.2.0/24` — IGW 경로 **없음**. 아웃바운드 필요 시 **NAT 게이트웨이**(패키지 설치용) |
| 웹서버 EC2 | 퍼블릭 서브넷. 퍼블릭 IP 또는 EIP 할당. 예: `10.0.1.10` |
| DB서버 EC2 | 프라이빗 서브넷. 퍼블릭 IP 없음. 예: `10.0.2.20` |

DB서버에 SSH 로 붙으려면 웹서버를 배스천으로 쓰거나(`ssh -J`), SSM Session Manager 를 쓴다.
패키지 설치가 끝나면 NAT 를 내려도 된다(운영 중엔 불필요).

### 4.2 보안그룹 규칙

**web-sg (웹서버)**

| 방향 | 포트 | 소스/대상 | 용도 |
|---|---|---|---|
| 인바운드 | TCP 80 | `0.0.0.0/0` (또는 사내 대역) | 사용자 HTTP |
| 인바운드 | TCP 22 | 관리자 IP `/32` | SSH |
| 아웃바운드 | TCP 3306 | `db-sg` | DB 접속 |
| 아웃바운드 | TCP 80/443 | `0.0.0.0/0` | dnf 패키지 |

**db-sg (DB서버)**

| 방향 | 포트 | 소스/대상 | 용도 |
|---|---|---|---|
| 인바운드 | TCP 3306 | **`web-sg`** (CIDR 아님, 보안그룹 참조) | 웹서버만 접속 |
| 인바운드 | TCP 22 | `web-sg` 또는 관리 대역 | 배스천 경유 SSH |
| 아웃바운드 | TCP 80/443 | `0.0.0.0/0` | dnf 패키지 (NAT 경유) |

핵심은 db-sg 인바운드 3306 의 소스를 **web-sg 자체로 지정**하는 것. 웹서버 IP 가 바뀌어도 규칙 수정 불필요.

### 4.3 DB서버 EC2 셋업

```bash
# (배스천 경유 접속 후)
sudo dnf install -y mariadb105-server
sudo systemctl enable --now mariadb
sudo mysql_secure_installation          # root 비밀번호 설정

# 외부 바인딩: 프라이빗 IP 로만. 0.0.0.0 금지
echo -e "[mysqld]\nbind-address = 10.0.2.20" | sudo tee /etc/my.cnf.d/bind.cnf
sudo systemctl restart mariadb

# 스키마 + 앱 계정 생성
#   schema.sql 의 'board_app'@'10.0.1.10' 을 실제 웹서버 프라이빗 IP 로,
#   비밀번호를 강력한 값으로 수정한 뒤:
sudo mysql -u root -p < schema.sql
```

> **이미 운영 중인 DB 에 삭제 기능을 반영할 때**: `schema.sql` 재실행은 기존 계정 권한을
> 갱신하지 않는다. DB 서버에서 아래를 1회 실행해 `DELETE` 권한을 추가한다.
> ```sql
> GRANT DELETE ON board.posts TO 'board_app'@'10.0.1.10';
> FLUSH PRIVILEGES;
> ```

> RDS(MySQL) 를 쓰면 이 EC2 는 불필요하다. RDS 를 프라이빗 서브넷에 두고 db-sg 를
> 동일하게 적용, `.env` 의 `DB_HOST` 를 RDS 엔드포인트로 지정하면 된다.

### 4.4 웹서버 EC2 셋업

```bash
sudo dnf install -y nginx python3.11 python3.11-pip git
sudo useradd --system --home-dir /opt/board --shell /sbin/nologin board

# 코드 배치: board/ "내용물" 을 /opt/board 에 둔다 (systemd WorkingDirectory=/opt/board 와 일치시킴)
git clone https://github.com/wogusckrgo11-spec/secure-cloud-board.git /tmp/repo
sudo rsync -a --exclude '.venv' --exclude '__pycache__' /tmp/repo/board/ /opt/board/
cd /opt/board
sudo python3.11 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo chown -R board:board /opt/board

# 민감값 주입: /etc/board/.env (권한 600)
sudo mkdir -p /etc/board
sudo cp .env.example /etc/board/.env
sudo vi /etc/board/.env                        # DB_HOST=10.0.2.20, DB_PASSWORD=..., SECRET_KEY 생성해 입력
sudo chown root:board /etc/board/.env
sudo chmod 600 /etc/board/.env

sudo cp deploy/gunicorn-board.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn-board
systemctl status gunicorn-board

# Nginx
sudo cp deploy/nginx-board.conf /etc/nginx/conf.d/board.conf
sudo nginx -t && sudo systemctl enable --now nginx

# SELinux 가 enforcing 이면 Nginx→Gunicorn 프록시 허용 (AL2023 기본 permissive 면 불필요)
sudo setsebool -P httpd_can_network_connect 1
```

`.env` 예시 값:

```
DB_HOST=10.0.2.20
DB_PORT=3306
DB_USER=board_app
DB_PASSWORD=<강력한 비밀번호>
DB_NAME=board
SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))">
PAGE_SIZE=10
```

### 4.5 동작 확인

```bash
# 웹서버에서
curl -I http://127.0.0.1/                       # 200 (Nginx→Gunicorn)
curl -s -X POST -d "title=배포확인&content=hello" http://127.0.0.1/write -i | head -1  # 302

# 로컬 PC 에서 (web-sg 인바운드 80 허용 대역)
curl -I http://<웹서버-퍼블릭-IP>/               # 200

# DB 연결 확인 (웹서버에서)
mysql -h 10.0.2.20 -u board_app -p board -e "SELECT COUNT(*) FROM posts;"
```

### 4.6 운영 팁

| 항목 | 방법 |
|---|---|
| 앱 로그 | `sudo journalctl -u gunicorn-board -f` (access/error 를 stdout 으로 출력하도록 설정됨) |
| Nginx 로그 | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| 코드 재배포 | `git pull` → `sudo .venv/bin/pip install -r requirements.txt` → `sudo systemctl restart gunicorn-board` |
| 설정 변경 | `/etc/board/.env` 수정 후 `sudo systemctl restart gunicorn-board` |
| DB 백업 | `mysqldump -u root -p board > board_$(date +%F).sql` (cron) 또는 RDS 자동 스냅샷 |
| 워커 수 | `gunicorn-board.service` 의 `--workers` 를 `(2 × vCPU) + 1` 로 조정 |
| HTTPS | ALB + ACM 인증서를 앞단에 두거나, 웹서버에 certbot 설치 후 `nginx-board.conf` 의 확장 지점대로 443 블록 추가 |
| 모니터링 | CloudWatch Agent 로 `journalctl`/nginx 로그 수집, `systemctl` 상태 알람 |
