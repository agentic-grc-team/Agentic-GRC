# Ollama Setup and Benchmark Guide

Guide for setting up, configuring, and benchmarking Ollama for the Agentic GRC interview agent.

## 1. What runs where

Ollama runs locally on the same machine that runs the backend for the demo.
The agent and backend communicate with Ollama over HTTP at `AGRC_OLLAMA_HOST` (default: `http://localhost:11434`).
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
   curl http://localhost:11434/api/tags
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
   curl http://localhost:11434/api/tags
   ```

## 3. Settings

Every runtime setting can be configured via environment variables. The defaults defined in `agentic_grc_agent/config.py` are:

| Variable | Default | Description |
|---|---|---|
| `AGRC_OLLAMA_HOST` | `http://localhost:11434` | Endpoint where Ollama listens for API requests. |
| `AGRC_LLM_MODEL` | `llama3.1:8b` | Ollama model identifier to use. |
| `AGRC_LLM_TIMEOUT_S` | `8` | Timeout per call in seconds (keeps the turn under the 10 s NFR). |
| `AGRC_LLM_RETRIES` | `1` | Number of retries on malformed structured output. |
| `AGRC_LLM_KEEP_ALIVE` | `30m` | Duration to keep the model loaded in memory between turns. |
| `AGRC_LLM_NUM_PREDICT` | `320` | Maximum token cap for generated outputs to constrain latency. |
| `AGRC_MAX_FOLLOW_UPS` | `3` | Maximum adaptive follow-up questions per control before closing (HU-06). |
| `AGRC_KB_PATH` | `agentic_grc_agent/data/kb_demo.yaml` | Path to the YAML knowledge base file. |
| `AGRC_TRACE_DIR` | `traces` | Directory where JSONL audit traces are written. |

## 4. Before a demo

To ensure consistent and responsive performance during demonstrations:

1. **Start Ollama** and make sure the daemon is active.
2. **Warm up the model** by running a single question:
   ```bash
   python scripts/run_interview.py --only IAM-01
   ```
   (Type `/quit` to exit once loaded).
3. **Keep the machine plugged into AC power**: Laptop battery saving profiles throttle GPU and CPU clock speeds, which significantly increases token generation latency.

## 5. Benchmark

To measure accuracy and latency across multiple runs and record hardware metrics:

### Execution
Run the benchmark script:
```bash
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

The benchmark also outputs a Markdown row that can be pasted directly into the table below, and saves full results to `evals/results/<timestamp>-<model>.json`.

### Results

| Date | Machine | Model | Prompt version | p50/p95 per call | p50/p95 per turn | Turns over 10 s | Cold load |
|---|---|---|---|---|---|---|---|

*(Table left empty; to be filled after running benchmarks on the alpha machine).*

## 6. Troubleshooting

- **Connection refused (`ConnectionError` / `Failed to connect`)**:
  Ollama is not running. Start the Ollama application or service.
- **Model not found (`model 'llama3.1:8b' not found`)**:
  The model has not been downloaded yet. Run `ollama pull llama3.1:8b`.
- **Slow first turn**:
  The model was unloaded from memory. Run `llm.warm_up()` / `run_interview.py` before starting, and check that `AGRC_LLM_KEEP_ALIVE` is set (default: `30m`).
- **Every turn falls back to heuristic keyword matching**:
  The per-call timeout is too low for the hardware. Increase `AGRC_LLM_TIMEOUT_S`.
- **Security warning**:
  **Do not expose Ollama on `0.0.0.0`** or on a shared/public network. Ollama provides no authentication or authorization out of the box. Keep it bound to `localhost` (`127.0.0.1`).
