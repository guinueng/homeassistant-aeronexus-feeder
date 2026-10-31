# 1.1.1 검증 결과

- Windows와 Linux Python에서 48개 회귀 검사 통과.
- 매시간/24시간 후에도 추가 확인 없음, 같은 앱 버전 재시작 시 HTTP 요청 없음 확인.
- 새 앱 버전에서 한 번 확인, 최초 실패는 다음 재시작에서 재시도, 적용 중 재시작은 캐시 사용 확인.
- 기존 UUID/Beast/DF17/18/MLAT 및 원본 main 루프 모의 전송 검사 유지.
- 공식 서버에 시험용 ADS-B 자료나 UUID를 전송하지 않음.
- amd64/aarch64 Docker 이미지 빌드 및 일반 사용자 실행 검사.
- YAML, 번역, 파일 해시, UTF-8/LF, 문서 링크 및 ZIP 내용 검사.

사용자 HAOS에서의 설치·재부팅·백업 복원과 실제 UUID의 AeroNexus 수신은 아직 확인하지 않았습니다.
tests/RESULTS.txt에 최종 검사 결과를 포함합니다.
