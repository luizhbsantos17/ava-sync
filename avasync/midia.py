"""Imagens embutidas, livros do Moodle e links externos.

Por que este modulo existe:
  - O texto que o Moodle devolve (paginas, enunciados, avisos, rotulos, capitulos de
    livro) e HTML com <img src="https://SEU-MOODLE/.../pluginfile.php/...">. Essas
    imagens so abrem com login, entao offline elas somem. Aqui cada imagem e baixada
    e o src passa a apontar para o arquivo local.
  - O recurso "Livro" do Moodle nao e um arquivo: sao capitulos em HTML. Aqui eles
    viram um LIVRO.html (para ler) e um LIVRO.md (para busca e agentes de IA).
  - Recursos do tipo URL: se o link e um arquivo (PDF, PPT...), baixa; se e uma
    pagina HTML publica, salva uma copia com as imagens.

Seguranca: o token do Moodle so e anexado a enderecos do PROPRIO Moodle. Para sites
externos a requisicao vai sem token e sem cookies.
"""
import hashlib
import html as html_mod
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

from .util import escrever_se_mudou, log, nome_seguro, para_md

MB = 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (ava-sync; copia pessoal de material de aula)"}
IMG_RE = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*)(["\'])(.*?)\2', re.I | re.S)
HREF_RE = re.compile(r'(<(?:a|link)\b[^>]*?\bhref\s*=\s*)(["\'])(.*?)\2', re.I | re.S)

# links que nunca sao baixados: video, documentos que pedem login, reunioes,
# formularios e bibliotecas virtuais (leitores protegidos)
HOSTS_SO_LINK = (
    "youtube.com", "youtu.be", "vimeo.com", "drive.google.com", "docs.google.com",
    "forms.gle", "forms.office.com", "meet.google.com", "classroom.google.com", "zoom.us",
    "teams.microsoft.com", "sharepoint.com", "onedrive.live.com", "1drv.ms",
    "bvirtual.com.br", "digitalpages.com.br", "minhabiblioteca.com.br", "pearson.com",
    "bibliotecavirtual", "dliportal", "elsevier", "springer.com", "scribd.com",
)
SINAIS_LOGIN = ("login", "signin", "sign-in", "/auth", "sso", "accounts.", "/cas/")


def _ext_por_tipo(ct, url):
    ext = mimetypes.guess_extension(ct or "") if ct else None
    if ext in (None, ".bin", ".ksh"):
        ext = Path(unquote(urlparse(url).path)).suffix[:8] or ".bin"
    return ext


def baixar_externo(url, destino: Path, max_mb):
    """GET sem token e sem cookies. Devolve o content-type, ou None se nao baixou."""
    with requests.get(url, stream=True, timeout=30, headers=UA, allow_redirects=True) as r:
        r.raise_for_status()
        if int(r.headers.get("Content-Length") or 0) > max_mb * MB:
            log(f"  pulei (maior que {max_mb} MB): {url}")
            return None
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".part")
        total = 0
        with open(tmp, "wb") as f:
            for bloco in r.iter_content(256 * 1024):
                total += len(bloco)
                if total > max_mb * MB:
                    break
                f.write(bloco)
        if total > max_mb * MB:
            tmp.unlink(missing_ok=True)
            log(f"  pulei (maior que {max_mb} MB): {url}")
            return None
        tmp.replace(destino)
        return (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()


class Midia:
    def __init__(self, m, cfg):
        self.m, self.cfg = m, cfg
        self.host = urlparse(cfg.site).netloc.lower()
        self.cache = {}
        self.baixar_links = getattr(cfg, "baixar_links", True)
        self.dias_links = getattr(cfg, "atualizar_links_dias", 7)
        self.ignorar = tuple(HOSTS_SO_LINK) + tuple(getattr(cfg, "links_ignorar", []) or [])

    # ---------- imagens ----------
    def eh_moodle(self, url):
        return urlparse(url).netloc.lower() == self.host

    @staticmethod
    def _nome_local(url):
        base = nome_seguro(unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "imagem", 60)
        h = hashlib.sha1(url.split("?token=")[0].encode()).hexdigest()[:8]
        return f"{h}_{base}"

    def baixar_imagem(self, url, pasta: Path):
        """Baixa uma imagem (uma vez so) e devolve o caminho local, ou None."""
        chave = (url, str(pasta))
        if chave in self.cache:
            return self.cache[chave]
        dest = pasta / self._nome_local(url)
        local = None
        try:
            if dest.exists():
                local = dest
            elif self.eh_moodle(url):
                if "/webservice/pluginfile.php" not in url:
                    url_ws = url.replace("/pluginfile.php", "/webservice/pluginfile.php", 1)
                else:
                    url_ws = url
                self.m.baixar(url_ws, dest)
                local = dest if dest.exists() else None
            elif urlparse(url).scheme in ("http", "https"):
                if baixar_externo(url, dest, min(self.m.max_mb, 30)):
                    local = dest
        except Exception as e:  # noqa: BLE001
            log(f"  imagem nao baixada ({e}): {url[:120]}")
        self.cache[chave] = local
        return local

    def localizar(self, html, pasta_img: Path, pasta_doc: Path, base_url=None):
        """Baixa as imagens do HTML e troca o src pelo caminho relativo a pasta_doc."""
        if not html or "<img" not in html.lower():
            return html or ""

        def troca(mt):
            src = html_mod.unescape(mt.group(3)).strip()
            if src.startswith("data:"):
                return mt.group(0)
            if base_url:
                src = urljoin(base_url, src)
            if not src.startswith(("http://", "https://")):
                return mt.group(0)
            p = self.baixar_imagem(src, pasta_img)
            if not p:
                return mt.group(0)
            rel = quote(os.path.relpath(p, pasta_doc).replace(os.sep, "/"))
            return f"{mt.group(1)}{mt.group(2)}{rel}{mt.group(2)}"

        return IMG_RE.sub(troca, html)

    def md(self, html, pasta_img: Path, pasta_doc: Path):
        """HTML do Moodle -> Markdown, com as imagens baixadas e apontando para o disco."""
        return para_md(self.localizar(html, pasta_img, pasta_doc))

    # ---------- livro do Moodle ----------
    def salvar_livro(self, mod, pasta: Path):
        """Capitulos -> LIVRO.html (com imagens) e LIVRO.md. Devolve True se mudou."""
        conteudos = mod.get("contents") or []
        capitulos = {}
        for c in conteudos:
            if c.get("type") == "file" and c.get("filename") == "index.html":
                cid = (c.get("filepath") or "/").strip("/")
                capitulos[cid] = c
        if not capitulos:
            return False
        ordem = []
        estrutura = next((c for c in conteudos if c.get("filename") == "structure"), None)
        try:
            itens = json.loads(estrutura.get("content")) if estrutura else []
        except (TypeError, ValueError):
            itens = []

        def andar(lista, nivel):
            for it in lista or []:
                cid = (it.get("href") or "").split("/")[0]
                ordem.append((cid, it.get("title") or "", nivel))
                andar(it.get("subitems"), nivel + 1)
        andar(itens, 0)
        if not ordem:
            ordem = [(cid, c.get("content") or f"Capitulo {i + 1}", 0)
                     for i, (cid, c) in enumerate(capitulos.items())]

        img = pasta / "_imagens"
        partes_html, partes_md = [], []
        for cid, titulo, nivel in ordem:
            c = capitulos.get(cid)
            if not c:
                continue
            try:
                corpo = self.m.ler(c.get("fileurl"))
            except Exception as e:  # noqa: BLE001
                log(f"  capitulo nao baixado ({titulo}): {e}")
                continue
            corpo = self.localizar(corpo, img, pasta)
            h = "h2" if nivel == 0 else "h3"
            partes_html.append(f'<section id="cap{cid}"><{h}>{html_mod.escape(titulo)}</{h}>\n{corpo}\n</section>')
            partes_md.append(f"{'##' if nivel == 0 else '###'} {titulo}\n\n{para_md(corpo)}\n")
        if not partes_html:
            return False
        nome = mod.get("name") or "Livro"
        sumario = "".join(f'<li style="margin-left:{n * 18}px"><a href="#cap{c}">{html_mod.escape(t)}</a></li>'
                          for c, t, n in ordem if c in capitulos)
        pagina = (
            "<!doctype html><html lang=\"pt-br\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html_mod.escape(nome)}</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;line-height:1.6}"
            "img{max-width:100%;height:auto}section{border-top:1px solid #ddd;margin-top:28px}"
            "pre{white-space:pre-wrap;background:#f4f4f4;padding:8px}</style></head><body>"
            f"<h1>{html_mod.escape(nome)}</h1><p><small>Copia offline feita pelo ava-sync. "
            f"Original: <a href=\"{html_mod.escape(mod.get('url') or '')}\">{html_mod.escape(mod.get('url') or '')}</a></small></p>"
            f"<nav><b>Sumario</b><ul>{sumario}</ul></nav>" + "\n".join(partes_html) + "</body></html>\n")
        a = escrever_se_mudou(pasta / "LIVRO.html", pagina)
        b = escrever_se_mudou(pasta / "LIVRO.md", f"# {nome}\n\nOriginal: {mod.get('url') or '-'}\n\n" + "\n".join(partes_md))
        return a or b

    # ---------- links externos (recurso URL) ----------
    def salvar_link(self, url, nome, pasta: Path):
        """Baixa o arquivo do link ou salva uma copia da pagina. Devolve o caminho salvo ou None."""
        if not self.baixar_links or not url or not url.startswith(("http://", "https://")):
            return None
        host = urlparse(url).netloc.lower()
        if self.eh_moodle(url) or any(h in host for h in self.ignorar):
            return None
        base = nome_seguro(nome, 80)
        existentes = [p for p in pasta.glob("*") if p.is_file() and p.stem == base and not p.name.endswith(".part")]
        if existentes and time.time() - max(p.stat().st_mtime for p in existentes) < self.dias_links * 86400:
            return None
        try:
            with requests.get(url, stream=True, timeout=30, headers=UA, allow_redirects=True) as r:
                if r.status_code >= 400:
                    log(f"  link {r.status_code}: {url}")
                    return None
                final = r.url.lower()
                if final != url.lower() and any(s in final for s in SINAIS_LOGIN):
                    log(f"  link pede login, ficou so o endereco: {url}")
                    return None
                ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                tam = int(r.headers.get("Content-Length") or 0)
                if tam > self.m.max_mb * MB:
                    log(f"  link maior que {self.m.max_mb} MB, ficou so o endereco: {url}")
                    return None
                if ct in ("text/html", "application/xhtml+xml"):
                    bruto = r.raw.read(10 * MB, decode_content=True)
                    texto = bruto.decode(r.encoding or r.apparent_encoding or "utf-8", errors="replace")
                    return self._salvar_pagina(texto, r.url, url, base, pasta)
        except Exception as e:  # noqa: BLE001
            log(f"  link nao baixado ({e}): {url}")
            return None
        # arquivo (pdf, pptx, zip...): baixa de novo, agora gravando no disco
        try:
            dest = pasta / (base + _ext_por_tipo(ct, url))
            if baixar_externo(url, dest, self.m.max_mb):
                return dest
        except Exception as e:  # noqa: BLE001
            log(f"  link nao baixado ({e}): {url}")
        return None

    def _salvar_pagina(self, texto, url_final, url, base, pasta: Path):
        if any(s in texto.lower() for s in ('type="password"', "type='password'")):
            log(f"  link e uma tela de login, ficou so o endereco: {url}")
            return None
        local = self.localizar(texto, pasta / f"{base}_arquivos", pasta, base_url=url_final)
        aviso = f"<!-- copia salva pelo ava-sync de {html_mod.escape(url)} -->\n"
        # links e estilos relativos passam a apontar para o site original (as imagens ja sao locais)
        def absoluto(mt):
            alvo = html_mod.unescape(mt.group(3)).strip()
            if alvo.startswith(("#", "http://", "https://", "mailto:", "data:", "javascript:")):
                return mt.group(0)
            return f"{mt.group(1)}{mt.group(2)}{html_mod.escape(urljoin(url_final, alvo))}{mt.group(2)}"
        local = HREF_RE.sub(absoluto, local)
        dest = pasta / f"{base}.html"
        escrever_se_mudou(dest, aviso + local)
        escrever_se_mudou(pasta / f"{base}.md", f"# {base}\n\nFonte: {url}\n\n{para_md(local)}\n")
        return dest
