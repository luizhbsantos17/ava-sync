"""Sync com livro, link, pagina e rotulo com imagens (API e rede SIMULADAS)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from avasync import config, midia, moodle, painel, sync, util
from tests.test_mock import R, fake_baixar
from tests.test_midia import FakeMoodle, fake_get

SITE = "https://moodle.exemplo"
IMG = f'<img src="{SITE}/pluginfile.php/5/mod_label/intro/esquema.png">'


class TesteSyncMidia(unittest.TestCase):
    def test_sync_baixa_livro_link_e_imagens(self):
        r = copy.deepcopy(R)
        r["core_course_get_contents"][0]["modules"] += [
            {"name": "Rotulo", "modname": "label", "description": f"<p>Esquema</p>{IMG}"},
            {"name": "Notas de aula", "modname": "url",
             "contents": [{"type": "url", "fileurl": "https://prof.exemplo/notas.html"}]},
            {"name": "Livro", "modname": "book", "url": f"{SITE}/mod/book/view.php?id=4", "contents": [
                {"type": "file", "filename": "index.html", "filepath": "/11/", "content": "Cap 1",
                 "fileurl": f"{SITE}/webservice/pluginfile.php/9/mod_book/chapter/11/index.html"}]}]
        r["mod_page_get_pages_by_courses"] = {"pages": [{"course": 10, "name": "Pagina", "intro": "",
                                                         "content": f"<p>Oi</p>{IMG}"}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            p.write_text(f'site = "{SITE}"\npasta_saida = "{Path(d).as_posix()}/saida"\n', encoding="utf-8")
            cfg = config.carregar(str(p))
            util.configurar(-3, cfg.interno / "t.log")
            with mock.patch.object(moodle.Moodle, "call", lambda self, f, **k: r[f]), \
                 mock.patch.object(moodle.Moodle, "baixar", fake_baixar), \
                 mock.patch.object(moodle.Moodle, "ler", lambda self, u: FakeMoodle().ler(u)), \
                 mock.patch.object(midia.requests, "get", fake_get), \
                 mock.patch.object(sync, "pegar_token", lambda cfg: "X"):
                sync.sync(cfg)
            curso = cfg.disc / "Redes de Computadores 2026-2"
            mat = curso / "Materiais" / "Semana 1"
            self.assertTrue((mat / "Livro" / "LIVRO.html").exists())
            self.assertTrue((mat / "Links" / "Notas de aula.html").exists())
            conteudo = (curso / "CONTEUDO_DA_DISCIPLINA.md").read_text(encoding="utf-8")
            self.assertIn("](Materiais/_imagens/", conteudo)
            self.assertIn("_imagens/", (curso / "Materiais" / "Paginas" / "Pagina.md").read_text(encoding="utf-8"))
            html = painel.gerar(cfg).read_text(encoding="utf-8")
            self.assertIn("LIVRO.html", html)
            mats = [x for m in painel.coletar()["materias"] for x in m["materiais"]]
            self.assertIn("LIVRO.html", [x["nome"] for x in mats])
            self.assertFalse([x for x in mats if "_imagens" in x["grupo"] or "_arquivos" in x["grupo"]])  # pastas de imagens nao poluem a lista


if __name__ == "__main__":
    unittest.main()
