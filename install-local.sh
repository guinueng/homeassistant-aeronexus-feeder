#!/usr/bin/env bash
# Fetch the latest app source from this public GitHub repository, then stage it
# in the actual local-app share of the Home Assistant Terminal container.
set -euo pipefail
umask 077
fail() { printf '오류: %s\n' "$*" >&2; exit 1; }
for tool in curl awk readlink sha256sum tar cp mkdir mktemp date; do
    command -v "$tool" >/dev/null 2>&1 || fail "필요한 도구가 없습니다: $tool"
done
apps_dir=''
for candidate in /local_apps /addons "${HOME:-/root}/local_apps" "${HOME:-/root}/addons"; do
    [ -d "$candidate" ] || continue
    resolved=$(readlink -f "$candidate")
    if awk -v dest="$resolved" '$5 == dest {found=1} END {exit !found}' /proc/self/mountinfo; then
        apps_dir="$resolved"
        break
    fi
done
[ -n "$apps_dir" ] || fail '실제 로컬 앱 공유를 찾지 못했습니다. Terminal & SSH 앱의 마운트를 확인하세요.'
[ -w "$apps_dir" ] || fail "앱 공유에 쓸 수 없습니다: $apps_dir"
target="$apps_dir/aeronexus_feeder"
[ ! -L "$target" ] || fail "대상이 심볼릭 링크입니다: $target"
if [ -e "$target" ] && [ ! -d "$target" ]; then fail '대상과 같은 이름의 파일이 있습니다.'; fi
work_dir=$(mktemp -d /tmp/aeronexus-source.XXXXXX)
printf 'GitHub 최신 앱 소스를 내려받습니다.\n'
curl --fail --location --silent --show-error --retry 2 --connect-timeout 10 --max-time 120 \
    --proto '=https' --proto-redir '=https' \
    'https://github.com/guinueng/homeassistant-aeronexus-feeder/archive/refs/heads/main.tar.gz' \
    --output "$work_dir/source.tar.gz"
tar -xzf "$work_dir/source.tar.gz" -C "$work_dir"
source_dir="$work_dir/homeassistant-aeronexus-feeder-main/aeronexus_feeder"
[ -f "$source_dir/config.yaml" ] && [ -f "$source_dir/Dockerfile" ] || fail '앱 소스를 찾지 못했습니다.'
(cd "$source_dir" && sha256sum -c MANIFEST.sha256 >/dev/null)
if [ -d "$target" ]; then
    backup_dir="$apps_dir/.aeronexus_source_backups"
    mkdir -p "$backup_dir"
    backup="$backup_dir/aeronexus_feeder-$(date +%Y%m%d-%H%M%S)-$$.tar.gz"
    [ ! -e "$backup" ] || fail '백업 경로가 이미 있습니다.'
    tar -czf "$backup" -C "$apps_dir" aeronexus_feeder
    printf '기존 소스 백업: %s\n' "$backup"
fi
mkdir -p "$target"
cp -a "$source_dir/." "$target/"
(cd "$target" && sha256sum -c MANIFEST.sha256 >/dev/null)
printf '최신 소스 배치 완료: %s\n' "$target"
printf '설정 → 앱 → 앱 설치 → 업데이트 확인 후 로컬 앱을 설치/업데이트하세요.\n'
printf 'UUID 입력 → 저장 → 시작. 부팅 시 시작과 Watchdog도 켜세요.\n'
