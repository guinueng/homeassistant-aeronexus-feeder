# 로직 작동 개략도 — AeroNexus Feeder 1.1.3

현재 구현 기준의 TUI 개략도입니다. **앱 설치**, **공식 중계기 확인**, **실제 ADS-B 전송**은 아래처럼 이어집니다.

## 1. 설치한 앱은 어떻게 실행되나요?

```text
[GitHub repository]
        |
        | HA: Add repository -> Install / Update
        v
[Supervisor builds Dockerfile]
        |
        v
[Installed app image]
        |
        | Start / Restart / Boot
        v
[/init (S6)] -> [aeronexus/run] -> [manager.py]
                                      |
                                      +-> /data/options.json
                                      |   UUID / Beast settings / refresh request
                                      |
                                      +-> /data/upstream/
                                          cached Python / version state
```

- 저장소 추가 버튼은 **저장소 등록 화면**을 엽니다. 설치와 UUID 입력은 HA에서 완료합니다.
- `config.yaml`에 사전 빌드 `image`를 지정하지 않았으므로 설치/앱 업데이트 시 HA가 이미지를 빌드합니다.
- 실행 진입점은 S6의 `aeronexus/run`이며, 이 파일이 `manager.py`를 실행합니다.
- Terminal용 `install-local.sh`는 GitHub 소스를 로컬 앱 공유에 배치하는 별도 설치 도구입니다. 앱 시작 때 실행되는 파일이 아닙니다.

## 2. 시작할 때 최신 코드를 확인하나요?

```text
[manager.py starts]
        |
        v
[Read /data/options.json]
        |
        +-- UUID empty --------------------> [Wait; no network]
        |
        v
[Load working code from persistent cache / bundled fallback]
        |
        v
[Upstream check needed?]
        |
        +-- NO ----------------------------> [Keep saved code selection]
        |
        +-- YES --> [Download official feed.sh over HTTPS]
                               |
                               v
                    [Extract Python; do NOT execute shell]
                               |
                               v
                    [Syntax / interface / protocol checks]
                               |
                               +-- FAIL --> [Keep working code]
                               +-- SAME --> [Use working code]
                               +-- NEW ---> [Save pending candidate]

        All paths with a valid UUID join here:
        |
        v
[Resolve Beast source]
        |
        v
[New candidate pending?]
        |
        +-- NO ---> [Run working Python -> Forward logs]
        |
        +-- YES --> [Run candidate Python -> Forward logs]
                               |
                               v
                    [Alive for 30 seconds?]
                               |
                               +-- YES --> [Activate + retain previous]
                               +-- NO ---> [Reject + run working code]
```

최초 실행, 현재 앱 버전의 확인 성공 기록이 없는 경우, 새 HA 앱 버전 설치 후 첫 실행,
또는 `refresh_upstream: true`인 경우 공식 코드를 한 번 확인합니다.
새 후보의 30초 검사는 Beast 주소를 얻어 실제 프로세스를 시작한 뒤 진행합니다.
검사 도중 앱이 재시작되면 저장된 후보 검사를 이어갈 수 있으며, 이를 위해 다시 다운로드하지는 않습니다.

- 다운로드 주소: `https://aeronexus.kr/feed.sh`. shell/systemd 설치 명령은 실행하지 않고 Python 중계기 전체만 추출합니다.
- 검사는 문법·필수 인터페이스·UUID·Beast escape·DF17/18·MLAT 제외와 모의 소켓 전송을 확인합니다.
- **성공적으로 확인한 앱 버전**을 저장하므로 같은 버전의 일반 재시작과 HA 재부팅은 저장된 코드를 사용합니다.
- 최초 확인이 실패하면 현재 코드로 동작하고 다음 앱 재시작 때 재시도합니다. 실행 중 주기적인 최신 버전 확인은 없습니다.
- 저장된 활성 코드가 손상되면 이전 정상 캐시, 이어서 이미지에 포함된 초기 중계기 순으로 복구합니다.
- 30초 생존은 프로세스 실행 검사입니다. 서버의 UUID 승인이나 자료 저장 성공은 AeroNexus 화면에서 확인해야 합니다.

## 3. 설정 UI에서 수동으로 갱신하면?

```text
[HA app Configuration]
        |
        | Show unused optional options
        | Enable "다음 시작 시 최신 중계기 받기"
        | Save -> Restart
        v
[refresh_upstream = true]
        |
        v
[One upstream check, even at the same HA app version]
        |
        +-- download / validation FAIL --> [Keep current code]
        |                                 [Keep request ON for next restart]
        |
        +-- check SUCCESS --------------> [Save checked app version]
                                          [Clear request through self options API]
                                          [Use same code or test new candidate]
```

공식 코드가 그대로여도 확인에 성공하면 요청을 끕니다. 자동 해제는 **확인·호환성 검사 성공 후**이며,
새 후보의 30초 실행 검사와는 별도입니다. 후보가 이후 조기 종료하면 이전 버전으로 복구합니다.

옵션을 해제할 때 Supervisor에서 현재 설정 전체를 읽고 `refresh_upstream`만 `false`로 바꿉니다.
UUID·다른 선택 설정·`!secret` 참조는 보존합니다. API 해제가 실패하면 로그 안내에 따라 직접 꺼 주세요.
공식 Python 코드만 바뀐 경우 이 기능으로 받을 수 있습니다. HA 설정 UI·관리 코드·Dockerfile 변경은
새 HA 앱 버전으로 배포하고 HA의 앱 업데이트로 적용합니다. GitHub Actions의 자동 배포 작업은 현재 구성하지 않았습니다.

## 4. 실제 자료와 관리 정보는 어디로 흐르나요?

```text
                 Home Assistant app/container network

[ADS-B Multi-Portal Feeder]              [AeroNexus Feeder app]
             |                                      |
             +-- Beast stream, TCP 30005 ----------> [Official Python relay]
                                                    |
                                                    | UUID + filtered Beast
                                                    | outbound TCP 30004 (*)
                                                    v
                                             [AeroNexus server]

[HA Configuration UI] -> [Supervisor] -> /data/options.json
                              ^
                              | discovery / self options API
                         [manager.py] -> [HA app log]
                              |
                              +-> /data/upstream/ -> [HA app backup]
```

`(*)` 현재 기본 목적지는 `aeronexus.kr:30004`입니다. 공식 원본의 목적지 설정도 검증하여 반영합니다.
앱은 기존 피더의 TCP 30005에 연결해 읽으며, 새 호스트 포트나 인바운드 포트를 공개하지 않습니다.
기존 SDR 장치나 다른 포털로 보내는 피더 설정은 변경하지 않습니다.

| 위치/이름 | 의미 |
|---|---|
| `f1c878cb-adsb-multi-portal-feeder:30005` | 표준 설치에서의 기존 피더 내부 DNS 예시. 자동 탐색 또는 `beast_host`로 지정 |
| `127.0.0.1` | AeroNexus 앱 컨테이너 자신. 다른 앱 주소가 아님 |
| `/data/options.json` | AeroNexus 앱 안에서 읽는 Supervisor 설정 파일 |
| `/data/upstream/` | AeroNexus 앱의 영구 저장소. 코드·상태·이전 버전을 보관하고 앱 백업에 포함 |
| Terminal의 `~/addons`, `/addons` 등 | Terminal 컨테이너에서 보이는 로컬 앱 소스 공유. `/data/upstream`과 별개 |

`host_network: false`이며 Supervisor 내부 네트워크로 기존 피더에 접속합니다.
부팅 시 시작과 Watchdog은 HA 앱 정보 화면에서 켭니다. 실행 로그에는 코드 SHA와 연결·통계가 표시되며 UUID는 숨깁니다.
Beast 주소 재탐색과 연결 재시도는 중계를 유지하는 동작이며 공식 코드의 정기 업데이트 확인이 아닙니다.

## 5. 접속 직후 서버가 끊으면?

```text
[Official Python relay -> connect to AeroNexus]
                      |
                      v
[HA runner observes the destination socket]
                      |
                      +-- EOF / reset / broken pipe within 10 seconds
                      |     -> UUID conflict possibility -> WARNING log
                      |     -> At most one extra notice per 60 seconds
                      |
                      +-- Source close / timeout / local close / later close
                            -> Original log only

Official Python source / wire bytes / reconnect loop: unchanged
```

경고는 중복 UUID의 가능성입니다. 이전 기기의 AeroNexus 피더를 먼저 제거하고 UUID 등록/활성화 상태도 확인하세요.
UUID 하나를 두 기기에서 쓰면 서버가 나중에 접속한 쪽을 끊습니다.

관련 문서: [설치·파일 편집·경로](INSTALL_KO.md), [업데이트·복구 상세](UPDATING.md), [검증 범위](VALIDATION.md).
