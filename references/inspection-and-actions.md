# 检查与执行参考

按当前问题选择命令，不整段盲跑。以下是只读检查与命令形式；变量应由已观察到的精确目标赋值，并保持引用。先用本机 `--help`/man 核对版本支持。中间文件放任务的 `work/`，最终报告放该环境指定的输出目录。

## 系统、硬件和固件

```sh
sw_vers
uname -m
system_profiler -listDataTypes
system_profiler SPHardwareDataType SPPowerDataType SPNVMeDataType SPDisplaysDataType -detailLevel mini -json
softwareupdate --list
diskutil info /
diskutil apfs list
df -k /System/Volumes/Data
```

- 先查实际存在的数据类型。新系统可能提供 `SPUSBHostDataType`；`SPUSBDataType` 返回空时按列表改用受支持类型，不能推断无 USB 外设。按需要检查 Thunderbolt 与 Bluetooth 数据类型。
- 固件字符串和 SMART “Verified”只是读到的状态；不等于固件已是最新版、SSD 完整寿命正常或硬件压力测试通过。离线附件、需厂商 Windows 工具的升级，记录可核实范围与实际下一步。
- 不采用面向 Windows 的“万能驱动更新”思路。Apple 内置驱动/固件先查系统支持方式，第三方设备查精确型号官方说明。

## 应用和 plist

限定扫描 `/Applications`、用户 Applications 和本次要求的额外位置；使用 `rg --files` 或限深目录遍历，遇到 `.app` 后不再递归其内部寻找独立应用。跳过链接并记录异常；辅助程序、卸载器不重复算作独立常用软件。

```sh
plutil -lint "$maintenance_plist"
plutil -convert json -o - "$maintenance_plist"
plutil -extract CFBundleShortVersionString raw -o - "$maintenance_app/Contents/Info.plist"
plutil -extract CFBundleVersion raw -o - "$maintenance_app/Contents/Info.plist"
plutil -extract CFBundleIdentifier raw -o - "$maintenance_app/Contents/Info.plist"
codesign -dv --verbose=4 "$maintenance_app"
codesign --verify --deep --strict "$maintenance_app"
```

OpenStep/ASCII plist 可能被 Python `plistlib` 拒绝。先用系统 `plutil` 转换并把结果输出到 stdout；解析失败不证明配置损坏，避免原地转换。应用主二进制名读取 `CFBundleExecutable` 后再用 `file` 检查架构，不能从应用名称推断。`codesign -dv` 用于读签名身份，`--verify` 才执行签名验证；二者均需结合官方来源和实际安装结果。

安装来源可由 App Store receipt、应用内更新器、`SUFeedURL`、厂商安装器或包管理器记录交叉识别。App Store lookup 需要核对产品页面和 Mac 适用性；iPhone/iPad 产品版本不能证明 Mac 更新。Sparkle 除 shortVersion/build 外还需看 channel、系统最低/最高版本、架构、enclosure 和 rollout 条件；优先让应用官方更新器选择兼容项。

官网文章滞后时交叉检查官方发布 feed、下载页/更新器和发布说明。记录“当前官方可取得且匹配的版本”；不以搜索摘要或第三方下载站独立认定最新版本。

## 服务、驱动与连接

```sh
systemextensionsctl list
kmutil showloaded
launchctl print "system/$maintenance_label"
codesign -dv --verbose=4 "$maintenance_component"
lsof -nP -iTCP -sTCP:LISTEN
```

查看 LaunchAgent/LaunchDaemon 的 Label、Program/ProgramArguments、所属应用、可执行文件是否存在，再检查加载状态。未加载不能单独作为删除依据；Apple 签名组件、当前网络扩展、远程访问 helper 和许可服务需按实际用途判断。监听端口不证明公网可达。软件清理不自动授权调整防火墙、SIP、Gatekeeper 或远程设置。

## 备份与项目

```sh
tmutil status
tmutil destinationinfo
tmutil latestbackup
tmutil listlocalsnapshots /
```

查询备份成功还需确认相关项目包含在可访问目标中；“无法挂载”只能说明本次不能验证，不能断言从未备份。按专业软件支持方式导出/备份项目库；数据库使用其一致性备份方式，不能把运行中数据目录的随手复制当作可恢复备份。只有本次任务要求恢复演练或迁移风险需要时才扩大到完整恢复测试。

专业软件更新前检查项目库位置和插件兼容；涉及库格式变更先备份并明确回退方式。受保护备份目标需要用户解锁时，将该项记为等待用户，并继续普通独立事项。

## Homebrew

```sh
HOMEBREW_NO_AUTO_UPDATE=1 brew outdated --json=v2
brew services list
brew info --json=v2 "$maintenance_formula"
brew uses --installed --recursive "$maintenance_formula"
brew deps --tree --installed "$maintenance_formula"
brew cleanup -n "$maintenance_formula"
brew list --versions "$maintenance_formula"
```

只读模式区分本地包元数据与已在线核对的版本；需要时查询官方 formula API。执行模式先确认 brew 将连带处理的依赖和服务，再按精确 formula 更新。可在升级期间用 `HOMEBREW_NO_INSTALL_CLEANUP=1` 分开更新与清理阶段；它不阻止依赖更新。

数据库补丁与大版本迁移分开判断。读取新版本不等于运行中的服务已换新；核实可执行路径、服务器版本和重启要求。清理旧 keg 前检查活动进程是否仍使用它及回退需求。Xcode 许可报错由用户处理，不为清理自动执行许可接受命令。

## 目录占用与精确清理

```sh
du -x -k -d 1 "$maintenance_root"
du -xsk "$maintenance_target"
ls -ld "$maintenance_target"
lsof -nP +D "$maintenance_target"
df -k "$maintenance_root"
```

- 根路径和目标在调用前已验证；`-x` 限制跨文件系统，默认不跟随符号链接。大量目录先限深找重点，`lsof +D` 只用于精确候选，并限制执行时长。
- `du` 有权限错误/超时就标记不完整。`lsof` 的无匹配可能返回非零退出码，必须同时看 stderr；有遍历/权限错误不算完整的零句柄结果。活动进程暂时没有句柄也不能单独证明删除时不会再写入。
- 操作前记录 canonical path、所属卷、条目类型、数量、占用、修改时间、应用用途、句柄/进程、授权和预定操作；执行前再次核对。对大批条目保存精确 manifest，使用结构化路径参数，不把用户路径拼进可执行 shell 文本。
- 优先应用设置内的清理、包管理器预览和官方卸载器。手动清理限定在已证实可重建的精确内容，不跟随链接、不跨挂载点，不用全盘 `find -delete` 或全库缓存通配删除。
- 旧下载先从下载管理器核实任务和去留；历史会话按历史管理需求处理；模拟器通过所属设备与支持的工具/恢复方式核实。日期旧、名字包含 Cache/Temp 或设备 Shutdown 都不是充分依据。
- 清理若需同步更新应用任务记录，优先应用支持方式；直接修改数据库前备份、核实没有活动写入，只改与精确目标对应的行，随后检查数据库完整性和其他任务保留数量。
- 验证项目/设备身份使用稳定字段及关键数据目录。正常启动可能原子替换配置 plist，其 inode 改变不必然代表身份/数据损坏；结合 UUID、名称及内容判断。启动成功、数据目录保留、缓存实际重建分别记证据，不互相替代。
- `du` 表示目录统计，APFS clone/hardlink/快照、后台写入和 purgeable 会影响空间结果。嵌套目录不能重复相加；同卷移动不释放空间；分别报告目标减少与 `df` 实际变化。

## 工具链与交付记录

优先系统自带工具。确需脚本时先通过 `command -v` 检查运行时；系统 Python 不可用时，可以调用当前环境的依赖发现工具寻找可用 Python。不要把某台机器的缓存运行时绝对路径写入可复用脚本，也不为检查任务额外安装大套工具链。

执行记录一项一行：`对象 | 操作 | 授权/范围 | 前值与证据 | 结果/后值 | 验证方式 | 剩余动作/原因`。状态使用“已验证完成、无需处理、部分完成、等待用户、未确认”。未完成项说明具体缺失，例如“更新包已安装，进程仍运行旧版，等待已安排的重启”，避免笼统的“已更新”。
