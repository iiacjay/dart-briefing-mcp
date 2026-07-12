# DART 공시 브리핑 MCP 서버

관심 기업의 DART 전자공시를 검색·필터링해 AI 에이전트가 투자자 관점 브리핑을 만들 수 있도록 데이터를 제공하는 MCP 서버입니다.

## 사용 예시

- "삼성전자 최근 공시 알려줘"
- "이번 달 LG에너지솔루션 주요 공시 브리핑해줘"
- "카카오 최근 30일 유상증자나 수주 공시 있어?"

## 도구 목록

| 도구 | 설명 |
|------|------|
| `search_company` | 기업명/종목코드로 DART 등록 기업 검색 |
| `get_recent_disclosures` | 최근 N일 공시 목록 조회 (공시유형 필터 가능) |
| `get_major_events` | 주가 민감 공시(유상증자·수주·자사주 등) 카테고리 분류 |
| `get_company_profile` | 기업 개황 (대표자·업종·설립일·상장시장·홈페이지) |

## 로컬 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. API 키 설정
cp .env.example .env
# .env 파일에 DART_API_KEY 입력 (https://opendart.fss.or.kr 발급)

# 3. 서버 실행
python-dotenv run -- python server.py
# 또는
export DART_API_KEY=your_key && python server.py
```

## MCP Inspector로 테스트

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

## Railway 배포

1. GitHub에 푸시
2. Railway에서 새 프로젝트 → GitHub 리포 연결
3. 환경변수 `DART_API_KEY` 설정
4. 자동 배포 완료 후 공개 URL 확인

## 배포 후 PlayMCP 등록

1. [playmcp.kakao.com](https://playmcp.kakao.com) 에서 MCP 서버 등록
2. 서버 URL: `https://your-app.railway.app/mcp`
3. Transport: Streamable HTTP

## 면책사항

본 서비스는 금융감독원 DART 공개 데이터를 활용하며, 투자 권유 또는 투자 판단의 근거로 사용할 수 없습니다.
