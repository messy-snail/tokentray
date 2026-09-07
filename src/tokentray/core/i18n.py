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
        "window.5h": "5-Hour Session",
        "window.7d": "7-Day Window",
        "window.7d_opus": "7-Day Opus",
        "window.7d_sonnet": "7-Day Sonnet",
        "window.codex": "Codex {window}",
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
        "notify.title": "Claude Code Usage Warning",
        "notify.reset_title": "Reset Reminder",
        "notify.summary_title": "Usage Warning",
        "notify.info_title": "tokentray",
        "welcome.title": "tokentray is running",
        "welcome.body": "It lives in your system tray — click the icon for details.",
        "welcome.ack": "Got it",
        "welcome.tray_settings": "Open tray settings",
        "test.body": "Notifications are working. This is what an alert looks like.",
        # formats
        "fmt.remaining": "{pct}% remaining",
        "fmt.refills": "Refills in {dur}",
        "fmt.burns": "Burns out in ~{dur}",
        "fmt.resets_at": "Resets at {time}",
        "fmt.pace": "Pace: {pace}x",
        "fmt.notify": "{label}: {pct}% remaining",
        "fmt.reset_remind": "{label} resets in ~{mins}m ({time})",
        "fmt.summary": "{n} windows crossed a threshold",
        "fmt.extra_usage": "{used} / {limit} {currency}",
        "fmt.plan": "{provider} ({plan})",
    },
    "ko": {
        # window labels
        "window.5h": "5시간 세션",
        "window.7d": "7일 윈도우",
        "window.7d_opus": "7일 Opus",
        "window.7d_sonnet": "7일 Sonnet",
        "window.codex": "Codex {window}",
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
        "notify.title": "Claude Code 사용량 경고",
        "notify.reset_title": "리셋 알림",
        "notify.summary_title": "사용량 경고",
        "notify.info_title": "tokentray",
        "welcome.title": "tokentray가 실행 중입니다",
        "welcome.body": "시스템 트레이에서 백그라운드로 동작해요 — 아이콘을 클릭하면 상세를 볼 수 있어요.",
        "welcome.ack": "알겠어요",
        "welcome.tray_settings": "트레이 설정 열기",
        "test.body": "알림이 정상 동작합니다. 실제 알림은 이런 모습이에요.",
        # formats
        "fmt.remaining": "{pct}% 남음",
        "fmt.refills": "리셋까지 {dur}",
        "fmt.burns": "소진 예상 ~{dur}",
        "fmt.resets_at": "리셋 시각: {time}",
        "fmt.pace": "속도: {pace}x",
        "fmt.notify": "{label}: {pct}% 남음",
        "fmt.reset_remind": "{label} ~{mins}분 후 리셋 ({time})",
        "fmt.summary": "{n}개 창이 임계값에 도달했어요",
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
