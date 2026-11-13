"""
painel.py - Gera <pasta_saida>/PAINEL.html a partir do que esta nas pastas.

E uma pagina unica, offline (sem internet), que le:
  - 03_RELATORIOS/ultima_sincronizacao.json  -> prazos e situacao das entregas
  - 01_DISCIPLINAS/<materia>/...              -> atividades, provas, avisos, guias, materiais
  - 03_RELATORIOS/novidades.md                -> historico de novidades
Os dados sao embutidos no HTML como JSON; o JavaScript da pagina monta a tela.
Links de materiais usam caminho relativo, entao abrem direto do disco no navegador.

Uso: python -m avasync painel   (tambem roda no fim de cada sync)
"""
import datetime as dt
import json
import os
from pathlib import Path
from urllib.parse import quote

BASE = Path(".")
TZ = dt.timezone(dt.timedelta(hours=-3))
TEXTO = (".md", ".txt")


def _ler(p: Path, limite=60000):
    try:
        t = p.read_text(encoding="utf-8")
        if t.startswith("---\n") and "\n---\n" in t[4:]:
            t = t[4:].split("\n---\n", 1)[1]   # tira o cabecalho (frontmatter) dos guias
        return t[:limite]
    except (OSError, UnicodeDecodeError):
        return ""


def _rel(p: Path):
    return quote(p.relative_to(BASE).as_posix())


def coletar():
    sync = {}
    sj = BASE / "03_RELATORIOS" / "ultima_sincronizacao.json"
    if sj.exists():
        try:
            sync = json.loads(sj.read_text(encoding="utf-8"))
        except ValueError:
            sync = {}
    por_pasta = {Path(d["pasta"]).name: d for d in sync.get("disciplinas", [])}
    id_por_arquivo = {Path(t["arquivo"]).stem: t.get("id") for d in sync.get("disciplinas", [])
                      for t in d.get("tarefas", []) if t.get("arquivo")}

    materias = []
    disc_dir = BASE / "01_DISCIPLINAS"
    for pasta in sorted(p for p in disc_dir.iterdir() if p.is_dir()) if disc_dir.exists() else []:
        m = {"nome": por_pasta.get(pasta.name, {}).get("nome") or pasta.name,
             "pasta": _rel(pasta), "conteudo": _ler(pasta / "CONTEUDO_DA_DISCIPLINA.md"),
             "secoes": {}}
        for sec in ("Atividades", "Provas", "Anuncios", "Guias"):
            itens = []
            d = pasta / sec
            if d.exists():
                for f in sorted(d.glob("*.md"), reverse=(sec == "Anuncios")):
                    if f.name.upper() == "README.MD":
                        continue
                    anexos = []
                    ad = d / (f.stem + "_anexos")
                    if ad.exists():
                        anexos = [{"nome": a.name, "href": _rel(a)} for a in sorted(ad.iterdir()) if a.is_file()]
                    itens.append({"titulo": f.stem, "md": _ler(f), "href": _rel(f), "dir": _rel(f.parent), "anexos": anexos,
                                  "tarefa_id": id_por_arquivo.get(f.stem) if sec == "Atividades" else None})
                # arquivos que nao sao .md (ex.: docx do aluno)
                for f in sorted(d.iterdir()):
                    if f.is_file() and f.suffix.lower() not in TEXTO:
                        itens.append({"titulo": f.name, "md": "", "href": _rel(f), "anexos": [], "arquivo": True})
            m["secoes"][sec] = itens
        mats = []
        md = pasta / "Materiais"
        if md.exists():
            for f in sorted(md.rglob("*")):
                partes = f.relative_to(md).parts[:-1]
                if any(x.startswith("_") or x.endswith("_arquivos") for x in partes):
                    continue  # imagens baixadas para paginas, livros e links (aparecem dentro deles)
                if f.is_file() and f.name.upper() != "README.MD" and not f.name.endswith(".part"):
                    mats.append({"nome": f.name, "grupo": f.parent.relative_to(md).as_posix() or "Geral",
                                 "href": _rel(f), "dir": _rel(f.parent), "kb": round(f.stat().st_size / 1024),
                                 "md": _ler(f) if f.suffix.lower() in TEXTO else ""})
        m["materiais"] = mats
        materias.append(m)

    prazos = []
    for d in sync.get("disciplinas", []):
        for t in d.get("tarefas", []):
            if t.get("entrega"):
                prazos.append({"ts": t["entrega"], "materia": d["nome"], "tipo": "Tarefa",
                               "nome": t["nome"], "situacao": t.get("situacao", "")})
        for q in d.get("questionarios", []):
            if q.get("fecha"):
                prazos.append({"ts": q["fecha"], "materia": d["nome"], "tipo": "Prova/questionario",
                               "nome": q["nome"], "situacao": ""})
    prazos.sort(key=lambda x: x["ts"])

    return {"gerado": dt.datetime.now(TZ).strftime("%d/%m/%Y %H:%M"),
            "sincronizado": sync.get("gerado_em", ""),
            "status": _ler(BASE / "03_RELATORIOS" / "STATUS.md"),
            "novidades": _ler(BASE / "03_RELATORIOS" / "novidades.md")[-20000:],
            "materias": materias, "prazos": prazos}


def gerar(cfg=None):
    global BASE
    if cfg is not None:
        BASE = cfg.pasta_saida
    dados = json.dumps(coletar(), ensure_ascii=False).replace("</", "<\\/")
    html_out = MODELO.replace("__DADOS__", dados)
    destino = BASE / "PAINEL.html"
    destino.write_text(html_out, encoding="utf-8")
    return destino


MODELO = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel AVA</title>
<style>
:root{color-scheme:dark;--bg:#100d17;--paper:#181421;--surface:#211b2c;--ink:#f3effa;--muted:#a49ab3;--line:#302a3b;--green:#b49aff;--green-dark:#9675f3;--lime:#e1d5ff;--soft:#292239;--amber:#f2bb70;--red:#ff8994;--danger-bg:#3e242d;--warning-bg:#3c2d1d;--success-bg:#20352c;--subtle:#25202f;--field:#1d1827;--hero:linear-gradient(118deg,#382b5a 0%,#241b36 72%,#211a31 100%);--shadow:0 16px 48px rgba(0,0,0,.28)}
html[data-theme="light"]{color-scheme:light;--bg:#f5f6f8;--paper:#fff;--surface:#fafbf9;--ink:#202321;--muted:#858b86;--line:#e8eae6;--green:#285f4b;--green-dark:#174532;--lime:#d9ef9b;--soft:#eef4e9;--amber:#b46a27;--red:#c0524b;--danger-bg:#fbe9e7;--warning-bg:#fff1de;--success-bg:#e9f4e8;--subtle:#eff1ee;--field:#f8f9f7;--hero:linear-gradient(118deg,#285f4b 0%,#214b3c 72%,#1b4234 100%);--shadow:0 12px 36px rgba(34,48,39,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:-.01em}
button,input,textarea{font:inherit}header{height:82px;padding:0 42px;display:flex;align-items:center;gap:16px;background:color-mix(in srgb,var(--paper) 88%,transparent);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3;backdrop-filter:blur(16px)}
.brand{display:flex;align-items:center;gap:12px;min-width:250px}.brand-mark{width:38px;height:38px;border-radius:13px;background:var(--green);color:var(--lime);display:grid;place-items:center;font-size:19px;font-weight:800;letter-spacing:-.08em}.brand h1{font-size:16px;line-height:1.15;margin:0;font-weight:750;letter-spacing:-.04em}.brand small{display:block;margin-top:4px;color:var(--muted);font-size:11px;letter-spacing:.01em}
#info{margin-left:auto;color:var(--muted);font-size:12px;white-space:nowrap}.searchbox{position:relative}.searchbox:before{content:"⌕";position:absolute;left:13px;top:5px;font-size:21px;color:var(--muted);pointer-events:none}input[type=search]{width:min(260px,24vw);padding:10px 14px 10px 38px;border:1px solid var(--line);border-radius:11px;background:var(--field);color:var(--ink);outline:none;transition:.2s}input[type=search]:focus{border-color:var(--green);box-shadow:0 0 0 3px color-mix(in srgb,var(--green) 20%,transparent)}
.theme-btn{height:38px;min-width:40px;padding:0 11px;display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink);cursor:pointer;font-size:16px;transition:.18s}.theme-btn:hover{border-color:var(--green);color:var(--green)}.theme-btn span{font-size:11px;font-weight:650}
.wrap{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:calc(100vh - 82px);max-width:1600px;margin:auto}nav{padding:31px 18px 24px 28px;border-right:1px solid var(--line);background:var(--surface)}nav button{display:flex;align-items:center;gap:11px;width:100%;text-align:left;padding:10px 12px;border:0;border-radius:10px;background:none;color:var(--muted);cursor:pointer;font:inherit;font-size:13px;margin:3px 0;transition:.18s}nav button:before{content:"";width:7px;height:7px;border:1.5px solid #786d88;border-radius:3px;transform:rotate(45deg)}nav button:hover{background:var(--soft);color:var(--green)}nav button.on{background:#392d58;color:#fff;font-weight:650;box-shadow:0 5px 18px #0003}nav button.on:before{background:var(--lime);border-color:var(--lime)}nav .lb{font-size:10px;font-weight:750;letter-spacing:.12em;color:var(--muted);margin:30px 12px 9px;text-transform:uppercase}
main{min-width:0;width:100%;max-width:1260px;padding:42px clamp(24px,5vw,76px) 70px}.card{background:var(--paper);border:1px solid var(--line);border-radius:15px;padding:20px 22px;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,0,0,.1)}
.hero{position:relative;overflow:hidden;background:var(--hero);color:#fff;border:1px solid #ffffff12;border-radius:20px;padding:32px 36px;margin-bottom:20px;box-shadow:var(--shadow)}.hero:after{content:"";position:absolute;width:270px;height:270px;right:3%;top:-120px;border:1px solid #ffffff20;border-radius:50%;box-shadow:0 0 0 28px #ffffff0a,0 0 0 58px #ffffff08}.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.16em;font-weight:750;color:var(--lime);margin-bottom:12px}.hero h2{font-size:clamp(24px,3vw,34px);letter-spacing:-.055em;line-height:1.1;margin:0 0 10px;max-width:650px}.hero p{color:#e0d8ec;margin:0;max-width:560px}.hero .hero-tag{display:inline-flex;align-items:center;gap:7px;margin-top:22px;background:#ffffff12;border:1px solid #ffffff20;border-radius:999px;padding:7px 11px;font-size:11px;color:#f3effa}.hero-tag i{display:block;width:7px;height:7px;border-radius:50%;background:var(--lime)}
details>summary{cursor:pointer;font-weight:650;list-style:none;font-size:13px}details>summary::-webkit-details-marker{display:none}details>summary:before{content:"＋";display:inline-grid;place-items:center;width:23px;height:23px;margin-right:10px;border-radius:7px;background:var(--soft);color:var(--green);font-size:12px}details[open]>summary:before{content:"−"}.md{margin:12px 0 0 34px;overflow-wrap:anywhere}.md h1{font-size:19px}.md h2{font-size:16px}.md h3{font-size:14px}.md pre{white-space:pre-wrap;background:var(--surface);padding:13px;border-radius:10px}a{color:var(--green);text-decoration-color:color-mix(in srgb,var(--green) 50%,transparent);text-underline-offset:3px}a:hover{color:var(--lime)}.mu{color:var(--muted)}.vazio{color:var(--muted);font-size:13px;padding:12px 4px}
.md-link-gallery{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:12px 0}.md-link-gallery a{display:inline-flex;align-items:center;justify-content:center;min-width:96px;min-height:68px;padding:9px 13px;border:1px solid var(--line);border-radius:12px;background:var(--surface);transition:transform .15s,border-color .15s}.md-link-gallery a:hover{transform:translateY(-2px);border-color:var(--green)}.md-link-gallery img{display:block;width:auto;max-width:100%;height:auto;max-height:76px;object-fit:contain}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-bottom:30px}.stats .stat{padding:17px 19px;background:var(--paper);border:1px solid var(--line);border-radius:14px}.stat-label{font-size:11px;color:var(--muted)}.stat-value{font-size:25px;font-weight:750;letter-spacing:-.06em;margin-top:5px}.stat-note{font-size:11px;color:var(--muted);margin-top:2px}.stat.accent{background:var(--soft);border-color:color-mix(in srgb,var(--green) 22%,var(--line))}.stat.accent .stat-value{color:var(--green)}
.tabs{display:flex;gap:5px;margin:20px 0 18px;padding:5px;background:var(--surface);border-radius:12px;width:max-content;max-width:100%;overflow:auto}.tabs button{padding:8px 13px;border:0;border-radius:8px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px;white-space:nowrap}.tabs button.on{background:var(--paper);color:var(--green);font-weight:700;box-shadow:0 2px 8px #0002}
table{width:100%;border-collapse:collapse}td,th{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--muted);font-weight:700;font-size:10px;letter-spacing:.1em;text-transform:uppercase}tr:last-child td{border-bottom:0}td:first-child{white-space:nowrap;color:var(--muted);font-size:12px}td b{font-weight:650}.bd{display:inline-block;padding:4px 9px;border-radius:999px;font-size:10px;font-weight:750;white-space:nowrap;letter-spacing:.01em}.b-er{background:var(--danger-bg);color:var(--red)}.b-wa{background:var(--warning-bg);color:var(--amber)}.b-ok{background:var(--success-bg);color:#8bd4a6}.b-mu{background:var(--subtle);color:var(--muted)}
.btn{padding:9px 14px;border:1px solid var(--green);border-radius:9px;background:var(--green-dark);color:#fff;cursor:pointer;font-size:12px;font-weight:650;transition:.18s}.btn:hover{filter:brightness(1.12)}.btn.sec{background:var(--paper);color:var(--green);border-color:var(--line)}.btn.sec:hover{background:var(--soft);border-color:var(--green)}.btn:disabled{opacity:.5;cursor:default}
#modal{position:fixed;inset:0;background:rgba(5,3,9,.68);display:none;align-items:flex-start;justify-content:center;z-index:9;overflow:auto;padding:50px 16px;backdrop-filter:blur(4px)}#modal .card{max-width:620px;width:100%;border-radius:18px;padding:25px;box-shadow:0 22px 80px #0008}#modal label{display:block;margin:13px 0;font-size:12px;font-weight:600}#modal input[type=text],#modal textarea{width:100%;margin-top:6px;padding:10px 11px;border:1px solid var(--line);border-radius:8px;background:var(--field);color:var(--ink);font:inherit}#modal input[type=file]{display:block;margin-top:8px}.aviso{background:var(--warning-bg);border:1px solid color-mix(in srgb,var(--amber) 24%,var(--line));border-radius:10px;padding:11px 13px;margin:10px 0;font-size:12px}
@media(max-width:900px){header{padding:0 22px;gap:14px}.brand{min-width:0}#info{display:none}.wrap{grid-template-columns:215px minmax(0,1fr)}nav{padding-left:16px}main{padding:30px 24px 55px}}
@media(max-width:650px){header{height:auto;min-height:72px;padding:12px 16px;flex-wrap:wrap;gap:10px}.brand{flex:1}.brand small{font-size:10px}.searchbox{order:3;width:100%}input[type=search]{width:100%}#acoes,#tema{order:2}.theme-btn{min-width:36px;width:36px;padding:0}.theme-btn span{display:none}.wrap{display:flex;flex-direction:column;min-height:calc(100vh - 112px)}nav{padding:10px 12px;border-right:0;border-bottom:1px solid var(--line);display:flex;gap:6px;overflow:auto;white-space:nowrap}nav .lb{display:none}nav button{width:auto;flex:0 0 auto;padding:8px 11px;margin:0;font-size:11px}main{padding:22px 15px 45px}.hero{padding:25px 23px;border-radius:16px}.hero:after{right:-170px}.stats{gap:8px}.stat{padding:13px 12px}.stat-value{font-size:21px}.stat-note{font-size:10px}.stats{grid-template-columns:repeat(3,minmax(0,1fr))}.card{padding:16px}.tabs{width:100%}.table-scroll{overflow:visible}table,tbody{display:block;width:100%;min-width:0}tr:first-child{display:none}tr:not(:first-child){display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 12px;padding:13px 0;border-bottom:1px solid var(--line)}tr:last-child{border-bottom:0}td{padding:0;border:0;min-width:0}td:first-child{grid-column:1;grid-row:1;white-space:normal;font-weight:650}td:nth-child(2){grid-column:2;grid-row:1;justify-self:end}td:nth-child(3){grid-column:1;grid-row:2;font-size:11px}td:nth-child(4){grid-column:1/-1;grid-row:3;padding-top:3px}.section-heading{margin-top:24px}}
</style></head><body>
<header><div class="brand"><div class="brand-mark">a.</div><div><h1>ava sync</h1><small>seu espaço acadêmico</small></div></div><small id="info"></small><span id="acoes"></span><button class="theme-btn" id="tema" type="button" aria-label="Ativar tema claro" title="Ativar tema claro">☼ <span>Claro</span></button><label class="searchbox"><input type="search" id="q" placeholder="Buscar disciplinas, atividades..."></label></header>
<div class="wrap"><nav id="nav"></nav><main id="main"></main></div><div id="modal"></div>
<script>
const D=__DADOS__;const $=s=>document.querySelector(s);
const temaBtn=$("#tema");let temaAtual="dark";
try{if(localStorage.getItem("ava-sync-tema")==="light")temaAtual="light";}catch(e){}
function aplicarTema(){document.documentElement.dataset.theme=temaAtual;const claro=temaAtual==="dark";temaBtn.innerHTML=(claro?"☼":"☾")+" <span>"+(claro?"Claro":"Escuro")+"</span>";temaBtn.title=claro?"Ativar tema claro":"Ativar tema escuro";temaBtn.setAttribute("aria-label",temaBtn.title);try{localStorage.setItem("ava-sync-tema",temaAtual);}catch(e){}}
temaBtn.addEventListener("click",()=>{temaAtual=temaAtual==="dark"?"light":"dark";aplicarTema();});aplicarTema();
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function md(t,b){if(!t)return"";let h=esc(t);
 h=h.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,(m,a,s)=>'<img alt="'+a+'" src="'+(/^(https?:|data:|\/)/.test(s)||!b?s:b+"/"+s)+'" loading="lazy" style="max-width:100%">');
 h=h.replace(/```([\s\S]*?)```/g,(m,c)=>"<pre>"+c+"</pre>");
 h=h.replace(/^### (.*)$/gm,"<h3>$1</h3>").replace(/^## (.*)$/gm,"<h2>$1</h2>").replace(/^# (.*)$/gm,"<h1>$1</h1>");
 h=h.replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g,"$1<i>$2</i>");
 h=h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)(?:\s+(?:"[^"]*"|&quot;[\s\S]*?&quot;))?\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
 h=h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,'$1<a href="$2" target="_blank">$2</a>');
 const imagem='(?:<a\\b[^>]*>\\s*<img\\b[^>]*>\\s*<\\/a>|<img\\b[^>]*>)';
 h=h.replace(new RegExp('^\\s*'+imagem+'(?:\\s*\\|\\s*'+imagem+')+(?:\\s*\\|\\s*)?\\s*$','gm'),r=>'<div class="md-link-gallery">'+r.replace(/\s*\|\s*/g,'')+'</div>');
 h=h.replace(/^\s*[-*] (.*)$/gm,"<li>$1</li>").replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g,"<ul>$1</ul>");
 h=h.replace(/^\|(.+)\|$/gm,(m,r)=>/^[-| :]+$/.test(r)?"":"<tr>"+r.split("|").map(c=>"<td>"+c.trim()+"</td>").join("")+"</tr>");
 h=h.replace(/(<tr>[\s\S]*?<\/tr>)(?!\s*<tr>)/g,"<table>$1</table>");
 return h.split(/\n{2,}/).map(p=>/^\s*<(h\d|ul|pre|table|div)/.test(p)?p:"<p>"+p.replace(/\n/g,"<br>")+"</p>").join("");}

const S=window.AVASYNC||null;
async function api(url,corpo){const r=await fetch(url,{method:corpo?"POST":"GET",headers:{"X-Avasync-Chave":S.chave,"Content-Type":"application/json"},body:corpo?JSON.stringify(corpo):undefined});
 const j=await r.json().catch(()=>({erro:"resposta invalida"}));if(!r.ok)throw new Error(j.erro||r.status);return j;}
const modal=$("#modal");function fechar(){modal.style.display="none";modal.innerHTML="";}
function lerB64(f){return new Promise((ok,er)=>{const r=new FileReader();r.onload=()=>ok(r.result.split(",")[1]);r.onerror=er;r.readAsDataURL(f);});}
async function abrirEnvio(id){modal.style.display="flex";modal.innerHTML='<div class="card">Consultando a tarefa no AVA...</div>';
 let t;try{t=await api("/api/tarefa?id="+id);}catch(e){modal.innerHTML='<div class="card"><p>Erro: '+esc(e.message)+'</p><button class="btn sec" onclick="fechar()">Fechar</button></div>';return;}
 modal.innerHTML='<div class="card"><h3 style="margin-top:0">Enviar: '+esc(t.nome)+'</h3>'
 +'<p class="mu">'+esc(t.curso)+'<br>Entrega: <b>'+esc(t.entrega_txt)+'</b> · limite: '+esc(t.limite_txt)+'<br>Situação: <b>'+esc(t.situacao)+'</b> · já enviados: '+esc(t.ja_enviados.join(", ")||"nenhum")+'</p>'
 +(t.pode_editar?'':'<div class="aviso">O AVA informa que esta entrega não pode mais ser editada.</div>')
 +(t.ja_enviados.length?'<div class="aviso">Os arquivos novos <b>substituem</b> os que já estão na entrega.</div>':'')
 +'<label>Arquivos '+(t.tipos_aceitos?'('+esc(t.tipos_aceitos)+')':'')+(t.max_arquivos?' · máx. '+t.max_arquivos:'')+'<input type="file" id="f_arq" multiple></label>'
 +'<label>Texto online (opcional)<textarea id="f_txt" rows="3"></textarea></label>'
 +(t.usa_rascunho?'<label><input type="checkbox" id="f_fin"> Também <b>enviar para avaliação</b> (botão "Enviar tarefa"; depois em geral não dá para alterar)</label>':'<div class="aviso">Esta tarefa não usa rascunho: ao salvar, a entrega já fica enviada.</div>')
 +(t.usa_rascunho&&t.exige_declaracao?'<div id="decl" style="display:none" class="aviso"><b>Declaração exigida:</b><br>'+esc(t.declaracao)+'<label><input type="checkbox" id="f_ace"> Li e concordo</label></div>':'')
 +'<label>Digite <b>ENVIAR</b> para confirmar<input type="text" id="f_conf" autocomplete="off"></label>'
 +'<p><button class="btn" id="f_ok">Enviar</button> <button class="btn sec" onclick="fechar()">Cancelar</button></p><div id="f_res"></div></div>';
 const fin=$("#f_fin");if(fin&&$("#decl"))fin.onchange=()=>$("#decl").style.display=fin.checked?"block":"none";
 $("#f_ok").onclick=async()=>{const res=$("#f_res");if($("#f_conf").value.trim()!=="ENVIAR"){res.textContent="Digite ENVIAR.";return;}
  const finalizar=!!(fin&&fin.checked);if(finalizar&&$("#f_ace")&&!$("#f_ace").checked){res.textContent="Marque a declaração para finalizar.";return;}
  const arquivos=[];for(const f of $("#f_arq").files)arquivos.push({nome:f.name,base64:await lerB64(f)});
  $("#f_ok").disabled=true;res.textContent="Enviando...";
  try{const r=await api("/api/enviar",{tarefa_id:id,arquivos,texto:$("#f_txt").value,finalizar,aceito:!!($("#f_ace")&&$("#f_ace").checked),confirmacao:"ENVIAR"});
   res.innerHTML='<div class="aviso">Pronto. Situação no AVA: <b>'+esc(r.situacao)+'</b> · arquivos: '+esc(r.ja_enviados.join(", ")||"-")+'<br><a href="'+r.link+'" target="_blank">conferir no AVA</a></div>';}
  catch(e){res.innerHTML='<div class="aviso">Erro: '+esc(e.message)+'</div>';$("#f_ok").disabled=false;}};}
async function carregarFila(){const el=$("#fila");let l;try{l=await api("/api/fila");}catch(e){el.textContent="Erro: "+e.message;return;}
 if(!l.length){el.innerHTML='<p class="vazio">Nenhum pedido. Agentes de IA deixam pedidos em 04_ENVIOS/fila (veja AGENTS.md).</p>';return;}
 el.innerHTML=l.map(p=>'<div class="card"><b>'+esc(p.titulo||("tarefa "+p.tarefa_id))+'</b> <span class="mu">pedido por '+esc(p.agente||"?")+'</span>'
  +(p.rascunho_salvo?'<br><span class="bd b-ok">rascunho já salvo no AVA '+esc(p.rascunho_salvo)+'</span>':'')
  +'<br>Arquivos: '+esc((p.arquivos||[]).join(", ")||"-")+(p.observacao?'<br><span class="mu">'+esc(p.observacao)+'</span>':'')
  +'<p><button class="btn" onclick="aprovar(\''+p._pasta+'\','+p.tarefa_id+')">Revisar e enviar</button> <button class="btn sec" onclick="rejeitar(\''+p._pasta+'\')">Rejeitar</button></p></div>').join("");}
async function aprovar(pedido,id){let t;try{t=await api("/api/tarefa?id="+id);}catch(e){alert(e.message);return;}
 modal.style.display="flex";modal.innerHTML='<div class="card"><h3 style="margin-top:0">Aprovar envio: '+esc(t.nome)+'</h3><p class="mu">Entrega: '+esc(t.entrega_txt)+' · situação: '+esc(t.situacao)+'</p>'
 +'<p>Abra e confira os arquivos em <code>04_ENVIOS/fila/'+esc(pedido)+'</code> antes de aprovar.</p>'
 +(t.usa_rascunho?'<label><input type="checkbox" id="a_fin"> Também enviar para avaliação</label>':'')
 +(t.usa_rascunho&&t.exige_declaracao?'<div class="aviso"><b>Declaração:</b><br>'+esc(t.declaracao)+'<label><input type="checkbox" id="a_ace"> Li e concordo (é meu trabalho)</label></div>':'')
 +'<label>Digite <b>ENVIAR</b><input type="text" id="a_conf"></label><p><button class="btn" id="a_ok">Aprovar</button> <button class="btn sec" onclick="fechar()">Cancelar</button></p><div id="a_res"></div></div>';
 $("#a_ok").onclick=async()=>{const fin=!!($("#a_fin")&&$("#a_fin").checked);if($("#a_conf").value.trim()!=="ENVIAR"){$("#a_res").textContent="Digite ENVIAR.";return;}
  if(fin&&$("#a_ace")&&!$("#a_ace").checked){$("#a_res").textContent="Marque a declaração.";return;}
  try{const r=await api("/api/fila/aprovar",{pedido,finalizar:fin,aceito:!!($("#a_ace")&&$("#a_ace").checked),confirmacao:"ENVIAR"});$("#a_res").innerHTML='<div class="aviso">Enviado. Situação: <b>'+esc(r.situacao)+'</b></div>';carregarFila();}
  catch(e){$("#a_res").textContent="Erro: "+e.message;}};}
async function rejeitar(pedido){if(!confirm("Rejeitar este pedido?"))return;try{await api("/api/fila/rejeitar",{pedido});carregarFila();}catch(e){alert(e.message);}}
async function atualizarAgora(b){b.disabled=true;b.textContent="Atualizando...";try{await api("/api/sync",{});location.reload();}catch(e){alert("Erro: "+e.message);b.disabled=false;b.textContent="Atualizar agora";}}
if(S)$("#acoes").innerHTML='<button class="btn" onclick="atualizarAgora(this)">Atualizar agora</button>';
const agora=Date.now()/1000;
function badge(ts,sit){if(sit&&/ENTREGUE/.test(sit)&&!/NAO/.test(sit))return'<span class="bd b-ok">entregue</span>';
 const d=(ts-agora)/86400;if(d<0)return'<span class="bd b-er">venceu</span>';if(d<1)return'<span class="bd b-er">hoje</span>';
 if(d<=3)return'<span class="bd b-wa">'+Math.ceil(d)+' dias</span>';return'<span class="bd b-mu">'+Math.ceil(d)+' dias</span>';}
const fdata=ts=>new Date(ts*1000).toLocaleString("pt-BR",{weekday:"short",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
let vista={tipo:"prazos"},aba="Atividades";
function nav(){let h='<div class="lb">Visão geral</div><button data-v="prazos">Painel inicial</button><button data-v="novidades">Novidades</button>'+(S?'<button data-v="fila">Envios da IA</button>':'')+'<div class="lb">Suas disciplinas</div>';
 D.materias.forEach((m,i)=>h+='<button data-v="m'+i+'">'+esc(m.nome)+'</button>');
 if(!D.materias.length)h+='<div class="vazio" style="padding:8px">Nenhuma ainda</div>';$("#nav").innerHTML=h;
 document.querySelectorAll("nav button").forEach(b=>{b.classList.toggle("on",b.dataset.v===(vista.tipo==="m"?"m"+vista.i:vista.tipo));
  b.onclick=()=>{const v=b.dataset.v;vista=v[0]==="m"?{tipo:"m",i:+v.slice(1)}:{tipo:v};$("#q").value="";render();}});}
function prazos(lista){if(!lista.length)return'<p class="vazio">Nenhum prazo encontrado.</p>';
 return'<div class="table-scroll"><table><tr><th>Data de entrega</th><th>Situação</th><th>Disciplina</th><th>Atividade</th></tr>'+lista.map(p=>'<tr><td>'+fdata(p.ts)+'</td><td>'+badge(p.ts,p.situacao)+'</td><td>'+esc(p.materia)+'</td><td><span class="mu">'+esc(p.tipo)+' · </span><b>'+esc(p.nome)+'</b>'+(p.situacao?'<br><span class="mu">'+esc(p.situacao)+'</span>':'')+'</td></tr>').join("")+'</table></div>';}
function item(it){if(it.arquivo)return'<div class="card"><a href="'+it.href+'">'+esc(it.titulo)+'</a></div>';
 return'<details class="card"><summary>'+esc(it.titulo)+'</summary><div class="md">'+md(it.md,it.dir)+'</div>'+(it.anexos.length?'<p><b>Anexos:</b> '+it.anexos.map(a=>'<a href="'+a.href+'">'+esc(a.nome)+'</a>').join(" · ")+'</p>':'')+'<p class="mu"><a href="'+it.href+'">abrir arquivo</a>'+(it.tarefa_id?(S?' · <button class="btn" onclick="abrirEnvio('+it.tarefa_id+')">Enviar atividade</button>':' · <span title="rode: python -m avasync servidor">para enviar, abra o painel pelo servidor local</span>'):'')+'</p></details>';}
function materia(m){const tabs=["Atividades","Provas","Guias","Anuncios","Materiais","Conteudo"];
 const nomes={Anuncios:"Avisos",Conteudo:"Conteúdo do AVA",Guias:"Guias da IA"};
 let h='<div class="eyebrow" style="color:var(--green);margin-bottom:8px">Sua disciplina</div><div class="section-heading" style="margin:0"><div><h2 style="font-size:27px;letter-spacing:-.05em;margin:0">'+esc(m.nome)+'</h2><p>Materiais, atividades e informações da matéria</p></div><a href="'+m.pasta+'" style="font-size:12px">Abrir pasta ↗</a></div><div class="tabs">'+tabs.map(t=>'<button data-t="'+t+'" class="'+(t===aba?"on":"")+'">'+(nomes[t]||t)+'</button>').join("")+'</div>';
 const pz=D.prazos.filter(p=>p.materia===m.nome&&p.ts>agora-86400);if(pz.length&&aba==="Atividades")h+='<div class="card">'+prazos(pz)+'</div>';
 if(aba==="Materiais"){if(!m.materiais.length)h+='<p class="vazio">Nenhum material baixado ainda.</p>';
  const g={};m.materiais.forEach(x=>(g[x.grupo]=g[x.grupo]||[]).push(x));
  for(const k in g)h+='<div class="card"><b>'+esc(k)+'</b><ul>'+g[k].map(x=>'<li><a href="'+x.href+'">'+esc(x.nome)+'</a> <span class="mu">'+x.kb+' KB</span></li>').join("")+'</ul></div>';}
 else if(aba==="Conteudo")h+=m.conteudo?'<div class="card md">'+md(m.conteudo,m.pasta)+'</div>':'<p class="vazio">Ainda não sincronizado.</p>';
 else{const l=m.secoes[aba]||[];h+=l.length?l.map(item).join(""):'<p class="vazio">Nada aqui ainda.</p>';}
 return h;}
function busca(q){q=q.toLowerCase();let r=[];D.materias.forEach(m=>{for(const s in m.secoes)m.secoes[s].forEach(it=>{if((it.titulo+" "+it.md).toLowerCase().includes(q))r.push([m.nome,s,it]);});
 m.materiais.forEach(x=>{if((x.nome+" "+x.md).toLowerCase().includes(q))r.push([m.nome,"Materiais",{titulo:x.nome,md:x.md,href:x.href,dir:x.dir,anexos:[],arquivo:!x.md}]);});});
 return'<h2>Busca: '+esc(q)+'</h2>'+(r.length?r.map(([n,s,it])=>'<div class="mu">'+esc(n)+' › '+esc(s)+'</div>'+item(it)).join(""):'<p class="vazio">Nada encontrado.</p>');}
function render(){nav();const q=$("#q").value.trim();let h;
 if(q)h=busca(q);
 else if(vista.tipo==="prazos"){
  const pendentes=D.prazos.filter(p=>!(p.situacao&&/ENTREGUE/.test(p.situacao)&&!/NAO/.test(p.situacao)));
  const proximos=D.prazos.filter(p=>p.ts>agora-2*86400).slice(0,12);
  const urgentes=pendentes.filter(p=>p.ts>=agora&&p.ts<agora+7*86400).length;
  const concluidos=D.prazos.length-pendentes.length;
  const data=new Intl.DateTimeFormat("pt-BR",{weekday:"long",day:"numeric",month:"long"}).format(new Date());
  h='<section class="hero"><div class="eyebrow">'+esc(data)+'</div><h2>Um semestre mais leve começa com clareza.</h2><p>Acompanhe suas entregas, encontre seus materiais e mantenha cada disciplina em dia.</p><span class="hero-tag"><i></i>'+D.materias.length+' disciplinas conectadas</span></section>'
   +'<section class="stats"><div class="stat accent"><div class="stat-label">Prazos nesta semana</div><div class="stat-value">'+urgentes+'</div><div class="stat-note">entregas e avaliações</div></div><div class="stat"><div class="stat-label">Disciplinas</div><div class="stat-value">'+D.materias.length+'</div><div class="stat-note">organizadas em um só lugar</div></div><div class="stat"><div class="stat-label">Concluídos</div><div class="stat-value">'+concluidos+'</div><div class="stat-note">itens entregues</div></div></section>'
   +'<div class="section-heading"><div><h3>Próximos prazos</h3><p>O que merece sua atenção agora</p></div><span class="bd b-mu">'+proximos.length+' itens</span></div><div class="card">'+prazos(proximos)+'</div>';
 }
 else if(vista.tipo==="fila"){h='<h2 style="margin-top:0">Envios pedidos por agentes de IA</h2><div id="fila" class="card">carregando...</div>';setTimeout(carregarFila,0);}
 else if(vista.tipo==="novidades")h='<h2 style="margin-top:0">Novidades</h2><div class="card md">'+(md(D.novidades)||'<p class="vazio">Nenhuma ainda.</p>')+'</div><div class="card md">'+md(D.status)+'</div>';
 else h=materia(D.materias[vista.i]);
 $("#main").innerHTML=h;document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{aba=b.dataset.t;render();});}
$("#info").textContent="Sincronizado: "+(D.sincronizado?new Date(D.sincronizado).toLocaleString("pt-BR"):"ainda não")+" · página gerada "+D.gerado;
$("#q").oninput=render;render();
</script></body></html>"""

