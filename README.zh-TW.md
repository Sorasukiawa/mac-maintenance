# mac-maintenance

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

[![Tests](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml/badge.svg)](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

適用於 Codex 的 Mac 維護 Skill：盤點軟硬體、確認更新、評估舊版應用程式，並保存清理前後可供複查的證據。

輔助腳本僅使用 Python 標準函式庫蒐集證據；實際更新與清理由代理依使用者授權，透過適當的維護工具完成。腳本本身不會安裝、刪除、重新啟動或啟動服務。

**語言範圍：** 本介紹提供四種語言版本。Skill 指令、詳細參考文件及腳本產生的 Markdown 報告目前使用簡體中文；CLI 參數與 JSON 欄位名稱使用英文。

## 功能

| 能力 | 輸出與範圍 |
|---|---|
| 唯讀檢查 | 盤點系統、硬體、電池、應用程式、Homebrew 中繼資料與目錄用量，輸出 JSON 及中文 Markdown 報告 |
| 更新確認 | 引導代理核對官方來源、平台、架構、版本及專案相容性；無法確認適用性的項目保留為未確認 |
| 清理預覽 | 保存明確目標的中繼資料快照，檢查連結、受保護路徑交集、重疊目標、跨卷的子掛載點與所屬程序 |
| 執行前複查 | 偵測預覽後的檔案、路徑或偏好設定變更；中繼資料一致不代表獲准刪除 |
| 結果紀錄 | 區分操作者回報與實際觀察，分別記錄原路徑減少量、記為刪除的用量及卷宗可用空間變化 |
| 個人規則 | 指定不更新的應用程式、廠商更新管理器及受保護路徑；使用者當前的明確指令優先 |

適合需要代理逐項判斷、在授權範圍內執行並保留紀錄的維護工作。本工具沒有一鍵清空所有快取的指令；官方更新器、解除安裝工具、專案備份及必要的功能驗證仍屬於維護流程。

## 安裝至 Codex

將以下要求交給 Codex：

```text
使用 $skill-installer，從 https://github.com/Sorasukiawa/mac-maintenance 的根目錄安裝 mac-maintenance Skill。若已有同名安裝，請先檢查差異並保留我的個人設定。
```

也可以依目前的 [Codex 本機 Skill 目錄說明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)，手動安裝至使用者目錄：

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/Sorasukiawa/mac-maintenance.git "$HOME/.agents/skills/mac-maintenance"
```

若目的目錄非空，`git clone` 會停止。已有同名 Skill 時請更新原安裝，避免保留重複副本。Codex 通常會自動偵測變更；若未出現，請重新啟動。

使用範例：

```text
使用 $mac-maintenance，以唯讀方式檢查這台 Mac，列出可以更新與整理的項目。
```

```text
使用 $mac-maintenance，在已授權範圍內完成更新、整理與清理，排除我指定的應用程式。確認新版實際可用且不影響相關相依項目後，可以刪除舊版。
```

## 直接執行腳本

需要 macOS 及可正常運作的 Python 3.10+，無須安裝 Python 套件。請先確認 `python3 --version` 能成功執行；若系統執行環境受授權條款或權限要求限制，請使用其他現有可用環境。

在儲存庫目錄內執行：

```sh
mkdir -p work/maintenance
python3 scripts/audit.py --quick \
  --output work/maintenance/audit.json \
  --report work/maintenance/audit.md
```

加上 `--online` 可查詢可用的系統更新；移除 `--quick` 可取得周邊裝置、擴充功能、備份與服務詳細資料。既有輸出檔案不會被覆寫，每次請使用新路徑。部分檢查失敗會記錄於 `coverage_gaps`，不能只憑成功的結束代碼認定所有檢查都已通過。

明確清理目標的處理流程：

```sh
python3 scripts/cleanup.py preview --targets work/maintenance/targets.json \
  --output work/maintenance/plan.json
python3 scripts/cleanup.py verify --plan work/maintenance/plan.json
# 依既有授權，以及已核實的用途與活動狀態證據，執行具體維護動作。
python3 scripts/cleanup.py record --plan work/maintenance/plan.json \
  --results work/maintenance/results.json --log work/maintenance/actions.jsonl
```

`targets.json`、`results.json` 的完整格式與狀態定義請見[腳本使用說明](references/script-usage.md)。`review` 仍需要維護判斷，`unchanged` 不是寫入鎖定，同一卷宗內的移動不代表釋放磁碟空間。代理可執行哪些動作，也取決於所在環境的工具與權限。

## 設定個人規則

公開預設設定不包含應用程式排除項目或個人路徑。將範例複製到 Git 忽略的本機設定檔，再依需要調整：

```sh
cp -n config/preferences.example.json config/preferences.local.json
python3 scripts/audit.py --quick --preferences config/preferences.local.json
```

範例中的 `com.example.*` 為虛構 bundle ID，請替換為實際讀取到的識別碼。同一項工作的 `preview` 與 `verify` 應使用相同設定。將個人設定保留於本機檔案或工作目錄，可避免儲存庫更新時被覆寫；請勿將個人檢查報告或操作紀錄提交至儲存庫。

## 驗證與限制

```sh
python3 -m unittest discover -v -s tests
```

測試僅在暫存測試資料中建立、移動及刪除檔案，涵蓋 plist 格式、權限錯誤、逾時、連結與大小寫別名、目標變更、舊版替代品、紀錄完整性及空間統計。平台或檔案系統專屬測試在不適用時會明確略過。Linux CI 僅驗證共用輔助邏輯，不代表支援 Linux 主機維護。

首個公開版本曾在一台 Mac 上進行唯讀試行，並接受獨立情境複核。軟硬體組合的涵蓋範圍仍有限：完整硬體診斷、廠商韌體適用性、專業應用程式授權及專案相容性，皆需要個別取得證據。快照只記錄中繼資料，不是內容雜湊或交易，也不保證刪除後可復原。紀錄包含本機路徑與應用程式資訊，分享前請依需要移除個人內容。

## 貢獻與授權

歡迎提交可重現的 Issue 或 PR，附上 macOS/Python 版本、預期結果，以及已移除個人資料的最小測試案例。變更判斷流程時請說明具體觸發情境，變更腳本時請補上對應測試。請勿以真實專案資料庫或使用者快取作為測試刪除目標。

程式碼與文件採用 [MIT License](LICENSE) 發布。

設計參考了 [mac-storage-cleaner](https://github.com/JubaKitiashvili/mac-storage-cleaner) 的預覽、紀錄與測試組織方式，以及 [mac-performance-maintenance](https://github.com/rioriost/skills/tree/main/plugins/mac-performance-maintenance) 的分層盤點與涵蓋範圍缺口。本儲存庫的腳本為獨立實作，未引入這些專案的清理程式碼或刪除規則。
