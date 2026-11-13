import datetime as dt
import html
import re
from pathlib import Path

try:
    import html2text
except ImportError:
    html2text = None

_TZ = dt.timezone(dt.timedelta(hours=-3))
_LOG = None


def configurar(fuso_horas: int, arquivo_log: Path):
    global _TZ, _LOG
    _TZ = dt.timezone(dt.timedelta(hours=fuso_horas))
    _LOG = arquivo_log


def tz():
    return _TZ


def log(msg):
    linha = f"{dt.datetime.now(_TZ):%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha)
    if _LOG:
        try:
            _LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass


def nome_seguro(texto, limite=80):
    """Titulo -> nome de arquivo/pasta valido no Windows, Linux e macOS."""
    texto = html.unescape(texto or "sem_nome")
    texto = re.sub(r"[/\\]", "-", texto)
    texto = re.sub(r'[<>:"|?*\x00-\x1f]', "", texto)
    texto = re.sub(r"\s+", " ", texto).strip().rstrip(".")
    return texto[:limite].strip() or "sem_nome"


def data(ts):
    return dt.datetime.fromtimestamp(int(ts), _TZ).strftime("%d/%m/%Y %H:%M") if ts else "-"


def data_iso(ts):
    return dt.datetime.fromtimestamp(int(ts), _TZ).strftime("%Y-%m-%d") if ts else "sem-data"


def para_md(html_txt):
    """HTML do Moodle -> Markdown."""
    if not html_txt:
        return ""
    if html2text:
        h = html2text.HTML2Text()
        h.body_width = 0
        return h.handle(html_txt).strip()
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", html_txt, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def escrever_se_mudou(caminho: Path, conteudo: str) -> bool:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists() and caminho.read_text(encoding="utf-8") == conteudo:
        return False
    caminho.write_text(conteudo, encoding="utf-8")
    return True
