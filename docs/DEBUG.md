# GPU Monitor Debug Notes

本文档汇总跨服务器部署和调试时遇到的关键问题。优先用于判断服务无法启动、Dashboard 无法访问、依赖缺失、权限异常和验收脚本失败的原因。

## 1. 先确认服务状态

服务由 systemd 托管时，先看 systemd 状态和最近日志：

```bash
sudo systemctl status gpu-monitor.service --no-pager
sudo journalctl -u gpu-monitor.service -n 100 --no-pager
```

如果服务不断重启，先停止服务再排查，避免日志持续刷屏：

```bash
sudo systemctl stop gpu-monitor.service
```

排查完成后再启动：

```bash
sudo systemctl restart gpu-monitor.service
```

## 2. Python 3.8 缺少 zoneinfo/backports

现象：

```text
ModuleNotFoundError: No module named 'zoneinfo'
ModuleNotFoundError: No module named 'backports'
```

原因：

- `zoneinfo` 是 Python 3.9 之后的标准库；
- Python 3.8 需要安装 `backports.zoneinfo` 和 `tzdata`；
- systemd service 当前使用 `/usr/bin/python3` 启动，看到的是 root/system Python 环境，不一定能看到普通用户 `pip install --user` 安装的包。

修复：

```bash
cd /data/root/gpu_dog
sudo -H /usr/bin/python3 -m pip install -r requirements.txt
```

如果没有 pip：

```bash
sudo apt update
sudo apt install -y python3-pip
sudo -H /usr/bin/python3 -m pip install -r requirements.txt
```

如果 `backports.zoneinfo` 编译失败：

```bash
sudo apt install -y build-essential python3-dev
sudo -H /usr/bin/python3 -m pip install -r requirements.txt
```

验证：

```bash
cd /data/root/gpu_dog
sudo -H /usr/bin/python3 -c "from gpu_monitor.utils.zoneinfo_compat import ZoneInfo; ZoneInfo('Asia/Shanghai'); print('deps ok')"
```

## 3. Python 3.8 不支持 removeprefix

现象：

```text
AttributeError: 'str' object has no attribute 'removeprefix'
```

该问题会导致 Dashboard 访问如下页面时返回 500：

```text
/day/YYYY-MM-DD
/week/YYYY-MM-DD
```

修复方式是拉取包含 Python 3.8 兼容修复的代码：

```bash
cd /data/root/gpu_dog
git pull
sudo systemctl restart gpu-monitor.service
```

验证：

```bash
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```

## 4. 已部署 systemd 后跑验收

如果服务已经由 systemd 占用 `8765`，完整验收脚本再启动一个临时服务时可能发生端口冲突。

推荐流程：

```bash
sudo systemctl stop gpu-monitor.service
python3 scripts/acceptance_check.py --config config.yaml
sudo systemctl restart gpu-monitor.service
```

如果只想验证当前已启动的 Dashboard：

```bash
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```

## 5. systemd-analyze verify 的宿主机警告

验收过程中可能看到类似宿主机其他服务的警告：

```text
netplan-ovs-cleanup.service: Failed to open ...
Failed to bind to varlink socket ...
snap-*.mount: Unit is bound to inactive unit ...
```

这些信息通常来自宿主机 systemd/snap/netplan 状态，不一定是 GPU Monitor service 文件错误。判断标准是：

- `systemd-analyze verify` 是否导致命令失败；
- 后续服务是否能启动；
- Dashboard smoke test 是否通过。

如果最终输出 `ACCEPTANCE OK`，通常可以忽略这些宿主机噪声。

## 6. 端口和访问方式

默认 Dashboard 只监听服务器本机：

```yaml
web:
  host: "127.0.0.1"
  port: 8765
```

检查监听地址：

```bash
ss -ltnp | grep ':8765'
```

预期看到：

```text
127.0.0.1:8765
```

远程访问时使用 VSCode Ports 面板或 SSH 端口转发：

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

然后在本地浏览器打开：

```text
http://localhost:8765
```

不要直接依赖 `http://服务器IP:8765`，当前部署目标不是开放公网或内网 IP 访问。

## 7. 二次部署和临时文件

`scripts/install_systemd.sh` 会用 `mktemp` 渲染临时 service 文件，并通过 `trap` 在脚本正常退出时删除临时文件。

正常二次运行脚本不会留下项目垃圾文件：

```bash
bash scripts/install_systemd.sh
```

如果机器断电或进程被强杀，可能在 `/tmp` 留下极少量临时文件。这类文件通常由操作系统的 `/tmp` 清理策略处理，不属于项目数据目录，也不会影响 GPU Monitor 运行。

## 8. 最小排查命令集合

部署目录：

```bash
cd /data/root/gpu_dog
```

依赖：

```bash
python3 --version
python3 -m pip install -r requirements.txt
python3 -c "import yaml, psutil; from gpu_monitor.utils.zoneinfo_compat import ZoneInfo; ZoneInfo('Asia/Shanghai'); print('deps ok')"
```

权限：

```bash
ls -ld .
ls -ld data logs 2>/dev/null
```

GPU：

```bash
nvidia-smi
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv,noheader,nounits
```

服务：

```bash
sudo systemctl status gpu-monitor.service --no-pager
sudo journalctl -u gpu-monitor.service -n 100 --no-pager
```

Dashboard：

```bash
curl http://127.0.0.1:8765/api/health
python3 scripts/smoke_test_dashboard.py --base-url http://127.0.0.1:8765
```
