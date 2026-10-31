# Changelog

## 1.0.0 — 2026-10-31

- 제공된 feed.sh의 Python Beast 중계기를 Home Assistant 로컬 앱으로 구성.
- UUID 구성 UI, 빈 UUID 대기, 한국어/영어 번역.
- 기존 ADS-B Multi-Portal Feeder 자동 탐색 및 직접 주소 지정.
- DF17/18 필터, MLAT 표식 제외, UUID/심장박동 프로토콜 유지.
- 소켓 타임아웃, 독립 재접속, 단조 시간 타이머, 실제 쓰기 기준 통계.
- S6 서비스, 부팅 자동 시작, Supervisor 로그·백업 안내.
- 원본 receiver-id E3 처리의 잘못된 escape 복구 보완.
- 로컬 TCP 모의 서버를 포함한 회귀 검사, 경로/설치/편집/백업 문서 제공.
