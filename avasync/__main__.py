"""Linha de comando:  python -m avasync <comando> [--config caminho]

  login    pede usuario/senha UMA vez, gera o token e guarda no cofre do sistema
  logout   apaga o token deste computador
  sync     le o Moodle e atualiza as pastas + painel (padrao)
  painel   so regera o PAINEL.html (nao acessa o Moodle)
  guias    gera guias das atividades pendentes com a IA configurada em [ia]
  tudo     sync + guias + painel (bom para o agendador)
  enviar   ENVIA uma tarefa pelo terminal (interativo, pede confirmacao)
  servidor abre o painel com botoes de Enviar e Atualizar agora (http://127.0.0.1:8765)
  fila     processa a fila de envios dos agentes de IA (so rascunho, se [envio] auto_rascunho)
"""
import argparse
import sys

import requests

from . import config, envio, ia, moodle, painel, servidor, sync, util


def main(argv=None):
    ap = argparse.ArgumentParser(prog="avasync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", nargs="?", default="sync",
                    choices=["login", "logout", "sync", "painel", "guias", "tudo", "enviar", "servidor", "fila"])
    ap.add_argument("--config", help="caminho do config.toml (padrao: config.toml na raiz do projeto)")
    ap.add_argument("--forcar", action="store_true", help="guias: regenera mesmo sem mudancas")
    ap.add_argument("--atividade", help="enviar: id da tarefa ou trecho do nome")
    ap.add_argument("--arquivo", action="append", help="enviar: arquivo a anexar (pode repetir)")
    ap.add_argument("--texto", help="enviar: arquivo .md/.txt com o texto online")
    ap.add_argument("--finalizar", action="store_true", help="enviar: tambem 'Enviar para avaliacao'")
    a = ap.parse_args(argv)

    cfg = config.carregar(a.config)
    util.configurar(cfg.fuso_horas, cfg.interno / "avasync.log")

    if a.comando == "login":
        return moodle.login(cfg)
    if a.comando == "logout":
        return moodle.logout(cfg)
    if a.comando == "enviar":
        if not a.atividade:
            ap.error("enviar precisa de --atividade")
        try:
            return envio.enviar(cfg, a.atividade, a.arquivo, a.texto, a.finalizar)
        except envio.Cancelado as e:
            print(e)
            return 1
    if a.comando == "servidor":
        return servidor.rodar(cfg)
    try:
        if a.comando in ("fila", "tudo"):
            envio.auto_rascunho(cfg)
        if a.comando in ("sync", "tudo"):
            sync.sync(cfg)
        if a.comando in ("guias", "tudo"):
            ia.gerar_guias(cfg, forcar=a.forcar)
    except requests.RequestException as e:
        util.log(f"Erro de rede: {e}")
        sys.exit(1)
    util.log(f"Painel: {painel.gerar(cfg)}")


if __name__ == "__main__":
    main()
