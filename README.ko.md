# tokentray

[![English](https://img.shields.io/badge/README-English-64748B?style=flat-square)](https://github.com/messy-snail/tokentray/blob/main/README.md)
[![한국어](https://img.shields.io/badge/README-%ED%95%9C%EA%B5%AD%EC%96%B4-2563EB?style=flat-square)](https://github.com/messy-snail/tokentray/blob/main/README.ko.md)

[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6B7280?style=flat-square)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)](LICENSE)

<!-- Restore these two inside the badge row at the 0.1.0 tag. Until a
     package and a release exist they render as "not found" and
     "no releases", which reads as a broken project.
[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
-->

**Claude Code**와 **OpenAI Codex**의 남은 사용량을 시스템 트레이에서 확인하고,
한도를 모두 사용하기 전에 데스크톱 알림을 받을 수 있습니다.
Windows, macOS, Linux를 지원합니다.

> **출처.** tokentray는
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT)를 바탕으로 Python으로 새롭게 구현한 프로젝트입니다. 원본의 SwiftBar 플러그인과
> PowerShell 트레이 스크립트에서 사용량 조회 API, 사용 속도·소진 예측 공식, 색상 구간을
> 따랐으며, MIT 고지는 [LICENSE](LICENSE)에 유지했습니다. 세 운영체제에서 공통된
> 화면과 알림 기능을 제공하도록 구성했습니다.

## 무엇을 보여주나요

- **Claude Code** — 5시간·7일 한도, 사용을 시작한 Opus/Sonnet의 모델별 한도,
  종량제 추가 사용량(Extra Usage)을 표시합니다.
- **Codex** — 요금제에서 제공하는 기간별 한도, 모델별 한도, 크레딧을 표시합니다.
  계정 한도가 주간 단위라면 7일로 표시합니다. 모델별 한도는 사용량이 0%여도 표시하므로,
  별도의 5시간 한도가 있다면 함께 확인할 수 있습니다.
- 각 기간의 남은 비율, 리셋까지 남은 시간, **사용 속도**, 소진 예상 시점을 보여줍니다.
  속도 1.0x는 지금까지의 평균 사용 속도가 유지될 경우 리셋 시점에 한도가 소진될 것으로
  예상된다는 뜻입니다.

트레이 아이콘은 12시 방향부터 시계방향으로 줄어드는 링입니다. 두 서비스를 모두 켜면
바깥쪽은 Claude, 안쪽은 Codex를 나타냅니다. 색상은 남은 비율의 소수점을 버린 값을
기준으로 50% 초과는 초록, 21~50%는 주황, 20% 이하는 빨강입니다.
사용량 데이터가 없는 서비스는 회색 링으로 표시합니다.

## 설치

> **0.1.0은 아직 릴리스 전입니다.** Linux 데스크톱 검증이 남아 있습니다.
> PyPI 패키지와 배포용 실행 파일은 아직 제공하지 않으므로 아래 명령으로 소스에서 설치하세요.

```bash
git clone https://github.com/messy-snail/tokentray
cd tokentray
uv tool install .
```

0.1.0에서는 `uv tool install tokentray` 명령과
[Releases](https://github.com/messy-snail/tokentray/releases)의 운영체제별 실행 파일을
제공할 예정입니다. 배포용 실행 파일은 Python을 별도로 설치하지 않아도 됩니다.

그다음:

```bash
tokentray setup
```

설정 마법사가 기존 로그인 정보를 확인하고 시스템 언어에 맞춰 표시 언어를 선택합니다.
로그인 시 자동 실행 여부도 설정할 수 있습니다.

## 명령어

| 명령 | 설명 |
|---|---|
| `tokentray` | 트레이 앱 시작 |
| `tokentray setup` | 최초 실행 대화형 설정 |
| `tokentray status` | 현재 사용량 출력(실행 중인 앱의 데이터를 우선 사용) |
| `tokentray open` / `refresh` / `stop` | 실행 중인 인스턴스 제어 |
| `tokentray doctor` | 자격 증명, 키링, 트레이 사용 가능 여부 점검 |
| `tokentray config get/set/path` | 설정 읽기와 쓰기 |
| `tokentray webhook setup/test` | Slack, Discord, ntfy 또는 일반 웹훅 설정과 테스트 |
| `tokentray autostart enable/disable/status` | 로그인 시 시작 관리 |

## 로그인 정보

tokentray는 Claude Code와 Codex가 이 컴퓨터에 저장한 로그인 정보를 읽습니다.
인증 정보의 동시 변경을 피하기 위해 **Claude 토큰 갱신은 Claude Code에 맡깁니다**.
토큰이 만료되면 `claude`를 실행해 로그인을 갱신하도록 안내합니다.

| 서비스 | 위치 |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (또는 `$CLAUDE_CONFIG_DIR`), 없으면 macOS 로그인 키체인 |
| Codex | `~/.codex/auth.json` (또는 `$CODEX_HOME`) |

인증 파일에 요금제 정보만 있고 유효한 `accessToken`이 없으면 `tokentray doctor`는
`no token in file`이라고 표시합니다. 데스크톱 앱 등 다른 곳에서 인증을 처리하는 경우에도
발생할 수 있으므로, 이 메시지가 반드시 로그아웃 상태를 뜻하지는 않습니다.

`setup`에서 토큰을 직접 입력할 수도 있습니다. 토큰은 OS 키링에 저장하며, 키링을 사용할
수 없으면 별도의 로컬 시크릿 파일에 저장합니다(개인정보 항목 참고). 직접 입력한 Claude
토큰은 만료 시 tokentray가 갱신할 수 없으므로 임시로 사용할 때 적합합니다.

Codex 토큰 갱신은 **직접 켜야 하는 기능**입니다
(`tokentray config set codex.refresh true`). 파일 기반 인증은 Codex CLI와 `auth.json`을
공유하기 때문입니다. 갱신된 인증 정보를 저장하기 직전에 파일을 다시 읽고,
그사이 CLI가 파일을 변경했다면 덮어쓰지 않습니다.

## 설정

`tokentray config path`로 설정과 데이터 저장 경로를 확인할 수 있습니다. 주요 설정은 다음과 같습니다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `poll_interval` | `120` | 확인 주기(초, 최소 30) |
| `thresholds` | `[50, 25, 10]` | 알림을 띄울 남은 % |
| `remind_before` | `[60, 30, 10]` | 리셋 전 알림 시점(분), 빈 목록이면 끔 |
| `language` | 시스템 언어 | `en` 또는 `ko` |
| `popup.duration` | `8` | 팝업 표시 시간(초) |
| `native_notifications` | `true` | OS 알림 센터로도 함께 보내기 |
| `webhook.enabled` / `webhook.kind` | `false` / `ntfy` | 외부 알림 활성화 및 `slack`, `discord`, `ntfy`, `generic` 중 선택 |
| `codex.refresh` | `false` | tokentray가 Codex 토큰을 갱신하도록 허용 |
| `linux.force_xwayland` | `true` | 아래 참고 |

트레이 메뉴의 **알림 연동 설정…**에서 알림을 받을 서비스 한 곳을 선택하고 URL 확인과
테스트 전송을 할 수 있습니다. Slack과 Discord는 Incoming Webhook을 사용합니다.
URL은 OS 키링에 저장하며, 키링을 사용할 수 없으면 별도의 로컬 시크릿 파일에 저장합니다
(개인정보 항목 참고). 터미널에서도 설정할 수 있습니다.

```bash
tokentray webhook setup --service slack
tokentray webhook test
```

> **알림 수신 조건**
>
> 외부 알림은 tokentray가 실행 중이고 인터넷에 연결된 기기에서 전송합니다. 사용량을
> 조회하려면 유효한 로그인 정보도 필요합니다. 앱 종료·기기 종료·절전 중에는 해당 기기의
> 조회와 전송이 중단됩니다. 상세 창을 닫아도 트레이에서 실행 중이면 계속 동작합니다.
>
> 여러 기기에서 같은 계정을 감시하고 같은 곳으로 알림을 보내면 중복 수신할 수 있습니다.
> 외부 알림은 한 기기에서만 켜고, 나머지 기기에서는 데스크톱 알림만 사용하는 것을
> 권장합니다. 전송 담당 기기가 멈춰도 다른 기기가 자동으로 대신 전송하지는 않습니다.

Slack 발신자 이름과 아이콘은 웹훅을 만든 Slack 앱 설정을 따릅니다. 앱 아이콘에는
`packaging/resources/tokentray-512.png`를 쓰면 됩니다. Discord도 채널의 웹훅 설정에서
같은 파일을 아바타로 지정할 수 있습니다.

## 알림 방식

남은 사용량을 게이지가 포함된 데스크톱 팝업으로 보여줍니다. OS 알림 센터와 설정한
외부 서비스로도 알림을 보낼 수 있습니다. 자체 팝업은 운영체제에 관계없이 일관된 형식으로
표시하며, OS 알림은 운영체제의 지원 여부와 알림 설정에 따라 표시됩니다.

## 플랫폼별 참고

**Windows.** 새 트레이 아이콘은 작업 표시줄의 숨겨진 아이콘 목록에 나타날 수 있습니다.
시작 안내 팝업에서 관련 설정으로 이동할 수 있습니다. 배포 파일은 서명되지 않아
SmartScreen 경고가 나타날 수 있습니다. 계속하려면 *추가 정보*를 누른 뒤 *실행*을
선택하세요. `uv tool`로 설치하면 백그라운드 프로세스가 작업 관리자에 `pythonw.exe`로 보입니다.

**macOS.** 빌드는 ad-hoc 서명만 되어 있고 공증은 받지 않았습니다. 내려받은 앱을
Gatekeeper가 차단하면 다음 명령으로 격리 속성을 해제할 수 있습니다.

```bash
xattr -dr com.apple.quarantine /Applications/tokentray.app
```

메뉴 막대 전용 앱(`LSUIElement`)이므로 Dock 아이콘은 표시하지 않습니다. 빌드는
arm64 전용이며 Intel 빌드는 없습니다. CLI는 번들 안에 들어 있어서 `status`,
`doctor`, `autostart`는 `/Applications/tokentray.app/Contents/MacOS/tokentray`에
있습니다. `tokentray` 명령으로 바로 실행하려면 PATH에 심볼릭 링크를 추가하세요.
Claude Code 로그인 정보가 키체인에 저장된 경우, 처음 읽을 때 접근 허용 창이 나타날 수 있습니다.

**Linux.** 배포 형식은 tar 압축 파일이며 `.deb`, AppImage, Flatpak은 제공하지 않습니다. 압축을
푼 뒤 `./install.sh`를 실행하면 런처 항목과 아이콘이 등록됩니다(사용자 단위, root
불필요. `./install.sh --uninstall`로 제거). GNOME의 트레이 표시에는 AppIndicator 확장이
필요하고, KDE는 기본으로 지원합니다. 일부 배포판에서는 `libxcb-cursor0` 설치가 필요합니다.
Wayland에서는 팝업 위치 제어가 제한되므로 기본적으로 XWayland를 거쳐 실행합니다.
네이티브 Wayland와 알림 센터 알림을 사용하려면 `linux.force_xwayland = false`로 바꾸세요.
SecretService 등 키링 서비스를 사용할 수 없으면 시크릿을 소유자 전용 권한의 로컬 파일에
저장하고, setup에서 대체 저장 여부를 안내합니다.

## 개인정보

Claude와 Codex 로그인 토큰은 각 서비스의 `api.anthropic.com`, `chatgpt.com`,
`auth.openai.com`으로만 HTTPS를 통해 전송합니다. 설정한 웹훅에는 알림 내용을 보내며,
이 로그인 토큰들은 포함하지 않습니다. 원격 사용 통계(텔레메트리)는 수집하지 않습니다.
macOS와 Linux에서는 캐시와 대체 시크릿 파일에 소유자 전용 권한(`0600`)을 적용합니다.
Windows에서는 사용자 프로필 디렉터리의 접근 권한(ACL)을 상속하며, 별도의 추가 제한은
설정하지 않습니다.

## 개발

```bash
uv sync
uv run pytest
```

위젯 테스트는 화면을 띄우지 않는 Qt offscreen 모드로 실행합니다. 실제 데스크톱에서의
표시 상태와 외부 알림 수신은 [수동 테스트 체크리스트](MANUAL_TEST.ko.md)에 따라 별도로 확인합니다.

패키징 빌드:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
./packaging/smoke.sh
```

`smoke.sh`는 CI와 릴리스 워크플로에서 새 빌드를 검사합니다. 실행 파일 두 개의 존재 여부,
GUI 실행 파일의 `--version` 응답, macOS 앱 번들의 GUI 실행 여부를 확인합니다.

아이콘 파일은 트레이 아이콘 렌더러로 생성합니다. 아이콘 디자인을 바꾸면 다시 생성해서 커밋하세요.

```bash
QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
```

Linux에서는 `./scripts/verify-linux.sh`로 데스크톱 환경의 자동 검사 항목을 실행할 수 있습니다.
수동 확인이 필요한 항목은 [수동 테스트 체크리스트](MANUAL_TEST.ko.md)를 기준으로 안내합니다.

## 라이선스

MIT — [LICENSE](LICENSE)를 보세요. tokentray는 PySide6로 Qt를 함께 배포하며 Qt는
LGPLv3입니다. 패키징 빌드에는 동적 링크 라이브러리로 포함됩니다.
