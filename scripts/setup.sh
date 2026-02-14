#!/bin/bash
set -e

echo "========================================="
echo "  简历自动投递机器人 - 环境自动部署"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

success() { echo -e "${GREEN}✓ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }
fail()    { echo -e "${RED}✗ $1${NC}"; exit 1; }

# ---- 1. 检测系统 ----
echo ">> 检测系统环境..."
OS="$(uname -s)"
ARCH="$(uname -m)"
echo "   系统: $OS / $ARCH"

# 检测内存（macOS）
if [ "$OS" = "Darwin" ]; then
  TOTAL_MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  echo "   内存: ${TOTAL_MEM_GB}GB"
fi

# ---- 2. 检测/安装 Homebrew ----
echo ""
echo ">> 检测 Homebrew..."
if command -v brew &> /dev/null; then
  success "Homebrew 已安装"
else
  warn "Homebrew 未安装，正在安装..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  success "Homebrew 安装完成"
fi

# ---- 3. 检测/安装 Node.js ----
echo ""
echo ">> 检测 Node.js..."
if command -v node &> /dev/null; then
  NODE_VERSION=$(node -v)
  success "Node.js 已安装: $NODE_VERSION"
else
  warn "Node.js 未安装，正在安装..."
  brew install node
  success "Node.js 安装完成: $(node -v)"
fi

# ---- 4. 检测/安装 Ollama ----
echo ""
echo ">> 检测 Ollama..."
if command -v ollama &> /dev/null; then
  success "Ollama 已安装"
else
  warn "Ollama 未安装，正在安装..."
  brew install ollama
  success "Ollama 安装完成"
fi

# ---- 5. 启动 Ollama 服务 ----
echo ""
echo ">> 启动 Ollama 服务..."
if curl -s http://localhost:11434/api/tags &> /dev/null; then
  success "Ollama 服务已在运行"
else
  ollama serve &> /dev/null &
  OLLAMA_PID=$!
  sleep 3
  if curl -s http://localhost:11434/api/tags &> /dev/null; then
    success "Ollama 服务已启动 (PID: $OLLAMA_PID)"
  else
    fail "Ollama 服务启动失败，请手动运行: ollama serve"
  fi
fi

# ---- 6. 根据内存选择并拉取模型 ----
echo ""
echo ">> 选择并下载 LLM 模型..."

# 默认模型选择逻辑
if [ "$OS" = "Darwin" ] && [ -n "$TOTAL_MEM_GB" ]; then
  if [ "$TOTAL_MEM_GB" -ge 16 ]; then
    MODEL="qwen2.5:7b"
    echo "   内存 ${TOTAL_MEM_GB}GB >= 16GB，选择 $MODEL"
  elif [ "$TOTAL_MEM_GB" -ge 8 ]; then
    MODEL="qwen2.5:3b"
    echo "   内存 ${TOTAL_MEM_GB}GB >= 8GB，选择 $MODEL"
  else
    MODEL="phi3:mini"
    echo "   内存 ${TOTAL_MEM_GB}GB < 8GB，选择 $MODEL"
  fi
else
  MODEL="qwen2.5:7b"
  echo "   默认选择 $MODEL"
fi

# 允许用户覆盖
if [ -n "$LLM_MODEL" ]; then
  MODEL="$LLM_MODEL"
  echo "   使用环境变量指定的模型: $MODEL"
fi

# 检查模型是否已下载
if ollama list 2>/dev/null | grep -q "$MODEL"; then
  success "模型 $MODEL 已存在"
else
  echo "   正在下载 $MODEL（首次下载可能需要几分钟）..."
  ollama pull "$MODEL"
  success "模型 $MODEL 下载完成"
fi

# ---- 7. 安装项目依赖 ----
echo ""
echo ">> 安装项目依赖..."
if [ -f "package.json" ]; then
  npm install
  success "npm 依赖安装完成"
else
  warn "未找到 package.json，跳过 npm install"
fi

# ---- 8. 安装 Playwright 浏览器 ----
echo ""
echo ">> 安装 Playwright 浏览器..."
if npx playwright --version &> /dev/null 2>&1; then
  npx playwright install chromium
  success "Playwright Chromium 安装完成"
else
  warn "Playwright 未在依赖中，跳过浏览器安装"
fi

# ---- 9. 初始化配置文件 ----
echo ""
echo ">> 初始化配置文件..."

mkdir -p config data

if [ ! -f "config/profile.json" ]; then
  cat > config/profile.json << 'EOF'
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
EOF
  success "已创建 config/profile.json（请填写你的简历信息）"
else
  success "config/profile.json 已存在，跳过"
fi

if [ ! -f "config/settings.json" ]; then
  cat > config/settings.json << EOF
{
  "llm": {
    "base_url": "http://localhost:11434",
    "model": "$MODEL",
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
EOF
  success "已创建 config/settings.json"
else
  success "config/settings.json 已存在，跳过"
fi

if [ ! -f "data/applications.json" ]; then
  echo "[]" > data/applications.json
  success "已创建 data/applications.json"
fi

# ---- 10. 验证 ----
echo ""
echo ">> 验证环境..."
echo -n "   Ollama API: "
if curl -s http://localhost:11434/api/tags | grep -q "$MODEL"; then
  success "模型 $MODEL 可用"
else
  warn "模型验证失败，请检查 Ollama 服务"
fi

# ---- 完成 ----
echo ""
echo "========================================="
echo -e "${GREEN}  部署完成！${NC}"
echo "========================================="
echo ""
echo "  下一步："
echo "  1. 编辑 config/profile.json 填写你的简历信息"
echo "  2. 将简历 PDF 放到项目根目录"
echo "  3. 运行: npm start"
echo ""
echo "  模型: $MODEL"
echo "  Ollama: http://localhost:11434"
echo ""
