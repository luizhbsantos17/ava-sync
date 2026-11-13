"""Servidor local: exige chave, recusa outra origem e envia com confirmacao (API simulada)."""
import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from avasync import config, envio, servidor, util


class TesteServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        p = Path(cls.d.name) / "config.toml"
        p.write_text(f'site = "https://m.ex"\npasta_saida = "{Path(cls.d.name).as_posix()}/s"\n[envio]\nporta = 8799\n',
                     encoding="utf-8")
        cls.cfg = config.carregar(str(p))
        cls.cfg.pasta_saida.mkdir(parents=True)
        util.configurar(-3, None)
        cls.enviados = []
        fake = mock.MagicMock()
        cls.p1 = mock.patch.object(envio, "conectar", lambda cfg: fake)
        cls.p2 = mock.patch.object(envio, "achar_tarefa", lambda m, b: {"id": 7, "name": "E04"})
        cls.p3 = mock.patch.object(envio, "executar",
                                   lambda m, cfg, a, arqs, txt, fin, ace: cls.enviados.append(
                                       ([x.read_bytes() for x in arqs], fin, ace)) or {"situacao": "submitted",
                                                                                       "ja_enviados": ["x.pdf"]})
        for p_ in (cls.p1, cls.p2, cls.p3):
            p_.start()
        chave = {}
        orig = servidor.secrets.token_urlsafe
        cls.p4 = mock.patch.object(servidor.secrets, "token_urlsafe", lambda n: chave.setdefault("k", orig(n)))
        cls.p4.start()
        threading.Thread(target=servidor.rodar, args=(cls.cfg, False), daemon=True).start()
        time.sleep(0.5)
        cls.chave = chave["k"]

    @classmethod
    def tearDownClass(cls):
        for p_ in (cls.p1, cls.p2, cls.p3, cls.p4):
            p_.stop()

    def post(self, path, corpo, chave=None, origem="http://127.0.0.1:8799"):
        req = urllib.request.Request("http://127.0.0.1:8799" + path, data=json.dumps(corpo).encode(), method="POST",
                                     headers={"X-Avasync-Chave": chave or "", "Origin": origem,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_sem_chave_403(self):
        self.assertEqual(self.post("/api/enviar", {"confirmacao": "ENVIAR"})[0], 403)

    def test_outra_origem_403(self):
        self.assertEqual(self.post("/api/enviar", {"confirmacao": "ENVIAR"}, self.chave, "https://site-mau.com")[0], 403)

    def test_sem_confirmacao_400(self):
        self.assertEqual(self.post("/api/enviar", {"tarefa_id": 7}, self.chave)[0], 400)

    def test_envia(self):
        cod, r = self.post("/api/enviar", {"tarefa_id": 7, "confirmacao": "ENVIAR", "finalizar": True, "aceito": True,
                                           "arquivos": [{"nome": "x.pdf", "base64": base64.b64encode(b"%PDF").decode()}]},
                           self.chave)
        self.assertEqual(cod, 200)
        self.assertEqual(self.enviados[-1], ([b"%PDF"], True, True))

    def test_pagina_tem_chave(self):
        with urllib.request.urlopen("http://127.0.0.1:8799/") as r:
            self.assertIn("window.AVASYNC", r.read().decode())


if __name__ == "__main__":
    unittest.main()
