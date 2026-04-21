#!/usr/bin/env python3
"""
Git Commit Message Generator com IA Local (Ollama)
Analisa alterações em stage e sugere mensagens de commit usando IA local.

Requisitos:
- Git instalado e configurado
- Ollama rodando localmente
- Python 3.10+
- Bibliotecas: requests, subprocess

Uso: python git_commit_ai.py [--model modelo] [--repo caminho]
"""

import subprocess
import json
import argparse
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests
from datetime import datetime
from prompt_toolkit import prompt
from abc import ABC, abstractmethod

# ---------------------------------------------------------------------------
# Prompt utilities – shared between all AI providers
# ---------------------------------------------------------------------------

class PromptBuilder:
    """Mixin that contains all prompt‑construction and response‑parsing helpers.

    Keeping this logic separate means both ``OllamaClient`` and ``OpenRouterClient``
    can reuse the same behaviour without code duplication.
    """

    def _build_prompt(self, git_changes: Dict[str, Any], language: str = "pt") -> str:
        """Constrói o prompt a ser enviado à IA.

        The implementation is identical to the previous version that lived inside
        ``OllamaClient``; it was moved here so other providers can call it.
        """
        files_changed = ', '.join(git_changes['files'][:10])  # limit displayed files
        file_types = self._analyze_file_types(git_changes['files'])
        change_context = self._analyze_change_context(git_changes['diff'], git_changes['status'])
        if language == "pt":
            prompt = f"""És um desenvolvedor experiente a analisar alterações do Git para sugerir mensagens de commit convencionais.

FICHEIROS ALTERADOS ({git_changes['file_count']} ficheiros):
{files_changed}

TIPOS DE FICHEIRO: {file_types}

ESTATÍSTICAS DAS ALTERAÇÕES:
{git_changes['stats']}

ESTADO DO GIT:
{git_changes['status']}

DIFF DO CÓDIGO (principais alterações):
{git_changes['diff'][:1800]}

ANÁLISE DAS ALTERAÇÕES:
{change_context}

CRÍTICO: Responde APENAS com 3 mensagens de commit, uma por linha. Sem explicações, sem numeração, sem texto extra.

Requisitos para cada mensagem:
- Usa formato conventional commit: tipo(âmbito): descrição
- Tipos: feat, fix, docs, style, refactor, test, chore, build, ci, perf, revert
- Máximo 25-60 caracteres
- Modo imperativo (adiciona, corrige, actualiza)
- Sê específico sobre O QUE mudou

Formato dos exemplos:
feat(api): adiciona endpoint de autenticação
fix: resolve referência nula no mapper  
refactor: extrai lógica de validação para serviço
chore: atualizar dependências do projeto

Gera exactamente 3 linhas:"""
        else:
            prompt = f"""You are an expert developer analyzing Git changes to suggest conventional commit messages.

FILES CHANGED ({git_changes['file_count']} files):
{files_changed}

FILE TYPES: {file_types}

CHANGE STATISTICS:
{git_changes['stats']}

GIT STATUS:
{git_changes['status']}

CODE DIFF (key changes):
{git_changes['diff'][:1800]}

CHANGE ANALYSIS:
{change_context}

CRITICAL: Respond ONLY with 3 commit messages, one per line. No explanations, no numbering, no extra text.

Requirements for each message:
- Use conventional commit format: type(scope): description
- Types: feat, fix, docs, style, refactor, test, chore, build, ci, perf, revert
- 25-60 characters max
- Imperative mood (add, fix, update)
- Be specific about WHAT changed

Examples format:
feat(api): add user authentication endpoint
fix: resolve null pointer in data mapper
refactor: extract validation logic to service

Generate exactly 3 lines:"""
        return prompt

    def _analyze_file_types(self, files: List[str]) -> str:
        extensions = {}
        for file in files:
            ext = Path(file).suffix.lower()
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
            else:
                extensions['no_extension'] = extensions.get('no_extension', 0) + 1
        file_summary = []
        for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
            if ext == 'no_extension':
                file_summary.append(f"config/other files ({count})")
            else:
                file_summary.append(f"{ext} ({count})")
        return ', '.join(file_summary[:5])

    def _analyze_change_context(self, diff: str, status: str) -> str:
        contexts = []
        if 'A  ' in status:
            contexts.append("New files added")
        if 'M  ' in status:
            contexts.append("Files modified")
        if 'D  ' in status:
            contexts.append("Files deleted")
        if 'R  ' in status:
            contexts.append("Files renamed/moved")
        diff_lower = diff.lower()
        if any(keyword in diff_lower for keyword in ['class ', 'function ', 'def ', 'public ', 'private ']):
            contexts.append("Code structure changes")
        if any(keyword in diff_lower for keyword in ['test', 'spec', 'unit', 'integration']):
            contexts.append("Test-related changes")
        if any(keyword in diff_lower for keyword in ['config', 'setting', 'parameter', '.json', '.xml', '.yml']):
            contexts.append("Configuration changes")
        if any(keyword in diff_lower for keyword in ['bug', 'fix', 'error', 'exception', 'null']):
            contexts.append("Bug fixes")
        if any(keyword in diff_lower for keyword in ['api', 'endpoint', 'controller', 'service']):
            contexts.append("API/Service layer")
        if any(keyword in diff_lower for keyword in ['database', 'migration', 'schema', 'entity']):
            contexts.append("Database changes")
        if any(keyword in diff_lower for keyword in ['readme', 'doc', 'comment', '///', 'xml doc']):
            contexts.append("Documentation updates")
        return ', '.join(contexts) if contexts else "General code changes"

    def _parse_suggestions(self, response: str) -> List[str]:
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        suggestions = []
        skip_patterns = [
            'here are', 'suggestions', 'commit message', 'conventional',
            'three', 'following', 'provide', 'generate', 'examples',
            'requirements', 'instructions', 'note:', 'remember:'
        ]
        for line in lines:
            clean_line = line.lstrip('123456789.- *•▪▫').strip('"\'`')
            if any(pattern in clean_line.lower() for pattern in skip_patterns):
                continue
            if len(clean_line) < 10 or len(clean_line) > 80:
                continue
            if ':' in clean_line:
                commit_type = clean_line.split(':')[0].strip()
                base_type = commit_type.split('(')[0] if '(' in commit_type else commit_type
                valid = {
                    'feat', 'fix', 'docs', 'style', 'refactor', 'test',
                    'chore', 'build', 'ci', 'perf', 'revert', 'hotfix',
                    'improvement', 'update', 'add', 'remove'
                }
                if base_type.lower() in valid:
                    suggestions.append(clean_line)
            elif any(verb in clean_line.lower()[:20] for verb in ['add', 'fix', 'update', 'remove', 'improve', 'create']):
                suggestions.append(clean_line)
            if len(suggestions) >= 3:
                break
        if not suggestions:
            for line in lines:
                clean_line = line.strip().lstrip('123456789.- *•▪▫').strip('"\'`')
                if 10 <= len(clean_line) <= 80 and not any(p in clean_line.lower() for p in skip_patterns):
                    suggestions.append(clean_line)
                if len(suggestions) >= 3:
                    break
        return suggestions[:3] if suggestions else ["feat: actualizar código"]

# ---------------------------------------------------------------------------
# Abstract AI client interface
# ---------------------------------------------------------------------------

class AbstractAIClient(ABC, PromptBuilder):
    """Base class for any AI provider used by git‑commit‑ai.

    Sub‑classes must implement ``generate_commit_message``. The prompt‑building
    utilities are provided via ``PromptBuilder``.
    """

    @abstractmethod
    def generate_commit_message(self, git_changes: Dict[str, Any], language: str = "pt", debug: bool = False) -> List[str]:
        pass

class GitAnalyzer:
    """Classe para analisar alterações do Git."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self._validate_git_repo()
    
    def _validate_git_repo(self) -> None:
        """Valida se o diretório é um repositório Git."""
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Diretório {self.repo_path} não é um repositório Git válido")
    
    def _run_git_command(self, command: List[str]) -> str:
        """Executa comando Git e retorna o resultado."""
        try:
            result = subprocess.run(
                ["git"] + command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, command, result.stderr)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Erro ao executar comando Git: {e.stderr}")
            return ""
    
    def get_staged_changes(self) -> Dict[str, Any]:
        """Obtém informações detalhadas sobre alterações em stage."""
        # Verifica se há alterações em stage
        staged_files = self._run_git_command(["diff", "--cached", "--name-only"])
        if not staged_files:
            return {"has_changes": False, "message": "Nenhuma alteração em stage encontrada"}
        
        # Obtém estatísticas das alterações
        stats = self._run_git_command(["diff", "--cached", "--stat"])
        
        # Obtém diff detalhado (limitado para não sobrecarregar a IA)
        diff_output = self._run_git_command(["diff", "--cached", "--unified=3"])
        
        # Limita o tamanho do diff para evitar tokens excessivos
        if len(diff_output) > 4000:
            diff_output = diff_output[:4000] + "\n... (diff truncado para economizar tokens)"
        
        # Obtém status dos arquivos
        status_output = self._run_git_command(["status", "--porcelain", "--cached"])
        
        return {
            "has_changes": True,
            "files": staged_files.split('\n') if staged_files else [],
            "stats": stats,
            "diff": diff_output,
            "status": status_output,
            "file_count": len(staged_files.split('\n')) if staged_files else 0
        }

class OllamaClient(AbstractAIClient):
    """Cliente para comunicação com Ollama (default provider)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2", timeout: float = 30.0):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self._validate_connection()

    def _validate_connection(self) -> None:
        """Valida a conexão com o servidor Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                raise ConnectionError("Ollama não está respondendo")
            models = response.json().get('models', [])
            available_models = [m['name'] for m in models]
            if not any(self.model in name for name in available_models):
                print(f"⚠️  Modelo '{self.model}' não encontrado.")
                print(f"Modelos disponíveis: {', '.join(available_models)}")
                if available_models:
                    self.model = available_models[0]
                    print(f"Usando modelo: {self.model}")
                else:
                    raise ValueError("Nenhum modelo disponível no Ollama")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Não foi possível conectar ao Ollama: {e}")

    def generate_commit_message(self, git_changes: Dict[str, Any], language: str = "pt", debug: bool = False) -> List[str]:
        """Envia o prompt ao Ollama e devolve sugestões de commit."""
        prompt = self._build_prompt(git_changes, language)
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "max_tokens": 200,
                    },
                },
                timeout=self.timeout,
            )
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('response', '')
                if debug:
                    print("\n🔍 DEBUG - Resposta raw da IA:")
                    print("-" * 40)
                    print(ai_response)
                    print("-" * 40)
                suggestions = self._parse_suggestions(ai_response)
                return suggestions if suggestions else self._get_fallback_message(language)
            else:
                print(f"Erro na API Ollama: {response.status_code}")
                return self._get_fallback_message(language)
        except requests.exceptions.RequestException as e:
            print(f"Erro ao comunicar com Ollama: {e}")
            return self._get_fallback_message(language)

    def _get_fallback_message(self, language: str) -> List[str]:
        if language == "pt":
            return ["feat: actualização de código"]
        return ["feat: update codebase"]

# ---------------------------------------------------------------------------
# OpenRouter client implementation
# ---------------------------------------------------------------------------

class OpenRouterClient(AbstractAIClient):
    """Cliente para a API OpenRouter.

    A chave de API é lida de uma variável de ambiente (por padrão ``OPENROUTER_API_KEY``).
    """

    def __init__(self, model: str = "openrouter/auto", timeout: float = 30.0, api_key_env: str = "OPENROUTER_API_KEY", base_url: str = "https://openrouter.ai/api/v1"):
        self.model = model
        self.timeout = timeout
        self.base_url = base_url.rstrip('/')
        self.api_key = os.getenv(api_key_env)
        if not self.api_key:
            raise ValueError(f"Variável de ambiente '{api_key_env}' não definida para OpenRouter")
        self._validate_connection()

    def _validate_connection(self) -> None:
        """Valida a conexão realizando uma chamada simples de listagem de modelos."""
        try:
            resp = requests.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=5)
            if resp.status_code != 200:
                raise ConnectionError("OpenRouter não está respondendo corretamente")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Não foi possível conectar ao OpenRouter: {e}")

    def generate_commit_message(self, git_changes: Dict[str, Any], language: str = "pt", debug: bool = False) -> List[str]:
        prompt = self._build_prompt(git_changes, language)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 200,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                # OpenRouter returns `choices[0].message.content`
                ai_response = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                if debug:
                    print("\n🔍 DEBUG - Resposta raw da IA (OpenRouter):")
                    print("-" * 40)
                    print(ai_response)
                    print("-" * 40)
                suggestions = self._parse_suggestions(ai_response)
                return suggestions if suggestions else self._get_fallback_message(language)
            else:
                print(f"Erro na API OpenRouter: {resp.status_code}")
                return self._get_fallback_message(language)
        except requests.exceptions.RequestException as e:
            print(f"Erro ao comunicar com OpenRouter: {e}")
            return self._get_fallback_message(language)

    def _get_fallback_message(self, language: str) -> List[str]:
        if language == "pt":
            return ["feat: actualização de código"]
        return ["feat: update codebase"]


    
    def _build_prompt(self, git_changes: Dict[str, Any], language: str = "pt") -> str:
        """Constrói prompt para IA baseado nas alterações do Git."""
        files_changed = ', '.join(git_changes['files'][:10])  # Limita arquivos mostrados
        
        # Analisa o tipo de mudanças para contexto
        file_types = self._analyze_file_types(git_changes['files'])
        change_context = self._analyze_change_context(git_changes['diff'], git_changes['status'])
        
        if language == "pt":
            prompt = f"""És um desenvolvedor experiente a analisar alterações do Git para sugerir mensagens de commit convencionais.

FICHEIROS ALTERADOS ({git_changes['file_count']} ficheiros):
{files_changed}

TIPOS DE FICHEIRO: {file_types}

ESTATÍSTICAS DAS ALTERAÇÕES:
{git_changes['stats']}

ESTADO DO GIT:
{git_changes['status']}

DIFF DO CÓDIGO (principais alterações):
{git_changes['diff'][:1800]}

ANÁLISE DAS ALTERAÇÕES:
{change_context}

CRÍTICO: Responde APENAS com 3 mensagens de commit, uma por linha. Sem explicações, sem numeração, sem texto extra.

Requisitos para cada mensagem:
- Usa formato conventional commit: tipo(âmbito): descrição
- Tipos: feat, fix, docs, style, refactor, test, chore, build, ci, perf, revert
- Máximo 25-60 caracteres
- Modo imperativo (adiciona, corrige, actualiza)
- Sê específico sobre O QUE mudou

Formato dos exemplos:
feat(api): adiciona endpoint de autenticação
fix: resolve referência nula no mapper  
refactor: extrai lógica de validação para serviço
chore: atualizar dependências do projeto

Gera exactamente 3 linhas:"""
        else:
            prompt = f"""You are an expert developer analyzing Git changes to suggest conventional commit messages.

FILES CHANGED ({git_changes['file_count']} files):
{files_changed}

FILE TYPES: {file_types}

CHANGE STATISTICS:
{git_changes['stats']}

GIT STATUS:
{git_changes['status']}

CODE DIFF (key changes):
{git_changes['diff'][:1800]}

CHANGE ANALYSIS:
{change_context}

CRITICAL: Respond ONLY with 3 commit messages, one per line. No explanations, no numbering, no extra text.

Requirements for each message:
- Use conventional commit format: type(scope): description
- Types: feat, fix, docs, style, refactor, test, chore, build, ci, perf, revert
- 25-60 characters max
- Imperative mood (add, fix, update)
- Be specific about WHAT changed

Examples format:
feat(api): add user authentication endpoint
fix: resolve null pointer in data mapper
refactor: extract validation logic to service

Generate exactly 3 lines:"""
        
        return prompt
    
    def _analyze_file_types(self, files: List[str]) -> str:
        """Analisa tipos de arquivos alterados."""
        extensions = {}
        for file in files:
            ext = Path(file).suffix.lower()
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
            else:
                extensions['no_extension'] = extensions.get('no_extension', 0) + 1
        
        file_summary = []
        for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
            if ext == 'no_extension':
                file_summary.append(f"config/other files ({count})")
            else:
                file_summary.append(f"{ext} ({count})")
        
        return ', '.join(file_summary[:5])
    
    def _analyze_change_context(self, diff: str, status: str) -> str:
        """Analisa o contexto das mudanças para melhorar sugestões."""
        contexts = []
        
        # Analisa o status para entender tipos de mudança
        if 'A  ' in status:
            contexts.append("New files added")
        if 'M  ' in status:
            contexts.append("Files modified")
        if 'D  ' in status:
            contexts.append("Files deleted")
        if 'R  ' in status:
            contexts.append("Files renamed/moved")
        
        # Analisa o diff para padrões comuns
        diff_lower = diff.lower()
        
        if any(keyword in diff_lower for keyword in ['class ', 'function ', 'def ', 'public ', 'private ']):
            contexts.append("Code structure changes")
        
        if any(keyword in diff_lower for keyword in ['test', 'spec', 'unit', 'integration']):
            contexts.append("Test-related changes")
        
        if any(keyword in diff_lower for keyword in ['config', 'setting', 'parameter', '.json', '.xml', '.yml']):
            contexts.append("Configuration changes")
        
        if any(keyword in diff_lower for keyword in ['bug', 'fix', 'error', 'exception', 'null']):
            contexts.append("Bug fixes")
        
        if any(keyword in diff_lower for keyword in ['api', 'endpoint', 'controller', 'service']):
            contexts.append("API/Service layer")
        
        if any(keyword in diff_lower for keyword in ['database', 'migration', 'schema', 'entity']):
            contexts.append("Database changes")
        
        if any(keyword in diff_lower for keyword in ['readme', 'doc', 'comment', '///', 'xml doc']):
            contexts.append("Documentation updates")
        
        return ', '.join(contexts) if contexts else "General code changes"
    
    def _parse_suggestions(self, response: str) -> List[str]:
        """Extrai sugestões de mensagem da resposta da IA com parsing robusto."""
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        suggestions = []
        
        # Patterns que indicam que a linha não é uma sugestão
        skip_patterns = [
            'here are', 'suggestions', 'commit message', 'conventional',
            'three', 'following', 'provide', 'generate', 'examples',
            'requirements', 'instructions', 'note:', 'remember:'
        ]
        
        for line in lines:
            # Remove numeração, bullets e formatação extra
            clean_line = line.lstrip('123456789.- *•▪▫').strip('"\'`')
            
            # Ignora linhas explicativas
            if any(pattern in clean_line.lower() for pattern in skip_patterns):
                continue
            
            # Ignora linhas muito curtas ou muito longas
            if len(clean_line) < 10 or len(clean_line) > 80:
                continue
            
            # Valida formato de conventional commit
            if ':' in clean_line:
                # Extrai o tipo de commit
                commit_type = clean_line.split(':')[0].strip()
                
                # Remove possível scope: feat(api) -> feat
                if '(' in commit_type:
                    base_type = commit_type.split('(')[0]
                else:
                    base_type = commit_type
                
                # Lista de tipos válidos de conventional commits
                valid_types = {
                    'feat', 'fix', 'docs', 'style', 'refactor', 'test', 
                    'chore', 'build', 'ci', 'perf', 'revert', 'hotfix',
                    'improvement', 'update', 'add', 'remove'
                }
                
                # Verifica se é um tipo válido
                if base_type.lower() in valid_types:
                    suggestions.append(clean_line)
            
            # Para caso a IA não use conventional commits, aceita linhas que pareçam commits
            elif any(verb in clean_line.lower()[:20] for verb in ['add', 'fix', 'update', 'remove', 'improve', 'create']):
                suggestions.append(clean_line)
            
            if len(suggestions) >= 3:
                break
        
        # Se ainda não conseguiu, tenta uma abordagem mais agressiva
        if not suggestions:
            print("⚠️  A tentar parsing alternativo...")
            for line in lines:
                clean_line = line.strip().lstrip('123456789.- *•▪▫').strip('"\'`')
                
                # Aceita qualquer linha que tenha características de commit
                if (10 <= len(clean_line) <= 80 and 
                    not any(pattern in clean_line.lower() for pattern in skip_patterns)):
                    suggestions.append(clean_line)
                    
                if len(suggestions) >= 3:
                    break
        
        return suggestions[:3] if suggestions else ["feat: actualizar código"]

class CommitMessageGenerator:
    """Classe principal para geração de mensagens de commit."""
    
    def __init__(self, repo_path: str = ".", ai_client: AbstractAIClient = None, language: str = "pt", debug: bool = False):
        self.git_analyzer = GitAnalyzer(repo_path)
        if ai_client is None:
            raise ValueError("Um cliente de IA deve ser fornecido")
        self.ai_client = ai_client
        self.language = language.lower()
        self.debug = debug
        
        if self.language not in ["pt", "en"]:
            raise ValueError("Idioma deve ser 'pt' ou 'en'")
    
    def generate_suggestions(self) -> None:
        """Gera e exibe sugestões de mensagens de commit."""
        print("🔍 Analisando alterações em stage...")
        
        changes = self.git_analyzer.get_staged_changes()
        
        if not changes["has_changes"]:
            print("❌ " + changes["message"])
            return
        
        print(f"✅ Encontradas alterações em {changes['file_count']} arquivo(s)")
        print(f"📁 Arquivos: {', '.join(changes['files'][:5])}")
        if changes['file_count'] > 5:
            print(f"   ... e mais {changes['file_count'] - 5} arquivo(s)")
        
        print("\n🤖 A gerar sugestões com IA...")
        suggestions = self.ai_client.generate_commit_message(changes, self.language, self.debug)
        
        if self.language == "pt":
            print("\n💡 Sugestões de mensagens de commit:")
            print("=" * 55)
            
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")
            
            print("=" * 55)
            print("\n📋 Para usar uma sugestão:")
            print("git commit -m \"mensagem escolhida\"")
        else:
            print("\n💡 Commit message suggestions:")
            print("=" * 55)
            
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")
            
            print("=" * 55)
            print("\n📋 To use a suggestion:")
            print("git commit -m \"chosen message\"")
        
        # Opção interativa para aplicar commit
        self._interactive_commit(suggestions)
    
    def _interactive_commit(self, suggestions: List[str]) -> None:
        """Permite aplicar commit interactivamente com opção de edição."""
        try:
            if self.language == "pt":
                choice = input("\n🚀 Aplicar alguma sugestão? (1-3 ou Enter para saltar): ").strip()
                
                if choice in ['1', '2', '3']:
                    idx = int(choice) - 1
                    if 0 <= idx < len(suggestions):
                        message = suggestions[idx]
                        
                        # Loop para permitir edição
                        while True:
                            print(f"\n📝 Sugestão selecionada: '{message}'")
                            action = input("Quer (A)plicar, (E)ditar ou (C)ancelar? (a/e/c): ").strip().lower()
                            
                            if action in ['e', 'editar']:
                                # Permite ao utilizador editar a mensagem
                                print("\n✏️  Digite a nova mensagem de commit (ou deixe em branco para cancelar):")
                                print(f"Original: {message}")
                                # new_message = input(f"Nova mensagem: ").strip()

                                new_message = prompt("Nova mensagem: ", default=message)
                                
                                if new_message:
                                    message = new_message
                                    print(f"✅ Mensagem atualizada: '{message}'")
                                else:
                                    print("Edição cancelada.")
                                # Volta ao loop para perguntar o que fazer
                                continue
                            
                            elif action in ['a', 'aplicar']:
                                confirm = input(f"Confirmar commit: '{message}'? (s/N): ").strip().lower()
                                
                                if confirm in ['s', 'sim']:
                                    result = subprocess.run(
                                        ["git", "commit", "-m", message],
                                        cwd=self.git_analyzer.repo_path,
                                        capture_output=True,
                                        text=True
                                    )
                                    
                                    if result.returncode == 0:
                                        print("✅ Commit aplicado com sucesso!")
                                    else:
                                        print(f"❌ Erro ao aplicar commit: {result.stderr}")
                                else:
                                    print("Commit cancelado.")
                                break
                            
                            elif action in ['c', 'cancelar']:
                                print("Operação cancelada.")
                                break
                            
                            else:
                                print("❌ Opção inválida. Use (A)plicar, (E)ditar ou (C)ancelar")
            else:
                choice = input("\n🚀 Apply a suggestion? (1-3 or Enter to skip): ").strip()
                
                if choice in ['1', '2', '3']:
                    idx = int(choice) - 1
                    if 0 <= idx < len(suggestions):
                        message = suggestions[idx]
                        
                        # Loop para permitir edição
                        while True:
                            print(f"\n📝 Selected suggestion: '{message}'")
                            action = input("Do you want to (A)pply, (E)dit or (C)ancel? (a/e/c): ").strip().lower()
                            
                            if action in ['e', 'edit']:
                                # Permite ao utilizador editar a mensagem
                                print("\nType the new commit message (or leave blank to cancel):")
                                print(f"Original: {message}")
                                # new_message = input("New message: ").strip()

                                new_message = prompt("New message: ", default=message)
                                
                                if new_message:
                                    message = new_message
                                    print(f"✅ Message updated: '{message}'")
                                else:
                                    print("Edit cancelled.")
                                # Volta ao loop para perguntar o que fazer
                                continue
                            
                            elif action in ['a', 'apply']:
                                confirm = input(f"Confirm commit: '{message}'? (y/N): ").strip().lower()
                                
                                if confirm in ['y', 'yes']:
                                    result = subprocess.run(
                                        ["git", "commit", "-m", message],
                                        cwd=self.git_analyzer.repo_path,
                                        capture_output=True,
                                        text=True
                                    )
                                    
                                    if result.returncode == 0:
                                        print("✅ Commit applied successfully!")
                                    else:
                                        print(f"❌ Error applying commit: {result.stderr}")
                                else:
                                    print("Commit cancelled.")
                                break
                            
                            elif action in ['c', 'cancel']:
                                print("Operation cancelled.")
                                break
                            
                            else:
                                print("❌ Invalid option. Use (A)pply, (E)dit or (C)ancel")
            
        except (ValueError, KeyboardInterrupt):
            if self.language == "pt":
                print("\nOperação cancelada.")
            else:
                print("\nOperation cancelled.")

def _make_client(provider: str, *, model: str, timeout: float, api_key_env: str) -> AbstractAIClient:
    """Factory that returns an AI client implementation based on ``provider``.

    ``provider`` can be ``ollama`` (default) or ``openrouter``.
    ``api_key_env`` is only consulted for OpenRouter.
    """
    if provider == "ollama":
        return OllamaClient(model=model, timeout=timeout)
    if provider == "openrouter":
        return OpenRouterClient(model=model, timeout=timeout, api_key_env=api_key_env)
    raise ValueError(f"Provider '{provider}' não suportado. Use 'ollama' ou 'openrouter'.")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Gera sugestões de mensagens de commit usando IA local ou OpenRouter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python git_commit_ai.py                     # Ollama (default)
  python git_commit_ai.py --provider openrouter --api-key-env OPENROUTER_API_KEY
  python git_commit_ai.py --lang en --model llama3.2
  python git_commit_ai.py --lang pt --repo /path/to/repo
  python git_commit_ai.py --model codellama --lang en
        """
    )
    
    parser.add_argument(
        "--provider",
        default="ollama",
        choices=["ollama", "openrouter"],
        help="Provedor de IA a ser usado (default: ollama)"
    )
    
    parser.add_argument(
        "--model",
        default="llama3.2",
        help="Modelo a usar no provedor escolhido"
    )
    
    parser.add_argument(
        "--repo",
        default=".",
        help="Caminho para o repositório Git (default: diretório atual)"
    )
    
    parser.add_argument(
        "--lang",
        default="pt",
        help="Idioma para as mensagens (pt ou en, default: pt)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Mostra a resposta raw da IA para debug"
    )
    
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=30.0,
        help="Timeout (segundos) para as requisições à API de IA"
    )
    
    parser.add_argument(
        "--api-key-env",
        default="OPENROUTER_API_KEY",
        help="Nome da variável de ambiente que contém a API‑key (usado só por OpenRouter)"
    )
    
    args = parser.parse_args()
    
    try:
        print("🚀 Git Commit Message Generator")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌍 Idioma: {'Português' if args.lang == 'pt' else 'English'}")
        print(f"🛠️ Provider: {args.provider}")
        print(f"⏱️ Timeout API: {args.api_timeout}s")
        print("-" * 50)
        
        client = _make_client(
            provider=args.provider,
            model=args.model,
            timeout=args.api_timeout,
            api_key_env=args.api_key_env,
        )
        
        generator = CommitMessageGenerator(
            repo_path=args.repo,
            ai_client=client,
            language=args.lang,
            debug=args.debug,
        )
        
        generator.generate_suggestions()
        
    except KeyboardInterrupt:
        print("👋 Operação cancelada pelo utilizador.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
