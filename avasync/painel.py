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
:root{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mu:#667085;--bd:#e3e6eb;--ac:#2563eb;--ok:#16a34a;--wa:#d97706;--er:#dc2626}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1a1e24;--tx:#e6e8eb;--mu:#98a2b3;--bd:#2b313a;--ac:#60a5fa;--ok:#4ade80;--wa:#fbbf24;--er:#f87171}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--tx)}
header{padding:14px 20px;border-bottom:1px solid var(--bd);display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:var(--card);position:sticky;top:0;z-index:2}
header h1{font-size:18px;margin:0;margin-right:auto}header small{color:var(--mu)}
input[type=search]{padding:7px 10px;border:1px solid var(--bd);border-radius:8px;background:var(--bg);color:var(--tx);min-width:220px}
.wrap{display:flex;min-height:calc(100vh - 60px)}
nav{width:250px;border-right:1px solid var(--bd);padding:12px;flex-shrink:0;background:var(--card)}
nav button{display:block;width:100%;text-align:left;padding:8px 10px;border:0;border-radius:8px;background:none;color:var(--tx);cursor:pointer;font:inherit;margin-bottom:2px}
nav button:hover{background:var(--bg)}nav button.on{background:var(--ac);color:#fff}
nav .lb{font-size:12px;color:var(--mu);text-transform:uppercase;margin:12px 8px 4px}
main{flex:1;padding:20px;max-width:1000px;min-width:0}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.tabs{display:flex;gap:6px;margin:8px 0 14px;flex-wrap:wrap}.tabs button{padding:6px 12px;border:1px solid var(--bd);border-radius:999px;background:var(--card);color:var(--tx);cursor:pointer;font:inherit}
.tabs button.on{background:var(--ac);border-color:var(--ac);color:#fff}
table{width:100%;border-collapse:collapse}td,th{padding:8px 6px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}th{color:var(--mu);font-weight:500;font-size:13px}
.bd{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.b-er{background:color-mix(in srgb,var(--er) 18%,transparent);color:var(--er)}.b-wa{background:color-mix(in srgb,var(--wa) 18%,transparent);color:var(--wa)}
.b-ok{background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok)}.b-mu{background:var(--bg);color:var(--mu)}
details>summary{cursor:pointer;font-weight:600;list-style:none}details>summary::before{content:"▸ ";color:var(--mu)}details[open]>summary::before{content:"▾ "}
.md{margin-top:8px;overflow-wrap:anywhere}.md h1{font-size:18px}.md h2{font-size:16px}.md h3{font-size:15px}.md pre{white-space:pre-wrap;background:var(--bg);padding:8px;border-radius:8px}
a{color:var(--ac)}.mu{color:var(--mu)}.vazio{color:var(--mu);font-style:italic}
.btn{padding:6px 12px;border:1px solid var(--ac);border-radius:8px;background:var(--ac);color:#fff;cursor:pointer;font:inherit}
.btn.sec{background:none;color:var(--ac)}.btn:disabled{opacity:.5;cursor:default}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:flex-start;justify-content:center;z-index:9;overflow:auto;padding:30px 12px}
#modal .card{max-width:620px;width:100%}#modal label{display:block;margin:8px 0}
#modal input[type=text],#modal textarea{width:100%;padding:6px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--tx);font:inherit}
.aviso{background:color-mix(in srgb,var(--wa) 15%,transparent);border-radius:8px;padding:8px 10px;margin:8px 0}
@media (max-width:760px){.wrap{flex-direction:column}nav{width:auto;border-right:0;border-bottom:1px solid var(--bd)}}
</style></head><body>
<header><h1>Painel AVA</h1><small id="info"></small><span id="acoes"></span><input type="search" id="q" placeholder="Buscar em tudo..."></header>
<div class="wrap"><nav id="nav"></nav><main id="main"></main></div><div id="modal"></div>
<script>
const D=__DADOS__;const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function md(t,b){if(!t)return"";let h=esc(t);
 h=h.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,(m,a,s)=>'<img alt="'+a+'" src="'+(/^(https?:|data:|\/)/.test(s)||!b?s:b+"/"+s)+'" loading="lazy" style="max-width:100%">');
 h=h.replace(/```([\s\S]*?)```/g,(m,c)=>"<pre>"+c+"</pre>");
 h=h.replace(/^### (.*)$/gm,"<h3>$1</h3>").replace(/^## (.*)$/gm,"<h2>$1</h2>").replace(/^# (.*)$/gm,"<h1>$1</h1>");
 h=h.replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g,"$1<i>$2</i>");
 h=h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank">$1</a>');
 h=h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,'$1<a href="$2" target="_blank">$2</a>');
 h=h.replace(/^\s*[-*] (.*)$/gm,"<li>$1</li>").replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g,"<ul>$1</ul>");
 h=h.replace(/^\|(.+)\|$/gm,(m,r)=>/^[-| :]+$/.test(r)?"":"<tr>"+r.split("|").map(c=>"<td>"+c.trim()+"</td>").join("")+"</tr>");
 h=h.replace(/(<tr>[\s\S]*?<\/tr>)(?!\s*<tr>)/g,"<table>$1</table>");
 return h.split(/\n{2,}/).map(p=>/^\s*<(h\d|ul|pre|table)/.test(p)?p:"<p>"+p.replace(/\n/g,"<br>")+"</p>").join("");}

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
function nav(){let h='<button data-v="prazos">Próximos prazos</button><button data-v="novidades">Novidades</button>'+(S?'<button data-v="fila">Envios da IA (fila)</button>':'')+'<div class="lb">Matérias</div>';
 D.materias.forEach((m,i)=>h+='<button data-v="m'+i+'">'+esc(m.nome)+'</button>');
 if(!D.materias.length)h+='<div class="vazio" style="padding:8px">Nenhuma ainda</div>';$("#nav").innerHTML=h;
 document.querySelectorAll("nav button").forEach(b=>{b.classList.toggle("on",b.dataset.v===(vista.tipo==="m"?"m"+vista.i:vista.tipo));
  b.onclick=()=>{const v=b.dataset.v;vista=v[0]==="m"?{tipo:"m",i:+v.slice(1)}:{tipo:v};$("#q").value="";render();}});}
function prazos(lista){if(!lista.length)return'<p class="vazio">Nenhum prazo encontrado.</p>';
 return'<table><tr><th>Quando</th><th></th><th>Matéria</th><th>Item</th></tr>'+lista.map(p=>'<tr><td>'+fdata(p.ts)+'</td><td>'+badge(p.ts,p.situacao)+'</td><td>'+esc(p.materia)+'</td><td>'+esc(p.tipo)+': <b>'+esc(p.nome)+'</b>'+(p.situacao?'<br><span class="mu">'+esc(p.situacao)+'</span>':'')+'</td></tr>').join("")+'</table>';}
function item(it){if(it.arquivo)return'<div class="card"><a href="'+it.href+'">'+esc(it.titulo)+'</a></div>';
 return'<details class="card"><summary>'+esc(it.titulo)+'</summary><div class="md">'+md(it.md,it.dir)+'</div>'+(it.anexos.length?'<p><b>Anexos:</b> '+it.anexos.map(a=>'<a href="'+a.href+'">'+esc(a.nome)+'</a>').join(" · ")+'</p>':'')+'<p class="mu"><a href="'+it.href+'">abrir arquivo</a>'+(it.tarefa_id?(S?' · <button class="btn" onclick="abrirEnvio('+it.tarefa_id+')">Enviar atividade</button>':' · <span title="rode: python -m avasync servidor">para enviar, abra o painel pelo servidor local</span>'):'')+'</p></details>';}
function materia(m){const tabs=["Atividades","Provas","Guias","Anuncios","Materiais","Conteudo"];
 const nomes={Anuncios:"Avisos",Conteudo:"Conteúdo do AVA",Guias:"Guias da IA"};
 let h='<h2 style="margin:0">'+esc(m.nome)+'</h2><p class="mu"><a href="'+m.pasta+'">abrir pasta</a></p><div class="tabs">'+tabs.map(t=>'<button data-t="'+t+'" class="'+(t===aba?"on":"")+'">'+(nomes[t]||t)+'</button>').join("")+'</div>';
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
 else if(vista.tipo==="prazos")h='<h2 style="margin-top:0">Próximos prazos</h2><div class="card">'+prazos(D.prazos.filter(p=>p.ts>agora-2*86400))+'</div>';
 else if(vista.tipo==="fila"){h='<h2 style="margin-top:0">Envios pedidos por agentes de IA</h2><div id="fila" class="card">carregando...</div>';setTimeout(carregarFila,0);}
 else if(vista.tipo==="novidades")h='<h2 style="margin-top:0">Novidades</h2><div class="card md">'+(md(D.novidades)||'<p class="vazio">Nenhuma ainda.</p>')+'</div><div class="card md">'+md(D.status)+'</div>';
 else h=materia(D.materias[vista.i]);
 $("#main").innerHTML=h;document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{aba=b.dataset.t;render();});}
$("#info").textContent="Sincronizado: "+(D.sincronizado?new Date(D.sincronizado).toLocaleString("pt-BR"):"ainda não")+" · página gerada "+D.gerado;
$("#q").oninput=render;render();
</script></body></html>"""

