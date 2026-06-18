"""Tests for hosted app URL resolution."""

from __future__ import annotations

from band.config import LOCAL_HOSTED_APP_URL, Settings, get_health_path, get_hosted_app_url


def test_get_hosted_app_url_defaults_local():
    settings = Settings(hosted_app_url="")
    assert get_hosted_app_url(settings) == LOCAL_HOSTED_APP_URL


def test_get_hosted_app_url_from_env():
    settings = Settings(hosted_app_url="https://band-of-agents-demo.vercel.app")
    assert get_hosted_app_url(settings) == "https://band-of-agents-demo.vercel.app"


def test_get_hosted_app_url_adds_scheme():
    settings = Settings(hosted_app_url="localhost:3000")
    assert get_hosted_app_url(settings) == "http://localhost:3000"


def test_get_hosted_app_url_strips_trailing_slash():
    settings = Settings(hosted_app_url="https://example.com/")
    assert get_hosted_app_url(settings) == "https://example.com"


def test_get_health_path_local_uses_dynamic_route():
    settings = Settings(hosted_app_url="http://localhost:3000")
    assert get_health_path(settings) == "/api/health"


def test_get_health_path_hosted_uses_static_json():
    settings = Settings(hosted_app_url="https://ajitesh-jam.github.io/band-of-agents-demo")
    assert get_health_path(settings) == "/api/health.json"
