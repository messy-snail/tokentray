import httpx
import pytest
import respx

from tokentray.core.alerts import AlertEvent
from tokentray.notify.webhook import Webhook

URL = "https://discord.com/api/webhooks/123/test"


@pytest.mark.parametrize("provider", ["claude", "codex", None, "unknown"])
@pytest.mark.parametrize("retry", [False, True])
def test_text_and_card_delivery_without_images(provider, retry, monkeypatch, webhook_payload):
    monkeypatch.setattr("tokentray.notify.webhook.time.sleep", lambda _: None)
    responses = ([httpx.Response(429, json={"retry_after": 0})] if retry else []) + [httpx.Response(200)]
    with respx.mock:
        route = respx.post(URL).mock(side_effect=responses)
        result = Webhook(enabled=True, kind="discord", url=URL).deliver(
            AlertEvent(kind="info", key="test.usage", title="Usage", body="Current quota", provider=provider)
        )
    assert result.ok
    assert route.call_count == 1 + int(retry)
    for call in route.calls:
        request = call.request
        assert request.url.params["wait"] == "true"
        payload = webhook_payload(request)
        assert "Current quota" in payload["content"]
        assert "attachments" not in payload
        assert "avatar_url" not in payload
        embed = payload["embeds"][0]
        assert "icon_url" not in embed.get("author", {})
        assert "image" not in embed and "thumbnail" not in embed
        assert payload["allowed_mentions"] == {"parse": []}
