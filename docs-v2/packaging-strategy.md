# 打包策略

> 如何把 Tauri 前端 + Python 后端 + Chromium + LLM 打包成一键安装包（跨平台）

---

## 一、目标

三个平台用户体验：

| 平台 | 下载 | 安装 | 启动 |
|------|------|------|------|
| macOS | `ApplySlave.dmg` | 拖到 Applications | 双击 `.app` |
| Windows | `ApplySlave.exe`（NSIS 安装器） | 跟随安装向导 | 开始菜单点击 |
| Linux | `ApplySlave.AppImage` | 赋可执行权限 | 双击 |

首次启动统一：看到"正在下载 AI 模型..."进度条（~4GB），下载完成后进主界面。

**一步都不多**。不需要装 Node.js、Python、Rust、浏览器、Ollama。

---

## 二、`.app` bundle 结构（macOS）

```
ApplySlave.app/
├── Contents/
│   ├── Info.plist
│   ├── MacOS/
│   │   └── ApplySlave                   # Rust 编译的 Tauri 二进制（~10MB）
│   ├── Resources/
│   │   ├── assets/                      # 前端打包产物（HTML/CSS/JS）~5MB
│   │   ├── python-runtime/              # ~50MB
│   │   │   ├── bin/python3.12
│   │   │   └── lib/python3.12/
│   │   ├── python-backend/              # ~200MB
│   │   │   ├── packages/                # 我们的 monorepo 代码
│   │   │   └── site-packages/           # FastAPI, Playwright, llama-cpp-python 等
│   │   └── chromium/                    # ~200MB
│   │       └── chrome-mac-arm64/
│   └── _CodeSignature/
```

Windows 和 Linux 的产物结构类似，只是放在 `%APPDATA%` 或 `/opt/applyslave/` 路径。

**下载体积估算**：

| 平台 | 压缩后体积 |
|------|-----------|
| macOS `.dmg` | ~500MB |
| Windows `.exe` | ~500MB |
| Linux `.AppImage` | ~520MB |

---

## 三、关键技术选型

### 3.1 Python 运行时：python-build-standalone

不用系统 Python，也不用 PyInstaller。而是嵌入 [python-build-standalone](https://github.com/indygreg/python-build-standalone) —— Astral（uv 的开发商）维护的独立 Python 构建。

**优点**：
- 启动快（比 PyInstaller 快一个数量级）
- 产物干净（就是标准 CPython 分发）
- 与 uv 工作流兼容好
- 三平台都有预编译版本

**使用**：
```bash
# macOS ARM64
curl -L -o python-standalone.tar.gz \
  https://github.com/indygreg/python-build-standalone/releases/download/20250131/cpython-3.12.8+20250131-aarch64-apple-darwin-install_only.tar.gz

# Windows x86_64
curl -L -o python-standalone.tar.gz \
  https://github.com/indygreg/python-build-standalone/releases/download/20250131/cpython-3.12.8+20250131-x86_64-pc-windows-msvc-install_only.tar.gz

# Linux x86_64
curl -L -o python-standalone.tar.gz \
  https://github.com/indygreg/python-build-standalone/releases/download/20250131/cpython-3.12.8+20250131-x86_64-unknown-linux-gnu-install_only.tar.gz
```

### 3.2 Python 依赖：pip install --target

不用 venv，直接把依赖装到 bundle 里：

```bash
./python-runtime/bin/python3 -m pip install --target python-backend/site-packages \
    fastapi uvicorn playwright llama-cpp-python pdfplumber ...
```

### 3.3 Playwright Chromium：手动下载打包

```bash
PLAYWRIGHT_BROWSERS_PATH=./chromium \
    ./python-runtime/bin/python3 -m playwright install chromium

# 运行时通过环境变量告诉 Playwright 用 bundle 里的 Chromium
```

### 3.4 LLM 引擎：llama-cpp-python

不用 Ollama（那是独立应用）。用 [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) —— C++ 内核 + Python binding。

**为什么不用 Ollama**：
- Ollama 是独立应用，打包进 bundle 反模式
- llama-cpp-python 直接是库，import 就能用
- macOS 上有 Metal GPU 加速，Windows 有 CUDA，Linux 两者都支持

**模型**：Qwen2.5-7B-Instruct GGUF Q4 量化（~4GB）

**模型文件不打进 bundle**：首次启动时从 Hugging Face 下载到应用数据目录。

---

## 四、Tauri 的 Rust 侧：启动 Python 后端

Tauri 的 Rust 代码量很少，主要做两件事：窗口管理 + 启动 Python 子进程。

### 4.1 `src-tauri/src/main.rs`

```rust
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};

struct PythonProcess(Mutex<Option<Child>>);

fn start_python_backend(app_handle: &tauri::AppHandle) -> Result<Child, String> {
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?;
    let app_data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;

    // 跨平台的 python 可执行文件路径
    let python_bin = if cfg!(windows) {
        resource_dir.join("python-runtime/python.exe")
    } else {
        resource_dir.join("python-runtime/bin/python3")
    };

    let backend_entry = resource_dir
        .join("python-backend/packages/backend/src/backend/main.py");
    let site_packages = resource_dir.join("python-backend/site-packages");
    let chromium_path = resource_dir.join("chromium");

    Command::new(python_bin)
        .args([
            backend_entry.to_str().unwrap(),
            "--port",
            "8765",
        ])
        .env("PYTHONPATH", site_packages)
        .env("PLAYWRIGHT_BROWSERS_PATH", chromium_path)
        .env("APPLYSLAVE_DATA_DIR", app_data_dir)
        .spawn()
        .map_err(|error| format!("Failed to start Python backend: {}", error))
}

#[tauri::command]
fn backend_port() -> u16 {
    8765
}

fn main() {
    tauri::Builder::default()
        .manage(PythonProcess(Mutex::new(None)))
        .setup(|app| {
            let child = start_python_backend(&app.handle())?;
            app.state::<PythonProcess>().0.lock().unwrap().replace(child);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // 窗口关闭时干掉 Python 子进程
                let state = window.state::<PythonProcess>();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![backend_port])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

**Rust 代码总量**：这个项目整个 `src-tauri/` 目录大概 300 行 Rust，剩下都是抄文档。

### 4.2 前端怎么连后端

```typescript
// src/services/backend.ts
import { invoke } from '@tauri-apps/api/core';

const port = await invoke<number>('backend_port');
const BASE_URL = `http://localhost:${port}`;

export async function getProfile() {
    const response = await fetch(`${BASE_URL}/api/profile`);
    return response.json();
}

// WebSocket 实时进度
const ws = new WebSocket(`ws://localhost:${port}/api/ws`);
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // 更新 React state
};
```

---

## 五、`tauri.conf.json` 配置

```json
{
    "$schema": "https://schema.tauri.app/config/2",
    "productName": "ApplySlave",
    "version": "0.1.0",
    "identifier": "com.applyslave.app",
    "build": {
        "beforeDevCommand": "pnpm dev",
        "beforeBuildCommand": "pnpm build",
        "devUrl": "http://localhost:1420",
        "frontendDist": "../dist"
    },
    "app": {
        "windows": [
            {
                "title": "ApplySlave",
                "width": 1200,
                "height": 800,
                "minWidth": 800,
                "minHeight": 600
            }
        ],
        "security": {
            "csp": null
        }
    },
    "bundle": {
        "active": true,
        "targets": ["dmg", "app", "nsis", "msi", "deb", "appimage"],
        "icon": [
            "icons/32x32.png",
            "icons/128x128.png",
            "icons/icon.icns",
            "icons/icon.ico"
        ],
        "resources": [
            "resources/python-runtime/**/*",
            "resources/python-backend/**/*",
            "resources/chromium/**/*"
        ],
        "macOS": {
            "minimumSystemVersion": "11.0",
            "signingIdentity": "Developer ID Application: Your Name (TEAMID)"
        },
        "windows": {
            "certificateThumbprint": null,
            "digestAlgorithm": "sha256",
            "timestampUrl": "http://timestamp.digicert.com"
        },
        "linux": {
            "deb": {
                "depends": ["libwebkit2gtk-4.1-0"]
            }
        }
    }
}
```

---

## 六、打包脚本

### 6.1 单平台打包

```bash
# 在对应平台机器上运行
cd apps/applyslave-desktop
pnpm tauri build
```

Tauri 自动：
1. 跑 `pnpm build`（Vite 打包前端为静态文件到 `dist/`）
2. 编译 Rust 二进制
3. 把前端产物、Rust 二进制、`resources/` 打包进 bundle
4. 根据 `targets` 产出对应平台的安装包

### 6.2 资源准备脚本

Tauri 打包时不会帮你准备 Python 运行时和 Chromium。需要自己写脚本：

```
packaging/
├── prepare-resources.sh    # macOS / Linux
├── prepare-resources.ps1   # Windows
└── lib/
    ├── python-runtime.sh   # 下载 python-build-standalone
    ├── python-deps.sh      # uv 导出 requirements + pip install --target
    └── chromium.sh         # 下载 Playwright Chromium
```

示例 `prepare-resources.sh`：

```bash
#!/bin/bash
set -euo pipefail

RESOURCES_DIR="apps/applyslave-desktop/src-tauri/resources"
rm -rf "$RESOURCES_DIR"
mkdir -p "$RESOURCES_DIR"

echo "==> [1/3] Python runtime..."
./packaging/lib/python-runtime.sh "$RESOURCES_DIR/python-runtime"

echo "==> [2/3] Python dependencies..."
./packaging/lib/python-deps.sh "$RESOURCES_DIR/python-backend"

echo "==> [3/3] Chromium..."
./packaging/lib/chromium.sh "$RESOURCES_DIR/chromium"

echo "==> Resources prepared. Run 'pnpm tauri build' next."
```

---

## 七、多平台 CI：GitHub Actions

因为 Tauri 只能产**当前平台**的包，CI 上起三个 runner 并行构建：

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ['v*']

jobs:
  build:
    strategy:
      matrix:
        include:
          - platform: macos-14
            target: aarch64-apple-darwin
          - platform: macos-13
            target: x86_64-apple-darwin
          - platform: windows-latest
            target: x86_64-pc-windows-msvc
          - platform: ubuntu-22.04
            target: x86_64-unknown-linux-gnu

    runs-on: ${{ matrix.platform }}
    steps:
      - uses: actions/checkout@v4

      - name: Install pnpm
        uses: pnpm/action-setup@v3
        with:
          version: 9

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Setup uv
        uses: astral-sh/setup-uv@v4

      - name: Install Linux dependencies
        if: matrix.platform == 'ubuntu-22.04'
        run: |
          sudo apt-get update
          sudo apt-get install -y libwebkit2gtk-4.1-dev libssl-dev libayatana-appindicator3-dev

      - name: Prepare resources
        shell: bash
        run: ./packaging/prepare-resources.sh

      - name: Install frontend deps
        run: pnpm install
        working-directory: apps/applyslave-desktop

      - name: Build Tauri app
        uses: tauri-apps/tauri-action@v0
        env:
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
          APPLE_ID: ${{ secrets.APPLE_ID }}
          APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
          APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
        with:
          projectPath: apps/applyslave-desktop
          tagName: ${{ github.ref_name }}
          releaseName: 'ApplySlave ${{ github.ref_name }}'
          releaseDraft: true
          prerelease: false
```

一次 `git push --tags`，自动产出：
- `ApplySlave_aarch64.dmg`（Apple Silicon Mac）
- `ApplySlave_x64.dmg`（Intel Mac）
- `ApplySlave_x64-setup.exe`（Windows）
- `ApplySlave_amd64.AppImage`（Linux）

---

## 八、代码签名和公证

### 8.1 macOS

需要 [Apple Developer Program](https://developer.apple.com/programs/)（$99/年）。

Tauri 会自动用 `signingIdentity` 配置的证书签名。公证通过环境变量触发：

```bash
export APPLE_ID="your@email.com"
export APPLE_PASSWORD="app-specific-password"
export APPLE_TEAM_ID="XXXXXXXXXX"
pnpm tauri build
```

### 8.2 Windows

需要代码签名证书（DigiCert、Sectigo 等，$200-400/年）。

或者用 [Azure Trusted Signing](https://azure.microsoft.com/en-us/products/trusted-signing)（便宜很多）。

不签名的话 Windows SmartScreen 会吓用户。

### 8.3 Linux

不需要签名。

### 8.4 先发布未签名版本

完全可以先发不签名的内测版：
- macOS 用户右键 → 打开，绕过 Gatekeeper
- Windows 用户 "仍要运行"，绕过 SmartScreen

等产品打磨好再买签名。

---

## 九、自动更新：Tauri Updater

Tauri 2.x 有官方内置的 updater 插件，不需要第三方（比如 Sparkle）。

### 9.1 配置

```json
// tauri.conf.json
{
    "plugins": {
        "updater": {
            "active": true,
            "endpoints": [
                "https://github.com/your/applyslave/releases/latest/download/latest.json"
            ],
            "dialog": true,
            "pubkey": "YOUR_PUBLIC_KEY_HERE"
        }
    }
}
```

### 9.2 工作流程

1. 用 `tauri signer generate` 生成公私钥对
2. GitHub Actions 构建时用私钥签名 `.dmg` / `.exe` / `.AppImage`
3. 生成 `latest.json` 元数据，上传到 GitHub Releases
4. 客户端启动时自动检查 `latest.json`，有新版本提示用户更新

### 9.3 前端触发检查

```typescript
import { check } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';

const update = await check();
if (update?.available) {
    await update.downloadAndInstall();
    await relaunch();
}
```

---

## 十、体积优化

如果 500MB 嫌大：

| 优化 | 节省 | 代价 |
|------|------|------|
| 按需下载 Chromium（首次启动下载） | -200MB | 首次启动慢，需要联网 |
| 按需下载 LLM 模型（默认做法） | -4GB | 首次启动下载 4GB |
| 精简 Python 依赖（剔除不用的） | -30MB | 需要 careful |
| Tauri 的 app size optimization | -5-10MB | 跟随文档配置 |

**建议**：Chromium 打包进 bundle（保证离线可用），LLM 模型按需下载（必须这样，不然 app 就 5GB 了）。

---

## 十一、测试清单

发布前必须测试（每个平台都测）：

- [ ] 首次启动：能下载 LLM 模型
- [ ] 后端启动：前端能连上 localhost:8765
- [ ] 后端崩溃：Rust 监控到能提示用户重启
- [ ] 退出清理：关窗口时 Python 子进程也退出
- [ ] 浏览器自动化：能打开 bundle 里的 Chromium 完成投递
- [ ] 代码签名（macOS / Windows）：系统安全检查不弹警告
- [ ] 公证（macOS）：`spctl --assess --verbose ApplySlave.app` 通过
- [ ] 自动更新：从 v1.0.0 升到 v1.0.1 不出错
- [ ] 卸载干净：删除应用和数据目录，无残留
- [ ] Intel Mac / Apple Silicon 都能跑（macOS）
- [ ] Win10 / Win11 都能跑（Windows）
- [ ] 常见发行版都能跑（Ubuntu 22.04 / 24.04, Fedora 40）

---

## 十二、打包体积详细分解

| 组件 | 打包后大小 | 说明 |
|------|-----------|------|
| Tauri Rust 二进制 | ~10-15MB | 比 Electron 的 ~150MB 小 10 倍 |
| 前端静态资源（React + Tailwind 打包后） | ~3-5MB | Vite tree-shaking |
| Python 运行时 | ~50MB | python-build-standalone |
| Python 依赖 site-packages | ~200MB | FastAPI + Playwright + llama-cpp-python + 其他 |
| Chromium | ~200MB | Playwright 需要 |
| **压缩后 `.dmg` / `.exe` / `.AppImage`** | **~500MB** | 跟 Docker Desktop 差不多 |
| 首次启动下载 LLM 模型 | +4GB | 存到 app data dir |

对比参考：
- Docker Desktop: ~600MB
- Postman: ~300MB
- Slack: ~250MB
- Cursor: ~250MB

500MB 完全可接受。
