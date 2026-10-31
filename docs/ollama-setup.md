# Ollama Setup and Benchmark Guide

Guide for setting up, configuring, and benchmarking Ollama for the Agentic GRC interview agent.

## 1. What runs where

Ollama runs locally on the same machine that runs the backend for the demo.
The agent and backend communicate with Ollama over HTTP at `AGRC_OLLAMA_HOST` (default: `http://127.0.0.1:11434`).
In accordance with our data governance policy and Architecture Decision Record (0002), all inference is performed on-device: **no assessment data ever leaves the machine**.

## 2. Installation

### Windows
1. Download the Windows installer from [ollama.com](https://ollama.com).
2. Run the installer. Ollama will start and run in the background (visible in the system tray).
3. Open `cmd` or PowerShell and pull the default model:
   ```cmd
   ollama pull llama3.1:8b
   ```
4. Verify that Ollama is running and the model is available:
   ```cmd
   ollama list
   curl http://127.0.0.1:11434/api/tags
   ```
   In PowerShell, type `curl.exe` instead of `curl` (in Windows PowerShell, `curl` is an alias for `Invoke-WebRequest`).

### macOS
1. Download the macOS application from [ollama.com](https://ollama.com) or install via Homebrew:
   ```bash
   brew install ollama
   ```
2. Start Ollama and pull the default model. With the app, open Ollama from Applications. With Homebrew, start it as a background service first:
   ```bash
   brew services start ollama
   ollama pull llama3.1:8b
   ```
3. Verify that the model is ready:
   ```bash
   ollama list
   curl http://127.0.0.1:11434/api/tags
   ```

## 3. Settings

Every runtime setting can be configured in `backend/.env` (or via environment variables). The settings read by `backend/app/core/config.py` are:

| Variable | Default | Description |
|---|---|---|
| `AGRC_OLLAMA_HOST` | `http://127.0.0.1:11434` | Endpoint where Ollama listens for API requests. |
| `AGRC_LLM_MODEL` | `llama3.1:8b` | Ollama model identifier to use. |
| `AGRC_LLM_TIMEOUT_S` | `8` | Timeout per call in seconds (keeps the turn under the 10 s NFR). Set to `15` for the demo. |
| `AGRC_LLM_RETRIES` | `1` | Number of retries on malformed structured output. |
| `AGRC_LLM_KEEP_ALIVE` | `30m` | Duration to keep the model loaded in memory between turns. |
| `AGRC_LLM_NUM_PREDICT` | `320` | Maximum token cap for generated outputs to constrain latency (32 to 2048). |
| `AGRC_MAX_FOLLOW_UPS` | `3` | Maximum adaptive follow-up questions per control before closing (HU-06). |
| `AGRC_KB_PATH` | `None` (`backend/app/agent/data/kb_demo.yaml`) | Path to the YAML knowledge base file. |

## 4. Alpha demo checklist

- Run on the MacBook Air M4, never on a CPU-only laptop.
- In `backend/.env`, set `AGRC_LLM_TIMEOUT_S=15`, so a slow call (p95 ≈ 11 s) does not fall back to keywords.
- Run `ollama serve` (or open the Ollama app), then run `python -m app.cli warm-up-model` from `backend/` just before the demo.
- After running database migrations, run `python -m app.cli init-interview-checkpointer` once on the demo database.
- **Create a fresh assessment for every demo run.** A restarted session can get stuck (#28 review).
- Show draft results with the consultant account; representatives should not see them yet.
- Keep the laptop plugged in to AC power.

## 5. Benchmark

To measure accuracy and latency across multiple runs and record hardware metrics:

### Execution
Run the benchmark script from the `backend/` directory with the virtual environment activated:
```bash
cd backend
python scripts/benchmark_models.py llama3.1:8b --repeat 3 --machine "<name>"
```

### Reading the output
The script outputs:
- **Per-field accuracy**: Accuracy on `intent`, `category`, `specificity`, `mentions_evidence`, and resulting `action` against labelled evaluation cases (first run).
- **p50 / p95 per call**: Median and 95th percentile latency for individual model invocations.
- **p50 / p95 per turn**: Turn latency, including follow-up generation or clarification calls when triggered (evidence requests use zero-cost templates).
- **Turns over 10 s**: Count and percentage of turns exceeding the 10-second non-functional requirement (HU-05 NFR).
- **Cold load**: Initial model load time into memory in milliseconds.
- **Failed**: Count of invalid structured outputs or network errors.

The benchmark also outputs a Markdown row that can be pasted directly into the table below, and saves full results to `backend/evals/results/<timestamp>-<model>.json`.

### Results

| Date | Machine | Model | Prompt version | p50/p95 per call | p50/p95 per turn | Turns over 10 s | Cold load | Evaluation / Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 | HP laptop (CPU only) | llama3.1:8b | 0.3.0 (df6285e) | 22042 / 36075 ms | 34017 / 47654 ms | 24 (100%) | 24436 ms | not suitable |
| | MacBook Air M4 16GB | llama3.1:8b | 0.3.0 | | | | | (to be filled after demo Mac run) |

A shorter-output interpret prompt (0.4.0: word limits on `summary`, `key_quote` and `rationale`) was tried on 2026-10-24 and reverted, because action accuracy fell to 22/24. Both misses were MFA cases (`mfa-partial-detailed`, `mfa-followup-resolves-to-detailed`), and MFA is the first question of the demo. The alpha keeps the 0.3.0 prompt.

## 6. Troubleshooting

- **Connection refused (`ConnectionError` / `Failed to connect`)**:
  Ollama is not running. Start the Ollama application or service (`ollama serve`).
- **Model not found (`model 'llama3.1:8b' not found`)**:
  The model has not been downloaded yet. Run `ollama pull llama3.1:8b`.
- **Slow first turn**:
  The model was unloaded from memory. Run `python -m app.cli warm-up-model` before starting, and check that `AGRC_LLM_KEEP_ALIVE` is set (default: `30m`).
- **Every turn falls back to heuristic keyword matching**:
  The per-call timeout is too low for the hardware. Increase `AGRC_LLM_TIMEOUT_S` (e.g. `15`).
- **Every answer returns 409 after a restart**:
  Use a fresh assessment for every demo run. A restarted session can get stuck.
- **Security warning**:
  **Do not expose Ollama on `0.0.0.0`** or on a shared/public network. Ollama provides no authentication or authorization out of the box. Keep it bound to `localhost` (`127.0.0.1`).
