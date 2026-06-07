# GPU Monitor

Local GPU usage monitor for a shared server. The current implementation covers the phase 1 collector MVP:

- reads `config.yaml`
- initializes SQLite
- collects GPU device snapshots through `nvidia-smi`
- resolves GPU process owners through `psutil`
- writes process samples and heartbeat rows
- supports one-shot and long-running collection modes

## Quick Start

Initialize the database:

```bash
python3 -m gpu_monitor.main --config config.yaml init-db
```

Collect one sample:

```bash
python3 -m gpu_monitor.main --config config.yaml collect-once
```

Run the collector loop:

```bash
python3 -m gpu_monitor.main --config config.yaml run
```

Data and logs use the paths in `config.yaml`. The default development paths are:

- SQLite: `/mnt/ssd1t/gpu_dog/data/monitor.db`
- logs: `logs/gpu-monitor.log`
