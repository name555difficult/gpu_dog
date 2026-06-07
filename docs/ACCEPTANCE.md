# GPU Monitor 验收标准与证据

本文档把项目计划中的验收标准映射到当前实现和可运行命令。

## 1. 一键验收

在项目根目录运行：

```bash
python3 scripts/acceptance_check.py --config config.yaml
```

该脚本会执行：

- Python 编译检查；
- `unittest` 单元测试；
- SQLite 初始化；
- 真实 GPU 单次采集；
- 日报缓存生成；
- 周报缓存生成；
- 轻量清理；
- 启动本地 Dashboard；
- 请求首页、静态资源和核心 API；
- 停止临时 Dashboard 服务。

如果所在环境限制 Python 子进程访问 NVIDIA driver，可以先运行不启动服务的部分：

```bash
python3 scripts/acceptance_check.py --config config.yaml --skip-service
```

## 2. 验收项映射

### 采集验收

- 服务启动后 30 秒内开始采集：`run` 启动后立即执行 collector loop，验收脚本检查 `/api/current` 有最新采样。
- 每 30 秒写入当前 GPU 使用状态：`collector.sample_interval_seconds` 控制，服务日志显示周期采集。
- 无 GPU 进程时不误报用户使用：Dashboard 当前用户为空时显示“当前无 GPU 使用”。
- 多用户同卡分别归因：日报分析按 `username + gpu_index + sample_time` 聚合。
- 同一用户多进程合并显存：`tests/test_daily_analyzer.py` 验证同采样点多进程先求和。

### Dashboard 验收

- 首页可访问：验收脚本请求 `/`。
- 当前 GPU 状态：验收脚本请求 `/api/current`，检查 `gpus`。
- 当前活跃用户和进程：`/api/current` 返回 `users` 和每个 GPU 的 `processes`。
- 页面 30 秒刷新：`web.refresh_interval_seconds` 注入页面，`app.js` 对今日页定时刷新。
- 采集异常摘要：`/api/current` 和 `/api/today` 返回最近错误。
- 无 GPU 使用提示：`app.js` 当前用户为空时显示“当前无 GPU 使用”。

### 日报验收

- `/day/YYYY-MM-DD` 可访问：验收脚本请求页面。
- `/api/day?date=YYYY-MM-DD` 返回日报 JSON。
- 日报按用户组织：`DailyAnalyzer._users_summary` 和 `user_gpu`。
- 用户维度包含 GPU、时段、时长、平均显存、峰值显存：`user_gpu` 字段。
- 监控中断区间：`heartbeat_gaps` 字段。
- 缓存缺失补算：`ReportCache.generate_daily` 缓存不存在时从 SQLite 生成。

### 周报验收

- `/week/YYYY-MM-DD` 可访问：验收脚本请求页面。
- `/api/week?date=YYYY-MM-DD` 返回自然周 JSON。
- 基于 7 天日报聚合：`ReportCache.generate_weekly` 调用 7 次 `generate_daily`。
- 用户维度和 GPU 维度统计：`WeeklyAnalyzer` 生成 `users` 和 `gpus`。
- 缺失/空日报标记：周报 `overview.missing_or_empty_dates`。
- 缓存缺失补生成：`ReportCache.generate_weekly` 缓存不存在时生成。

### 重启恢复验收

- systemd 模板：`systemd/gpu-monitor.service`。
- 重启前数据不丢失：SQLite 持久化到 `storage.sqlite_path`。
- 重启后继续采集：`run` 启动即初始化 DB、补偿缓存、启动 collector。
- 启动补偿：`SimpleScheduler.run_startup_compensation`。
- 中断区间显示：日报/今日统计包含 `heartbeat_gaps`。

## 3. 已验证命令

常规验证：

```bash
python3 -m compileall gpu_monitor tests scripts
python3 -m unittest discover -v
python3 -m gpu_monitor.main --config config.yaml init-db
python3 -m gpu_monitor.main --config config.yaml collect-once
python3 -m gpu_monitor.main --config config.yaml generate-daily --force
python3 -m gpu_monitor.main --config config.yaml generate-weekly --force
python3 -m gpu_monitor.main --config config.yaml cleanup
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```

完整验收：

```bash
python3 scripts/acceptance_check.py --config config.yaml
```
