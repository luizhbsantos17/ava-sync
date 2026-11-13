"""Cliente da API REST do Moodle (Web Services) + guarda do token.

Como funciona:
  1. login: POST /login/token.php (usuario, senha, service=moodle_mobile_app)
     -> o Moodle devolve um TOKEN. A senha so e usada nesse momento.
  2. o token vai para o cofre do sistema (Gerenciador de Credenciais no Windows,
     Keychain no macOS, Secret Service no Linux) pela biblioteca `keyring`.
  3. cada chamada: POST /webservice/rest/server.php com
     wstoken, wsfunction=<funcao>, moodlewsrestformat=json e os parametros.
  4. arquivos: <fileurl>?token=<token> (fileurl ja aponta para webservice/pluginfile.php).
"""
import getpass
import sys
from pathlib import Path

import requests

from .util import log

try:
    import keyring
except ImportError:
    keyring = None


def _precisa_keyring():
    if keyring is None:
        sys.exit("Falta a biblioteca keyring:  pip install -r requirements.txt")


def pegar_token(cfg):
    _precisa_keyring()
    tok = keyring.get_password(cfg.chave_keyring, "token")
    if not tok:
        sys.exit("Sem token salvo. Rode primeiro:  python -m avasync login")
    return tok


def login(cfg):
    _precisa_keyring()
    print(f"Login em {cfg.site} (a senha so e usada agora para gerar o token; NAO e salva).")
    usuario = input("Usuario: ").strip()
    senha = getpass.getpass("Senha (nao aparece enquanto digita): ")
    r = requests.post(f"{cfg.site}/login/token.php",
                      data={"username": usuario, "password": senha, "service": cfg.servico}, timeout=30)
    senha = None
    dados = r.json()
    if "token" not in dados:
        sys.exit(f"Login recusado: {dados.get('error', dados)}")
    keyring.set_password(cfg.chave_keyring, "token", dados["token"])
    print("Token salvo no cofre de credenciais do sistema.")


def logout(cfg):
    if keyring and keyring.get_password(cfg.chave_keyring, "token"):
        keyring.delete_password(cfg.chave_keyring, "token")
    print("Token apagado deste computador. Para revogar no servidor: Moodle > Preferencias > Chaves de seguranca.")


class Moodle:
    def __init__(self, site, token, max_download_mb=200):
        self.site, self.token, self.max_mb = site, token, max_download_mb
        self.s = requests.Session()

    def call(self, funcao, **params):
        dados = {"wstoken": self.token, "wsfunction": funcao, "moodlewsrestformat": "json"}
        for k, v in params.items():
            if isinstance(v, (list, tuple)):
                for i, item in enumerate(v):
                    dados[f"{k}[{i}]"] = item
            else:
                dados[k] = v
        r = self.s.post(f"{self.site}/webservice/rest/server.php", data=dados, timeout=60)
        r.raise_for_status()
        res = r.json()
        if isinstance(res, dict) and res.get("exception"):
            if res.get("errorcode") in ("invalidtoken", "accessexception"):
                raise PermissionError(res.get("message"))
            raise RuntimeError(f"{funcao}: {res.get('errorcode')} - {res.get('message')}")
        return res

    def tentar(self, funcao, padrao=None, **params):
        """Como call, mas uma funcao nao liberada no site nao derruba a sincronizacao."""
        try:
            return self.call(funcao, **params)
        except PermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"  aviso: {funcao} falhou ({e})")
            return padrao

    def ler(self, url):
        """Baixa um arquivo pequeno do Moodle (ex.: capitulo de livro) e devolve o texto."""
        sep = "&" if "?" in url else "?"
        r = self.s.get(f"{url}{sep}token={self.token}", timeout=60)
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text

    def baixar(self, url, destino: Path, tamanho=None):
        if not url:
            return False
        if destino.exists() and (tamanho is None or destino.stat().st_size == tamanho):
            return False
        if tamanho and tamanho > self.max_mb * 1024 * 1024:
            log(f"  pulei (maior que {self.max_mb} MB): {destino.name}")
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(destino.suffix + ".part")
        sep = "&" if "?" in url else "?"
        with self.s.get(f"{url}{sep}token={self.token}", stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for bloco in r.iter_content(1024 * 256):
                    f.write(bloco)
        tmp.replace(destino)
        return True
