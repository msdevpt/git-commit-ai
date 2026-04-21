# 🤖 git-commit-ai

Gera mensagens de commit inteligentes com ajuda de modelos locais via [Ollama](https://ollama.com). 
Ideal para quem quer automatizar e melhorar a qualidade dos commits sem depender de serviços externos.

## ✨ Funcionalidades

- Geração automática de mensagens de commit com base nas alterações do repositório
- Suporte a múltiplos modelos locais (ex: `llama3.2`, `qwen2.5-coder`, `mistral`)
- Interface por linha de comandos com argumentos opcionais
- Suporte a português e inglês
- Modo debug para inspeção detalhada

## 📦 Requisitos

- Python 3.10+
- [Ollama](https://ollama.com) instalado e com modelos disponíveis localmente
- Git instalado e acessível via terminal

## 🚀 Instalação

```bash
git clone https://github.com/msdevpt/git-commit-ai.git
cd git-commit-ai
pip install -r requirements.txt
```

## ▶️ Exemplos de uso:

```bash
# Usar português (padrão)
python git_commit_ai.py

# Usar inglês
python git_commit_ai.py --lang en

# Com debug
python git_commit_ai.py --lang en --debug

# Repositório específico
python git_commit_ai.py --repo /caminho/para/repo --lang pt

# Todos os argumentos (Ollama)
python git_commit_ai.py --model llama3.2 --lang en --repo ./meu-projeto --debug

# Usar OpenRouter (necessita variável de ambiente OPENROUTER_API_KEY)
export OPENROUTER_API_KEY="sua_chave_aqui"
python git_commit_ai.py --provider openrouter --model openrouter/auto --lang en

# Usar OpenRouter com variável de ambiente customizada
export MINHA_API_KEY="sua_chave_aqui"
python git_commit_ai.py --provider openrouter --api-key-env MINHA_API_KEY --model openrouter/auto --lang en

# Definir timeout da API (ex.: 60 s)
python git_commit_ai.py --api-timeout 60
```

## ⚙️ Argumentos disponíveis

| Argumento      | Descrição                                      | Padrão                 |
|----------------|------------------------------------------------|-----------------------|
| `--provider`   | Provedor de IA (`ollama` ou `openrouter`)     | `ollama`              |
| `--model`      | Nome do modelo a usar (dependente do provedor) | `llama3.2`            |
| `--repo`       | Caminho para o repositório Git                 | diretório atual        |
| `--lang`       | Idioma da mensagem (`pt` ou `en`)              | `pt`                  |
| `--debug`      | Ativa modo verboso para depuração              | `False`               |
| `--api-timeout`| Timeout (segundos) para chamadas à API        | `30.0`                |
| `--api-key-env`| Nome da variável de ambiente com a API‑key (só usado por OpenRouter) | `OPENROUTER_API_KEY` |


## 🧠 Modelos suportados

```bash
ollama pull llama3.2
ollama pull qwen2.5-coder
```

## 🧪 Ambiente isolado com Miniconda

Para evitar instalar dependências globalmente, recomenda-se usar [Miniconda](https://docs.conda.io/en/latest/miniconda.html) para criar um ambiente virtual:

### 🔧 Passos para configurar

```bash
# Criar um novo ambiente com Python 3.10 (ou versão compatível)
conda create -n git-commit-ai python=3.10

# Ativar o ambiente
conda activate git-commit-ai

# Instalar as dependências do projeto
pip install -r requirements.txt
