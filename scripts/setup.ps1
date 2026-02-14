# 简历自动投递机器人 - Windows 环境自动部署
# 运行方式: 右键 -> 使用 PowerShell 运行
# 或: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  简历自动投递机器人 - 环境自动部署 (Windows)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

function Success($msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

# ---- 1. 检测系统 ----
Write-Host ">> 检测系统环境..."
$totalMemGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "   系统: Windows / $([Environment]::Is64BitOperatingSystem ? 'x64' : 'x86')"
Write-Host "   内存: ${totalMemGB}GB"

# ---- 2. 检测/安装 winget ----
Write-Host ""
Write-Host ">> 检测 winget..."
if (Get-Command winget -ErrorAction SilentlyContinue) {
    Success "winget 已可用"
} else {
    Fail "winget 不可用，请先安装 App Installer（从 Microsoft Store 搜索 'App Installer'）"
}

# ---- 3. 检测/安装 Node.js ----
Write-Host ""
Write-Host ">> 检测 Node.js..."
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVersion = node -v
    Success "Node.js 已安装: $nodeVersion"
} else {
    Warn "Node.js 未安装，正在安装..."
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Success "Node.js 安装完成: $(node -v)"
}

# ---- 4. 检测/安装 Ollama ----
Write-Host ""
Write-Host ">> 检测 Ollama..."
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Success "Ollama 已安装"
} else {
    Warn "Ollama 未安装，正在安装..."
    winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Success "Ollama 安装完成"
}

# ---- 5. 启动 Ollama 服务 ----
Write-Host ""
Write-Host ">> 启动 Ollama 服务..."
$ollamaRunning = $false
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
    $ollamaRunning = $true
    Success "Ollama 服务已在运行"
} catch {
    Warn "正在启动 Ollama 服务..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
    try {
        Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
        Success "Ollama 服务已启动"
    } catch {
        Fail "Ollama 服务启动失败，请手动运行: ollama serve"
    }
}

# ---- 6. 根据内存选择并拉取模型 ----
Write-Host ""
Write-Host ">> 选择并下载 LLM 模型..."

if ($totalMemGB -ge 16) {
    $model = "qwen2.5:7b"
    Write-Host "   内存 ${totalMemGB}GB >= 16GB，选择 $model"
} elseif ($totalMemGB -ge 8) {
    $model = "qwen2.5:3b"
    Write-Host "   内存 ${totalMemGB}GB >= 8GB，选择 $model"
} else {
    $model = "phi3:mini"
    Write-Host "   内存 ${totalMemGB}GB < 8GB，选择 $model"
}

# 允许环境变量覆盖
if ($env:LLM_MODEL) {
    $model = $env:LLM_MODEL
    Write-Host "   使用环境变量指定的模型: $model"
}

$existingModels = ollama list 2>&1
if ($existingModels -match [regex]::Escape($model)) {
    Success "模型 $model 已存在"
} else {
    Write-Host "   正在下载 $model（首次下载可能需要几分钟）..."
    ollama pull $model
    Success "模型 $model 下载完成"
}

# ---- 7. 安装项目依赖 ----
Write-Host ""
Write-Host ">> 安装项目依赖..."
if (Test-Path "package.json") {
    npm install
    Success "npm 依赖安装完成"
} else {
    Warn "未找到 package.json，跳过 npm install"
}

# ---- 8. 安装 Playwright 浏览器 ----
Write-Host ""
Write-Host ">> 安装 Playwright 浏览器..."
try {
    npx playwright install chromium
    Success "Playwright Chromium 安装完成"
} catch {
    Warn "Playwright 未在依赖中，跳过浏览器安装"
}

# ---- 9. 初始化配置文件 ----
Write-Host ""
Write-Host ">> 初始化配置文件..."

if (-not (Test-Path "config")) { New-Item -ItemType Directory -Path "config" | Out-Null }
if (-not (Test-Path "data"))   { New-Item -ItemType Directory -Path "data"   | Out-Null }

if (-not (Test-Path "config/profile.json")) {
    @'
{
  "personal": {
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "location": ""
  },
  "education": [
    {
      "school": "",
      "degree": "",
      "major": "",
      "start": "",
      "end": ""
    }
  ],
  "experience": [
    {
      "company": "",
      "title": "",
      "start": "",
      "end": "",
      "description": ""
    }
  ],
  "skills": [],
  "resume_file": "./resume.pdf",
  "cover_letter_template": "./cover_letter.md"
}
'@ | Set-Content -Path "config/profile.json" -Encoding UTF8
    Success "已创建 config/profile.json（请填写你的简历信息）"
} else {
    Success "config/profile.json 已存在，跳过"
}

if (-not (Test-Path "config/settings.json")) {
    @"
{
  "llm": {
    "base_url": "http://localhost:11434",
    "model": "$model",
    "timeout": 30000
  },
  "browser": {
    "headless": false,
    "slow_mo": 500
  },
  "retry": {
    "max_attempts": 3,
    "delay_ms": 2000
  }
}
"@ | Set-Content -Path "config/settings.json" -Encoding UTF8
    Success "已创建 config/settings.json"
} else {
    Success "config/settings.json 已存在，跳过"
}

if (-not (Test-Path "data/applications.json")) {
    "[]" | Set-Content -Path "data/applications.json" -Encoding UTF8
    Success "已创建 data/applications.json"
}

# ---- 10. 验证 ----
Write-Host ""
Write-Host ">> 验证环境..."
try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    if ($tags.models.name -match [regex]::Escape($model)) {
        Success "模型 $model 可用"
    } else {
        Warn "模型验证失败，请检查 Ollama 服务"
    }
} catch {
    Warn "无法连接 Ollama 服务"
}

# ---- 完成 ----
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  下一步："
Write-Host "  1. 编辑 config/profile.json 填写你的简历信息"
Write-Host "  2. 将简历 PDF 放到项目根目录"
Write-Host "  3. 运行: npm start"
Write-Host ""
Write-Host "  模型: $model"
Write-Host "  Ollama: http://localhost:11434"
Write-Host ""
