# 维护脚本用法

这些脚本提供当前证据，不执行更新、卸载、删除、重启、服务启动或任意 shell 命令。运行需要 Python 3.10+ 和标准库；先确认可用运行时，系统 Python 受 Xcode 许可限制时通过当前环境的依赖发现工具定位已有运行时。不要为它们安装一套新工具链。

将 `maintenance_python` 指向已验证的 Python，`maintenance_skill` 指向本 Skill 目录。报告、计划和日志使用任务内的新路径；先创建 `work/maintenance/`。命令里的所有路径都必须按本次环境设置并保持引用。

## 1. 只读盘点

```sh
"$maintenance_python" "$maintenance_skill/scripts/audit.py" --quick \
  --output work/maintenance/audit.json --report work/maintenance/audit.md
```

- `--quick`：系统版本、硬件/电池/NVMe、内存/热状态、空间、应用、Homebrew 本地元数据与有限目录占用。
- 去掉 `--quick`：再查扩展、备份状态/最近备份、开发目录、Homebrew 服务和支持的 USB/Thunderbolt/显示器类型。
- `--online`：额外运行 `softwareupdate --list`，45 秒超时单独记录。不安装系统更新，也不切换更新通道。
- `--apps-only`：只读应用 plist，不运行系统体检命令；遇到 OpenStep plist 时可能调用系统 `plutil` 只读转换。`--app-root /absolute/path` 可重复；默认 `/Applications`、`~/Applications`，扫描深度 3、条目最多 10,000。遇到 `.app` 停止递归，读取 iOS 包装应用，跳过链接并记录覆盖缺口。
- `--storage-root /absolute/path` 可重复；默认只统计用户 Caches、Logs、Downloads，单目录命令限时 15 秒。统计可能重叠，不计算“可释放总量”。`du` 的任何错误都不记成零。
- `--preferences FILE` 使用本任务配置，便于落实当前指令且不改长期偏好。

JSON 始终输出到 stdout；`--output` 与 `--report` 额外创建权限 0600 的新文件，已有路径不覆盖。输出失败返回 2；体检部分超时、权限不足、工具缺失写入 `coverage_gaps`，报告仍可生成并返回 0，必须检查各项状态。

`checks` 保存命令、时间、退出码和有界输出。命令不经过 shell、不执行 `brew update`，Homebrew 自动刷新被禁用；其 outdated 结果依据本地元数据，不能称为全部软件已在线核对。系统命令/包管理器本身仍可能产生正常运行缓存。硬件 JSON 过滤序列号、UUID、UDID 和地址字段；日志含本机应用/路径信息，对外发送前仍需按分享范围审阅。

脚本不会穷尽登录项、活动远程连接、驱动适配、应用二进制架构/签名、工程兼容、外接卷、完整备份或厂商固件更新。按报告缺口和本次目标补查，不为“全绿”隐去缺口。不要启动未运行的 Docker/虚拟机只为盘点。

## 2. 精确目标预览

先确定用途、已有授权和可重建/去留证据，再写 `targets.json`。只列本次真正要操作的路径；清理目录内容时列具体内容，不顺手扩大到父目录。

```json
{
  "version": 1,
  "targets": [
    {
      "id": "cache-001",
      "path": "/absolute/exact/cache-content",
      "kind": "cache",
      "reason": "本次核实的用途和可重建依据；记录当前授权",
      "owner_processes": ["ExactExecutableName"]
    }
  ]
}
```

`kind` 可用 `cache`、`obsolete_app`、`installer`、`user_selected`；类别不是删除许可。进程名必须来自实际所属程序的可执行文件名，省略时明确为 `not_checked`。进程查询只读 `comm`，不收集可能含令牌的命令行参数；未观察到进程不能证明没有其他写入者，脚本不代替精确 `lsof`/应用状态检查。

```sh
"$maintenance_python" "$maintenance_skill/scripts/cleanup.py" preview \
  --targets work/maintenance/targets.json --output work/maintenance/plan.json
"$maintenance_python" "$maintenance_skill/scripts/cleanup.py" verify \
  --plan work/maintenance/plan.json --output work/maintenance/verification.json
```

两次调用应使用相同的 `--preferences`。预览保存偏好摘要、完整计划摘要和目录元数据指纹（路径/类型/inode/大小/mtime/ctime 等，不读取文件内容），并记录卷可用空间。仅扫描本卷，不跟随链接；根目标/祖先含符号链接、保护项交叉、重叠目标、特殊文件、跨卷子挂载点或不完整扫描不能通过。脚本不全面识别作为目标的卷根，目标类型、所属卷与是否为卷根仍须维护流程核实。保护项/重叠检查结合路径和设备/inode，覆盖大小写不敏感卷的路径别名。根路径从 `/` 开始逐级用不跟随链接的目录描述符打开，子目录同样处理，扫描结束再核对根路径；单目标默认 50,000 条/10 秒。内含 symlink 只记录链接本身，后续操作同样不能跟随它。

`preview` 即使有阻塞项仍返回 0，逐项看 `status`；任一阻塞或发现硬链接时总量为 `null`，避免跨目标重复计数。`review` 只表示技术快照可供审阅。`verify` 返回 0 表示所有项目和偏好复查一致，返回 2 表示变化、不完整、计划被改动或其他错误。更新证据后生成新预览，无需对已有授权重复审批。

快照不是锁、事务或内容哈希；它无法保证复查后目标不再变化，也不能证明重建能力、许可、项目兼容或没有打开句柄。真正操作前仍核对活动状态与精确路径，并按所属工具约束动作。不要手改计划让校验通过；摘要用于发现意外改动，不是抗篡改签名。

`obsolete_app` 额外需要：

```json
"replacement": {
  "path": "/Applications/Verified New Version.app",
  "running_verified": true,
  "dependencies_checked": true,
  "evidence": "实际启动/许可/关键功能的时间和结果；适用工程、插件、CLI、文件关联与共享组件检查"
}
```

脚本只验证同 bundle ID、严格数字版本递增、替代路径不重叠和替代品快照；两个布尔字段是操作者提供的证据声明，必须与实测相符。新版许可失败不能设为 true。复杂版本/不同 bundle ID 迁移需单独取得产品证据，不能改成虚构的数字版本规避检查。

## 3. 记录实际动作后的观察

动作由维护流程通过合适工具完成。随后写 `results.json`：

```json
{
  "version": 1,
  "results": [
    {"id": "cache-001", "action": "removed", "detail": "实际工具、完成时间与必要验证"}
  ]
}
```

```sh
"$maintenance_python" "$maintenance_skill/scripts/cleanup.py" record \
  --plan work/maintenance/plan.json --results work/maintenance/results.json \
  --log work/maintenance/actions.jsonl
```

支持 `removed`、`moved`（另需绝对 `destination`）、`manual`、`skipped`。只接收计划中已知且不重复的 ID；不把 `detail` 当命令执行。日志每次追加一条新观察，有独立 `event_id`；重复调用会追加而非覆盖，因此重试前先检查是否已写入。已有文件必须是本工具格式的 JSONL 日志，拒绝链接、特殊文件和非日志文件；日志被占用或超过 16 MiB 时选择新的任务日志。日志写入不代表所有动作成功，必须查看事件的 `observed_status`。

| 结果字段/状态 | 含义 |
|---|---|
| `observed_absent` | 原路径此刻不存在；不独立证明由哪项动作造成 |
| `still_present` | 声明已删除/移动，但原目标仍存在 |
| `moved_same_volume` | 原路径缺失，目标卷与 inode 匹配；目标删除量记 0 |
| `move_not_verified` / `observation_incomplete` | 证据不足、路径异常或扫描不完整 |
| `reported_only` | 仅记录手工操作/跳过声明，没有提升为验证完成 |
| `source_path_bytes_decrease` | 原路径的统计减少量，同卷移走也计入；不是释放量 |
| `target_bytes_removed` | 按动作及观察记录为删除的目标统计量，同卷移动为 0，未确认为 `null`；不等于物理释放 |
| `volume_available_delta_bytes` | 同设备的操作前后可用空间变化，可能混入后台活动 |
| `reclaimed_bytes` | 保持 `null`；不声称可归因的 APFS 物理释放量 |

## 4. 偏好与自检

`config/preferences.json` 是通用默认值：没有预设应用排除或指定厂商管理器；旧版删除检查要求新版已验证可用且适用依赖无影响，仍以当前用户授权为前提。参考 `config/preferences.example.json` 创建自己的任务配置，再用 `--preferences` 指向它；当前明确指令优先。

通过 Skill 调用时，代理优先使用存在的 `config/preferences.local.json`，并在脚本命令中显式加 `--preferences`。脚本本身不会自动检测 local 文件；直接运行 CLI 时也需传入它。更新仓库时保留这个被 Git 忽略的个人配置。

`protect_paths` 可补充当前明确需要保护的绝对路径；父子交叉都阻塞该候选。不要把未知用途目录永久加入禁令。要删除旧版时 `remove_old_versions_if_replacement_verified` 为 true 也不免除替代品验证。

```sh
"$maintenance_python" -m unittest discover -v -s "$maintenance_skill/tests"
```

测试文件的变更、移动和删除只发生在临时 fixture 中；不会清理这台 Mac。程序仅使用 Python 标准库，未复制或执行第三方清理代码。

设计参考：[mac-storage-cleaner](https://github.com/JubaKitiashvili/mac-storage-cleaner) 的预览/日志/测试组织方式，以及 [mac-performance-maintenance](https://github.com/rioriost/skills/tree/main/plugins/mac-performance-maintenance) 的分层只读盘点和覆盖缺口。保留本 Skill 的授权接续、专业软件与本机偏好；不导入社区脚本的广域删除规则。
