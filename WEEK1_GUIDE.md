# Week 1 실행 가이드 — PostgreSQL 데이터 레이어 구축

## 프로젝트 구조

```
hns-platform/
├── db/
│   ├── schema.sql              ← 테이블 정의 (초안, CSV 대조 후 수정 필요)
│   └── sample_queries.sql      ← 검증 + 분석 쿼리 모음
├── etl/
│   ├── check_columns.py        ← CSV 컬럼 확인 스크립트
│   └── load_all.py             ← CSV → PostgreSQL 적재
├── agent/                      ← Week 3부터
├── api/                        ← Week 5부터
├── tests/
├── evals/
├── docker-compose.yml          ← PostgreSQL 컨테이너
├── requirements.txt
├── .env.example
└── 이 파일 (WEEK1_GUIDE.md)
```

---

## Step 1: 이 폴더를 작업 디렉토리로 세팅

```bash
# 원하는 위치에 복사 또는 새로 만들기
cd ~/Projects  # 또는 원하는 경로
cp -r /다운로드받은경로/hns-platform ./hns-platform
cd hns-platform

# 환경변수
cp .env.example .env

# Python 가상환경
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 2: Docker로 PostgreSQL 띄우기

```bash
# Docker Desktop이 실행 중인지 확인
docker --version

# PostgreSQL 컨테이너 시작
docker-compose up -d

# 확인 (healthy 나올 때까지 5-10초 대기)
docker-compose ps
```

잘 되면 이렇게 보여요:
```
NAME           STATUS         PORTS
hns_postgres   Up (healthy)   0.0.0.0:5432->5432/tcp
```

접속 테스트:
```bash
# psql CLI로 접속 (Docker 안에서)
docker exec -it hns_postgres psql -U hns_user -d hns_platform

# 테이블 확인
\dt

# 나가기
\q
```

> 💡 **PyCharm 쓰시니까**: PyCharm 하단 Database 탭에서 PostgreSQL 연결 추가하면
> GUI로 테이블/쿼리 관리 가능. 접속 정보: host=localhost, port=5432,
> database=hns_platform, user=hns_user, password=hns_local_dev_only

---

## Step 3: CSV 컬럼 확인 (가장 중요한 단계)

schema.sql은 README 기반 추정치입니다. 실제 CSV 컬럼과 맞지 않을 수 있어요.

```bash
python etl/check_columns.py \
    --data-dir /path/to/pg-hns-consumer-signal-pipeline
```

이 스크립트가 각 CSV의 컬럼명, 타입, 샘플값을 출력해줍니다.
출력을 `db/schema.sql`과 대조해서 불일치를 수정하세요.

### 확인 포인트

1. **hns_causal_signals.csv**: voc_documents 테이블과 대조.
   - 컬럼명이 다르면 schema.sql 수정
   - 빠진 컬럼이 있으면 추가
   - boolean vs integer vs text 타입 확인

2. **trend_features.csv**: trend_monthly 테이블과 대조.
   - 16개 컬럼명이 한글인지 영문인지 확인
   - schema.sql에서 영문으로 추정해놨는데 한글일 수 있음

3. **switching_prob_regression.csv**: voc_documents의 segment_label/switching_prob과
   별도 테이블 중 어디에 넣을지 판단

---

## Step 4: 스키마 수정 후 재생성

schema.sql을 수정했으면:

```bash
# 기존 컨테이너 삭제 (데이터도 같이)
docker-compose down -v

# 다시 시작 (수정된 schema.sql로 테이블 재생성)
docker-compose up -d
```

---

## Step 5: 데이터 적재

```bash
python etl/load_all.py \
    --data-dir /path/to/pg-hns-consumer-signal-pipeline
```

성공하면:
```
✅ PostgreSQL 연결 성공

📦 Layer 1: VoC 데이터
  ✅ voc_documents: 1744행 적재 완료
  ✅ temporal_signals: XX행 적재 완료
  ...

📦 Layer 2: 트렌드 데이터
  ✅ trend_monthly: 76행 적재 완료
  ...

총 XXXX행 적재 완료
```

> ⚠️ load_all.py는 pandas의 to_sql을 사용합니다.
> schema.sql의 테이블 정의와 CSV 컬럼이 다르면 에러 납니다.
> Step 3에서 반드시 대조하세요.

---

## Step 6: SQL 쿼리로 검증

`db/sample_queries.sql`의 쿼리들을 실행해보세요.

PyCharm Database Console이나 psql에서:

```sql
-- 각 테이블 행 수 확인
SELECT 'voc_documents' AS t, COUNT(*) AS n FROM voc_documents
UNION ALL
SELECT 'trend_monthly', COUNT(*) FROM trend_monthly;

-- 세그먼트별 분포
SELECT segment_label, COUNT(*) FROM voc_documents
GROUP BY segment_label
ORDER BY COUNT(*) DESC;
```

`sample_queries.sql`에 더 복잡한 쿼리들이 있어요 (cross-layer JOIN 포함).
면접 대비 SQL 연습으로도 활용하세요.

---

## 완료 기준

이 단계가 끝나면:
- [ ] PostgreSQL이 Docker에서 돌아가고 있다
- [ ] H&S의 모든 output CSV가 DB에 적재돼 있다
- [ ] sample_queries.sql의 쿼리들이 정상 동작한다
- [ ] PyCharm에서 DB 연결해서 테이블 확인 가능하다

여기까지 되면 **"SQL + Docker 경험"** 확보.
다음은 Week 2 — ChromaDB + RAG 파이프라인.

---

## 막혔을 때

- Docker 에러: `docker logs hns_postgres` 로 로그 확인
- psycopg2 설치 실패 (M2 Mac): `pip install psycopg2-binary` 대신 `pip install psycopg[binary]` 시도
- schema.sql 수정 후 반영 안 됨: `docker-compose down -v` 해야 volume이 삭제되고 schema가 다시 적용됨
- 그 외 막히면 이 채팅에서 에러 메시지 공유해주세요
