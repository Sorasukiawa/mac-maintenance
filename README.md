# mac-maintenance

[![Tests](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml/badge.svg)](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向 Codex 的 Mac 维护 Skill：盘点软硬件、核对更新、整理旧版应用，并为清理保存可复查的前后证据。

A macOS maintenance skill for Codex with read-only audits, exact-target cleanup previews, revalidation, and observed-result logs. Python standard library only. The helper scripts never install, delete, restart, or start services; the agent follows the user's scope and uses the appropriate maintenance tools. Skill instructions and detailed guides are in Chinese.

## 能做什么

| 能力 | 输出与边界 |
|---|---|
| 只读体检 | 系统、硬件、电池、应用、Homebrew 元数据及目录占用，输出 JSON 与中文报告 |
| 更新核对 | 指导代理核对官方来源、平台、架构、版本及项目兼容；未匹配项目保留为未确认 |
| 清理预览 | 对精确目标保存元数据快照，检查链接、保护项交叉、重叠路径、跨卷子挂载点与活动进程 |
| 执行前复查 | 识别预览后的文件/路径/偏好变化；不把元数据一致当成删除许可 |
| 结果日志 | 将动作声明与现场观察分开，区分原路径减少、记录的删除量与卷可用空间变化 |
| 个人规则 | 指定跳过更新的应用、厂商更新管理器与保护路径；当前明确指令优先 |

适合需要代理逐项判断、推进并留证的维护任务。它没有一键清空所有缓存的入口；官方更新器、卸载器、项目备份和必要的实际功能验证仍由维护流程完成。

## 安装到 Codex

把下面这段交给 Codex：

```text
使用 $skill-installer，从 https://github.com/Sorasukiawa/mac-maintenance 安装根目录的 mac-maintenance Skill。已有同名安装时先检查差异并保留我的个人配置。
```

也可以按当前 [Codex 本地 Skill 目录说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) 手动安装到用户目录：

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/Sorasukiawa/mac-maintenance.git "$HOME/.agents/skills/mac-maintenance"
```

`git clone` 遇到已存在的目录会停止。已有同名 Skill 时更新原安装，避免同时安装重复副本。Codex 通常会自动发现变更，未出现时重新启动。

调用示例：

```text
使用 $mac-maintenance，只读检查这台 Mac，列出可以更新和整理的项目。
```

```text
使用 $mac-maintenance，在已授权范围内完成更新、整理和清理；先排除我指定的应用。新版实际可用且没有适用依赖影响时可以删除旧版。
```

## 单独运行脚本

需要 macOS 和可用的 Python 3.10+，无需安装 Python 包。先确认 `python3 --version` 能正常运行；系统运行时被许可或权限阻挡时，使用已有可用运行时。

在仓库目录中：

```sh
mkdir -p work/maintenance
python3 scripts/audit.py --quick \
  --output work/maintenance/audit.json \
  --report work/maintenance/audit.md
```

需要系统在线更新查询时加 `--online`；需要外设、扩展、备份和服务详情时去掉 `--quick`。已有输出不覆盖，每次使用新的路径。部分检查失败会写入 `coverage_gaps`，不能只依据进程退出码认定全部检查通过。

精确清理流程：

```sh
python3 scripts/cleanup.py preview --targets work/maintenance/targets.json \
  --output work/maintenance/plan.json
python3 scripts/cleanup.py verify --plan work/maintenance/plan.json
# 由维护流程按已有授权、用途和活动证据执行具体动作。
python3 scripts/cleanup.py record --plan work/maintenance/plan.json \
  --results work/maintenance/results.json --log work/maintenance/actions.jsonl
```

`targets.json`、`results.json` 的完整格式与状态含义见 [脚本用法](references/script-usage.md)。`review` 需要维护判断，`unchanged` 不是写入锁，同卷移动不等于释放空间。助手能否执行某项动作还取决于所在环境的工具和权限。

## 配置自己的规则

公开默认配置没有应用排除或个人路径。把示例复制到被 Git 忽略的本地配置，再按需要修改：

```sh
cp -n config/preferences.example.json config/preferences.local.json
python3 scripts/audit.py --quick --preferences config/preferences.local.json
```

示例中的 `com.example.*` 是虚构 bundle ID，替换成实际读到的标识。相同任务的 `preview`、`verify` 使用同一份配置。将配置放在本地文件或任务目录中，可避免后续更新覆盖个人规则；不要把个人体检报告和操作日志提交到仓库。

## 验证与适用范围

```sh
python3 -m unittest discover -v -s tests
```

测试仅在临时 fixture 中创建、移动和删除文件，覆盖 plist 格式、权限错误、超时、链接与大小写别名、目标变化、旧版替代品、日志完整性及空间统计。macOS 专属与文件系统相关测试在不适用的环境中会明确跳过；Linux CI 只验证通用辅助逻辑，不代表支持 Linux 主机维护。

首个公开版本来自一次本机只读试运行及独立场景复核。软件/硬件组合的覆盖仍有限：完整硬件诊断、厂商固件适配、专业软件许可与工程兼容需要针对性证据。快照只读元数据，不是文件内容哈希、事务或删除后的恢复保证。日志包含本机路径和应用信息，分享时按需要删去个人内容。

## 贡献与许可

欢迎提交可复现的 Issue 或 PR，附 macOS/Python 版本、预期结果与经过脱敏的最小 fixture。涉及判断流程时说明具体触发场景，涉及脚本时补充对应测试。不要用真实工程库或用户缓存作为测试删除目标。

代码和文档以 [MIT License](LICENSE) 发布。

设计参考了 [mac-storage-cleaner](https://github.com/JubaKitiashvili/mac-storage-cleaner) 的预览/日志/测试组织方式，以及 [mac-performance-maintenance](https://github.com/rioriost/skills/tree/main/plugins/mac-performance-maintenance) 的分层盘点与覆盖缺口。本仓库脚本独立实现，没有引入这些项目的清理代码或删除规则。
