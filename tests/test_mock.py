"""Teste ponta a ponta com respostas SIMULADAS da API (nao acessa nenhum Moodle)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from avasync import config, ia, moodle, painel, sync, util

R = {
    "core_webservice_get_site_info": {"userid": 5, "fullname": "Aluno Teste", "functions": [1]},
    "core_course_get_enrolled_courses_by_timeline_classification": {"courses": [
        {"id": 10, "fullname": "Redes de Computadores 2026/2", "enddate": 0},
        {"id": 11, "fullname": "Biblioteca Virtual", "enddate": 0},
        {"id": 12, "fullname": "Calculo I 2025", "enddate": 1000}]},
    "mod_assign_get_assignments": {"courses": [{"id": 10, "assignments": [
        {"id": 1, "cmid": 99, "name": "Relatorio Lab", "duedate": 4102444800, "grade": 10,
         "intro": "<p>Faca o <b>relatorio</b></p>",
         "introattachments": [{"filename": "roteiro.txt", "fileurl": "u", "filesize": 3}]}]}]},
    "mod_assign_get_submission_status": {"lastattempt": {"submission": {"status": "new"}}},
    "mod_quiz_get_quizzes_by_courses": {"quizzes": [{"id": 2, "course": 10, "name": "Prova 1",
                                                      "timeopen": 4102444800, "timeclose": 4102531200}]},
    "mod_page_get_pages_by_courses": {"pages": []},
    "mod_forum_get_forums_by_courses": [{"id": 3, "course": 10, "name": "Avisos"}],
    "mod_forum_get_forum_discussions": {"discussions": [
        {"discussion": 8, "name": "Aula cancelada", "created": 1794900000, "message": "<p>Sem aula</p>"}]},
    "core_calendar_get_action_events_by_timesort": {"events": []},
    "core_course_get_contents": [{"name": "Semana 1", "summary": "<p>Leia o cap 1</p>", "modules": [
        {"name": "Slides", "modname": "resource",
         "contents": [{"type": "file", "filename": "slides.pdf", "fileurl": "f", "filesize": 3}]}]}],
}


def fake_baixar(self, url, destino, tamanho=None):
    if destino.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"abc")
    return True


class TesteSync(unittest.TestCase):
    def test_fluxo_completo(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "config.toml"
            cfg_path.write_text(f'site = "https://moodle.exemplo"\npasta_saida = "{Path(d).as_posix()}/saida"\n'
                                f'ignorar_cursos = ["Biblioteca"]\n[ia]\nprovedor = "openai"\nmodelo = "teste"\n',
                                encoding="utf-8")
            cfg = config.carregar(str(cfg_path))
            util.configurar(-3, cfg.interno / "t.log")
            with mock.patch.object(moodle.Moodle, "call", lambda self, f, **p: R[f]), \
                 mock.patch.object(moodle.Moodle, "baixar", fake_baixar), \
                 mock.patch.object(sync, "pegar_token", lambda cfg: "X"):
                sync.sync(cfg)
                sync.sync(cfg)  # 2a vez nao pode repetir novidades
            resumo = json.loads((cfg.rel / "ultima_sincronizacao.json").read_text(encoding="utf-8"))
            self.assertEqual([x["nome"] for x in resumo["disciplinas"]], ["Redes de Computadores 2026/2"])
            self.assertEqual(resumo["novidades"], [])
            self.assertEqual((cfg.rel / "novidades.md").read_text(encoding="utf-8").count("## "), 1)
            ativ = next((cfg.disc / "Redes de Computadores 2026-2" / "Atividades").glob("*.md"))
            self.assertIn("NAO ENTREGUE", ativ.read_text(encoding="utf-8"))

            # IA com provedor simulado
            with mock.patch.object(ia, "perguntar", lambda c, s, u: "# Guia: teste\nok"):
                self.assertEqual(ia.gerar_guias(cfg), 2)  # tarefa + prova
                self.assertEqual(ia.gerar_guias(cfg), 0)  # nada mudou
            guia = cfg.disc / "Redes de Computadores 2026-2" / "Guias" / (ativ.stem + ".md")
            self.assertIn("gerado_por: avasync-ia", guia.read_text(encoding="utf-8"))

            # guia escrito por agente nao e sobrescrito
            guia.write_text("---\ngerado_por: claude-cowork\n---\n# meu guia\n", encoding="utf-8")
            with mock.patch.object(ia, "perguntar", lambda c, s, u: "NOVO"):
                ia.gerar_guias(cfg, forcar=True)
            self.assertIn("meu guia", guia.read_text(encoding="utf-8"))

            html = painel.gerar(cfg).read_text(encoding="utf-8")
            self.assertIn("Relatorio Lab", html)
            self.assertNotIn("gerado_por: claude-cowork", html)


if __name__ == "__main__":
    unittest.main()
