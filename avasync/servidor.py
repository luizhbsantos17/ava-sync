"""Painel com envio: servidor local em http://127.0.0.1:<porta>.

Por que um servidor e nao so o PAINEL.html?
  Uma pagina aberta direto do disco (file://) nao consegue falar com o Moodle: o
  navegador bloqueia (CORS) e ela precisaria do token. Aqui o navegador fala so com
  este programa, no seu proprio computador, e e o Python que usa o token (que continua
  no cofre de credenciais e nunca vai para a pagina).

Seguranca:
  - escuta apenas em 127.0.0.1 (outros computadores da rede nao alcancam);
  - cada execucao gera uma chave aleatoria; toda chamada /api precisa dela no cabecalho
    X-Avasync-Chave, e o Origin precisa ser o proprio painel. Assim, um site qualquer
    aberto no navegador nao consegue disparar um envio;
  - envio exige: digitar ENVIAR; para finalizar, marcar a declaracao de autoria (se a
    tarefa exigir) e confirmar.
"""
import base64
import json
import secrets
import shutil
import tempfile
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import envio, painel, sync
from .util import log

MAX_UPLOAD_MB = 100


def rodar(cfg, abrir=True):
    chave = secrets.token_urlsafe(24)
    porta = cfg.servidor_porta
    origem = f"http://127.0.0.1:{porta}"
    raiz = cfg.pasta_saida.resolve()
    trava = threading.Lock()   # um envio/sync por vez

    def html_painel():
        painel.gerar(cfg)
        h = (raiz / "PAINEL.html").read_text(encoding="utf-8")
        cfg_js = json.dumps({"chave": chave})
        return h.replace("</head>", f"<script>window.AVASYNC={cfg_js};</script></head>", 1)

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(raiz), **k)

        def log_message(self, *a):  # silencioso
            pass

        def _json(self, cod, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(cod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _autorizado(self):
            ok = secrets.compare_digest(self.headers.get("X-Avasync-Chave", ""), chave)
            org = self.headers.get("Origin")
            return ok and (org is None or org == origem)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/PAINEL.html", "/index.html"):
                b = html_painel().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if u.path.startswith("/api/"):
                if not self._autorizado():
                    return self._json(403, {"erro": "nao autorizado"})
                q = parse_qs(u.query)
                try:
                    if u.path == "/api/tarefa":
                        m = envio.conectar(cfg)
                        return self._json(200, envio.info_tarefa(m, envio.achar_tarefa(m, q["id"][0])))
                    if u.path == "/api/fila":
                        return self._json(200, envio.listar_fila(cfg))
                except envio.Cancelado as e:
                    return self._json(400, {"erro": str(e)})
                except Exception as e:  # noqa: BLE001
                    return self._json(500, {"erro": str(e)})
                return self._json(404, {"erro": "?"})
            return super().do_GET()  # arquivos da pasta (materiais, anexos...)

        def do_POST(self):
            u = urlparse(self.path)
            if not self._autorizado():
                return self._json(403, {"erro": "nao autorizado"})
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_UPLOAD_MB * 1024 * 1024 * 1.4:
                return self._json(413, {"erro": f"maximo {MAX_UPLOAD_MB} MB"})
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"erro": "json invalido"})
            if not trava.acquire(blocking=False):
                return self._json(409, {"erro": "outra operacao em andamento"})
            try:
                if u.path == "/api/sync":
                    sync.sync(cfg)
                    painel.gerar(cfg)
                    return self._json(200, {"ok": True})
                if u.path == "/api/enviar":
                    return self._json(200, self._enviar(corpo))
                if u.path == "/api/fila/aprovar":
                    if corpo.get("confirmacao") != "ENVIAR":
                        raise envio.Cancelado("Confirmacao ausente.")
                    m = envio.conectar(cfg)
                    r = envio.processar_pedido(cfg, m, corpo["pedido"], bool(corpo.get("finalizar")),
                                               bool(corpo.get("aceito")), "pessoa (painel)")
                    return self._json(200, r)
                if u.path == "/api/fila/rejeitar":
                    return self._json(200, envio.rejeitar_pedido(cfg, corpo["pedido"], corpo.get("motivo", "")))
                return self._json(404, {"erro": "?"})
            except envio.Cancelado as e:
                return self._json(400, {"erro": str(e)})
            except SystemExit as e:
                return self._json(400, {"erro": str(e)})
            except Exception as e:  # noqa: BLE001
                log(f"servidor: erro em {u.path}: {e}")
                return self._json(500, {"erro": str(e)})
            finally:
                trava.release()

        def _enviar(self, c):
            if c.get("confirmacao") != "ENVIAR":
                raise envio.Cancelado("Digite ENVIAR para confirmar.")
            tmp = Path(tempfile.mkdtemp(prefix="avasync_"))
            try:
                caminhos = []
                for arq in c.get("arquivos", []):
                    nome = Path(arq["nome"]).name
                    p = tmp / nome
                    p.write_bytes(base64.b64decode(arq["base64"]))
                    caminhos.append(p)
                m = envio.conectar(cfg)
                a = envio.achar_tarefa(m, c["tarefa_id"])
                return envio.executar(m, cfg, a, caminhos, c.get("texto") or None,
                                      bool(c.get("finalizar")), bool(c.get("aceito")))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    url = f"{origem}/"
    log(f"Painel com envio em {url}  (Ctrl+C para parar)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
