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

class OllamaClient:
    """Cliente para comunicação com Ollama."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._validate_connection()
    
    def _validate_connection(self) -> None:
        """Valida conexão com Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                raise ConnectionError("Ollama não está respondendo")
            
            models = response.json().get('models', [])
            available_models = [m['name'] for m in models]
            
            if not any(self.model in model_name for model_name in available_models):
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
        """Gera sugestões de mensagens de commit usando IA."""
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
                        "max_tokens": 200
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('response', '')
                
                if debug:
                    print(f"\n🔍 DEBUG - Resposta raw da IA:")
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
        """Retorna mensagens de fallback baseadas no idioma."""
        if language == "pt":
            return ["feat: actualização de código"]
        else:
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
    
    def __init__(self, repo_path: str = ".", ollama_model: str = "llama3.2", language: str = "pt", debug: bool = False):
        self.git_analyzer = GitAnalyzer(repo_path)
        self.ollama_client = OllamaClient(model=ollama_model)
        self.language = language.lower()
        self.debug = debug
        
        # Validar idioma
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
        suggestions = self.ollama_client.generate_commit_message(changes, self.language, self.debug)
        
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
        """Permite aplicar commit interactivamente."""
        try:
            if self.language == "pt":
                choice = input("\n🚀 Aplicar alguma sugestão? (1-3 ou Enter para saltar): ").strip()
                
                if choice in ['1', '2', '3']:
                    idx = int(choice) - 1
                    if 0 <= idx < len(suggestions):
                        message = suggestions[idx]
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
            else:
                choice = input("\n🚀 Apply a suggestion? (1-3 or Enter to skip): ").strip()
                
                if choice in ['1', '2', '3']:
                    idx = int(choice) - 1
                    if 0 <= idx < len(suggestions):
                        message = suggestions[idx]
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
            
        except (ValueError, KeyboardInterrupt):
            if self.language == "pt":
                print("\nOperação cancelada.")
            else:
                print("\nOperation cancelled.")

def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Gera sugestões de mensagens de commit usando IA local",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python git_commit_ai.py
  python git_commit_ai.py --lang en --model llama3.2
  python git_commit_ai.py --lang pt --repo /path/to/repo
  python git_commit_ai.py --model codellama --lang en
        """
    )
    
    parser.add_argument(
        "--model", 
        default="llama3.2",
        help="Modelo Ollama a usar (default: llama3.2)"
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
    
    args = parser.parse_args()
    
    try:
        print("🚀 Git Commit Message Generator com IA")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌍 Idioma: {'Português' if args.lang == 'pt' else 'English'}")
        print("-" * 50)
        
        generator = CommitMessageGenerator(
            repo_path=args.repo,
            ollama_model=args.model,
            language=args.lang,
            debug=args.debug
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