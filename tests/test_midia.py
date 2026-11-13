"""Imagens, livros e links, com rede SIMULADA (nao acessa nenhum site)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from avasync import midia, util

SITE = "https://moodle.exemplo"


class FakeMoodle:
    max_mb = 50

    def __init__(self):
        self.baixados, self.lidos = [], []

    def baixar(self, url, destino, tamanho=None):
        self.baixados.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"PNG")
        return True

    def ler(self, url):
        self.lidos.append(url)
        cap = url.split("/chapter/")[1].split("/")[0]
        return f'<p>Texto do capitulo {cap}</p><img src="{SITE}/webservice/pluginfile.php/9/mod_book/chapter/{cap}/fig.png">'


class Resp:
    def __init__(self, url, ct, corpo=b"", status=200):
        self.url, self.status_code, self.encoding, self.apparent_encoding = url, status, "utf-8", "utf-8"
        self.headers = {"Content-Type": ct, "Content-Length": str(len(corpo))}
        self._c = corpo
        self.raw = SimpleNamespace(read=lambda n, decode_content=True: corpo[:n])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, n):
        yield self._c


WEB = {
    "https://prof.exemplo/notas.html": ("text/html", b'<html><head></head><body><h1>Notas</h1>'
                                       b'<img src="img/rede.png"><a href="cap2.html">prox</a></body></html>'),
    "https://prof.exemplo/img/rede.png": ("image/png", b"PNG"),
    "https://prof.exemplo/lista.pdf": ("application/pdf", b"%PDF-1.4"),
    "https://restrito.exemplo/x": ("text/html", b'<form><input type="password"></form>'),
}


def fake_get(url, **k):
    assert "token" not in url, "token nunca vai para site externo"
    ct, corpo = WEB.get(url, ("text/html", b""))
    return Resp(url, ct, corpo)


class TesteMidia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        util.configurar(-3, self.d / "t.log")
        self.m = FakeMoodle()
        self.cfg = SimpleNamespace(site=SITE, baixar_links=True, atualizar_links_dias=7, links_ignorar=[])
        self.mi = midia.Midia(self.m, self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_imagens_do_moodle_e_externas(self):
        html = (f'<p>Veja</p><img src="{SITE}/pluginfile.php/5/mod_page/content/1/diagrama%20A.png">'
                '<img src="https://outro.exemplo/foto.jpg"><img src="data:image/png;base64,AAA">')
        with mock.patch.object(midia.requests, "get", fake_get):
            md = self.mi.md(html, self.d / "Materiais" / "_imagens", self.d / "Atividades")
        self.assertIn("/webservice/pluginfile.php/", self.m.baixados[0])  # Moodle: via webservice + token
        self.assertIn("](../Materiais/_imagens/", md)
        self.assertEqual(len(list((self.d / "Materiais" / "_imagens").iterdir())), 2)
        self.assertIn("data:image/png", md)

    def test_livro(self):
        estrutura = [{"title": "Introducao", "href": "11/index.html", "level": 0,
                      "subitems": [{"title": "Detalhe", "href": "12/index.html", "level": 1}]}]
        mod = {"name": "Livro de Redes", "modname": "book", "url": f"{SITE}/mod/book/view.php?id=3", "contents": [
            {"type": "content", "filename": "structure", "content": json.dumps(estrutura)},
            {"type": "file", "filename": "index.html", "filepath": "/12/",
             "fileurl": f"{SITE}/webservice/pluginfile.php/9/mod_book/chapter/12/index.html"},
            {"type": "file", "filename": "index.html", "filepath": "/11/",
             "fileurl": f"{SITE}/webservice/pluginfile.php/9/mod_book/chapter/11/index.html"}]}
        pasta = self.d / "Livro de Redes"
        self.assertTrue(self.mi.salvar_livro(mod, pasta))
        h = (pasta / "LIVRO.html").read_text(encoding="utf-8")
        self.assertLess(h.index("Introducao</h2>"), h.index("Detalhe</h3>"))
        self.assertIn('src="_imagens/', h)
        self.assertIn("Texto do capitulo 12", (pasta / "LIVRO.md").read_text(encoding="utf-8"))
        self.assertFalse(self.mi.salvar_livro(mod, pasta))  # nada mudou

    def test_links(self):
        pasta = self.d / "Links"
        with mock.patch.object(midia.requests, "get", fake_get):
            pdf = self.mi.salvar_link("https://prof.exemplo/lista.pdf", "Lista 1", pasta)
            pag = self.mi.salvar_link("https://prof.exemplo/notas.html", "Notas de aula", pasta)
            self.assertIsNone(self.mi.salvar_link("https://www.youtube.com/watch?v=x", "Video", pasta))
            self.assertIsNone(self.mi.salvar_link("https://restrito.exemplo/x", "Restrito", pasta))
            self.assertIsNone(self.mi.salvar_link(f"{SITE}/mod/forum/view.php?id=1", "Forum", pasta))
            self.assertIsNone(self.mi.salvar_link("https://prof.exemplo/notas.html", "Notas de aula", pasta))  # recente
        self.assertEqual(pdf.name, "Lista 1.pdf")
        h = pag.read_text(encoding="utf-8")
        self.assertIn('src="Notas%20de%20aula_arquivos/', h)
        self.assertIn('href="https://prof.exemplo/cap2.html"', h)
        self.assertTrue((pasta / "Notas de aula.md").exists())


if __name__ == "__main__":
    unittest.main()
