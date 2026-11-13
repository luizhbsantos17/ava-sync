"""Envio de tarefas (mod_assign). Unico modulo que ESCREVE no Moodle.

Tres portas de entrada, todas passando pelas mesmas regras:
  - terminal:  python -m avasync enviar ...   (pede ENVIAR / ACEITO / FINALIZAR)
  - painel:    python -m avasync servidor     (botao Enviar no PAINEL, com as mesmas confirmacoes)
  - fila:      agentes de IA deixam pedidos em 04_ENVIOS/fila; a pessoa aprova no painel.
               Opcional (config [envio] auto_rascunho): pedidos da fila sao salvos sozinhos
               como RASCUNHO, so em tarefas que usam rascunho. Nunca finaliza nem aceita a
               declaracao de autoria sozinho.

Como funciona por baixo (mesma API do app Moodle Mobile):
  1. POST /webservice/upload.php (token, filearea=draft, itemid) -> area de rascunho -> itemid
  2. mod_assign_save_submission(assignmentid, plugindata[files_filemanager]=itemid, ...)
     ATENCAO: substitui os arquivos que ja estavam na entrega.
  3. mod_assign_submit_for_grading(assignmentid, acceptsubmissionstatement)
     = botao "Enviar tarefa" (so em tarefas com rascunho).
"""
import json
import shutil
import sys
import time
from pathlib import Path

from .moodle import Moodle, pegar_token
from .util import data, log, para_md

DECLARACAO_PADRAO = "Esta tarefa e meu proprio trabalho, exceto onde reconheci o uso do trabalho de outros."


class Cancelado(Exception):
    pass


def conectar(cfg):
    m = Moodle(cfg.site, pegar_token(cfg), cfg.max_download_mb)
    m.userid = m.call("core_webservice_get_site_info")["userid"]
    return m


def _config(a, plugin, nome):
    for c in a.get("configs", []):
        if c.get("plugin") == plugin and c.get("name") == nome:
            return c.get("value")
    return None


def tarefas(m):
    cursos = m.call("core_course_get_enrolled_courses_by_timeline_classification",
                    classification="inprogress").get("courses", [])
    nomes = {c["id"]: c.get("fullname") for c in cursos}
    res = m.call("mod_assign_get_assignments", courseids=[c["id"] for c in cursos])
    out = []
    for c in res.get("courses", []):
        for a in c.get("assignments", []):
            a["_curso"] = nomes.get(c["id"], "")
            out.append(a)
    return out


def achar_tarefa(m, busca):
    busca = str(busca)
    achadas = [a for a in tarefas(m) if str(a["id"]) == busca or str(a.get("cmid")) == busca
               or busca.lower() in (a.get("name") or "").lower()]
    if not achadas:
        raise Cancelado(f"Nenhuma tarefa encontrada com '{busca}'.")
    if len(achadas) > 1:
        raise Cancelado("Mais de uma tarefa encontrada; use o id: " +
                        "; ".join(f"id={a['id']} {a['name']}" for a in achadas))
    return achadas[0]


def _arquivos_da_entrega(sub):
    return [f.get("filename") for p in sub.get("plugins", []) for fa in p.get("fileareas", []) or []
            for f in fa.get("files", []) or []]


def info_tarefa(m, a):
    """Tudo que a pessoa precisa ver antes de confirmar."""
    st = m.call("mod_assign_get_submission_status", assignid=a["id"], userid=m.userid)
    ult = st.get("lastattempt") or {}
    sub = ult.get("submission") or {}
    return {
        "id": a["id"], "cmid": a.get("cmid"), "nome": a.get("name"), "curso": a.get("_curso"),
        "entrega": a.get("duedate"), "entrega_txt": data(a.get("duedate")),
        "limite_txt": data(a.get("cutoffdate")),
        "situacao": sub.get("status") or "sem entrega",
        "ja_enviados": _arquivos_da_entrega(sub),
        "pode_editar": ult.get("canedit", True),
        "usa_rascunho": str(a.get("submissiondrafts", 0)) == "1",
        "exige_declaracao": str(a.get("requiresubmissionstatement", 0)) == "1",
        "declaracao": para_md(a.get("submissionstatement") or "") or DECLARACAO_PADRAO,
        "max_arquivos": int(_config(a, "file", "maxfilesubmissions") or 0),
        "tipos_aceitos": _config(a, "file", "filetypeslist") or "",
    }


def executar(m, cfg, a, arquivos, texto=None, finalizar=False, aceitou_declaracao=False):
    """Faz o envio. As confirmacoes humanas ja devem ter acontecido ANTES de chamar isto."""
    info = info_tarefa(m, a)
    arquivos = [Path(x) for x in arquivos or []]
    if not arquivos and not texto:
        raise Cancelado("Nada para enviar (sem arquivos e sem texto).")
    if not info["pode_editar"]:
        raise Cancelado("O Moodle informa que esta entrega nao pode mais ser editada.")
    if info["max_arquivos"] and len(arquivos) > info["max_arquivos"]:
        raise Cancelado(f"A tarefa aceita no maximo {info['max_arquivos']} arquivo(s).")
    if finalizar and info["usa_rascunho"] and info["exige_declaracao"] and not aceitou_declaracao:
        raise Cancelado("Para enviar para avaliacao e preciso aceitar a declaracao de autoria.")

    params = {"assignmentid": a["id"]}
    if arquivos:
        itemid = 0
        for arq in arquivos:
            with open(arq, "rb") as f:
                r = m.s.post(f"{cfg.site}/webservice/upload.php",
                             data={"token": m.token, "filearea": "draft", "itemid": itemid},
                             files={"file_1": (arq.name, f)}, timeout=300)
            r.raise_for_status()
            res = r.json()
            if not isinstance(res, list) or not res or "itemid" not in res[0]:
                raise Cancelado(f"Falha no upload de {arq.name}: {res}")
            itemid = res[0]["itemid"]
        params["plugindata[files_filemanager]"] = itemid
    if texto:
        params["plugindata[onlinetext_editor][text]"] = texto.replace("\n", "<br>")
        params["plugindata[onlinetext_editor][format]"] = 1
        params["plugindata[onlinetext_editor][itemid]"] = 0
    avisos = m.call("mod_assign_save_submission", **params)
    if avisos:
        raise Cancelado(f"O Moodle recusou a entrega: {avisos}")
    log(f"ENVIO: salvo na tarefa {a['id']} ({a.get('name')}): {[p.name for p in arquivos]}")

    finalizado = False
    if finalizar and info["usa_rascunho"]:
        avisos = m.call("mod_assign_submit_for_grading", assignmentid=a["id"],
                        acceptsubmissionstatement=1 if aceitou_declaracao else 0)
        if avisos:
            raise Cancelado(f"O Moodle recusou o envio para avaliacao: {avisos}")
        finalizado = True
        log(f"ENVIO: tarefa {a['id']} enviada para avaliacao")
    depois = info_tarefa(m, a)
    depois["finalizado"] = finalizado
    depois["link"] = f"{cfg.site}/mod/assign/view.php?id={a.get('cmid')}"
    return depois


# ------------------------------------------------------------------ terminal
def _perguntar(texto, esperado):
    if input(texto).strip() != esperado:
        raise Cancelado("Envio cancelado (resposta diferente de " + esperado + ").")


def enviar(cfg, busca, arquivos, texto=None, finalizar=False):
    if not sys.stdin.isatty():
        sys.exit("O envio pelo terminal so pode ser feito por uma pessoa num terminal interativo.")
    for x in arquivos or []:
        if not Path(x).is_file():
            sys.exit(f"Arquivo nao encontrado: {x}")
    texto_md = Path(texto).read_text(encoding="utf-8") if texto else None
    m = conectar(cfg)
    a = achar_tarefa(m, busca)
    i = info_tarefa(m, a)
    print("\n================ CONFIRA ANTES DE ENVIAR ================")
    print(f"Disciplina : {i['curso']}\nTarefa     : {i['nome']}  (id {i['id']})")
    print(f"Entrega    : {i['entrega_txt']}   limite: {i['limite_txt']}")
    print(f"Situacao   : {i['situacao']}\nJa enviados: {', '.join(i['ja_enviados']) or '(nenhum)'}")
    print(f"Vai enviar : {', '.join(map(str, arquivos or [])) or '(nenhum arquivo)'}" + ("  + texto" if texto_md else ""))
    if i["tipos_aceitos"]:
        print(f"Tipos aceitos: {i['tipos_aceitos']}")
    if i["ja_enviados"] and arquivos:
        print("ATENCAO: os arquivos que ja estao na entrega serao SUBSTITUIDOS.")
    print("=========================================================")
    _perguntar("Digite ENVIAR para confirmar: ", "ENVIAR")
    aceitou = False
    if finalizar and i["usa_rascunho"]:
        if i["exige_declaracao"]:
            print("\nDeclaracao exigida pela tarefa:\n  " + i["declaracao"].replace("\n", "\n  "))
            _perguntar("Voce concorda? Digite ACEITO: ", "ACEITO")
            aceitou = True
        _perguntar("Depois disso em geral nao da mais para alterar. Digite FINALIZAR: ", "FINALIZAR")
    r = executar(m, cfg, a, arquivos, texto_md, finalizar, aceitou)
    if i["usa_rascunho"] and not r["finalizado"]:
        print("A entrega ficou como RASCUNHO (use --finalizar ou o botao 'Enviar tarefa' no AVA).")
    print(f"\nSituacao no AVA agora: {r['situacao']} | arquivos: {', '.join(r['ja_enviados']) or '-'}\nConfira: {r['link']}")


# ------------------------------------------------------------------ fila (agentes de IA)
def pasta_fila(cfg):
    return cfg.pasta_saida / "04_ENVIOS" / "fila"


def listar_fila(cfg):
    itens = []
    for d in sorted(pasta_fila(cfg).glob("*/pedido.json")) if pasta_fila(cfg).exists() else []:
        try:
            p = json.loads(d.read_text(encoding="utf-8"))
        except ValueError:
            continue
        p["_pasta"] = d.parent.name
        itens.append(p)
    return itens


def _mover_fila(cfg, nome, destino, extra):
    src = pasta_fila(cfg) / nome
    pj = src / "pedido.json"
    p = json.loads(pj.read_text(encoding="utf-8"))
    p.update(extra)
    pj.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    dst = cfg.pasta_saida / "04_ENVIOS" / destino / nome
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return p


def processar_pedido(cfg, m, nome, finalizar=False, aceitou_declaracao=False, aprovado_por="pessoa"):
    pasta = pasta_fila(cfg) / nome
    p = json.loads((pasta / "pedido.json").read_text(encoding="utf-8"))
    a = achar_tarefa(m, p["tarefa_id"])
    arquivos = [pasta / x for x in p.get("arquivos", [])]
    texto = (pasta / p["texto_arquivo"]).read_text(encoding="utf-8") if p.get("texto_arquivo") else None
    r = executar(m, cfg, a, arquivos, texto, finalizar, aceitou_declaracao)
    _mover_fila(cfg, nome, "enviados", {"resultado": r, "aprovado_por": aprovado_por,
                                        "processado_em": time.strftime("%Y-%m-%d %H:%M:%S")})
    return r


def rejeitar_pedido(cfg, nome, motivo=""):
    return _mover_fila(cfg, nome, "rejeitados", {"rejeitado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                  "motivo": motivo})


def auto_rascunho(cfg):
    """Opcional: salva sozinho, como RASCUNHO, os pedidos da fila cujas tarefas usam rascunho.
    Nunca finaliza nem aceita declaracao. Os demais continuam esperando aprovacao no painel."""
    if not getattr(cfg, "envio_auto_rascunho", False):
        return 0
    itens = [p for p in listar_fila(cfg) if not p.get("rascunho_salvo")]
    if not itens:
        return 0
    m = conectar(cfg)
    feitos = 0
    for p in itens:
        try:
            a = achar_tarefa(m, p["tarefa_id"])
            if not info_tarefa(m, a)["usa_rascunho"]:
                continue  # salvar ja seria entregar: espera aprovacao humana
            pasta = pasta_fila(cfg) / p["_pasta"]
            texto = (pasta / p["texto_arquivo"]).read_text(encoding="utf-8") if p.get("texto_arquivo") else None
            executar(m, cfg, a, [pasta / x for x in p.get("arquivos", [])], texto, finalizar=False)
            p2 = json.loads((pasta / "pedido.json").read_text(encoding="utf-8"))
            p2["rascunho_salvo"] = time.strftime("%Y-%m-%d %H:%M:%S")
            (pasta / "pedido.json").write_text(json.dumps(p2, ensure_ascii=False, indent=2), encoding="utf-8")
            feitos += 1
        except Exception as e:  # noqa: BLE001
            log(f"fila: pedido {p['_pasta']} nao processado ({e})")
    log(f"fila: {feitos} rascunho(s) salvo(s) automaticamente; finalizar continua com a pessoa.")
    return feitos
