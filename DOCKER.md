# 用 Docker 啟動前後端

先啟動 Docker 引擎，例如 Docker Desktop。以下指令都在專案根目錄執行。
如果還沒有 `.env`，複製 `.env.example` 成 `.env`，再填入 Gemini API key
與模型設定。已有 `.env` 就沿用。

```bash
docker compose up --build
```

`--build` 會先建置 image，再啟動前後端容器；終端機會顯示兩邊的 logs。
啟動完成後開啟：

- 前端：<http://localhost:8501>
- 後端 API 文件：<http://localhost:8000/docs>

按 `Ctrl+C` 停止服務。要在背景執行，改用 `docker compose up --build -d`；
要停止並移除容器，執行 `docker compose down`。

## 檔案分工

```text
.
├── compose.yaml         # 一起啟動前後端，設定連線、port 與環境變數
├── .dockerignore        # 不傳進建置環境的檔案，例如 .env、.venv
├── pyproject.toml       # 共用的 Python 套件清單
├── uv.lock              # 鎖定套件版本
├── backend/
│   └── Dockerfile       # 建置後端 image
└── frontend/
    └── Dockerfile       # 建置前端 image
```

兩份 Dockerfile 都是單階段建置，依序做這幾件事：

1. `FROM`：使用有 Python 3.12 的基礎 image。
2. `WORKDIR`：設定容器內的工作目錄 `/app`。
3. `RUN` 與 `COPY`：安裝 uv、複製套件清單，依 lockfile 安裝套件。
4. `COPY`：複製對應的前端或後端程式。
5. `EXPOSE`：標示程式使用的 port；實際對外連接由 Compose 的 `ports` 設定。
6. `CMD`：容器啟動時執行程式。`uv run --no-sync` 使用建置時已安裝的套件。

先安裝套件，再複製程式，讓修改程式時能重用套件安裝的 Docker 快取。
目前兩邊使用同一份套件清單，方便維護；所以前端 image 也包含後端套件。

## Compose 裡幾個必要設定

- `build.context: .`：可複製的檔案從根目錄開始算，因此能讀取共用的套件清單。
- `build.dockerfile`：指定這個服務要用哪份 Dockerfile。
- `ports`：例如 `127.0.0.1:8501:8501`，把本機 8501 接到容器的 8501，限本機存取。
- `env_file`：啟動後端時載入 `.env`；金鑰不會被複製進 image。
- `environment`：直接設定前端的 API 位址。
- `healthcheck` 與 `depends_on`：等後端 `/health_test` 能回應後，再啟動前端。

```text
瀏覽器 -> localhost:8501 -> Streamlit 容器
                                |
                                v
                           backend:8000 -> FastAPI 容器 -> Gemini
```

Streamlit 在容器內發出 API 請求，因此使用 `http://backend:8000`。
容器內的 `localhost` 指自己，不能用來連另一個容器。
Dockerfile 啟動指令的 `0.0.0.0` 則讓程式接受來自容器外的連線。

## 常用指令

```bash
# 修改程式後，重新建置並在背景啟動。
docker compose up --build -d

# 查看狀態與持續追蹤 logs。
docker compose ps
docker compose logs -f

# 停止並移除容器。
docker compose down

# 檢查 Compose 設定，不印出金鑰。
docker compose config --quiet
```

這份設定適合本機學習。知識庫存在後端記憶體，重啟後端會清空，
所以後端維持一個 worker。健康檢查只確認 API 能回應，不驗證 Gemini 金鑰。

參考：[Docker Compose](https://docs.docker.com/reference/compose-file/services/)、
[uv Docker 整合](https://docs.astral.sh/uv/guides/integration/docker/)。
