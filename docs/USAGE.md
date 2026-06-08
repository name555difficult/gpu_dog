# GPU Monitor 使用文档

本文档描述当前实现版本：本地 Dashboard 模式、SQLite 持久化、轻量数据保留、无邮件推送。

## 1. 功能概览

GPU Monitor 是一个单机 GPU 使用监控服务，适合多人共享的训练服务器。

当前已实现：

- 每 30 秒通过 `nvidia-smi` 采集 GPU 设备和 GPU 进程；
- 通过 `psutil` 将 PID 归因到 Linux 用户名；
- 将原始进程采样、GPU 快照、heartbeat、异常事件写入 SQLite；
- 提供 `http://127.0.0.1:8765` 本地 Dashboard；
- 提供当前状态、当天统计、日报、周报和健康检查 API；
- 自动生成日报/周报 JSON 缓存；
- 启动时补偿最近遗漏的日报/周报缓存；
- 每天执行轻量保留策略清理；
- 提供 systemd service 模板。

当前不做：

- QQ 邮件推送；
- 公网访问；
- 登录认证；
- 多服务器聚合；
- 秒级短任务审计。

## 2. 配置文件

默认配置位于项目根目录：

```bash
config.yaml
```

关键配置：

```yaml
app:
  server_name: "gpu-server"
  timezone: "Asia/Shanghai"

web:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  refresh_interval_seconds: 30

collector:
  backend: "nvidia-smi"
  sample_interval_seconds: 30
  active_memory_threshold_mb: 100
  command_timeout_seconds: 10
```

轻量数据保留策略：

```yaml
storage:
  cleanup:
    raw_retention_days: 3
    gpu_snapshot_retention_days: 3
    daily_cache_retention_days: 14
    weekly_cache_retention_weeks: 12
    error_log_retention_days: 7
    heartbeat_retention_days: 7
```

含义：

- 原始采样和 GPU 快照只保留 3 天；
- 日报 JSON 缓存保留 14 天；
- 周报 JSON 缓存保留 12 周；
- heartbeat 和异常日志保留 7 天。

用户别名可选配置：

```yaml
users:
  alias:
    wzb: "王志斌"
    unknown: "未知用户"
```

不配置别名时，Dashboard 直接展示 Linux 用户名。

## 3. 常用命令

初始化数据库：

```bash
python3 -m gpu_monitor.main --config config.yaml init-db
```

采集一次：

```bash
python3 -m gpu_monitor.main --config config.yaml collect-once
```

启动完整服务：

```bash
python3 -m gpu_monitor.main --config config.yaml run
```

查看数据库行数：

```bash
python3 -m gpu_monitor.main --config config.yaml status
```

生成指定日期日报缓存：

```bash
python3 -m gpu_monitor.main --config config.yaml generate-daily --date 2026-06-07 --force
```

生成指定自然周周报缓存：

```bash
python3 -m gpu_monitor.main --config config.yaml generate-weekly --date 2026-06-07 --force
```

执行一次清理：

```bash
python3 -m gpu_monitor.main --config config.yaml cleanup
```

修复因 PID 瞬时退出导致的历史 `unknown` 归因：

```bash
python3 -m gpu_monitor.main --config config.yaml repair-unknown-users --dry-run
python3 -m gpu_monitor.main --config config.yaml repair-unknown-users
python3 -m gpu_monitor.main --config config.yaml generate-daily --date YYYY-MM-DD --force
```

该命令只会修复“同一 PID 在其他采样点已经有明确 Linux 用户名”的记录。

运行测试：

```bash
python3 -m unittest discover -v
```

## 4. Dashboard 访问

服务启动后，服务器本机访问：

```text
http://127.0.0.1:8765
```

远程机器访问推荐使用 SSH 端口转发：

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

然后在本地浏览器打开：

```text
http://localhost:8765
```

页面：

- `/`：今日实时 Dashboard；
- `/day/YYYY-MM-DD`：指定日期日报；
- `/week/YYYY-MM-DD`：该日期所在自然周周报；
- `/health`：健康状态页面。

API：

- `/api/current`：最新 GPU 快照；
- `/api/today`：当天累计统计；
- `/api/day?date=YYYY-MM-DD`：指定日期统计；
- `/api/week?date=YYYY-MM-DD`：指定自然周统计；
- `/api/health`：数据库、采集、heartbeat 健康信息。

Dashboard smoke test：

```bash
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```

完整验收：

```bash
python3 scripts/acceptance_check.py --config config.yaml
```

## 5. 统计口径

用户归因：

```text
GPU PID -> psutil.Process(pid).username() -> Linux username
```

如果 PID 已退出或权限不足，用户记录为：

```text
unknown
```

活跃采样点：

```text
同一用户在同一 GPU 上的总显存 >= active_memory_threshold_mb
```

默认阈值是 100 MB。

平均显存：

```text
同一用户同一 GPU 的活跃采样点显存均值
```

峰值显存：

```text
同一用户同一 GPU 的活跃采样点显存最大值
```

同一用户同一 GPU 同一采样点有多个进程时，先求和，再计算均值和峰值。

使用时段合并：

```text
相邻活跃采样点间隔 <= 300 秒，合并为同一使用时段
```

使用时长估算：

```text
最后一个活跃采样点时间 + 采样间隔
```

短于采样间隔的 GPU 任务可能被漏记。

## 6. systemd 部署

仓库提供模板：

```bash
systemd/gpu-monitor.service
```

如果项目路径不是 `/mnt/ssd1t/gpu_dog`，先修改 service 文件中的：

```ini
WorkingDirectory=
ExecStart=
```

安装：

```bash
bash scripts/install_systemd.sh
```

脚本会执行 `systemd-analyze verify`、复制 service 文件、`daemon-reload`、`enable`、`restart` 和 `status`。

也可以手动安装：

```bash
sudo cp systemd/gpu-monitor.service /etc/systemd/system/gpu-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable gpu-monitor
sudo systemctl restart gpu-monitor
```

查看状态：

```bash
sudo systemctl status gpu-monitor
sudo journalctl -u gpu-monitor -f
```

重启：

```bash
sudo systemctl restart gpu-monitor
```

停止：

```bash
sudo systemctl stop gpu-monitor
```

## 7. 文件与数据

默认开发路径：

```text
SQLite: /mnt/ssd1t/gpu_dog/data/monitor.db
日报缓存: /mnt/ssd1t/gpu_dog/data/reports/daily/
周报缓存: /mnt/ssd1t/gpu_dog/data/reports/weekly/
日志: /mnt/ssd1t/gpu_dog/logs/gpu-monitor.log
```

`data/` 和 `logs/` 已被 `.gitignore` 排除，不会进入 Git。

## 8. 验收检查

基础采集：

```bash
python3 -m gpu_monitor.main --config config.yaml init-db
python3 -m gpu_monitor.main --config config.yaml collect-once
python3 -m gpu_monitor.main --config config.yaml status
```

统计缓存：

```bash
python3 -m gpu_monitor.main --config config.yaml generate-daily --force
python3 -m gpu_monitor.main --config config.yaml generate-weekly --force
```

服务和 Dashboard：

```bash
python3 -m gpu_monitor.main --config config.yaml run
python3 scripts/smoke_test_dashboard.py
```

测试：

```bash
python3 -m unittest discover -v
```

通过标准：

- `collect-once` 能写入 GPU 快照和进程样本；
- `/api/current` 能返回最新 GPU 状态；
- `/api/today` 能返回当天累计统计；
- `/day/YYYY-MM-DD` 和 `/week/YYYY-MM-DD` 返回 200；
- `unittest` 全部通过；
- systemd 启动后服务能自动恢复。

更详细的验收标准映射见 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 9. 故障排查

`nvidia-smi` 失败：

```bash
nvidia-smi
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv,noheader,nounits
```

如果在受限沙箱中运行，Python 子进程调用 `nvidia-smi` 可能无法访问 NVIDIA driver。systemd 真实部署通常不受该沙箱限制。

端口被占用：

```bash
ss -ltnp | grep 8765
```

修改 `config.yaml`：

```yaml
web:
  port: 8766
```

数据库路径无权限：

```bash
ls -ld /mnt/ssd1t/gpu_dog/data
```

确保运行用户可以写入 `storage.sqlite_path` 的父目录。

Dashboard 没有数据：

```bash
python3 -m gpu_monitor.main --config config.yaml collect-once
python3 -m gpu_monitor.main --config config.yaml status
```

如果 `gpu_device_snapshots` 和 `gpu_process_samples` 都是 0，先排查 `nvidia-smi` 和服务权限。
