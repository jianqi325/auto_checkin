# Auto Checkin Framework v1

一个面向 Windows 桌面环境的自动签到框架（当前已接入 `fishc`）。

## 目标

- 稳定：避免重复触发、并发冲突、状态漂移
- 可排障：统一日志、状态文件、历史运行记录
- 多站点可扩展：框架层与站点层解耦（v1 使用静态注册表）

## 当前目录

```text
bbxy-auto-checkin/
├── app/
│   ├── main.py
│   ├── runner.py
│   ├── core/
│   ├── scheduler/
│   └── sites/
├── config/
│   ├── global.env.example
│   ├── global.env
│   ├── fishc.env.example
│   └── fishc.env
├── data/
│   ├── status/
│   ├── history/
│   ├── logs/
│   └── locks/
├── scripts/
│   ├── install.ps1
│   ├── uninstall.ps1
│   ├── run_now.ps1
│   └── doctor.ps1
├── install.bat
├── uninstall.bat
├── run_now.bat
└── doctor.bat
```

## 快速开始

1. 运行 `install.bat`
2. 编辑 `config/fishc.env`（Cookie 或账号密码）
3. 手动测试：`run_now.bat`
4. 健康检查：`doctor.bat`

## CLI

```powershell
python -m app.main run --site fishc
python -m app.main doctor --site fishc
python -m app.main install-task --site fishc
python -m app.main remove-task --site fishc
python -m app.main sync --site fishc
python -m app.main status
```

## 调度策略（Windows）

默认安装两个任务：

- `FISHC-Checkin-Daily`：每日固定时间运行（默认 09:05）
- `FISHC-Checkin-LogonFallback`：登录后延迟 10 分钟补签检查

补签任务只在以下条件满足时才会真正执行：

- 当前时间已经超过计划时间
- 当天尚未记录成功
- 当天尚未执行过补签自检（每天最多一次）

## 状态与历史

- 状态：`data/status/fishc.status.json`
- 历史：`data/history/fishc-runs.jsonl`
- 日志：`data/logs/app.log`

## 失败提醒

失败会在桌面生成：

- 标记文件：`checkin_failed_fishc.txt`
- 详情日志：`checkin_failures/fishc_yyyy-MM-dd.log`

同一天失败日志覆盖更新，不会无限新增。

## 说明

- v1 保持“可扩展但不过度设计”，后续新增站点只需实现 `app/sites/base.py` 接口并注册到 `registry.py`。
