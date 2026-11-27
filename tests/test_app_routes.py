"""Integration and unit tests for config generation and TrendPulse Flask routes."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")


def test_settings_typed_fields_and_legacy_get():
    import config

    s = config.Settings()
    assert isinstance(s.PORT, int)
    assert s.get("PORT") == s.PORT
    assert s.get("NON_EXISTENT_KEY_XYZ", "fallback") == "fallback"
    assert s.get("WEBHOOK_ENDPOINTS") == "[]"


def test_generate_config_outputs_pydantic_v2(tmp_path):
    import generate_config

    out_file = tmp_path / "generated_config.py"
    sample_env = tmp_path / ".env.example"
    sample_env.write_text("PORT=5000\nHOST=0.0.0.0\nSECRET_KEY=\n", encoding="utf-8")

    # Verify generator function/template uses ConfigDict instead of deprecated class Config
    src = Path(generate_config.__file__).read_text(encoding="utf-8")
    assert "ConfigDict" in src
    assert "class Config:" not in src


@pytest.fixture
def flask_client():
    os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
    import app as trendpulse_app

    trendpulse_app.app.config["TESTING"] = True
    trendpulse_app.SEARCH_CACHE.clear()
    trendpulse_app.API_CACHE.clear()
    with patch.object(trendpulse_app, "read_config_values", return_value={"ADMIN_API_KEY": ""}):
        with trendpulse_app.app.test_client() as client:
            yield client, trendpulse_app


def test_index_and_health_routes(flask_client):
    client, _ = flask_client

    resp_home = client.get("/")
    assert resp_home.status_code == 200
    assert b"Trend Pulse" in resp_home.data
    assert b"ensurePdfFontLoaded" in resp_home.data

    resp_health = client.get("/api/health")
    assert resp_health.status_code == 200
    data = resp_health.get_json()
    assert data["status"] == "ok"
    assert "report_engine_available" in data
    assert isinstance(data["uptime_seconds"], int)


def test_admin_auth_enforces_api_key_when_configured():
    os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
    import app as trendpulse_app

    trendpulse_app.app.config["TESTING"] = True
    with patch.object(
        trendpulse_app,
        "read_config_values",
        return_value={"ADMIN_API_KEY": "super-secret-admin"},
    ):
        with trendpulse_app.app.test_client() as client:
            unauth = client.get("/api/status")
            assert unauth.status_code == 401
            assert unauth.get_json()["success"] is False

            wrong = client.get("/api/status", headers={"X-API-Key": "wrong"})
            assert wrong.status_code == 401

            ok = client.get("/api/status", headers={"X-API-Key": "super-secret-admin"})
            assert ok.status_code == 200


def test_status_and_invalid_app_control(flask_client):
    client, _ = flask_client

    status_resp = client.get("/api/status")
    assert status_resp.status_code == 200
    status_json = status_resp.get_json()
    for key in ("insight", "media", "query", "report", "forum"):
        assert key in status_json

    bad_start = client.get("/api/start/nonexistent")
    assert bad_start.status_code == 400

    bad_stop = client.get("/api/stop/nonexistent")
    assert bad_stop.status_code == 400


def test_search_suggest_and_post_search(flask_client):
    client, trendpulse_app = flask_client

    suggest = client.get("/api/search/suggest?q=NV")
    assert suggest.status_code == 200
    assert "suggestions" in suggest.get_json()

    empty_search = client.post("/api/search", json={"query": ""})
    assert empty_search.status_code == 200
    assert empty_search.get_json()["success"] is False

    too_long = client.post("/api/search", json={"query": "x" * 501})
    assert too_long.status_code == 400

    mock_db_resp = MagicMock()
    mock_db_resp.results = [
        MagicMock(
            ticker="NVDA",
            asset_class="Equity",
            title_or_content="NVIDIA beats revenue expectations",
            source="yfinance",
            publish_time=None,
            engagement={"likes": 12},
            sentiment_score=0.8,
        )
    ]
    with patch("InsightEngine.tools.search.TrendPulseDB") as mock_db_cls, patch.object(
        trendpulse_app, "write_log_to_file"
    ):
        mock_db_cls.return_value.search_topic_globally.return_value = mock_db_resp
        resp = client.post(
            "/api/search",
            json={"query": "NVDA earnings", "engines": ["insight"]},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["results"]["insight"]["count"] == 1
        assert payload["results"]["insight"]["results"][0]["ticker"] == "NVDA"


def test_mem0_nexus_and_oracle_endpoints(flask_client, tmp_path):
    client, trendpulse_app = flask_client

    # /api/mem0/feed empty rejects 400; valid injects log entry
    bad_feed = client.post("/api/mem0/feed", json={"content": "   "})
    assert bad_feed.status_code == 400

    with patch.object(trendpulse_app, "write_log_to_file") as mock_log:
        ok_feed = client.post(
            "/api/mem0/feed",
            json={"content": "Fed hawkish surprise impacts growth multiples", "source": "Test"},
        )
        assert ok_feed.status_code == 200
        assert ok_feed.get_json()["success"] is True
        mock_log.assert_called_once()

    # /api/nexus/debate without speeches returns clean empty-state notice
    with patch.object(trendpulse_app, "get_recent_agent_speeches", return_value=[]):
        debate_resp = client.get("/api/nexus/debate")
        assert debate_resp.status_code == 200
        debate_json = debate_resp.get_json()
        assert "topic" in debate_json
        assert len(debate_json["debate"]) == 1

    # /api/oracle/paths with mocked yfinance Close MultiIndex/columns
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    close_df = pd.DataFrame(
        {
            "SPY": [500.0, 502.0, 505.0, 507.0, 510.0],
            "QQQ": [420.0, 422.0, 424.0, 426.0, 430.0],
            "TLT": [95.0, 94.5, 94.0, 93.8, 93.5],
        },
        index=dates,
    )
    mock_dl = pd.concat({"Close": close_df}, axis=1)
    with patch.object(trendpulse_app.yf, "download", return_value=mock_dl):
        paths_resp = client.get("/api/oracle/paths")
        assert paths_resp.status_code == 200
        tree = paths_resp.get_json()["treeData"]
        assert tree["name"] == "Market Singularity"
        assert len(tree["children"]) == 2
        total_prob = sum(int(c["probability"]) for c in tree["children"])
        assert total_prob == 100

    # /api/oracle/simulate with 60 days of Close prices
    sim_dates = pd.date_range("2025-01-01", periods=60, freq="D")
    sim_df = pd.DataFrame(
        {"Close": [500.0 + i * 0.5 for i in range(60)]},
        index=sim_dates,
    )
    with patch.object(trendpulse_app.yf, "download", return_value=sim_df):
        sim_resp = client.post("/api/oracle/simulate", json={"scenario": "AI Expansion"})
        assert sim_resp.status_code == 200
        sim_json = sim_resp.get_json()
        assert sim_json["success"] is True
        assert "total_return" in sim_json["metrics"]
