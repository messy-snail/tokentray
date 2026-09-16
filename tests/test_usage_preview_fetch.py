from unittest.mock import Mock

import pytest

from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status
from tokentray.notify.preview import collect_views, send_usage_preview


def test_fetch_closes_all_clients_even_if_first_raises(monkeypatch):
    first, second = Mock(), Mock()
    first.fetch.side_effect = RuntimeError("private detail")
    monkeypatch.setattr("tokentray.providers.build_providers", lambda *args: [first, second])
    hook = Mock()
    result = send_usage_preview(Config({}), hook)
    assert result.error == "RuntimeError"
    assert result.sent == 0
    first.close.assert_called_once()
    second.close.assert_called_once()
    hook.deliver.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
def test_fetch_respects_provider_enablement(monkeypatch, enabled):
    from tokentray import providers

    created = []

    class Provider:
        def __init__(self, config, cache):
            self.enabled = config.get("claude.enabled")
            self.fetch = Mock(return_value=Snapshot(provider="claude", status=Status.ERROR))
            self.close = Mock()
            created.append(self)

    monkeypatch.setattr(providers, "PROVIDER_CLASSES", (Provider,))
    views = collect_views(Config({"claude": {"enabled": enabled}}), force=True)
    assert len(views) == int(enabled)
    if enabled:
        created[0].fetch.assert_called_once_with(force=True)
        created[0].close.assert_called_once()
    else:
        created[0].fetch.assert_not_called()
