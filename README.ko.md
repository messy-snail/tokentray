<div align="center">

<img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/packaging/resources/tokentray-256.png" alt="tokentray 아이콘" width="96">

# tokentray

**Claude Code와 Codex 사용량 한도를 시스템 트레이에서 바로 확인하세요.**

[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)](LICENSE)

![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D)
![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

[English](https://github.com/messy-snail/tokentray/blob/main/README.md) · **한국어**

</div>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/hero-ko-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/hero-ko-light.png" alt="tokentray 상세 패널, 알림 카드, 트레이 아이콘 상태" width="760">
  </picture>
</p>

> [!NOTE]
> **출처.** tokentray는
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT)를 바탕으로 Python으로 새로 구현한 프로젝트입니다. 원본의 SwiftBar 플러그인과
> PowerShell 트레이 스크립트에서 사용량 조회 API, 사용 속도·소진 예측 공식, 색상 구간을
> 따랐고, 세 운영체제에서 공통된 화면과 알림 기능을 제공하도록 구성했습니다.

## 주요 기능

- 🟢 **트레이 링으로 한눈에** - 바깥쪽은 Claude, 안쪽은 Codex. 남은 비율 50% 초과는
  초록, 21%까지 주황, 20% 이하는 빨강, 데이터가 없으면 회색입니다.
- 📊 **상세 패널** - Opus/Sonnet과 Codex 모델별 한도까지 한도마다 남은 비율, 리셋까지
  남은 시간, 소진 예상, 사용 속도를 보여줍니다.
- 🔔 **소진 전에 알림** - 50·25·10% 남았을 때와 리셋 직전에 알려줍니다.
- 🔑 **원클릭 로그인 복구** - 로그인이 만료되면 `claude auth login`이나 `codex login`을
  실행하는 터미널을 열어줍니다.
- 🌐 **웹훅** - Slack, Discord, ntfy 또는 원하는 HTTP 주소로 알림을 보냅니다.
- 🖥️ **Windows, macOS, Linux**를 지원하고 한국어와 영어로 쓸 수 있습니다.

사용 속도 **1.0x**는 지금까지의 평균 속도를 유지하면 리셋 시점에 딱 한도를 다 쓴다는
뜻입니다.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/login-recovery-ko-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/login-recovery-ko-light.png" alt="Claude Code 로그인 만료 안내와 로그인 바로가기, 다시 확인 버튼" width="250">
  </picture>
  &nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/integrations-ko-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/integrations-ko-light.png" alt="Discord 웹훅을 선택한 알림 연동 설정 창" width="344">
  </picture>
</p>

## 설치

> [!TIP]
> **uv로 설치하는 것을 권장합니다.** 맞는 Python을 알아서 내려받고 tokentray를 별도
> 환경에 설치하므로 시스템의 다른 부분을 건드리지 않습니다.

### ![uv](https://img.shields.io/badge/uv-%EA%B6%8C%EC%9E%A5-DE5FE9?style=flat-square&logo=uv&logoColor=white)

먼저 uv를 한 번 설치합니다.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`brew install uv`나 `winget install --id=astral-sh.uv -e`도 됩니다. 그다음:

```bash
uv tool install tokentray
```

설치 후 셸이 `tokentray`를 찾지 못하면 `uv tool update-shell`을 실행하고 터미널을
새로 여세요.

### pipx

```bash
pipx install tokentray
```

### pip

Python 3.11~3.13이 필요합니다. 가상환경에 설치하세요.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install tokentray
```

### 실행 파일 (Python 불필요)

| 플랫폼 | 내려받기 | 다음 단계 |
|---|---|---|
| ![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D) | [`tokentray-windows-x86_64.zip`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-windows-x86_64.zip) | 압축을 풀고 `tokentray\tokentray-gui.exe` 실행 |
| ![macOS](https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white) | [`tokentray-macos-arm64.zip`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-macos-arm64.zip) | `tokentray.app`을 응용 프로그램 폴더로 이동 |
| ![Linux](https://img.shields.io/badge/Linux-FCC624?style=flat-square&logo=linux&logoColor=black) | [`tokentray-linux-x86_64.tar.gz`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-linux-x86_64.tar.gz) | 압축을 풀고 `./install.sh` 실행 |

> [!IMPORTANT]
> 실행 파일은 코드 서명이 없어서 처음 실행할 때 Windows SmartScreen과 macOS
> Gatekeeper가 경고합니다. [플랫폼별 참고](#플랫폼별-참고)를 확인하세요.

## 빠른 시작

먼저 [Claude Code](https://code.claude.com/docs/en/setup)나
[Codex](https://developers.openai.com/codex/cli/)에 로그인하세요. 둘 중 하나만 있어도 됩니다.

```bash
tokentray setup              # 언어 선택, 로그인 상태 확인, 로그인 시 자동 시작 설정
tokentray                    # 백그라운드로 트레이 앱 시작, 터미널은 바로 반환
```

실행 파일을 쓴다면 `tokentray` CLI는 앱과 같은 위치에 있습니다(macOS는
`tokentray.app/Contents/MacOS` 안).

앱이 시작되면 터미널을 닫아도 계속 실행됩니다. `setup` 마지막에 앱 시작을 선택한
경우에도 같습니다. 종료는 트레이 메뉴나 `tokentray stop`을 사용하세요.
디버깅할 때만 `tokentray run --foreground`로 터미널에 연결해서 실행할 수 있습니다.

## 알림과 조회 주기 설정

| 설정 | 기본값 | 설명 |
|---|---|---|
| `poll_interval` | `120` | 사용량 확인 주기(초, 최소 30) |
| `thresholds` | `50,25,10` | 알림을 띄울 남은 비율(%) |
| `remind_before` | `60,30,10` | 리셋 몇 분 전에 알려줄지 |
| `popup.duration` | `8` | 알림 카드 표시 시간(초) |
| `popup.position` | `auto` | `bottom-right`, `top-right`, `auto`(macOS는 위, 나머지는 아래) |
| `native_notifications` | Windows `false`, 그 외 `true` | OS 알림도 함께 보내기 |

```bash
tokentray config set poll_interval 300    # 5분마다 확인
tokentray config set thresholds 50,20,5   # 50%, 20%, 5% 남았을 때 알림
tokentray config set remind_before 30,10  # 리셋 30분, 10분 전에 알림
tokentray config get thresholds
```

변경 사항은 실행 중인 앱에 바로 적용됩니다. `poll_interval`과 `language`만 재시작 후
적용됩니다. 설정 파일 위치는 `tokentray config path`로 확인할 수 있습니다.

> [!NOTE]
> **사용량 조회가 잠시 제한될 수 있습니다.**
> ‘요청 제한(HTTP 429)’이 발생하면 마지막 조회값을 표시하고, 대기 후 자동으로
> 다시 조회합니다. 이 응답 자체가 계정 정지나 대화 사용량 소진을 뜻하지는 않습니다.
> 제한 중에는 수동 새로고침을 눌러도 즉시 조회하지 않습니다.

<details>
<summary><b>갱신 문제 해결</b></summary>

갱신 결과는 **Claude 갱신 실패: 요청 제한**처럼 서비스와 이유를 표시합니다.
Claude 조회가 실패해도 Codex 갱신 결과는 따로 표시합니다.

TokenTray는 마지막 조회값을 유지하고 서버의 `Retry-After`와 사용자 조회 주기 중
긴 시간 이상 기다립니다. 서버가 유효한 대기 시간을 주지 않으면 반복 429에 따라
5→10→20→40→60분으로 대기를 늘리며, 사용자 설정 주기보다 짧게 재시도하지 않습니다.
조회에 성공하면 누적 대기를 초기화합니다. 표시된 시각은 재시도 가능한 시각이며
성공을 보장하는 시각은 아닙니다. 재시작·수동 새로고침·로그인 재확인·알림 테스트도
이 대기를 우회하지 않습니다. 요청 사이에는 최소 30초 간격을 두므로 새로고침을
연속으로 눌렀을 때는 최근 데이터를 유지할 수 있습니다.

`poll_interval`은 정상 상태의 조회 주기입니다. 제한 중에는 설정값을 변경하지 않고도
실제 요청 간격이 길어집니다. `/api/oauth/usage`의 공식 보장 조회 주기는 확인되지
않았으며, 2분이나 5분은 서버가 보장한 값이 아닙니다. TokenTray는 Claude Code,
다른 도구나 기기의 요청량까지 제어할 수 없습니다. 문제가 계속되면 트레이 메뉴의
**로그 열기**로 확인하세요. 네트워크 진단 로그에는 토큰·헤더 원문·응답 본문을 남기지 않습니다.

</details>

> [!TIP]
> 잠시 조용히 하고 싶다면 트레이 메뉴에서 **알림 1시간 일시정지**를 누르세요.
> **알림 테스트**로 알림 카드를 미리 볼 수 있습니다. 요청 제한 중에는 캐시 데이터를 사용합니다.

<details>
<summary><b>기타 설정과 웹훅</b></summary>

| 설정 | 기본값 | 설명 |
|---|---|---|
| `language` | 시스템 언어 | `en` 또는 `ko` |
| `webhook.enabled` / `webhook.kind` | `false` / `ntfy` | `slack`, `discord`, `ntfy`, `generic` 외부 알림 |
| `codex.refresh` | `false` | tokentray가 Codex 토큰을 갱신하도록 허용 |
| `linux.force_xwayland` | `true` | 플랫폼별 참고 확인 |

트레이 메뉴의 **알림 연동 설정…**에서 웹훅 한 곳을 설정하고 URL 확인과 테스트 전송을 할
수 있습니다. 터미널에서도 됩니다.

```bash
tokentray webhook setup --service slack
tokentray webhook test
```

URL은 OS 키링에 저장합니다. 외부 알림은 tokentray가 실행 중이고 인터넷에 연결된 기기에서만
보냅니다. 여러 기기에서 같은 계정을 감시한다면 중복을 피하도록 한 기기에서만 웹훅을 켜세요.
Slack은 앱 아이콘에 `packaging/resources/tokentray-512.png`를 쓰면 되고, Discord는 채널의
웹훅 설정에서 아바타를 지정할 수 있습니다.

</details>

<details>
<summary><b>전체 명령어</b></summary>

| 명령 | 설명 |
|---|---|
| `tokentray` | 트레이 앱 시작 |
| `tokentray setup` | 최초 실행 대화형 설정 |
| `tokentray status` | 현재 사용량 출력(실행 중인 앱의 데이터를 우선 사용) |
| `tokentray open` / `refresh` / `stop` | 실행 중인 인스턴스 제어 |
| `tokentray doctor` | 자격 증명, 키링, 트레이, 알림 전달 가능 여부 점검 |
| `tokentray config get/set/path` | 설정 읽기와 쓰기 |
| `tokentray state reset --welcome/--alerts/--all` | 시작 안내나 알림 발화 기록 초기화 |
| `tokentray webhook setup/test` | 웹훅 설정과 테스트 |
| `tokentray autostart enable/disable/status` | 로그인 시 시작 관리 |

</details>

## 플랫폼별 참고

<details>
<summary><img src="https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D" alt="Windows"></summary>

- 새 트레이 아이콘은 숨겨진 아이콘 목록에 들어갈 수 있습니다. 시작 안내 카드에서 작업 표시줄
  설정으로 이동할 수 있고, 목록에서는 `tokentray`로 시작하는 이름으로 보입니다.
- 실행 파일에서 SmartScreen 경고가 뜨면 *추가 정보*를 누른 뒤 *실행*을 선택하세요.
- uv나 pip로 설치했다면 작업 관리자에 백그라운드 프로세스가 `pythonw.exe`로 표시됩니다.

</details>

<details>
<summary><img src="https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS"></summary>

- 빌드는 ad-hoc 서명만 되어 있고 공증(notarization)은 되지 않았습니다. Gatekeeper가
  막으면 다음을 실행하세요.

  ```bash
  xattr -dr com.apple.quarantine /Applications/tokentray.app
  ```

- Apple silicon 전용입니다. 메뉴 막대 전용 앱이라 Dock 아이콘은 없습니다.
- CLI는 `/Applications/tokentray.app/Contents/MacOS/tokentray`에 있습니다. `tokentray`로
  바로 쓰려면 `PATH`에 심볼릭 링크를 추가하세요.
- Claude Code 로그인 정보를 키체인에서 처음 읽을 때 접근 허용 창이 뜰 수 있습니다.
- 트레이 앱이 보내는 알림 센터 알림은 신뢰하기 어려워서 tokentray 자체 알림 카드가 기본
  경로입니다. `tokentray doctor`로 현재 빌드의 상태를 확인할 수 있습니다.

</details>

<details>
<summary><img src="https://img.shields.io/badge/Linux-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux"></summary>

- x86_64 tar 압축 파일만 제공합니다. `./install.sh`는 사용자 단위로 런처 항목과 아이콘을
  등록하고, `./install.sh --uninstall`로 제거합니다.
- 최소 설치 환경에서는 기본 Ubuntu 24.04를 포함해 Qt가 쓰는 시스템 라이브러리가 없을 수
  있습니다.

  ```bash
  sudo apt install libxcb-cursor0 libxkbcommon0 libegl1 libgl1 libdbus-1-3 libfontconfig1 libglib2.0-0
  ```

- GNOME은 트레이 아이콘 표시에 AppIndicator 확장이 필요하고, KDE는 기본으로 지원합니다.
- Wayland에서는 알림 카드가 트레이 옆에 뜨도록 XWayland를 거쳐 실행합니다.
  `linux.force_xwayland = false`로 바꾸면 네이티브로 실행하지만 카드 위치는 컴포지터가
  정합니다.
- SecretService 같은 키링 서비스가 없으면 시크릿을 소유자 전용 로컬 파일에 저장하고,
  셋업에서 이를 안내합니다.

</details>

## 자세한 정보

<details>
<summary><b>로그인 정보</b></summary>

tokentray는 Claude Code와 Codex가 이미 저장한 로그인 정보를 읽습니다.

| 서비스 | 위치 |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (또는 `$CLAUDE_CONFIG_DIR`), 없으면 macOS 로그인 키체인 |
| Codex | `~/.codex/auth.json` (또는 `$CODEX_HOME`) |

- 패널이나 알림의 **로그인 바로가기**를 누르면 로그인 명령을 실행하는 터미널을 열고, 최대
  5분간 새 로그인 정보를 기다립니다. 터미널을 열 수 없으면 표시된 명령을 복사하세요.
- Claude 토큰 갱신은 Claude Code에 맡깁니다. Codex 토큰 갱신은 직접 켜야 하며
  (`codex.refresh`), 저장 직전에 `auth.json`을 다시 읽어 Codex CLI의 변경을 덮어쓰지
  않습니다.
- `setup`에서 붙여 넣은 토큰은 OS 키링에 저장합니다. 붙여 넣은 Claude 토큰은 만료되면
  갱신할 수 없습니다.
- `doctor`가 `no token in file`을 표시해도 로그아웃 상태라는 뜻은 아닐 수 있습니다. 파일에
  요금제 정보만 있고 로그인은 다른 곳에서 처리하는 경우입니다.

</details>

<details>
<summary><b>알림 전달 방식</b></summary>

- **Windows**는 tokentray 자체 카드를 보여줍니다. `native_notifications = true`로 바꾸면
  Windows 배너를 대신 쓰고, 배너 전송에 실패하면 카드로 보여줍니다. 시작 안내와 로그인
  복구 알림은 버튼이 동작하도록 항상 카드로 표시합니다.
- **macOS와 Linux**는 카드와 함께 OS 알림도 보냅니다.
- **알림 테스트**는 최신 사용량을 조회해 서비스별 카드를 보여주며, 알림 기록을 바꾸거나
  웹훅을 보내지 않습니다.
- OS 알림 시도는 모두 로그에 남습니다. 트레이 메뉴에서 로그를 열 수 있습니다.

</details>

## 개인정보

> [!NOTE]
> 원격 사용 통계(텔레메트리)는 수집하지 않습니다. Claude와 Codex 토큰은
> `api.anthropic.com`, `chatgpt.com`, `auth.openai.com`으로만 HTTPS를 통해 전송합니다.
> 웹훅에는 알림 내용만 보내고 토큰은 보내지 않습니다.

macOS와 Linux에서는 캐시와 대체 시크릿 파일을 소유자 전용(`0600`)으로 저장하고, Windows에서는
사용자 프로필 폴더의 권한을 따릅니다.

## 기여하기

버그 제보, 아이디어, PR 모두 환영합니다. 한국어나 영어 어느 쪽으로 써도 됩니다.

- 🐛 **버그를 찾았다면** `tokentray --version`과 `tokentray doctor` 출력을 담아
  [버그 리포트](https://github.com/messy-snail/tokentray/issues/new?template=bug_report.yml)를 열어 주세요.
- 💡 **아이디어가 있다면** [기능 제안](https://github.com/messy-snail/tokentray/issues/new?template=feature_request.yml)을 열어 주세요.
- 🔒 **보안 문제는** 공개 이슈 대신 비공개로 제보해 주세요. [SECURITY.md](SECURITY.md)를 참고하세요.
- 🛠️ **코드를 보내고 싶다면** [CONTRIBUTING.md](CONTRIBUTING.md)부터 읽어 주세요.

## 라이선스

MIT - [LICENSE](LICENSE)를 참고하세요. 원본
[haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)의 MIT
고지도 이 파일에 유지했습니다. 실행 파일은 PySide6를 통해 Qt(LGPLv3)를 동적 링크
라이브러리로 포함합니다.
