"""Sincronizacao: le o Moodle e escreve as pastas (somente leitura no Moodle)."""
import datetime as dt
import json
import sys
import time

from .moodle import Moodle, pegar_token
from .util import data, data_iso, escrever_se_mudou, log, nome_seguro, para_md, tz


def filtrar_cursos(cfg, cursos, agora):
    """Tira cursos que nao interessam: os da lista ignorar_cursos, os ja encerrados
    (enddate no passado) e, se somente_cursos estiver preenchido, tudo que nao estiver nela."""
    saida = []
    for c in cursos:
        nome = (c.get("fullname") or "").lower()
        if cfg.somente_cursos and not any(s.lower() in nome for s in cfg.somente_cursos):
            continue
        if any(s.lower() in nome for s in cfg.ignorar_cursos):
            continue
        if c.get("enddate") and c["enddate"] < agora:
            continue
        saida.append(c)
    return saida


def sync(cfg):
    m = Moodle(cfg.site, pegar_token(cfg), cfg.max_download_mb)
    STATE_FILE = cfg.interno / "estado.json"
    REL, DISC, CAL, SITE = cfg.rel, cfg.disc, cfg.cal, cfg.site
    agora = int(time.time())
    estado = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {"vistos": {}}
    vistos = estado.setdefault("vistos", {})
    novidades = []   # o que apareceu de novo desde a ultima execucao
    resumo = {"gerado_em": dt.datetime.now(tz()).isoformat(), "disciplinas": []}

    try:
        site = m.call("core_webservice_get_site_info")
    except PermissionError:
        msg = "TOKEN INVALIDO OU EXPIRADO - rode:  python -m avasync login"
        log(msg)
        escrever_se_mudou(REL / "STATUS.md", f"# Status da sincronizacao\n\n**{msg}**\n\nUltima tentativa: {data(agora)}\n")
        sys.exit(2)
    userid = site["userid"]
    log(f"Conectado como {site.get('fullname')} - {len(site.get('functions', []))} funcoes liberadas")

    cursos = m.call("core_course_get_enrolled_courses_by_timeline_classification",
                    classification="inprogress").get("courses", [])
    cursos = filtrar_cursos(cfg, cursos, agora)
    ids = [c["id"] for c in cursos]
    log(f"{len(cursos)} disciplinas em andamento")

    # chamadas que aceitam varios cursos de uma vez
    assigns = m.tentar("mod_assign_get_assignments", {"courses": []}, courseids=ids) or {"courses": []}
    quizzes = m.tentar("mod_quiz_get_quizzes_by_courses", {"quizzes": []}, courseids=ids) or {"quizzes": []}
    pages = m.tentar("mod_page_get_pages_by_courses", {"pages": []}, courseids=ids) or {"pages": []}
    foruns = m.tentar("mod_forum_get_forums_by_courses", [], courseids=ids) or []
    eventos = m.tentar("core_calendar_get_action_events_by_timesort", {"events": []},
                       timesortfrom=agora - 7 * 86400, limitnum=50) or {"events": []}

    assign_por_curso = {c["id"]: c.get("assignments", []) for c in assigns.get("courses", [])}

    for c in cursos:
        cid = c["id"]
        nome = nome_seguro(c.get("fullname") or c.get("shortname"))
        pasta = DISC / nome
        info = {"id": cid, "nome": c.get("fullname"), "pasta": str(pasta),
                "tarefas": [], "questionarios": [], "avisos": [], "arquivos_novos": 0}
        log(f"- {nome}")

        # 1) estrutura da materia: textos das secoes + arquivos
        conteudo = m.tentar("core_course_get_contents", [], courseid=cid) or []
        md = [f"# {c.get('fullname')}\n", f"Link: {SITE}/course/view.php?id={cid}\n"]
        for sec in conteudo:
            md.append(f"\n## {sec.get('name') or 'Secao'}\n")
            if sec.get("summary"):
                md.append(para_md(sec["summary"]) + "\n")
            for mod in sec.get("modules", []):
                if not mod.get("uservisible", True):
                    continue
                linha = f"- **{mod.get('name')}** ({mod.get('modname')})"
                if mod.get("url"):
                    linha += f" - {mod['url']}"
                md.append(linha)
                if mod.get("description"):
                    md.append("  " + para_md(mod["description"]).replace("\n", "\n  "))
                for arq in mod.get("contents", []) or []:
                    if arq.get("type") == "url":
                        md.append(f"  - link externo: {arq.get('fileurl')}")
                    elif arq.get("type") == "file" and mod.get("modname") in ("resource", "folder"):
                        sub = nome_seguro(sec.get("name") or "Geral", 50)
                        dest = pasta / "Materiais" / sub / nome_seguro(arq.get("filename"), 120)
                        try:
                            if m.baixar(arq.get("fileurl"), dest, arq.get("filesize")):
                                info["arquivos_novos"] += 1
                                novidades.append(f"[{nome}] material novo: {arq.get('filename')}")
                        except Exception as e:  # noqa: BLE001
                            log(f"  erro ao baixar {arq.get('filename')}: {e}")
        escrever_se_mudou(pasta / "CONTEUDO_DA_DISCIPLINA.md", "\n".join(md) + "\n")

        # 2) tarefas (enunciado completo + situacao da entrega)
        for a in assign_por_curso.get(cid, []):
            st = m.tentar("mod_assign_get_submission_status", {}, assignid=a["id"], userid=userid) or {}
            sub = (st.get("lastattempt") or {}).get("submission") or {}
            situacao = {"new": "NAO ENTREGUE", "draft": "RASCUNHO (nao enviado)",
                        "submitted": "ENTREGUE", "reopened": "REABERTA"}.get(sub.get("status"), sub.get("status") or "desconhecida")
            nota = ((st.get("feedback") or {}).get("gradefordisplay")) or "-"
            prazo = a.get("duedate")
            arq_md = pasta / "Atividades" / f"{data_iso(prazo)}_{nome_seguro(a.get('name'))}.md"
            anexos = []
            for f in a.get("introattachments", []) or []:
                d = arq_md.parent / (arq_md.stem + "_anexos") / nome_seguro(f.get("filename"), 120)
                try:
                    m.baixar(f.get("fileurl"), d, f.get("filesize"))
                except Exception as e:  # noqa: BLE001
                    log(f"  erro anexo {f.get('filename')}: {e}")
                anexos.append(f"- {f.get('filename')} -> {d.name}")
            texto = (
                f"# {a.get('name')}\n\n"
                f"- Disciplina: {c.get('fullname')}\n"
                f"- Entrega: **{data(prazo)}**\n"
                f"- Data limite (atraso): {data(a.get('cutoffdate'))}\n"
                f"- Abre em: {data(a.get('allowsubmissionsfromdate'))}\n"
                f"- Nota maxima: {a.get('grade')}\n"
                f"- Situacao: **{situacao}**\n"
                f"- Nota/feedback: {nota}\n"
                f"- Link: {SITE}/mod/assign/view.php?id={a.get('cmid')}\n\n"
                f"## Enunciado\n\n{para_md(a.get('intro')) or '(sem descricao)'}\n"
                + (f"\n## Instrucoes da atividade\n\n{para_md(a.get('activity'))}\n" if a.get("activity") else "")
                + ("\n## Anexos do professor\n\n" + "\n".join(anexos) + "\n" if anexos else "")
            )
            escrever_se_mudou(arq_md, texto)
            chave = f"assign:{a['id']}"
            if chave not in vistos:
                novidades.append(f"[{nome}] tarefa nova: {a.get('name')} (entrega {data(prazo)})")
            vistos[chave] = prazo
            info["tarefas"].append({"id": a["id"], "nome": a.get("name"), "entrega": prazo, "situacao": situacao,
                                    "arquivo": str(arq_md)})

        # 3) questionarios / provas online
        for q in [q for q in quizzes.get("quizzes", []) if q.get("course") == cid]:
            arq_md = pasta / "Provas" / f"{data_iso(q.get('timeclose') or q.get('timeopen'))}_{nome_seguro(q.get('name'))}.md"
            escrever_se_mudou(arq_md, (
                f"# {q.get('name')}\n\n"
                f"- Abre: **{data(q.get('timeopen'))}**\n- Fecha: **{data(q.get('timeclose'))}**\n"
                f"- Tempo limite: {int(q.get('timelimit') or 0) // 60} min\n"
                f"- Tentativas permitidas: {q.get('attempts') or 'ilimitadas'}\n"
                f"- Link: {SITE}/mod/quiz/view.php?id={q.get('coursemodule')}\n\n"
                f"## Descricao\n\n{para_md(q.get('intro')) or '(sem descricao)'}\n"))
            chave = f"quiz:{q['id']}"
            if chave not in vistos:
                novidades.append(f"[{nome}] questionario/prova: {q.get('name')} (fecha {data(q.get('timeclose'))})")
            vistos[chave] = q.get("timeclose")
            info["questionarios"].append({"nome": q.get("name"), "abre": q.get("timeopen"),
                                          "fecha": q.get("timeclose"), "arquivo": str(arq_md)})

        # 4) paginas de conteudo (texto inteiro)
        for p in [p for p in pages.get("pages", []) if p.get("course") == cid]:
            escrever_se_mudou(pasta / "Materiais" / "Paginas" / f"{nome_seguro(p.get('name'))}.md",
                              f"# {p.get('name')}\n\n{para_md(p.get('intro'))}\n\n{para_md(p.get('content'))}\n")

        # 5) avisos e foruns (ultimas discussoes)
        for fo in [f for f in foruns if f.get("course") == cid]:
            disc = m.tentar("mod_forum_get_forum_discussions", {"discussions": []},
                            forumid=fo["id"], sortorder=1, page=0, perpage=15) or {"discussions": []}
            for d in disc.get("discussions", []):
                arq_md = pasta / "Anuncios" / f"{data_iso(d.get('created'))}_{nome_seguro(d.get('name'))}.md"
                escrever_se_mudou(arq_md, (
                    f"# {d.get('name')}\n\n- Forum: {fo.get('name')}\n- Autor: {d.get('userfullname')}\n"
                    f"- Data: {data(d.get('created'))}\n- Link: {SITE}/mod/forum/discuss.php?d={d.get('discussion')}\n\n"
                    f"{para_md(d.get('message'))}\n"))
                chave = f"post:{d.get('discussion')}"
                if chave not in vistos:
                    novidades.append(f"[{nome}] aviso: {d.get('name')}")
                vistos[chave] = d.get("created")
                info["avisos"].append({"titulo": d.get("name"), "data": d.get("created"), "arquivo": str(arq_md)})

        resumo["disciplinas"].append(info)

    # 6) calendario consolidado
    linhas = ["# Prazos (gerado automaticamente)\n", f"Atualizado: {data(agora)}\n",
              "| Data | Disciplina | Item | Situacao |", "|---|---|---|---|"]
    itens = []
    for dsc in resumo["disciplinas"]:
        for t in dsc["tarefas"]:
            if t["entrega"]:
                itens.append((t["entrega"], dsc["nome"], "Tarefa: " + t["nome"], t["situacao"]))
        for q in dsc["questionarios"]:
            if q["fecha"]:
                itens.append((q["fecha"], dsc["nome"], "Questionario/prova: " + q["nome"], "-"))
    for ev in eventos.get("events", []):
        itens.append((ev.get("timesort"), (ev.get("course") or {}).get("fullname", "-"),
                      "Evento: " + (ev.get("name") or ""), "-"))
    vistos_cal = set()
    for ts, disc_nome, item, sit in sorted(i for i in itens if i[0]):
        if (ts, item) in vistos_cal:
            continue
        vistos_cal.add((ts, item))
        marca = " (passou)" if ts < agora else ""
        linhas.append(f"| {data(ts)}{marca} | {disc_nome} | {item} | {sit} |")
    escrever_se_mudou(CAL / "prazos.md", "\n".join(linhas) + "\n")

    # 7) relatorios
    resumo["novidades"] = novidades
    REL.mkdir(parents=True, exist_ok=True)
    (REL / "ultima_sincronizacao.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    if novidades:
        with open(REL / "novidades.md", "a", encoding="utf-8") as f:
            f.write(f"\n## {data(agora)}\n\n" + "\n".join(f"- {n}" for n in novidades) + "\n")
    escrever_se_mudou(REL / "STATUS.md",
                      f"# Status da sincronizacao\n\nOK - {data(agora)}\n\n"
                      f"- Disciplinas: {len(cursos)}\n- Novidades nesta execucao: {len(novidades)}\n")
    estado["ultima_execucao"] = agora
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Fim: {len(novidades)} novidade(s).")


