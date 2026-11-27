# Changelog

All notable changes to **Trend Pulse** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-27

### Added
- **Unified Flask Command Center (`app.py`):** Central orchestrator with WebSocket streaming, engine lifecycle management, runtime configuration UI, and interactive market analytics dashboards (`/geo`, `/heat`, `/mem0`, `/oracle`, `/nexus`, `/omnifeed`, `/swarm`, `/ta_matrix`, `/portfolio_optimizer`, `/anomaly_radar`, `/news_feed`, `/stress_matrix`).
- **Multi-Agent Research Engines:**
  - `InsightEngine`: Financial database analytics, technical indicators (`pandas-ta`), portfolio optimization & backtesting, and financial sentiment analysis.
  - `QueryEngine`: Iterative web and news intelligence via Tavily.
  - `MediaEngine`: Multimodal web and media intelligence via Bocha / Anspire.
  - `ForumEngine`: Event-driven inter-agent debate moderation using Redis Pub/Sub and `Mem0` contextual memory.
  - `ReportEngine`: Structured IR validation, chart/table validation & repair, and HTML/Markdown/PDF report rendering.
  - `MindSpider`: OHLCV market data ingestion (`yfinance`), daily market topic extraction, sentiment scoring, and SQLAlchemy persistence (`SQLite`, `PostgreSQL`, `MySQL`).
- **Deployment & CI/CD:** Docker (`Dockerfile`, `docker-compose.yml`), Kubernetes manifests (`k8s/`), GitHub Actions CI, Docker GHCR publishing, and automated GitHub Release workflow.
- **Open-Source Governance:** Standardized MIT License (`LICENSE`), `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `CITATION.cff`, and GitHub Sponsors / Buy Me a Coffee funding configuration.
