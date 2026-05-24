# send_alert.py

**Layer:** Alerting  
**Runtime:** Databricks notebook (PySpark + Anthropic SDK)  
**Schedule:** Daily via Databricks Workflows, after `isolation_forest.py` completes

## Purpose

Reads the previous day's high-confidence anomalies from `gold.vessel_risk_scores`, generates a structured maritime intelligence brief using Claude, and delivers it by email to the designated recipient.

## What it does

### 1. Load anomalies
Queries `gold.vessel_risk_scores` for rows where:
- `is_outlier = true`
- `anomaly_score >= 0.7` (configurable via `SCORE_THRESHOLD`)
- `date(event_ts) = current_date() - 1` (yesterday's events)

Top 20 by score are taken. If the result set is empty, the script exits cleanly with no email sent.

### 2. Format context for Claude
Each anomaly row is serialised into a plain-text line (`anomaly_context_line`) containing vessel name, MMSI, anomaly type, score, coordinates, and any sanctions match. These lines form the user-turn prompt.

### 3. Call Claude (claude-sonnet-4-6)
Uses the Anthropic Python SDK with **prompt caching** on the system prompt (`cache_control: ephemeral`). The system prompt instructs Claude to act as a NATO maritime intelligence analyst and produce a three-section brief:

- **EXECUTIVE SUMMARY** — vessel count, dominant threat pattern, sanctions involvement
- **VESSEL-BY-VESSEL ASSESSMENT** — per-vessel analysis with a specific recommended operational action
- **THREAT LEVEL ASSESSMENT** — ROUTINE / ELEVATED / HIGH rating with one-sentence justification

Cache hits are logged (`cache_read_input_tokens`) to monitor cost efficiency across daily runs.

### 4. Send email
Builds both a `plain/text` and an `text/html` version of the brief. Sends via Gmail SMTP over SSL (port 465) using credentials from environment variables.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `ALERT_EMAIL_FROM` | Yes | Gmail sender address |
| `ALERT_EMAIL_PASSWORD` | Yes | Gmail app password |
| `ALERT_EMAIL_TO` | Yes | Recipient address |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SCORE_THRESHOLD` | `0.7` | Minimum `anomaly_score` to include in the brief |

## Dependencies

- PySpark / Databricks Runtime
- `anthropic` Python SDK
- Standard library: `smtplib`, `email`

## Notes

The system prompt is stable across runs and benefits from prompt caching — only the user-turn (the anomaly list) changes daily. At `max_tokens=1500` the brief fits comfortably in a single email. Raise the limit if the vessel count regularly exceeds 20.
