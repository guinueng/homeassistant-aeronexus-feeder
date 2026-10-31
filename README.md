# AeroNexus Feeder for Home Assistant

기존 ADS-B Multi-Portal Feeder의 Beast 30005 출력을 AeroNexus로 전달하는 Home Assistant OS 앱입니다.
UUID를 설정 화면에서 입력하고, 별도 컨테이너에서 자동 실행·재연결·로그를 관리합니다.

## 비공개 저장소

이 저장소는 계정 소유자의 소스 보관·관리용 비공개 저장소로 준비했습니다.
인증되지 않은 Home Assistant는 일반적인 앱 저장소 추가만으로 이 저장소를 내려받을 수 없습니다.
계정으로 로그인한 GitHub에서 소스를 내려받아 로컬 앱으로 설치하세요.
접근 토큰이나 비밀번호를 소스 또는 설치 링크에 넣지 마세요.

## 설치

1. 이 저장소 소스를 내려받습니다.
2. `aeronexus_feeder` 폴더 전체를 Home Assistant의 `local_apps` 공유에 복사합니다.
3. 설정 → 앱 → 앱 설치 → 업데이트 확인을 실행합니다.
4. 로컬 앱의 AeroNexus Feeder를 설치합니다.
5. 구성에서 UUID 입력 → 저장 → 시작 또는 재시작합니다.

자세한 내용은 [한국어 설치 가이드](aeronexus_feeder/INSTALL_KO.md)를 읽으세요.

## 파일

- [앱 소스](aeronexus_feeder/)
- [검증 결과와 미검증 범위](aeronexus_feeder/VALIDATION.md)
- [공식 문서 대조 내역](aeronexus_feeder/SOURCES.md)
- [원본 출처와 라이선스 유의사항](aeronexus_feeder/NOTICE.md)

로컬 모의 TCP 서버를 포함한 25개 검사는 통과했습니다.
실제 HAOS 이미지 빌드·설치 및 AeroNexus 실서버 수신 확인은 아직 수행하지 않았습니다.

`repository.yaml`은 Home Assistant 저장소 구조에 맞춰 포함했습니다.
향후 공개 배포할 때는 원본의 재배포 조건과 실제 장비 검증을 확인한 뒤,
저장소 공개 여부 및 설치 버튼을 별도로 설정하세요.
