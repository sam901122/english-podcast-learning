# Daily podcast workflow bug 排查紀錄

這份文件記錄 2026-08-22 的兩個 GitHub Actions 問題，供後續維護者與 AI 排查相同症狀時參考。

## 系統流程

- `.github/workflows/daily-update.yml` 定時執行 `scripts/update_podcast.py`。
- 有新內容時，workflow 會更新 `site/data`，建立 commit 並 push 到預設分支。
- 網頁由 GitHub Pages 發布；`.github/workflows/pages.yml` 仍負責一般使用者 push 所觸發的部署。
- Daily workflow 現在會在同一次 run 裡上傳剛生成的 `site` artifact，再由 `deploy` job 直接發布 Pages。

## 問題一：第一次 daily run 失敗

### 症狀

- Run：<https://github.com/sam901122/english-podcast-learning/actions/runs/32533034518>
- 台北時間：2026-08-22 06:27
- 失敗 step：`Fetch and process the newest episode`
- Secret 驗證 step 已成功，因此不是 `GEMINI_FREE_API_KEY` 或 `GEMINI_PAID_API_KEY` 缺失。

GitHub annotation 中的實際例外：

```text
google.genai._gaos.lib.compat_errors.APIConnectionError: Server disconnected without sending a response.
```

### 根因

呼叫 Gemini API 時，遠端伺服器在送出完整 HTTP response 前中斷連線。這是上游服務或網路層的暫時性連線失敗，不是 workflow 語法、Secret 設定或 Git 權限問題。

### 處理方式

1. 先確認 `Verify Gemini secrets are configured` 是否成功。
2. 從失敗 step 最後一行及 GitHub annotation 判斷是否為 `APIConnectionError`。
3. 若只是單次斷線，重新執行 workflow，或等待下一個排程；本次第二次執行即成功。
4. 若頻繁發生，再考慮在 API client 加入只針對連線錯誤、HTTP 429 與 5xx 的有限次數 exponential backoff。不要對所有例外無條件重試，以免掩蓋資料或程式錯誤。

## 問題二：daily run 成功，但網頁沒有更新

### 症狀

- Run：<https://github.com/sam901122/english-podcast-learning/actions/runs/32543179035>
- 台北時間：2026-08-22 09:21
- `Fetch and process the newest episode` 與 `Commit generated notes` 都成功。
- `github-actions[bot]` 在 09:24 建立並 push `content: add latest learning notes`。
- push 後沒有新的 `Deploy site to Pages` run，因此線上網站仍是舊內容。

### 根因

Daily workflow 的 `git push` 使用 Actions 自動提供的 `GITHUB_TOKEN`。GitHub 為防止遞迴執行，使用 `GITHUB_TOKEN` 產生的事件通常不會觸發新的 workflow；因此即使 `pages.yml` 監聽 `site/**` 的 `push`，這次 bot push 也不會啟動它。GitHub 也明確說明，使用 `GITHUB_TOKEN` push 的 commit 不會觸發 GitHub Pages build。

官方文件：<https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs>

### 修正方式

`daily-update.yml` 已改成在同一次 workflow 中直接部署：

1. `update` job 生成內容、commit 並 push。
2. 在 runner 尚保有最新工作目錄時，以 `actions/upload-pages-artifact` 上傳整個 `site`。
3. 只有 `steps.podcast.outputs.updated == 'true'` 時才建立 artifact。
4. `deploy` job 透過 `needs.update.outputs.updated` 判斷是否需要執行，再使用 `actions/deploy-pages` 發布該 artifact。

這個設計刻意不讓新的 deploy job 再次 checkout，因為 workflow 開始時的 `github.sha` 是更新前的 commit；重新 checkout 該 SHA 可能再次部署舊內容。

Daily workflow 需要以下權限：

```yaml
permissions:
  contents: write
  pages: write
  id-token: write
```

## 驗證清單

有新節目時，確認同一個 `Update daily podcast` run 依序出現：

1. `Fetch and process the newest episode` 成功，並輸出 `updated=true`。
2. `Commit generated notes` 成功，遠端分支出現新 commit。
3. `Configure GitHub Pages` 與 `Upload GitHub Pages artifact` 成功。
4. `deploy` job 的 `Deploy GitHub Pages` 成功，environment URL 指向最新 deployment。
5. 線上 `site/data` 對應內容與新 commit 一致。

沒有新節目時，`updated=false` 屬於正常情況：commit、artifact 與 deploy job 都應跳過，不應視為故障。

## 排查原則

- Workflow 顯示綠燈只代表已執行的 step 成功，不代表後續的另一個 workflow 有被觸發。
- 同時檢查 Actions run、遠端 commit、Pages deployment 三層狀態。
- 若 commit 已存在但沒有 Pages run，先檢查 push 的 actor/token，而不是先歸因於瀏覽器或 CDN cache。
- 不要把未更新的網頁直接判定為快取問題；先確認新的 Pages deployment 是否真的存在。
