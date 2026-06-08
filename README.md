# GPU Monitor

Local GPU usage monitor for a shared server. It collects GPU usage with `nvidia-smi`, persists data in SQLite, and serves a lightweight localhost Dashboard.

Implemented capabilities:

- continuous GPU process and device snapshot collection
- Linux username attribution through `psutil`
- SQLite persistence with heartbeat and error events
- localhost Dashboard at `http://127.0.0.1:8765`
- APIs for current state, today, day, week, and health
- daily and weekly JSON cache generation
- lightweight retention cleanup and SQLite compaction
- systemd service template
- standard-library `unittest` coverage

## Quick Start

Initialize the database:

```bash
python3 -m gpu_monitor.main --config config.yaml init-db
```

Collect one sample:

```bash
python3 -m gpu_monitor.main --config config.yaml collect-once
```

Run the full service:

```bash
python3 -m gpu_monitor.main --config config.yaml run
```

Compact SQLite storage manually:

```bash
python3 -m gpu_monitor.main --config config.yaml compact-db
```

Open the Dashboard on the server:

```text
http://127.0.0.1:8765
```

For remote access:

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

Then open:

```text
http://localhost:8765
```

Run tests:

```bash
python3 -m unittest discover -v
```

Run the full acceptance check:

```bash
python3 scripts/acceptance_check.py --config config.yaml
```

Data and logs use the paths in `config.yaml`. The default development paths are:

- SQLite: `/mnt/ssd1t/gpu_dog/data/monitor.db`
- logs: `logs/gpu-monitor.log`

Detailed documentation:

- [docs/USAGE.md](docs/USAGE.md)
- [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)
