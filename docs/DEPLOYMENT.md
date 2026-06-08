# GPU Monitor systemd 部署与端口转发访问教程

本文档用于把 GPU Monitor 部署为系统级 `systemd` 服务，并保持 Dashboard 只监听服务器本机 `127.0.0.1:8765`。远程用户通过 VSCode Remote SSH 或 SSH 端口转发访问，不直接开放 `服务器IP:8765`。

## 1. 部署目标

- 服务由 `systemd` 托管，开机自动启动，异常退出自动重启。
- Dashboard 只绑定 `127.0.0.1:8765`，不监听 `0.0.0.0`。
- 用户先远程连接服务器，再通过本地浏览器访问转发后的 `http://localhost:8765`。
- 不需要配置防火墙开放 `8765/tcp`。

## 2. 部署前检查

进入项目目录：

```bash
cd <project-root>
```

确认代码版本：

```bash
git log -3 --oneline
```

安装并确认 Python 依赖可用：

```bash
python3 -m pip install -r requirements.txt
python3 -c "import yaml, psutil; from gpu_monitor.utils.zoneinfo_compat import ZoneInfo; ZoneInfo('Asia/Shanghai'); print('python deps ok')"
```

如果服务器是 Python 3.8，`requirements.txt` 会自动安装 `backports.zoneinfo` 和 `tzdata`，用于补齐 Python 3.9 才内置的时区模块。

确认 NVIDIA 工具可用：

```bash
nvidia-smi
command -v nvidia-smi
```

确认项目命令能访问数据库：

```bash
python3 -m gpu_monitor.main --config config.yaml status
```

## 3. 确认 Dashboard 只监听 localhost

`config.yaml` 应保持如下配置：

```yaml
web:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  refresh_interval_seconds: 60
  max_issue_items: 5
```

不要改成：

```yaml
host: "0.0.0.0"
```

保持 `127.0.0.1` 后，服务器外部不能直接通过 `http://服务器IP:8765` 访问 Dashboard，只能通过端口转发访问。

## 4. 停止手动后台进程

如果之前用 `nohup`、`setsid` 或手动命令启动过服务，安装 systemd 前需要先停掉，避免端口冲突。

查看进程：

```bash
pgrep -af "gpu_monitor.main.*run"
```

如果看到类似：

```text
python3 -m gpu_monitor.main --config config.yaml run
```

停止它：

```bash
kill -TERM <PID>
```

如果进程不属于当前用户：

```bash
sudo kill -TERM <PID>
```

确认端口未被占用：

```bash
ss -ltnp | grep ':8765'
```

没有输出表示端口已空闲。

## 5. 安装 systemd 服务

项目提供了 systemd 模板：

```bash
systemd/gpu-monitor.service
```

模板中使用 `__PROJECT_DIR__` 占位符：

```ini
WorkingDirectory=__PROJECT_DIR__
ExecStart=/usr/bin/python3 -m gpu_monitor.main --config config.yaml run
```

安装脚本会把 `__PROJECT_DIR__` 自动渲染为当前项目的绝对路径。一般不需要手动修改 service 文件。

推荐使用安装脚本：

```bash
bash scripts/install_systemd.sh
```

脚本会执行：

```bash
sudo install -m 0644 <rendered-service> /etc/systemd/system/gpu-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable gpu-monitor.service
sudo systemctl restart gpu-monitor.service
sudo systemctl status gpu-monitor.service --no-pager
```

也可以手动安装：

```bash
PROJECT_DIR="$(pwd)"
sed "s#__PROJECT_DIR__#${PROJECT_DIR}#g" systemd/gpu-monitor.service > /tmp/gpu-monitor.service
sudo install -m 0644 /tmp/gpu-monitor.service /etc/systemd/system/gpu-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now gpu-monitor.service
```

## 6. 验证服务运行

查看服务状态：

```bash
sudo systemctl status gpu-monitor.service --no-pager
```

预期看到：

```text
active (running)
```

查看实时日志：

```bash
sudo journalctl -u gpu-monitor.service -f
```

本机验证 API：

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/current
```

检查监听地址：

```bash
ss -ltnp | grep ':8765'
```

预期应看到 `127.0.0.1:8765`。如果看到 `0.0.0.0:8765` 或 `*:8765`，说明 Dashboard 对外监听了，需要把 `config.yaml` 的 `web.host` 改回 `127.0.0.1` 并重启：

```bash
sudo systemctl restart gpu-monitor.service
```

## 7. VSCode 端口转发访问

用户先用 VSCode Remote SSH 连接服务器。

在 VSCode 中：

1. 打开底部或侧边栏的 `PORTS` 面板。
2. 点击 `Forward a Port`。
3. 输入远端端口：

```text
8765
```

4. VSCode 会把服务器的 `127.0.0.1:8765` 转发到本地。
5. 在本地浏览器打开：

```text
http://localhost:8765
```

如果本地 `8765` 已被占用，VSCode 可能会分配另一个本地端口，例如 `8766` 或 `18765`。此时以 VSCode Ports 面板显示的本地地址为准。

## 8. SSH 命令行端口转发访问

如果不用 VSCode，也可以使用 SSH：

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

保持该 SSH 连接打开，然后在本地浏览器访问：

```text
http://localhost:8765
```

如果本地端口 `8765` 已被占用，换成本地其他端口：

```bash
ssh -L 18765:127.0.0.1:8765 user@server
```

然后访问：

```text
http://localhost:18765
```

## 9. 不需要开放防火墙端口

本部署方式不直接提供 `http://服务器IP:8765`，因此一般不需要执行：

```bash
sudo ufw allow 8765/tcp
sudo firewall-cmd --permanent --add-port=8765/tcp
```

如果已经开放过该端口，可以考虑关闭。具体命令取决于服务器使用的防火墙工具。

`ufw` 示例：

```bash
sudo ufw delete allow 8765/tcp
sudo ufw reload
sudo ufw status
```

`firewalld` 示例：

```bash
sudo firewall-cmd --permanent --remove-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

## 10. 日常维护命令

重启：

```bash
sudo systemctl restart gpu-monitor.service
```

停止：

```bash
sudo systemctl stop gpu-monitor.service
```

启动：

```bash
sudo systemctl start gpu-monitor.service
```

禁用开机自启：

```bash
sudo systemctl disable gpu-monitor.service
```

重新启用开机自启：

```bash
sudo systemctl enable gpu-monitor.service
```

查看日志：

```bash
sudo journalctl -u gpu-monitor.service -n 100 --no-pager
sudo journalctl -u gpu-monitor.service -f
```

查看数据库状态：

```bash
python3 -m gpu_monitor.main --config config.yaml status
```

手动清理旧数据：

```bash
python3 -m gpu_monitor.main --config config.yaml cleanup
```

手动压缩 SQLite：

```bash
python3 -m gpu_monitor.main --config config.yaml compact-db
```

## 11. 最终验收

服务器本机执行：

```bash
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```

检查 systemd：

```bash
sudo systemctl is-enabled gpu-monitor.service
sudo systemctl is-active gpu-monitor.service
ss -ltnp | grep ':8765'
```

预期：

```text
enabled
active
127.0.0.1:8765
```

用户侧验证：

1. VSCode Remote SSH 连接服务器。
2. Ports 面板转发远端 `8765`。
3. 本地浏览器打开 `http://localhost:8765`。
4. 能看到 Today Dashboard、Health 页面、日报/周报页面。

## 12. 故障排查

服务启动失败：

```bash
sudo systemctl status gpu-monitor.service --no-pager
sudo journalctl -u gpu-monitor.service -n 100 --no-pager
```

跨服务器部署时遇到的 Python 3.8、systemd 环境、权限和验收脚本问题，见 [DEBUG.md](DEBUG.md)。

端口被占用：

```bash
ss -ltnp | grep ':8765'
pgrep -af "gpu_monitor.main.*run"
```

如果是旧手动进程占用，停止旧进程后重启 systemd：

```bash
sudo systemctl restart gpu-monitor.service
```

VSCode 无法访问：

- 确认服务器本机 `curl http://127.0.0.1:8765/api/health` 正常。
- 确认 VSCode Ports 面板已经转发远端端口 `8765`。
- 确认浏览器访问的是本地转发地址，例如 `http://localhost:8765`，不是 `http://服务器IP:8765`。
- 如果本地端口冲突，以 VSCode Ports 面板显示的本地端口为准。

`nvidia-smi` 失败：

```bash
nvidia-smi
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv,noheader,nounits
```

数据库或日志权限异常：

```bash
ls -ld .
ls -ld data logs
sudo journalctl -u gpu-monitor.service -n 100 --no-pager
```
