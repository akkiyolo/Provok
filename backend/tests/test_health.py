"""Health endpoints, as uptime monitors and CI probe them."""
from __future__ import annotations


async def test_health_answers_get_and_head(client) -> None:
    for path in ("/health", "/health/ready"):
        r = await client.get(path)
        assert r.status_code == 200, (path, r.text)
        # Monitors (and wait-on) often send HEAD; a 405 would read as "site down".
        r = await client.head(path)
        assert r.status_code == 200, path
    assert (await client.get("/health/ready")).json()["checks"]["database"] == "ok"


async def test_assetlinks_lists_the_android_app_when_configured(client, monkeypatch) -> None:
    from backend.app.core.config import get_settings
    r = await client.get("/.well-known/assetlinks.json")
    assert r.status_code == 200 and r.json() == []  # nothing configured: valid, empty statement list

    s = get_settings()
    monkeypatch.setattr(s, "android_package", "in.provok.app")
    monkeypatch.setattr(s, "android_cert_sha256", "aa:bb , CC:DD")
    body = (await client.get("/.well-known/assetlinks.json")).json()
    assert body == [{"relation": ["delegate_permission/common.handle_all_urls"],
                     "target": {"namespace": "android_app", "package_name": "in.provok.app",
                                "sha256_cert_fingerprints": ["AA:BB", "CC:DD"]}}]
