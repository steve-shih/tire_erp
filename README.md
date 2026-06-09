# 中華全佑 ERP 系統運維與移轉手冊 (System Admin & Migration Guide)

本手冊詳細記載了本系統的架構、日常啟動指令、範本預處理，以及如何將整套系統與資料庫安全地移轉到新電腦上。

---

## 🚀 目前部署環境狀態 (Current Deployment Status)

此系統已經在此伺服器上架設完畢，目前的運行狀態與連線資訊如下：

### 1. 伺服器與架構配置
- **資料庫 (MongoDB)**: 已安裝為 Windows 服務，監聽 Port 27017。
- **後端 API (FastAPI)**: 使用 **PM2** 常駐運行，進程名稱為 `tire-erp-backend`，監聽 Port 8000。
- **前端代理 (Nginx)**: 監聽 Port 80，並反向代理至 Port 8000。

### 2. 外部連線網址
系統已設定 **ngrok** 隧道服務進行穿透，可透過以下專屬網址從外部存取 ERP 系統：
👉 **https://zhqy.ngrok.pro**

*(本機端存取請使用 http://localhost 或 http://127.0.0.1)*

### 3. 系統預設帳號與密碼
系統還原後已包含以下預設帳號：

**👑 最高權限管理者 (Owner)** (擁有所有權限)：
- `owner1` / `owner123`
- `owner2` / `owner123`

**🧑‍💼 一般員工 / 分店帳號 (Staff)**：
- `staff1` / `staff123`
- `staff2` / `staff123`
- `branch_taichung` / `taichung123`
- `branch_miaoli` / `miaoli123`
- `branch_hsinchu` / `hsinchu123`

### 4. 資料庫已載入之歷史資料概況
- **產品庫存 (products)**：2913 筆
- **客戶資料 (customers)**：3289 筆
- **進貨廠商 (vendors)**：333 筆
- **使用者帳號 (users)**：7 筆
- 其他包含出貨單、進貨單、報價單等資料均已完整還原。

---

## 系統架構簡介
- **前端 (Frontend)**: 原生 HTML + Vanilla CSS + Javascript (`frontend/` 目錄)
- **後端 (Backend)**: Python FastAPI 框架 (`backend/` 目率)
- **資料庫 (Database)**: MongoDB (預設連線為 `mongodb://localhost:27017`)
- **列印引擎**: 使用 `openpyxl` 載入原生 Excel 範本寫入資料 (`backend/excel_engine.py`)

---

## 1. 常用指令與指令啟用方法

本系統在主機上可以透過多種方式啟動，請依照您的需求選擇：

### 方式 A：使用 PM2 進行守護進程管理（推薦，斷線會自動重啟）
PM2 會在背景持續監控伺服器，若當機或重開機會自動重新拉起服務。
*   **重啟服務**：
    ```bash
    npx pm2 restart tire-erp-backend
    ```
*   **停止服務**：
    ```bash
    npx pm2 stop tire-erp-backend
    ```
*   **查看即時運行狀態**：
    ```bash
    npx pm2 status
    ```
*   **查看運作日誌**：
    ```bash
    npx pm2 logs tire-erp-backend
    ```

### 方式 B：手動在前台/後台啟動
如果您想直接觀察詳細的輸出訊息：
```bash
/opt/anaconda3/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*   `--host 0.0.0.0`：允許其他電腦透過主機 IP 連線。
*   `--port 8000`：指定連接埠為 8000。

---

## 2. 資料庫備份與還原腳本

我們已內建以 Python 撰寫的免安裝備份工具，其運作不依賴 MongoDB 命令列工具，十分簡便：

### 資料備份 (Backup)
當您需要備份目前所有單據、產品與客戶資料時：
```bash
/opt/anaconda3/bin/python backup_db.py
```
*   **效果**：系統會在根目錄產生 `database_backup/` 資料夾，並將所有資料表（Collections）匯出為符合 MongoDB 原生格式的 JSON 檔案。

### 資料還原 (Restore)
在新電腦上，或者需要復原歷史資料時：
```bash
/opt/anaconda3/bin/python restore_db.py
```
*   **警告**：此指令會先清空資料庫中對應的資料表，再將 `database_backup/` 內的資料全數載入。

---

## 3. 換電腦架設與資料移轉步驟 (Full Migration)

當您購買新電腦，或者需要將伺服器移轉至其他電腦時，請遵循以下步驟：

### 步驟 1：在【舊電腦】進行完整備份
1. 打開終端機，進入專案目錄：
   ```bash
   cd /Users/steve_shih/Desktop/tire_erp
   ```
2. 執行備份腳本以產生最新的資料庫檔案：
   ```bash
   /opt/anaconda3/bin/python backup_db.py
   ```
3. 確認目錄下已出現 `database_backup` 資料夾。

### 步驟 2：將專案拷貝至【新電腦】
1. 將整包 `/Users/steve_shih/Desktop/tire_erp` 資料夾（必須包含剛備份出來的 `database_backup`）複製到 USB 隨身碟或上傳至雲端硬碟。
2. 將此資料夾放到新電腦的指定路徑中（例如：`/Users/steve_shih/Desktop/tire_erp`）。

### 步驟 3：在【新電腦】安裝環境
1. **下載並安裝 Anaconda Python** (或是官方標準版 Python 3.9+)。
2. **安裝 MongoDB 社群版**：
   - Mac 使用者可使用 Homebrew 安裝：
     ```bash
     brew tap mongodb/brew
     brew install mongodb-community@7.0
     brew services start mongodb-community@7.0
     ```
   - Windows 使用者可以直接從官網下載 MSI 安裝檔安裝，並勾選 "Install MongoDB as a Service"。
3. 進入專案目錄，安裝 Python 相依套件：
   ```bash
   pip install fastapi uvicorn pymongo openpyxl pydantic
   ```

### 步驟 4：在【新電腦】還原資料庫
1. 在新電腦進入專案目錄，執行還原：
   ```bash
   python restore_db.py
   ```
2. 畫面顯示 "Database restore completed successfully!" 即代表資料庫已完整移植。

### 步驟 5：在新電腦上架設啟動
*   測試運行：
    ```bash
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ```
*   打開瀏覽器輸入 `http://localhost:8000` 即可正常登入使用！

---

## 4. 常見問題與排除 (Troubleshooting)

### Q1：其他電腦用同樣帳密登入不了？
*   **檢查網址是否正確**：不要在其他電腦的網址列輸入 `localhost:8000`，這會連到該台電腦自己。必須輸入 **主機的區域網路 IP**。
    - *例如：`http://192.168.1.120:8000`*
*   **取得主機 IP 的方法**：
    - **Mac 主機**：在終端機輸入 `ipconfig getifaddr en0` 或 `ifconfig` 查看 `inet` 後面的數值。
    - **Windows 主機**：在命令提示字元輸入 `ipconfig`，尋找 "IPv4 位址"。

### Q2：出現 "[Errno 48] address already in use" 錯誤？
這代表 8000 連接埠已被舊有的服務程式佔用。請使用以下方式釋放它：
1. 找出佔用連接埠的 PID：
   ```bash
   lsof -i :8000
   ```
2. 將該 PID 強制結束（假設 PID 為 41765）：
   ```bash
   kill -9 41765
   ```
3. 重新啟動服務即可。

### Q3：如何手動重新產生 Excel 簡化模板？
如果您修改了原版 `出貨單.xlsm` 或 `應收應付帳款.xlsm` 的樣式，想重新套用最新樣式：
1. 將新的 `出貨單.xlsm` 放進 `backend/templates/` 目錄。
2. 執行預處理指令：
   ```bash
   /opt/anaconda3/bin/python -c '
   import openpyxl
   # 預處理信封
   wb = openpyxl.load_workbook("backend/templates/應收應付帳款.xlsm", keep_vba=False)
   for name in list(wb.sheetnames):
       if name != "信封袋列印": wb.remove(wb[name])
   wb.save("backend/templates/envelope_template.xlsx")
   
   # 預處理出貨單
   wb = openpyxl.load_workbook("backend/templates/出貨單.xlsm", keep_vba=False)
   for name in list(wb.sheetnames):
       if name != "出貨單˙收據": wb.remove(wb[name])
   wb.save("backend/templates/sales_order_template.xlsx")
   print("預處理完成！")
   '
   ```
