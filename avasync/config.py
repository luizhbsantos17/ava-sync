"""Leitura do config.toml.

Por que um arquivo de configuracao: o codigo fica igual para todo mundo; o que
muda de pessoa para pessoa (site do Moodle, pasta de saida, materias a ignorar,
qual IA usar) fica no config.toml, que NAO vai para o Git (.gitignore).
"""
import os
import sys
try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass
class IAConfig:
    provedor: str = "nenhum"          # nenhum | openai | anthropic | gemini
    modelo: str = ""
    base_url: str = ""                # so para provedor "openai" (OpenAI, OpenRouter, Groq, Ollama, LM Studio...)
    api_key_env: str = ""             # NOME da variavel de ambiente com a chave (a chave nunca fica no arquivo)
    max_tokens: int = 2500
    temperatura: float = 0.3
    prompt: str = "prompts/guia_atividade.md"
    max_chars_anexos: int = 20000     # quanto texto dos anexos (PDF/DOCX) mandar para a IA
    guias_por_execucao: int = 10      # limite para nao gastar demais numa rodada


@dataclass
class Config:
    site: str
    pasta_saida: Path
    servico: str = "moodle_mobile_app"
    keyring_servico: str = ""
    fuso_horas: int = -3
    max_download_mb: int = 200
    ignorar_cursos: list = field(default_factory=list)   # trechos de nome (sem diferenciar maiusculas)
    somente_cursos: list = field(default_factory=list)   # se preenchido, so estes
    ia: IAConfig = field(default_factory=IAConfig)
    envio_auto_rascunho: bool = False   # [envio] auto_rascunho
    servidor_porta: int = 8765          # [envio] porta do painel local

    # pastas derivadas
    @property
    def disc(self): return self.pasta_saida / "01_DISCIPLINAS"
    @property
    def cal(self): return self.pasta_saida / "02_CALENDARIO"
    @property
    def rel(self): return self.pasta_saida / "03_RELATORIOS"
    @property
    def interno(self): return self.pasta_saida / ".avasync"
    @property
    def chave_keyring(self): return self.keyring_servico or f"ava-sync:{self.site}"


def carregar(caminho=None) -> Config:
    caminho = Path(caminho or os.environ.get("AVASYNC_CONFIG") or RAIZ / "config.toml")
    if not caminho.exists():
        sys.exit(f"Nao achei {caminho}. Copie config.example.toml para config.toml e preencha.")
    with open(caminho, "rb") as f:
        d = tomllib.load(f)
    ia = IAConfig(**d.pop("ia", {}))
    envio = d.pop("envio", {})
    d["envio_auto_rascunho"] = bool(envio.get("auto_rascunho", False))
    d["servidor_porta"] = int(envio.get("porta", 8765))
    if not d.get("site") or not d.get("pasta_saida"):
        sys.exit("config.toml precisa de 'site' e 'pasta_saida'.")
    d["site"] = d["site"].rstrip("/")
    d["pasta_saida"] = Path(os.path.expandvars(os.path.expanduser(d["pasta_saida"])))
    return Config(ia=ia, **d)
