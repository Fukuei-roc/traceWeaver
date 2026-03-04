# Playwright 網路錄製工具（手動控制版）

一個可手動控制的瀏覽器網路錄製工具，用於 HTTP 重放與 AI 輔助除錯。

## 功能特色

- 🌐 **可見瀏覽器** - 非 headless 模式，方便手動操作
- 🎬 **手動錄製控制** - 可自由控制錄製開始與停止時機
- 📡 **網路請求錄製** - 僅記錄高價值請求（XHR、Fetch）
- 📦 **豐富除錯構件** - HAR、Trace、Console、截圖、DOM 快照
- 🏷️ **標記功能** - 可在錄製過程中標註重要動作
- 💾 **狀態儲存** - 自動儲存瀏覽器 storage state

## 安裝需求

```bash
# 安裝 Playwright
pip install playwright

# 安裝瀏覽器
playwright install
```

## 使用方式

```bash
# 啟動工具
python advanced_record_manual.py
```

### CLI 命令

| 命令 | 說明 |
|------|------|
| `start` | 開始錄製網路請求 |
| `stop` | 停止錄製並擷取構件 |
| `save` | 立即儲存 storage state |
| `mark <訊息>` | 新建時間戳記標記 |
| `quit` | 儲存所有資料並退出 |

### 使用範例

```bash
> start           # 開始錄製
> mark 登入按鈕點擊
> mark 填入帳號密碼
> stop            # 停止錄製
> save            # 儲存狀態
> quit            # 退出
```

## 輸出結構

所有構件儲存於 `artifacts/run_{timestamp}/` 目錄：

```
artifacts/run_20240301_120000_abc123/
  run_meta.json           # 執行元數據
  network_log.jsonl       # 網路請求記錄（XHR/Fetch）
  console.jsonl           # Console 訊息
  pageerror.jsonl         # 頁面錯誤
  requestfailed.jsonl     # 失敗的請求
  storage_state.json      # 瀏覽器狀態
  trace.zip               # Playwright Trace
  trace.har               # HAR 檔案
  screenshots/
    initial.png           # 初始截圖
    start.png             # 錄製開始截圖
    stop.png              # 錄製停止截圖
    error.png             # 錯誤截圖
  dom/
    page.html             # DOM 快照
```

## 記錄的資料

### 1. 網路請求（network_log.jsonl）

記錄 XHR 和 Fetch 請求的完整資訊：

```json
{
  "timestamp": "2024-03-01T12:00:00Z",
  "url": "https://api.example.com/users",
  "method": "POST",
  "resource_type": "xhr",
  "headers": {...},
  "post_data": "{\"name\":\"test\"}",
  "response": {
    "status": 200,
    "status_text": "OK",
    "headers": {...},
    "body": "{\"users\":[...]}"
  }
}
```

### 2. 元數據（run_meta.json）

包含執行環境資訊：

```json
{
  "timestamp": "2024-03-01T12:00:00Z",
  "run_id": "run_20240301_120000_abc123",
  "os": "Windows",
  "python_version": "3.11.0",
  "playwright_version": "1.42.0",
  "browser": "chromium",
  "browser_version": "122.0.6261.69",
  "viewport": {"width": 1280, "height": 720},
  "markers": [
    {"timestamp": "...", "message": "登入按鈕點擊"}
  ]
}
```

## AI 除錯優化

本工具專為 AI 輔助除錯設計：

- **認證/會話問題** - 可分析 storage_state.json 和 Cookie
- **CSRF/Token 行為** - 可追蹤請求 Headers 中的 Token
- **HTTP 重放** - 可從 network_log.jsonl 重放請求
- **網路順序重建** - JSONL 格式保留請求時間順序
- **錯誤原因追蹤** - 可從 pageerror.jsonl 和 console.jsonl 分析

## 常見用途

1. **錄製 API 操作** - 手動操作瀏覽器，錄製 API 請求
2. **重放測試** - 使用錄製的請求進行 HTTP 重放測試
3. **除錯分析** - 分析認證流程、Token 交換
4. **回歸測試** - 儲存正常操作的網路行為作為基準

## 依賴

- Python 3.8+
- Playwright

## 許可

MIT License
