# 🎬 YouTube AI 幽默經理 (YouTube AI Manager)

一個集成了 **Google YouTube Data API v3** 與 **Gemini 2.5 Flash** 的自動化頻道行銷與優化 CLI 工具。

## ✨ 核心功能
1. 🔑 **OAuth 2.0 憑證授權與快取**：首次登入後，自動將存取權杖快取於 `token.json`，後續執行完全免人工干預（自動刷新 Token）。
2. 🤖 **Gemini AI 搞笑重塑**：
   - 自動將日常或單調的標題與描述，重塑為極具點閱吸引力的**吐槽/搞笑風格**新標題與描述。
   - 自動在影片描述結尾生成並附帶至少 3 個精準的**搞笑時間軸分段 (Timestamps)**。
3. 📺 **頻道影片快速盤點**：一行指令列出頻道中最新上傳的 10 部影片（含 ID、標題、上傳時間）。
4. 📁 **播放清單智能分類**：列出頻道所有播放清單，或一鍵將已處理的影片歸類。
5. 🔤 **搞笑字幕自動上傳**：支援將編寫好的搞笑/吐槽 SRT/VTT 字幕直接透過 API 上傳至 YouTube 影片。

---

## 🚀 快速開始指南

### 1. 安裝環境依賴
本專案已在您的 AgentOS 環境中完成了依賴安裝。如在其他環境部署，可執行：
```bash
pip install google-auth-oauthlib google-api-python-client google-generativeai tqdm
```

### 2. 獲取 Google API 憑證
因為本工具會「寫入/修改」您的 YouTube 影片，必須取得您個人的 Google API 授權：
1. 登入 [Google Cloud Console](https://console.cloud.google.com/) 並建立一個新專案。
2. 在 **API 程式庫** 中搜尋並啟用 **YouTube Data API v3**。
3. 前往 **OAuth 同意畫面**，配置為「測試」或「外部」，並將您個人的 Google 帳號加入「測試使用者」。
4. 前往 **憑證** 頁面，點擊「建立憑證」 -> **OAuth 用戶端 ID**（應用程式類型選擇「電腦應用程式」）。
5. 下載該憑證 JSON 檔案，重新命名為 `client_secret.json`，並放置於本專案目錄下：
   `/home/ubuntu/agentmanager/workspace/youtube-ai-manager/client_secret.json`

### 3. 一行指令執行

#### 🔑 A. 登入與授權
執行以下指令進行帳號授權連結：
```bash
python3 youtube_ai_manager.py login
```
* **Headless 遠端主機說明**：執行時控制台會輸出一個 OAuth 授權 URL，請複製該 URL 在您的瀏覽器打開，完成登入並點擊允許。
* 瀏覽器隨後會重新導向至 `localhost:xxxx` 並顯示連線失敗（此為正常現象，因為遠端 VM 無桌面環境）。**請直接複製瀏覽器地址列的整段 URL（包含 `code=` 與 `state=` 等參數），粘貼回控制台按 Enter** 即可完成認證！

#### 📺 B. 盤點最新上傳影片
列出您的頻道最新 10 部影片的 ID：
```bash
python3 youtube_ai_manager.py list
```

#### 🤖 C. 自動優化與搞笑大改造
將指定的影片 ID 丟給 AI 進行重寫與時間軸生成：
```bash
python3 youtube_ai_manager.py process YOUR_VIDEO_ID
```
* 執行後，AI 會立刻在控制台展示「新標題」與「含時間軸的新描述」預覽。
* 輸入 `y` 確認後，即可一鍵將變更同步上傳至 YouTube！
* 加上 `-y` 參數可跳過確認進行自動化排程更新：
  ```bash
  python3 youtube_ai_manager.py process YOUR_VIDEO_ID -y
  ```

#### 📁 D. 播放清單管理
查看所有播放清單：
```bash
python3 youtube_ai_manager.py playlists
```
建立新的播放清單：
```bash
python3 youtube_ai_manager.py playlists --create "石虎搞笑精選"
```

#### 🔤 E. 搞笑字幕上傳
上傳 SRT 或 VTT 字幕：
```bash
python3 youtube_ai_manager.py caption YOUR_VIDEO_ID subtitle.srt --name "繁體中文 (AI 搞笑版)"
```

---

## ⚙️ 系統變數
本工具會自動載入 `/home/ubuntu/agentmanager/.env` 中的 `GEMINI_API_KEY` 進行 AI 生成，無需額外手動輸入 API 金鑰，實現完美無縫整合！

---

## 🔍 常見問題與排錯 (Troubleshooting)

### ❌ 錯誤 403：access_denied
如果您在瀏覽器登入授權時遇到 **「錯誤 403：access_denied」**（如下圖所示提示）：
```text
錯誤 403：access_denied
要求詳情：access_type=offline scope=https://www.googleapis.com/auth/youtube.force-ssl ...
```
#### 💡 原因分析
因為您的 Google Cloud 專案目前的「發布狀態」為 **「測試中 (Testing)」**，Google 為了安全起見，**只允許被明確加入「測試使用者名單」的 Gmail 帳號進行登入與授權**。如果您使用的登入帳號未被加入，Google 就會直接阻擋並報 403 錯誤。

#### 🛠️ 解決步驟
1. 登入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 確保左上角選中了您的專案（例如：`youtubeaimanager-496906`）。
3. 點擊左側選單的 **「API 和服務」 (APIs & Services)** ➡️ **「OAuth 同意畫面」 (OAuth consent screen)**。
4. 滾動頁面至下方的 **「測試使用者」 (Test users)** 區塊。
5. 點擊 **「+ ADD USERS」 (新增使用者)** 按鈕。
6. 輸入您**用來登入 YouTube 頻道的那個 Gmail 帳號**。
7. 點擊 **「儲存」 (Save)**。
8. 回到終端機，重新執行 `python3 youtube_ai_manager.py login`，再次在瀏覽器中打開 URL 登入即可成功通過！

### ❌ 瀏覽器顯示「無法連上這個網站 / localhost 的回應時間過長」
當您在本地瀏覽器點擊「允許」後，瀏覽器會重新導向至 `http://localhost:8090/?code=...` 並顯示 **「無法連上這個網站」**。

#### 💡 原因分析
因為 Python 腳本是在**遠端 VM 虛擬機**上執行並監聽該埠口，而您的瀏覽器是在**您個人的本地電腦**上執行，所以瀏覽器嘗試連線您的本地 `localhost` 自然會超時失敗。

#### 🛠️ 解決步驟（有兩種超簡單的解決方案）：

##### 🎯 方案 A：使用 VS Code 自動埠口轉發 (最推薦 ⭐️)
如果您是使用 VS Code (或 Cursor) 透過 Remote-SSH 連線至遠端 VM：
1. 當您啟動 `login` 時，VS Code 會偵測到遠端開啟了 `8090` 埠口，並**自動在背景將您本地的 8090 轉發至遠端**！
2. 瀏覽器重新導向至 `http://localhost:8090/...` 時，將會**自動成功載入並完成認證**！您完全不需要做任何額外操作！
3. 如果沒有自動轉發，您可以手動在 VS Code 底部面板切換到 **「Ports (埠口)」** 標籤頁，點擊 **「Forward a Port」** 並輸入 `8090` 即可。

##### 🎯 方案 B：使用 `curl` 繞過限制
如果您使用的是普通 SSH 終端機：
1. **不要關閉**正在遠端終端機中執行等待的 `youtube_ai_manager.py login` 進程。
2. 在瀏覽器網址列中，**複製那段連線失敗的整段 URL**（它看起來像 `http://localhost:8090/?state=...&code=...&scope=...`）。
3. 在您的 VM 虛擬機中**打開第二個終端機視窗（或標籤頁）**。
4. 執行以下 `curl` 指令，將連線請求直接送給 VM 本地的 Python 服務：
   ```bash
   curl "將剛才複製的整段URL粘貼到這裡"
   ```
   *注意：請務必用雙引號 `""` 將 URL 包起來，避免裡面的 `&` 符號被 Bash 解析為背景執行。*
5. 執行後，第一個終端機的 Python 腳本將立刻收到授權訊號，並印出 `Saved authenticated credentials to token.json` 圓滿完成認證！



