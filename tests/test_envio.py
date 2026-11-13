"""Testa o fluxo de envio com API simulada (nao acessa nenhum Moodle)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from avasync import config, envio, moodle, util

A = {"id": 7, "cmid": 70, "name": "E04 Projeto", "duedate": 4102444800, "submissiondrafts": 1,
     "requiresubmissionstatement": 1, "submissionstatement": "<p>E meu trabalho.</p>",
     "configs": [{"plugin": "file", "name": "maxfilesubmissions", "value": "1"}]}


class FakeResp:
    def __init__(self, j): self._j = j
    def raise_for_status(self): pass
    def json(self): return self._j


class TesteEnvio(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        p = Path(self.d.name) / "config.toml"
        p.write_text(f'site = "https://m.ex"\npasta_saida = "{Path(self.d.name).as_posix()}/s"\n', encoding="utf-8")
        self.cfg = config.carregar(str(p))
        util.configurar(-3, None)
        self.pdf = Path(self.d.name) / "x.pdf"
        self.pdf.write_bytes(b"%PDF")
        self.chamadas = []

    def call(self, m, f, **p):
        self.chamadas.append((f, p))
        return {"core_webservice_get_site_info": {"userid": 1},
                "core_course_get_enrolled_courses_by_timeline_classification": {"courses": [{"id": 1, "fullname": "PS"}]},
                "mod_assign_get_assignments": {"courses": [{"id": 1, "assignments": [dict(A)]}]},
                "mod_assign_get_submission_status": {"lastattempt": {"canedit": True, "submission": {"status": "new"}}},
                "mod_assign_save_submission": [], "mod_assign_submit_for_grading": []}[f]

    def rodar(self, respostas, finalizar):
        with mock.patch.object(moodle.Moodle, "call", lambda m, f, **p: self.call(m, f, **p)), \
             mock.patch.object(envio, "pegar_token", lambda c: "T"), \
             mock.patch("sys.stdin.isatty", lambda: True), \
             mock.patch("builtins.input", side_effect=respostas), \
             mock.patch("requests.Session.post", lambda *a, **k: FakeResp([{"itemid": 555}])):
            return envio.enviar(self.cfg, "E04", [str(self.pdf)], finalizar=finalizar)

    def test_cancela_sem_ENVIAR(self):
        with self.assertRaises(envio.Cancelado):
            self.rodar(["sim"], False)
        self.assertNotIn("mod_assign_save_submission", [c[0] for c in self.chamadas])

    def test_envia_e_finaliza_com_declaracao(self):
        self.rodar(["ENVIAR", "ACEITO", "FINALIZAR"], True)
        nomes = [c[0] for c in self.chamadas]
        self.assertIn("mod_assign_save_submission", nomes)
        save = dict(self.chamadas[nomes.index("mod_assign_save_submission")][1])
        self.assertEqual(save["plugindata[files_filemanager]"], 555)
        fin = dict(self.chamadas[nomes.index("mod_assign_submit_for_grading")][1])
        self.assertEqual(fin["acceptsubmissionstatement"], 1)

    def test_sem_terminal_recusa(self):
        with mock.patch("sys.stdin.isatty", lambda: False), self.assertRaises(SystemExit):
            envio.enviar(self.cfg, "E04", [str(self.pdf)])

    def tearDown(self):
        self.d.cleanup()


if __name__ == "__main__":
    unittest.main()
