# tokentray

[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6B7280?style=flat-square)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)](LICENSE)

[English](README.md) · **한국어**

**Claude Code**와 **OpenAI Codex**의 사용량 한도를 시스템 트레이에서 지켜보고,
다 쓰기 전에 읽기 쉬운 데스크톱 알림을 띄웁니다. Windows, macOS, Linux를 하나의
코드베이스로 지원합니다.

> **출처.** tokentray는
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT)에서 출발해 처음부터 다시 구현한 프로젝트입니다. 원본은 SwiftBar 플러그인과
> PowerShell 트레이 스크립트로 이 아이디어를 처음 만들었습니다. 숫자를 그대로 비교할
> 수 있도록 사용량 엔드포인트, 속도/소진 예상 공식, 색상 구간은 원본을 따랐고, 원본의
> MIT 고지는 [LICENSE](LICENSE)에 유지했습니다. Python으로 다시 쓴 이유는 원본의 두
> 스크립트가 서로 갈라졌기 때문입니다. Windows 쪽에는 리셋 알림도, 휴대폰 알림도,
> Codex 알림도 끝내 들어가지 않았습니다.

## 무엇을 보여주나요

- **Claude Code** — 5시간 세션, 7일 윈도우, 쓰기 시작하면 나타나는 Opus/Sonnet
  모델별 하위 한도, 그리고 종량제 Extra Usage.
- **Codex** — 플랜이 실제로 보고하는 rate-limit 윈도우만 보여줍니다(주간 한도만 있는
  플랜이라면 `5h` 행을 잘못 붙이지 않고 `7d` 한 줄만 나옵니다). 크레딧도 함께.
- 모든 윈도우에 대해: 남은 %, 리셋까지 남은 시간, **속도**(1.0x면 리셋되는 바로 그
  순간에 정확히 0이 됩니다), 그리고 소진 예상 시점.

트레이 아이콘은 12시부터 시계방향으로 줄어드는 링이고, 50% 위는 초록, 20%까지는 주황,
그 아래는 빨강입니다. 두 provider를 모두 설정하면 링이 두 겹이 됩니다 — 바깥쪽 Claude,
안쪽 Codex. 각각 한 바퀴를 다 쓰므로 읽는 방식은 같습니다.

## 설치

```bash
uv tool install tokentray
```

또는 [Releases](https://github.com/messy-snail/tokentray/releases)에서 플랫폼별
패키징 빌드를 내려받으세요 — Python이 없어도 됩니다.

그다음:

```bash
tokentray setup
```

설정 마법사가 이미 로그인해 둔 것을 찾아내고, 데스크톱 로캘에서 언어를 고르고, 로그인
시 자동 실행을 켤지 물어봅니다.

## 명령어

| 명령 | |
|---|---|
| `tokentray` | 트레이 앱 시작 |
| `tokentray setup` | 최초 실행 대화형 설정 |
| `tokentray status` | 현재 사용량 출력(실행 중인 앱에 먼저 물어봅니다) |
| `tokentray open` / `refresh` / `stop` | 실행 중인 인스턴스 제어 |
| `tokentray doctor` | 자격 증명, 키링, 트레이 사용 가능 여부 점검 |
| `tokentray config get/set/path` | 설정 읽기와 쓰기 |
| `tokentray autostart enable/disable/status` | 로그인 시 시작 관리 |

## 토큰을 어떻게 찾나요

tokentray는 CLI들이 이미 이 컴퓨터에 저장해 둔 자격 증명을 읽고, **Claude 토큰은 절대
갱신하지 않습니다**. 그 토큰의 주인은 Claude Code이고, 두 번째 writer가 끼어드는 것이
바로 사람들이 로그아웃되는 경로이기 때문입니다. 만료되면 tokentray가 그 사실을 알려주고
`claude`를 실행하라고 안내합니다.

| | 위치 |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (또는 `$CLAUDE_CONFIG_DIR`), 없으면 macOS 로그인 키체인 |
| Codex | `~/.codex/auth.json` (또는 `$CODEX_HOME`) |

파일에 쓸 만한 토큰이 없을 때 — 데스크톱 앱처럼 다른 곳에서 인증된 세션이면 Claude
Code가 `accessToken`을 빈 값으로 두고 플랜 메타데이터만 기록합니다 — `tokentray
doctor`는 로그아웃됐다고 단정하지 않고 `no token in file`이라고 알려줍니다.

`setup` 중에 토큰을 직접 붙여넣을 수도 있으며, 이 값은 OS 키링에 저장됩니다. 다만 그
전에 알아둘 점이 있습니다. Claude 토큰은 몇 시간이면 만료되고 갱신할 수 있는 건 Claude
Code뿐이라, 붙여넣기는 설정이 아니라 임시방편입니다.

Codex 토큰 갱신은 **직접 켜야 하는 기능**입니다
(`tokentray config set codex.refresh true`). Codex CLI도 함께 소유한 `auth.json`을
다시 쓰기 때문입니다. 켜두면 tokentray는 쓰기 직전에 파일을 다시 읽고, 그사이 CLI가
파일을 바꿨다면 물러납니다.

## 설정

`tokentray config path`가 모든 경로를 출력합니다. 자주 쓰는 키는 다음과 같습니다.

| 키 | 기본값 | |
|---|---|---|
| `poll_interval` | `120` | 확인 주기(초, 최소 30) |
| `thresholds` | `[50, 25, 10]` | 알림을 띄울 남은 % |
| `remind_before` | `[60, 30, 10]` | 리셋 몇 분 전에 알릴지, 비우면 끔 |
| `language` | 로캘에서 결정 | `en` 또는 `ko` |
| `popup.duration` | `8` | 토스트가 떠 있는 시간(초) |
| `native_notifications` | `true` | OS 알림 센터로도 함께 보내기 |
| `webhook.enabled` / `.kind` / `.url` | 꺼짐 | `ntfy` 또는 `generic` JSON POST |
| `codex.refresh` | `false` | tokentray가 Codex 토큰을 갱신하도록 허용 |
| `linux.force_xwayland` | `true` | 아래 참고 |

## 알림을 왜 직접 그리나요

여기서 네이티브 알림은 보조 채널이지 주 채널이 아닙니다. macOS는 서명된 번들에서만
알림을 보내주고, Windows는 AppUserModelID 등록을 요구하면서 집중 지원 모드에서는 레거시
풍선 알림을 조용히 삼켜버리며, 세 플랫폼의 스타일이 제각각입니다. tokentray가 직접
그리는 창은 어디서나 같은 모습이고, 항상 뜨고, 게이지를 보여줄 수 있습니다 — 사실 그게
메시지의 대부분입니다.

## 플랫폼별 참고

**Windows.** 새로 생긴 트레이 아이콘은 오버플로 플라이아웃에 숨습니다. 환영 팝업에 그
설정으로 바로 가는 버튼을 넣어 뒀습니다. 배포 파일에는 서명이 없어서 SmartScreen이 한
번 경고합니다 — *추가 정보*를 누른 뒤 *실행*을 선택하세요. `uv tool`로 설치하면
백그라운드 프로세스가 작업 관리자에 `pythonw.exe`로 보입니다.

**macOS.** 빌드는 ad-hoc 서명만 되어 있고 공증은 받지 않아서 Gatekeeper가 격리합니다.

```bash
xattr -dr com.apple.quarantine /Applications/tokentray.app
```

메뉴 막대 전용 앱(`LSUIElement`)이라 Dock 아이콘은 의도적으로 없습니다. 빌드는
arm64 전용이며 Intel 빌드는 없습니다. CLI는 번들 안에 들어 있어서 `status`,
`doctor`, `autostart`는 `/Applications/tokentray.app/Contents/MacOS/tokentray`에
있습니다. 그냥 `tokentray`로 쓰고 싶으면 PATH에 심볼릭 링크를 걸면 됩니다.
macOS에서 Claude Code는 자격증명을 파일이 아니라 로그인 키체인에 두기 때문에, 처음
읽을 때 키체인 접근 허용 창이 뜰 수 있습니다.

**Linux.** tarball로만 배포합니다 — `.deb`, AppImage, Flatpak은 없습니다. 압축을
푼 뒤 `./install.sh`를 실행하면 런처 항목과 아이콘이 등록됩니다(사용자 단위, root
불필요. `./install.sh --uninstall`로 되돌립니다). GNOME은 트레이를 쓰려면
AppIndicator 확장이 필요하고, KDE는 그대로 동작합니다. 일부 배포판은 `libxcb-cursor0`를 설치해야 합니다. Wayland에서는 기본적으로
XWayland를 거쳐 실행되는데, Wayland가 클라이언트에게 창 위치를 정할 권한을 주지 않아
토스트가 컴포지터 마음대로 흩어지기 때문입니다. 네이티브 Wayland와 알림 센터 알림을
쓰려면 `linux.force_xwayland = false`로 바꾸세요. SecretService 데몬이 없으면 붙여넣은
토큰은 소유자 전용 파일로 대신 저장되고, setup이 그 사실을 알려줍니다.

## 개인정보

토큰은 각자의 vendor에게 HTTPS로만 전달되고 그 밖의 어디로도 가지 않습니다. tokentray가
접속하는 호스트는 `api.anthropic.com`, `chatgpt.com`, `auth.openai.com` 세 곳뿐입니다
(웹훅을 설정했다면 그 주소까지). 텔레메트리는 없습니다. macOS와 Linux에서는 캐시와 대체
시크릿 파일을 소유자 전용(`0600`)으로 씁니다. Windows에서는 사용자 프로필 디렉터리의
ACL을 그대로 물려받는데, 기본적으로 사용자 단위이긴 하지만 그 이상으로 좁히지는
않습니다.

## 개발

```bash
uv sync
uv run pytest
```

위젯 테스트는 Qt의 offscreen 플랫폼에서 돌기 때문에 코드가 동작한다는 것은 증명해도 보기
좋다는 것까지 증명하지는 못합니다 — 나머지는 [MANUAL_TEST.md](MANUAL_TEST.md)가 다룹니다.

패키징 빌드:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
./packaging/smoke.sh
```

`smoke.sh`는 CI와 릴리스 워크플로가 갓 만든 번들에 대해 똑같이 돌리는 스크립트입니다.
실행 파일 두 개가 다 있는지, 윈도우 모드 실행 파일이 이벤트 루프를 띄우지 않고
`--version`에 답하는지, macOS 번들이 CLI가 아니라 GUI를 띄우는지를 확인합니다.

아이콘 파일은 트레이 마크를 그리는 그 페인터에서 생성되므로 서로 어긋나지 않습니다.
마크를 바꾸면 다시 생성해서 커밋하세요.

```bash
QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
```

리눅스 머신에서는 `./scripts/verify-linux.sh`가 사람 없이 확인 가능한 항목을 모두
돌리고, 남은 항목을 [MANUAL_TEST.md](MANUAL_TEST.md) 기준으로 알려줍니다.

## 라이선스

MIT — [LICENSE](LICENSE)를 보세요. tokentray는 PySide6로 Qt를 함께 배포하며 Qt는
LGPLv3입니다. 패키징 빌드에는 동적 링크 라이브러리로 포함됩니다.
