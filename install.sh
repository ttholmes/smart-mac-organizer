#!/bin/bash

# ==========================================
# Smart Mac Organizer 
# ==========================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Iniciando Instalação do Smart Mac Organizer${NC}"

# 1. Definição de Caminhos
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
SRC_PATH="$PROJECT_ROOT/src/organizer.py"
CONFIG_FILE="$PROJECT_ROOT/config.yaml"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
DESKTOP_APP="$HOME/Desktop/Organizar com IA.app"

# 2. Check Homebrew & System Tools
echo -e "${BLUE}📦 Verificando ferramentas de sistema...${NC}"
if ! command -v brew &> /dev/null; then
    echo "Instalando Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Instala Python, Tesseract, Tag e Ollama
brew install python@3.11 tesseract tag
brew install --cask ollama

# 3. Setup Python Venv
echo -e "${BLUE}🐍 Configurando ambiente Python (venv)...${NC}"
if [ ! -d "$VENV_PATH" ]; then
    python3.11 -m venv "$VENV_PATH"
fi

# Garante pip atualizado
"$VENV_PATH/bin/pip" install --upgrade pip

# Cria requirements.txt se não existir (Fallback)
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Criando requirements.txt padrão..."
    cat <<EOF > "$REQUIREMENTS_FILE"
ollama==0.1.6
pymupdf==1.23.8
Pillow==10.2.0
pytesseract==0.3.10
PyYAML==6.0.1
watchdog==4.0.0
pyobjc-framework-Vision==10.0
pyobjc-framework-Cocoa==10.0
EOF
fi

# Instala dependências
echo "Instalando bibliotecas (isso pode demorar um pouco)..."
"$VENV_PATH/bin/pip" install -r "$REQUIREMENTS_FILE"

# 4. Setup AI Model (Qwen 2.5)
echo -e "${BLUE}🧠 Configurando Modelo de IA (Qwen 2.5 3B)...${NC}"
if ! pgrep -x "Ollama" > /dev/null; then
    open -a Ollama
    echo "⏳ Aguardando Ollama iniciar..."
    sleep 5
fi
# Baixa o modelo recomendado 
ollama pull qwen2.5:3b

# 5. Configuração Padrão do config.yaml
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${BLUE}⚙️ Gerando config.yaml a partir do template...${NC}"
    if [ -f "config.example.yaml" ]; then
        cp config.example.yaml "$CONFIG_FILE"
        echo "⚠️  IMPORTANTE: Edite o arquivo config.yaml caso queira destinos diferentes, por exemplo, GoogleDrive!"
    else
        echo "❌ Erro: config.example.yaml não encontrado."
    fi
fi

# 6. Criação do App (Droplet)
echo -e "${BLUE}🍎 Compilando App para Desktop...${NC}"

APPLESCRIPT="
on open droppedItems
    set pythonPath to \"$VENV_PATH/bin/python\"
    set scriptPath to \"$SRC_PATH\"
    set configFile to \"$CONFIG_FILE\"
    
    repeat with aFile in droppedItems
        set posixPath to POSIX path of aFile
        # Chama o script passando --config
        do shell script quoted form of pythonPath & \" \" & quoted form of scriptPath & \" --config \" & quoted form of configFile & \" \" & quoted form of posixPath
    end repeat
    
    display notification \"Organização concluída!\" with title \"Smart Organizer\" sound name \"Glass\"
end open

on run
    display dialog \"Arraste arquivos para este ícone para organizar.\" buttons {\"OK\"} default button 1
end run
"

osacompile -o "$DESKTOP_APP" -e "$APPLESCRIPT"

echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN}✅ INSTALAÇÃO CONCLUÍDA!${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "1. Use o app ${BLUE}'Organizar com IA'${NC} na Mesa."
echo -e "2. Ou rode o monitoramento contínuo: ${BLUE}./venv/bin/python src/watcher.py${NC}"
echo -e "3. Certifique-se de que o ${BLUE}config.yaml${NC} está correto."
echo -e "4. Para suporte, visite: ${BLUE}https://github.com/ttholmes/smart-mac-organizer/issues${NC}"