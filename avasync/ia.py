"""Geracao de guias de estudo por IA, com provedor plugavel.

A ideia: o sync so coleta dados; a IA e uma etapa separada e opcional.
Qualquer IA serve, de dois jeitos:

  1. Por API (este arquivo): configure [ia] no config.toml e rode
         python -m avasync guias
     Provedores:
       - "openai"    -> qualquer API compativel com OpenAI: OpenAI, OpenRouter, Groq,
                        DeepSeek, Ollama (local, gratis), LM Studio... (muda so base_url/modelo)
       - "anthropic" -> Claude pela API da Anthropic
       - "gemini"    -> Google Gemini
  2. Por agente (Claude Cowork, Codex, Gemini CLI, Copilot...): o agente le as pastas
     e escreve os guias seguindo o contrato do AGENTS.md. Nenhum codigo necessario.

As chaves de API NUNCA ficam no config: ele guarda so o NOME da variavel de
ambiente (api_key_env), e a chave fica na variavel.
"""
import datetime as dt
import hashlib
import os
import re
from pathlib import Path

import requests

from .config import RAIZ
from .util import escrever_se_mudou, log, tz

MARCA = "avasync-ia"


# ------------------------------------------------------------------ provedores
def _chave(cfg_ia):
    if not cfg_ia.api_key_env:
        return ""
    k = os.environ.get(cfg_ia.api_key_env, "")
    if not k:
        raise RuntimeError(f"Variavel de ambiente {cfg_ia.api_key_env} vazia (coloque a chave da API nela).")
    return k


def perguntar(cfg_ia, sistema: str, usuario: str) -> str:
    p = cfg_ia.provedor.lower()
    if p == "openai":
        url = (cfg_ia.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        cab = {"Content-Type": "application/json"}
        k = _chave(cfg_ia)
        if k:
            cab["Authorization"] = f"Bearer {k}"
        r = requests.post(url, headers=cab, timeout=300, json={
            "model": cfg_ia.modelo, "temperature": cfg_ia.temperatura, "max_tokens": cfg_ia.max_tokens,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    if p == "anthropic":
        r = requests.post((cfg_ia.base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages",
                          timeout=300, headers={"x-api-key": _chave(cfg_ia), "anthropic-version": "2023-06-01",
                                                "content-type": "application/json"},
                          json={"model": cfg_ia.modelo, "max_tokens": cfg_ia.max_tokens,
                                "temperature": cfg_ia.temperatura, "system": sistema,
                                "messages": [{"role": "user", "content": usuario}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    if p == "gemini":
        base = (cfg_ia.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        r = requests.post(f"{base}/models/{cfg_ia.modelo}:generateContent", timeout=300,
                          headers={"x-goog-api-key": _chave(cfg_ia), "Content-Type": "application/json"},
                          json={"systemInstruction": {"parts": [{"text": sistema}]},
                                "contents": [{"role": "user", "parts": [{"text": usuario}]}],
                                "generationConfig": {"temperature": cfg_ia.temperatura,
                                                     "maxOutputTokens": cfg_ia.max_tokens}})
        r.raise_for_status()
        return "".join(pt.get("text", "") for pt in r.json()["candidates"][0]["content"]["parts"])
    raise RuntimeError(f"Provedor de IA desconhecido: {cfg_ia.provedor!r} (use openai, anthropic ou gemini)")


# ------------------------------------------------------------------ anexos -> texto
def texto_de_arquivo(p: Path, limite: int) -> str:
    suf = p.suffix.lower()
    try:
        if suf in (".md", ".txt", ".csv", ".py", ".java", ".sql", ".c", ".html"):
            return p.read_text(encoding="utf-8", errors="ignore")[:limite]
        if suf == ".pdf":
            from pypdf import PdfReader  # opcional: pip install pypdf
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)[:limite]
        if suf == ".docx":
            import docx  # opcional: pip install python-docx
            return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)[:limite]
    except ImportError:
        return f"(nao consegui ler {p.name}: instale pypdf / python-docx para extrair texto)"
    except Exception as e:  # noqa: BLE001
        return f"(erro lendo {p.name}: {e})"
    return f"(arquivo {p.name} nao e texto; so o nome foi considerado)"


# ------------------------------------------------------------------ guias
def _frontmatter(texto):
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    if not m:
        return {}
    return dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)


def _pendente(md):
    entregue = re.search(r"Situacao: \*\*ENTREGUE\*\*", md)
    return not entregue


def gerar_guias(cfg, forcar=False):
    ia = cfg.ia
    if ia.provedor.lower() in ("", "nenhum", "none"):
        log("IA desativada no config.toml ([ia] provedor = \"nenhum\"). Use um agente seguindo o AGENTS.md.")
        return 0
    prompt_path = Path(ia.prompt)
    if not prompt_path.is_absolute():
        prompt_path = RAIZ / prompt_path
    modelo_prompt = prompt_path.read_text(encoding="utf-8")
    sistema, _, usuario_tpl = modelo_prompt.partition("\n===USUARIO===\n")
    feitos = 0
    hoje = dt.datetime.now(tz()).strftime("%d/%m/%Y")

    for pasta in sorted(p for p in cfg.disc.iterdir() if p.is_dir()) if cfg.disc.exists() else []:
        for sec in ("Atividades", "Provas"):
            for f in sorted((pasta / sec).glob("*.md")) if (pasta / sec).exists() else []:
                if f.name.upper() == "README.MD" or feitos >= ia.guias_por_execucao:
                    continue
                md = f.read_text(encoding="utf-8")
                if not _pendente(md):
                    continue
                anexos_dir = f.parent / (f.stem + "_anexos")
                anexos = sorted(a for a in anexos_dir.iterdir() if a.is_file()) if anexos_dir.exists() else []
                h = hashlib.sha256((md + "|".join(a.name for a in anexos)).encode()).hexdigest()[:16]
                guia = pasta / "Guias" / f"{f.stem}.md"
                if guia.exists():
                    fm = _frontmatter(guia.read_text(encoding="utf-8"))
                    if fm.get("gerado_por", "").strip() != MARCA:
                        continue          # guia escrito por pessoa/agente: nunca sobrescreve
                    if fm.get("fonte_hash", "").strip() == h and not forcar:
                        continue          # atividade nao mudou
                txt_anexos, resto = "", ia.max_chars_anexos
                for a in anexos:
                    t = texto_de_arquivo(a, resto)
                    txt_anexos += f"\n\n### Anexo: {a.name}\n{t}"
                    resto -= len(t)
                    if resto <= 0:
                        break
                usuario = (usuario_tpl.replace("{disciplina}", pasta.name).replace("{hoje}", hoje)
                           .replace("{atividade}", md).replace("{anexos}", txt_anexos or "(sem anexos)"))
                log(f"IA ({ia.provedor}/{ia.modelo}): guia para {pasta.name} / {f.stem}")
                try:
                    resposta = perguntar(ia, sistema.strip(), usuario)
                except Exception as e:  # noqa: BLE001
                    log(f"  erro na IA: {e}")
                    continue
                cab = (f"---\ngerado_por: {MARCA}\nprovedor: {ia.provedor}\nmodelo: {ia.modelo}\n"
                       f"fonte: {sec}/{f.name}\nfonte_hash: {h}\ngerado_em: {dt.datetime.now(tz()).isoformat()}\n---\n")
                escrever_se_mudou(guia, cab + resposta.strip() + "\n")
                feitos += 1
    log(f"{feitos} guia(s) gerado(s).")
    return feitos
