# 🧠 Smart Mac Organizer (AI-Powered)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

Um organizador de arquivos inteligente para macOS que utiliza **modelos locais (Ollama)** e **Apple Vision Framework** para classificar, renomear e mover arquivos automaticamente — tudo localmente.

> **Privacidade em primeiro lugar:** nenhum dado sai do seu computador; todo o processamento é local.

---

## ✨ Recursos principais

- **Inteligência local:** usa `qwen2.5:3b` via Ollama para entender o contexto dos arquivos.
- **OCR nativo:** aproveita o Apple Vision para extrair texto de imagens/PDFs.
- **Estratégia local-first:** renomeia e organiza localmente antes de qualquer upload para evitar problemas de sincronização.
- **Classificação fina:** diferencia documentos semelhantes (ex.: contratos vs termos de serviço).
- **Uso de metadados:** WhereFroms, EXIF e outras informações ajudam a melhorar a decisão de destino.

---

## 🚀 Requisitos

- macOS (recomendado Apple Silicon)
- Ollama instalado e em execução
  ```bash
  brew install --cask ollama
  ollama pull qwen2.5:3b
  ```
- Python 3.11+
- (Opcional) `tag` CLI para atribuir cores/tags no Finder
  ```bash
  brew install tag
  ```

> Observação: pode ser necessário conceder permissões (Full Disk Access) para que o aplicativo leia pastas como `~/Downloads` ou `Desktop`.

---

## 🛠️ Instalação

1. Clone o repositório:

```bash
git clone https://github.com/ttholmes/smart-mac-organizer.git
cd smart-mac-organizer
```

2. Execute o instalador (cria venv e instala dependências):

```bash
bash install.sh
```

### Quickstart (3 minutos)
Guia rápido para testar o projeto em poucos minutos.

1. Copie o arquivo de exemplo e edite `config.yaml`:

```bash
cp config.example.yaml config.yaml
# abra e ajuste os campos em config.yaml (roots, categories)
```

2. Instale dependências e ative o ambiente:

```bash
bash install.sh
source venv/bin/activate
```

3. Faça um teste rápido com um arquivo real:

```bash
# Verifique se o Ollama está ativo
ollama status

# Verifique o Python do venv
./venv/bin/python -V

# Teste o organizer em um arquivo de exemplo (ajuste o caminho para um arquivo real)
./venv/bin/python src/organizer.py ~/Downloads/exemplo.pdf
```

> Dica: se tudo funcionar, rode o modo observador: `./venv/bin/python src/watcher.py ~/Downloads`

## ⚙️ Personalização Avançada (config.yaml)
O coração deste projeto é o arquivo `config.yaml`. É aqui que você define como a IA deve **classificar** e para onde os arquivos devem ir. O sistema usa uma taxonomia flexível que você pode adaptar ao seu fluxo.

Consulte `config.example.yaml` como referência antes de editar.

### Como criar uma nova categoria
Para adicionar uma nova regra, insira um novo bloco na seção `categories`. A IA usa o campo `description` para entender o contexto do arquivo.

```yaml
categories:
  # Nome da chave (usado internamente pelo script)
  freelas_design:
    # Para onde o arquivo vai (suporta variáveis como {drive} ou {docs})
    path: "{drive}/Trabalho/Freelance/Design"

    # Cor da etiqueta no Finder (Red, Orange, Yellow, Green, Blue, Purple, Gray)
    tag: "Purple"

    # O texto que orienta a IA. Seja específico!
    description: "Projetos de design, arquivos .psd, .ai, briefings de clientes, invoices de freela."
```

### Dicas de prompting na descrição
A IA lê a descrição para decidir. Para melhores resultados:

- Seja explícito: em vez de "Coisas de banco", use "Extratos bancários, comprovantes de Pix, informes de rendimentos".
- Use palavras-chave: inclua nomes recorrentes de fornecedores ou clientes (ex: "Notas fiscais da AWS").
- Indique exclusões: por exemplo, "Exames médicos (NÃO incluir recibos de pagamento de consultas)".

### Variáveis de caminho
Use variáveis na seção `roots` para facilitar o compartilhamento:

- `{drive}`: caminho base (pode apontar para Google Drive/Dropbox montado).
- `{docs}`: atalho para sua pasta de Documentos.
- `{local_dl}`: sua pasta de Downloads (local monitorado pelo watcher).

Este projeto foi iniciado para uso pessoal; personalize a **taxonomia** conforme seu perfil, criando suas próprias variáveis em `roots` e usando-as nos caminhos das categorias.

---

### Verificação rápida (testes básicos / smoke tests) ✅
Após a instalação, execute estas verificações básicas para garantir que tudo está OK:

```bash
# 1) Ollama: verifique se o daemon/modelo está pronto
ollama status

# 2) Python: versão do venv
./venv/bin/python -V

# 3) Rodar o organizer em um arquivo de teste
./venv/bin/python src/organizer.py ~/Downloads/exemplo.pdf

```

Outras verificações:
- Conceda **Full Disk Access** (Preferências do Sistema → Privacidade e Segurança → Full Disk Access) se o organizador não ler pastas.
- Se estiver usando `launchd`, verifique logs em `/tmp/smart-organizer.*.log` ou carregue o job e confira `launchctl list | grep smart-organizer`.
- Teste o "Droplet": arraste um arquivo para o app criado na Mesa e confira se o arquivo é processado (ou verifique `/tmp` para logs de erro).


---

## 📖 Como usar

### 1) Aplicativo Desktop (Droplet) 🍎
Durante a instalação, o script cria automaticamente um aplicativo na sua Área de Trabalho chamado "Organizar com IA".

**O que é**

Um pequeno aplicativo macOS (droplet) que serve como atalho direto para o organizador.

#### Como usar

Basta arrastar e soltar qualquer arquivo (ou vários) para cima do ícone do aplicativo. 

**Feedback:** Você ouvirá um som de notificação ("Glass") quando a organização for concluída.

#### Como funciona

Ele executa um AppleScript interno que aciona o ambiente Python especificamente para os arquivos arrastados.

#### Dica: 

Dica: Você pode arrastar este aplicativo para o seu Dock para ter acesso rápido sempre que precisar organizar um arquivo manualmente.

### 2) Execução manual
Organize arquivos específicos (por padrão aceita curingas):

```bash
./venv/bin/python src/organizer.py ~/Downloads/*
```
### 3) Execução com o Automator
Torne o processo invisível e integrado ao Finder do macOS.

1. Abra o app **Automator** no seu Mac.
2. Escolha **Ação de Pasta (Folder Action)**.
3. No topo, onde diz **"A ação de pasta recebe arquivos adicionados a"**, selecione sua pasta `Downloads`.
4. Na barra lateral, procure por **Executar Script do Shell (Run Shell Script)** e arraste para o fluxo de trabalho.

Configure as opções da ação:

- **Shell:** `/bin/bash`
- **Passar entrada:** **como argumentos** (isso é crucial)

Cole o seguinte script (substitua `SEU_USUARIO` pelo seu usuário):

```bash
# --- CONFIGURAÇÃO ---
# Substitua pelo seu usuário real
USER_HOME="/Users/SEU_USUARIO"
# Ajuste se salvou o projeto em outro local
PROJECT_DIR="$USER_HOME/Scripts/smart-mac-organizer"

# --- EXECUÇÃO ---
PYTHON_CMD="$PROJECT_DIR/venv/bin/python"
SCRIPT_PY="$PROJECT_DIR/src/organizer.py"

# Log de Debug (erros serão acrescentados em /tmp/automator_error.log)
exec 2>>/tmp/automator_error.log

# Garante que estamos na pasta do projeto para ler o config.yaml
cd "$PROJECT_DIR"

# Executa o script passando os arquivos novos como argumento
"$PYTHON_CMD" "$SCRIPT_PY" "$@"
```

Salve a ação com o nome **"Smart Organizer"** (Cmd+S).

---

## 🧭 Arquitetura & Fluxo

1. Para cada arquivo, coleta texto (OCR) e metadados.
2. O modelo local (Ollama) decide categoria e nome sugerido.
3. O arquivo é renomeado/movido conforme regras no `config.yaml`.

---

## 🩺 Solução de problemas

- Ollama não conectado: verifique `ollama status` e se o modelo `qwen2.5:3b` foi baixado.
- OCR fraco em imagens: confira se o Apple Vision tem permissão para acessar arquivos e teste com imagens de alta qualidade.
- Permissões no macOS: conceda **Full Disk Access** se arquivos não estiverem sendo lidos.
- `tag` não aplica cores: verifique se o utilitário `tag` está instalado (`which tag`).

Se encontrar um erro, anote a mensagem do Python e abra uma issue anexando trechos do log.

---

## ❓ FAQ

**P: O Ollama não encontra o modelo `qwen2.5:3b` — o que faço?**
R: Execute `ollama list`; se o modelo não aparecer, faça `ollama pull qwen2.5:3b`. Verifique `ollama status` para confirmar que o daemon está ativo.

**P: O OCR não extrai texto corretamente — tem solução?**
R: A qualidade do OCR depende da imagem/PDF. Tente imagens com maior resolução/contraste ou converta para PDF de alta qualidade. Ajuste suas categorias para reduzir ambiguidade.

**P: Como evitar que arquivos sejam movidos incorretamente?**
R: Teste com uma pasta de rascunho, refine as `description` das categorias e use a execução manual para validar nomes sugeridos antes de mover em massa.

**P: O projeto envia dados para a nuvem?**
R: Não — todo o processamento e os modelos são locais, a menos que você opte por integrar serviços externos de forma explícita.

---

## 🤝 Contribuindo

Contribuições são bem-vindas!

- Abra uma issue antes de mudanças grandes.
- Faça um fork, crie uma branch, escreva testes e envie um PR.

---

## 📄 Licença

Este projeto está licenciado sob a **MIT License** — veja `LICENSE`.

---

#### Contato

Se quiser colaborar, sugestões ou bugs, abra uma issue ou envie um PR no repositório.
