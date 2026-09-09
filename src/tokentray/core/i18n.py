"""Translation table and lookup.

Strings live in a plain nested dict rather than gettext: there are two locales,
no plural rules worth the machinery, and a dict lets the parity test prove the
key sets and format placeholders match exactly across languages.
"""

from __future__ import annotations

import re
from typing import Iterable

DEFAULT_LANGUAGE = "en"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ko": "한국어",
}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # window labels
        # One naming scheme for every window either provider reports: the
        # duration is the name, and a sub-limit adds what it covers.
        "window.hours": "{n} hours",
        "window.hours_one": "{n} hour",
        "window.days": "{n} days",
        "window.days_one": "{n} day",
        "window.qualified": "{window} · {name}",
        "window.unknown": "Limit",
        # field labels
        "label.remaining": "remaining",
        "label.refills": "Refills in",
        "label.burns": "Burns out in",
        "label.resets_at": "Resets at",
        "label.pace": "Pace",
        "label.source": "Source",
        "label.extra_usage": "Extra Usage",
        "label.extra_off": "off",
        "label.credits": "Codex credits",
        "label.credits_unlimited": "unlimited",
        # menu
        "menu.open_panel": "Open details",
        "menu.refresh": "Refresh now",
        "menu.pause_alerts": "Pause alerts for 1 hour",
        "menu.resume_alerts": "Resume alerts",
        "menu.test_alert": "Test notification",
        "menu.integration": "Notification integrations…",
        "menu.language": "Language",
        "menu.autostart": "Start at login",
        "menu.open_log": "Open log",
        "menu.quit": "Quit",
        # statuses
        "status.no_data": "Not available yet — updates after usage",
        "status.rate_limited": "Rate limited — try again later",
        "status.not_configured_claude": "Not logged into Claude Code",
        "status.not_configured_codex": "Not logged into Codex",
        "status.expired_claude": "Claude Code login expired — run 'claude' in a terminal",
        "status.expired_codex": "Codex login expired — run 'codex' in a terminal",
        "status.schema_changed": "The API response format changed — please file an issue",
        "status.api_error": "API error",
        "status.window_reset": "Window reset — awaiting fresh data",
        "status.live": "live",
        "status.cached": "cached",
        "status.stale": "stale",
        # notifications
        "notify.summary_title": "Usage Warning",
        "notify.info_title": "tokentray",
        "welcome.title": "tokentray is running",
        "welcome.body": "It lives in your system tray — click the icon for details.",
        "welcome.ack": "Got it",
        "welcome.tray_settings": "Open tray settings",
        "welcome.menu_bar_manager": "Using a menu bar manager like Bartender, "
                                    "Ice or Hidden Bar? You may need to unhide "
                                    "tokentray there.",
        "test.body": "Notifications are working. This is what an alert looks like.",
        "test.claude_body": "5-Hour Session: 62% remaining",
        "test.codex_body": "Codex 7d: 38% remaining",
        # integration settings
        "integration.title": "Notification integrations",
        "integration.intro": "Send tokentray alerts to one Slack, Discord, ntfy, or generic webhook.",
        "integration.enabled": "Send alerts to this destination",
        "integration.service": "Service",
        "integration.url": "Webhook URL",
        "integration.saved_url": "Saved securely — leave blank to keep it",
        # Numbered steps rather than a screenshot: nothing here is loaded from
        # disk in a packaged build, and a picture of someone else's settings
        # page goes stale the next time they redesign it.
        "integration.steps.slack": "<ol><li>Open <a href=\"{url}\">Slack incoming webhooks</a> and create or pick an app for your workspace.</li><li>Turn on <b>Incoming Webhooks</b>, then <b>Add New Webhook to Workspace</b> and choose a channel.</li><li>Copy the webhook URL and paste it above.</li><li>In that app's <b>Basic Information</b>, set the tokentray icon so alerts are recognisable.</li></ol>",
        "integration.steps.discord": "<ol><li>In the target server, open <b>Server Settings</b> → <b>Integrations</b> → <b>Webhooks</b>.</li><li>Choose <b>New Webhook</b>, pick the channel, and name it tokentray.</li><li>Use <b>Copy Webhook URL</b> and paste it above.</li><li>Set the avatar on the same screen. <a href=\"{url}\">Discord's guide</a></li></ol>",
        "integration.steps.ntfy": "<ol><li>Pick a topic name that is hard to guess - anyone who knows it can read your alerts.</li><li>Subscribe to it in the ntfy app or at ntfy.sh.</li><li>Paste the topic URL above. <a href=\"{url}\">Publishing docs</a></li></ol>",
        "integration.steps.generic": "<ol><li>Point this at any HTTPS endpoint that accepts a JSON POST.</li><li>Each alert arrives as one request with the title, body and remaining percentage.</li></ol>",
        "integration.url_shape": "Format: {shape}",
        "integration.test": "Send test",
        "integration.save": "Save",
        "integration.testing": "Sending a test…",
        "integration.saving": "Saving securely…",
        "integration.test_ok": "Test notification sent.",
        "integration.test_failed": "Test failed: {reason}",
        "integration.error": "Could not apply the setting: {reason}",
        "integration.url_required": "Enter a webhook URL first.",
        # formats
        "fmt.remaining": "{pct}% remaining",
        "fmt.refills": "Refills in {dur}",
        "fmt.burns": "Burns out in ~{dur}",
        "fmt.resets_at": "Resets at {time}",
        "fmt.pace": "Pace: {pace}x",
        "fmt.notify": "{label}: {pct}% remaining",
        "fmt.notify_title": "tokentray · {provider}",
        "fmt.reset_remind": "{label} resets in ~{mins}m ({time})",
        "fmt.summary": "{n} alerts ({providers})",
        "fmt.extra_usage": "{used} / {limit} {currency}",
        "fmt.plan": "{provider} ({plan})",
    },
    "ko": {
        # window labels
        "window.hours": "{n}시간",
        "window.hours_one": "{n}시간",
        "window.days": "{n}일",
        "window.days_one": "{n}일",
        "window.qualified": "{window} · {name}",
        "window.unknown": "한도",
        # field labels
        "label.remaining": "남음",
        "label.refills": "리셋까지",
        "label.burns": "소진 예상",
        "label.resets_at": "리셋 시각",
        "label.pace": "속도",
        "label.source": "소스",
        "label.extra_usage": "추가 사용량",
        "label.extra_off": "꺼짐",
        "label.credits": "Codex 크레딧",
        "label.credits_unlimited": "무제한",
        # menu
        "menu.open_panel": "상세 열기",
        "menu.refresh": "새로고침",
        "menu.pause_alerts": "알림 1시간 일시정지",
        "menu.resume_alerts": "알림 다시 켜기",
        "menu.test_alert": "알림 테스트",
        "menu.integration": "알림 연동 설정…",
        "menu.language": "언어",
        "menu.autostart": "로그인 시 시작",
        "menu.open_log": "로그 열기",
        "menu.quit": "종료",
        # statuses
        "status.no_data": "데이터 없음 — 사용 후 업데이트됩니다",
        "status.rate_limited": "요청 제한 — 잠시 후 다시 시도",
        "status.not_configured_claude": "Claude Code 미로그인",
        "status.not_configured_codex": "Codex 미로그인",
        "status.expired_claude": "Claude Code 로그인이 만료됐어요 — 터미널에서 'claude' 실행",
        "status.expired_codex": "Codex 로그인이 만료됐어요 — 터미널에서 'codex' 실행",
        "status.schema_changed": "API 응답 형식이 바뀐 것 같아요 — 이슈로 알려주세요",
        "status.api_error": "API 오류",
        "status.window_reset": "창 리셋됨 — 새 데이터 대기 중",
        "status.live": "실시간",
        "status.cached": "캐시",
        "status.stale": "오래된 데이터",
        # notifications
        "notify.summary_title": "사용량 경고",
        "notify.info_title": "tokentray",
        "welcome.title": "tokentray가 실행 중입니다",
        "welcome.body": "시스템 트레이에서 백그라운드로 동작해요 — 아이콘을 클릭하면 상세를 볼 수 있어요.",
        "welcome.ack": "알겠어요",
        "welcome.tray_settings": "트레이 설정 열기",
        "welcome.menu_bar_manager": "Bartender, Ice, Hidden Bar 같은 메뉴 막대 관리 "
                                    "앱을 쓰고 있다면 거기서 tokentray를 보이도록 "
                                    "설정해야 할 수 있어요.",
        "test.body": "알림이 정상 동작합니다. 실제 알림은 이런 모습이에요.",
        "test.claude_body": "5시간 세션: 62% 남음",
        "test.codex_body": "Codex 7일: 38% 남음",
        # integration settings
        "integration.title": "알림 연동 설정",
        "integration.intro": "tokentray 알림을 Slack, Discord, ntfy 또는 일반 웹훅 한 곳으로 보냅니다.",
        "integration.enabled": "이 목적지로 알림 보내기",
        "integration.service": "서비스",
        "integration.url": "웹훅 URL",
        "integration.saved_url": "안전하게 저장됨 — 유지하려면 비워 두세요",
        "integration.steps.slack": "<ol><li><a href=\"{url}\">Slack 수신 웹훅</a> 페이지를 열고 워크스페이스에 쓸 앱을 만들거나 고릅니다.</li><li><b>Incoming Webhooks</b>를 켜고 <b>Add New Webhook to Workspace</b>에서 채널을 선택합니다.</li><li>웹훅 URL을 복사해 위에 붙여넣습니다.</li><li>같은 앱의 <b>Basic Information</b>에서 tokentray 아이콘을 지정하면 알림을 알아보기 쉽습니다.</li></ol>",
        "integration.steps.discord": "<ol><li>보낼 서버에서 <b>서버 설정</b> → <b>연동</b> → <b>웹후크</b>를 엽니다.</li><li><b>새 웹후크</b>를 만들고 채널을 고른 뒤 이름을 tokentray로 합니다.</li><li><b>웹후크 URL 복사</b>를 눌러 위에 붙여넣습니다.</li><li>같은 화면에서 아바타도 지정할 수 있습니다. <a href=\"{url}\">Discord 안내</a></li></ol>",
        "integration.steps.ntfy": "<ol><li>추측하기 어려운 토픽 이름을 정합니다 — 이름을 아는 사람은 누구나 알림을 볼 수 있습니다.</li><li>ntfy 앱이나 ntfy.sh에서 그 토픽을 구독합니다.</li><li>토픽 URL을 위에 붙여넣습니다. <a href=\"{url}\">발행 문서</a></li></ol>",
        "integration.steps.generic": "<ol><li>JSON POST를 받는 HTTPS 엔드포인트면 무엇이든 됩니다.</li><li>알림 하나가 제목, 본문, 남은 비율을 담은 요청 하나로 전달됩니다.</li></ol>",
        "integration.url_shape": "형식: {shape}",
        "integration.test": "테스트 전송",
        "integration.save": "저장",
        "integration.testing": "테스트 알림을 보내는 중…",
        "integration.saving": "안전하게 저장하는 중…",
        "integration.test_ok": "테스트 알림을 보냈습니다.",
        "integration.test_failed": "테스트 실패: {reason}",
        "integration.error": "설정을 적용하지 못했습니다: {reason}",
        "integration.url_required": "웹훅 URL을 먼저 입력하세요.",
        # formats
        "fmt.remaining": "{pct}% 남음",
        "fmt.refills": "리셋까지 {dur}",
        "fmt.burns": "소진 예상 ~{dur}",
        "fmt.resets_at": "리셋 시각: {time}",
        "fmt.pace": "속도: {pace}x",
        "fmt.notify": "{label}: {pct}% 남음",
        "fmt.notify_title": "tokentray · {provider}",
        "fmt.reset_remind": "{label} ~{mins}분 후 리셋 ({time})",
        "fmt.summary": "알림 {n}건 ({providers})",
        "fmt.extra_usage": "{used} / {limit} {currency}",
        "fmt.plan": "{provider} ({plan})",
    },
}

_PLACEHOLDER = re.compile(r"\{(\w+)")

_current = DEFAULT_LANGUAGE


def available_languages() -> list[tuple[str, str]]:
    return [(code, LANGUAGE_NAMES[code]) for code in STRINGS]


def normalize(language: str | None) -> str:
    """Map anything locale-ish (``ko_KR``, ``ko-KR.UTF-8``) onto a known code."""
    if not language:
        return DEFAULT_LANGUAGE
    base = re.split(r"[_\-.]", language.strip())[0].lower()
    return base if base in STRINGS else DEFAULT_LANGUAGE


def set_language(language: str | None) -> str:
    global _current
    _current = normalize(language)
    return _current


def current_language() -> str:
    return _current


def t(key: str, **kwargs: object) -> str:
    """Look up ``key``, falling back to English and then to the key itself.

    A missing key must never raise in the UI thread, so this degrades instead.
    """
    table = STRINGS.get(_current, {})
    text = table.get(key) or STRINGS[DEFAULT_LANGUAGE].get(key)
    if text is None:
        return key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def placeholders(text: str) -> set[str]:
    """Format field names used in ``text`` — used by the parity test."""
    return set(_PLACEHOLDER.findall(text))


def keys() -> Iterable[str]:
    return STRINGS[DEFAULT_LANGUAGE].keys()
