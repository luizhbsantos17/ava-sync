# ava-sync

Sincroniza o seu **Moodle** (AVA da faculdade) com pastas no seu computador e gera um
**painel** offline com prazos, atividades, avisos e materiais. Opcionalmente, uma **IA à sua
escolha** (OpenAI, Claude, Gemini, Ollama local, OpenRouter, Groq...) escreve guias de estudo
para cada atividade pendente.

- **Leitura por padrão:** sincronizar, gerar guias e o painel nunca alteram nada no Moodle. O único comando que escreve é o `enviar`, que só roda num terminal, com confirmação digitada pela pessoa.
- **Sem senha salva:** o login gera um token do Moodle, guardado no cofre de credenciais do
  sistema (Gerenciador de Credenciais do Windows, Keychain do macOS, Secret Service do Linux).
- **Funciona em qualquer Moodle** que tenha o serviço do app oficial habilitado.

> Use apenas com a **sua própria conta** e respeite as regras da sua instituição.

## Como funciona

```
Moodle (API REST)  -->  avasync sync  -->  pastas .md + arquivos  -->  PAINEL.html
                                                  |
                              avasync guias (IA via API)  ou  um agente de IA (AGENTS.md)
                                                  |
                                     01_DISCIPLINAS/<materia>/Guias/*.md
```

O Moodle tem uma API REST (Web Services), a mesma usada pelo app "Moodle Mobile".
No `login`, o script troca seu usuário e senha por um **token**, e daí em diante só usa o token.

### Meu Moodle tem a API?

Pelo terminal (troque o endereço):

```bash
curl -s -X POST "https://SEU-MOODLE/lib/ajax/service-nologin.php?info=tool_mobile_get_public_config" \
  -H "Content-Type: application/json" \
  -d '[{"index":0,"methodname":"tool_mobile_get_public_config","args":{}}]'
```

Procure `"enablewebservices":1` e `"enablemobilewebservice":1`. Se `typeoflogin` for 2 ou 3
(login por navegador/SSO), o `login` por usuário e senha pode não funcionar.

## Instalação

Requer Python 3.10+.

```bash
git clone https://github.com/SEU-USUARIO/ava-sync.git
cd ava-sync
pip install -r requirements.txt
cp config.example.toml config.toml      # Windows: copy config.example.toml config.toml
# edite config.toml: site e pasta_saida
python -m avasync login
python -m avasync sync
```

Abra `<pasta_saida>/PAINEL.html` no navegador.

## Comandos

| Comando | O que faz |
|---|---|
| `python -m avasync login` | gera e guarda o token (pede a senha uma vez) |
| `python -m avasync sync` | sincroniza e atualiza o painel |
| `python -m avasync guias` | gera guias das atividades pendentes com a IA do `[ia]` |
| `python -m avasync tudo` | sync + guias + painel |
| `python -m avasync painel` | só regera o painel |
| `python -m avasync servidor` | abre o painel com os botões **Atualizar agora** e **Enviar atividade**, e a fila da IA |
| `python -m avasync fila` | processa a fila de envios dos agentes (só rascunho, se `auto_rascunho`) |
| `python -m avasync logout` | apaga o token deste computador |
| `python -m avasync enviar --atividade "Trabalho 2" --arquivo trabalho.pdf` | envia uma tarefa (pede confirmação) |

Use `--config caminho/do/config.toml` para ter mais de uma configuração.

## Enviar uma tarefa

### Pelo painel

```bash
python -m avasync servidor
```

O navegador abre em `http://127.0.0.1:8765`, com o mesmo painel e mais três recursos:

- **Atualizar agora**: roda a sincronização na hora, sem esperar o agendador.
- **Enviar atividade**, dentro de cada tarefa: mostra prazo, situação e o que já foi enviado. Você escolhe os arquivos e confirma digitando ENVIAR. Se a tarefa exigir a declaração de autoria, é preciso marcá-la para finalizar.
- **Envios da IA**: pedidos deixados por agentes, para você aprovar ou rejeitar.

O servidor só aceita conexões do próprio computador e usa uma chave aleatória a cada execução, então um site aberto no navegador não consegue disparar um envio. O token continua no cofre de credenciais e nunca vai para a página.

### Pelo terminal

```bash
python -m avasync enviar --atividade "Trabalho 2" --arquivo trabalho.pdf            # salva a entrega
python -m avasync enviar --atividade "Trabalho 2" --arquivo trabalho.pdf --finalizar # e envia para avaliação
python -m avasync enviar --atividade 1234 --texto resposta.md                 # texto online
```

- `--atividade` aceita o id da tarefa ou um trecho do nome. Se mais de uma tarefa combinar, o comando lista as opções e para.
- Antes de enviar, ele mostra a tarefa, o prazo, a situação e os arquivos que já foram entregues, e só continua se você digitar **ENVIAR**.
- Se a tarefa exige a declaração de autoria, o texto aparece na tela e você precisa digitar **ACEITO**. Para enviar para avaliação, é preciso digitar **FINALIZAR**.
- Os arquivos novos **substituem** os que já estavam na entrega.
- Por segurança, o comando recusa rodar sem terminal interativo, então não funciona pelo agendador nem por agentes de IA.

## Agentes de IA enviando atividades

Agentes não enviam direto: eles deixam um pedido em `04_ENVIOS/fila/` (formato no [AGENTS.md](AGENTS.md)), e você aprova no painel. Com `[envio] auto_rascunho = true`, os pedidos já são salvos no Moodle como **rascunho**, nas tarefas que usam rascunho, e você só finaliza.

Finalizar a entrega e aceitar a declaração de autoria ("este é meu próprio trabalho") ficam sempre com a pessoa. Essa declaração é sua, e um programa não pode fazê-la por você.

## Agendar

- **Windows:** `powershell -ExecutionPolicy Bypass -File scripts\agendar_windows.ps1`
  (cria duas tarefas diárias, 07:10 e 19:10).
- **Linux/macOS:** `bash scripts/agendar_cron.sh`.

## IA (opcional)

### Opção 1: por API (`python -m avasync guias`)

No `config.toml`, seção `[ia]`. A chave fica numa **variável de ambiente**; o config guarda
só o nome dela.

| Provedor | Exemplo |
|---|---|
| Ollama (local, grátis) | `provedor="openai"` `base_url="http://localhost:11434/v1"` `modelo="llama3.1"` `api_key_env=""` |
| OpenAI | `provedor="openai"` `modelo="<modelo>"` `api_key_env="OPENAI_API_KEY"` |
| OpenRouter | `provedor="openai"` `base_url="https://openrouter.ai/api/v1"` `modelo="<modelo>"` `api_key_env="OPENROUTER_API_KEY"` |
| Groq | `provedor="openai"` `base_url="https://api.groq.com/openai/v1"` `modelo="<modelo>"` `api_key_env="GROQ_API_KEY"` |
| Anthropic (Claude) | `provedor="anthropic"` `modelo="<modelo>"` `api_key_env="ANTHROPIC_API_KEY"` |
| Google Gemini | `provedor="gemini"` `modelo="<modelo>"` `api_key_env="GEMINI_API_KEY"` |

Consulte a documentação do provedor para os nomes de modelo atuais. O texto enviado à IA
está em `prompts/guia_atividade.md` e pode ser editado. Para a IA ler anexos PDF/DOCX:
`pip install pypdf python-docx`.

Atenção: no modo API, o enunciado e o texto dos anexos são **enviados ao provedor**
escolhido. Se não quiser que saiam do seu computador, use o Ollama.

### Opção 2: por agente

Agentes como Claude (Cowork/Code), Codex, Gemini CLI ou Copilot podem ler as pastas e escrever
guias diretamente, seguindo o [AGENTS.md](AGENTS.md). Guias escritos por agentes nunca são
sobrescritos pelo modo API.

## O que é baixado

| No Moodle | No seu computador |
|---|---|
| Arquivo, Pasta, Pacote de conteúdo | o arquivo, mantendo as subpastas (um HTML com imagens continua abrindo) |
| Página, Rótulo, enunciados, avisos | o texto em `.md`, com as **imagens baixadas** em `_imagens/` |
| Livro | `LIVRO.html` (com sumário e imagens) e `LIVRO.md` |
| URL para um arquivo (PDF, PPT...) | o arquivo, em `Materiais/<seção>/Links/` |
| URL para uma página pública | uma cópia `.html` com as imagens e um `.md` com o texto, refeita a cada 7 dias |
| YouTube, Google Drive, reuniões, formulários, bibliotecas virtuais, páginas com login | só o link, no `CONTEUDO_DA_DISCIPLINA.md` |
| Questionários, H5P, SCORM, ferramentas externas (LTI) | só o link |

O token do Moodle só é usado em endereços do próprio Moodle. Sites externos são acessados sem token e sem login.
Livros de bibliotecas virtuais (Pearson, Minha Biblioteca etc.) abrem num leitor protegido e não são baixados.

## Estrutura gerada

```
pasta_saida/
  PAINEL.html
  01_DISCIPLINAS/<materia>/
    CONTEUDO_DA_DISCIPLINA.md
    Atividades/  Provas/  Anuncios/  Materiais/  Guias/
  02_CALENDARIO/prazos.md
  03_RELATORIOS/  STATUS.md  novidades.md  ultima_sincronizacao.json
  .avasync/       estado.json  avasync.log
```

## Privacidade

- O repositório não contém dados de ninguém: `config.toml`, a pasta de saída, logs e
  painel estão no `.gitignore`.
- O log nunca registra senha nem token.
- Para revogar o token: no Moodle, *Preferências → Chaves de segurança*, e `python -m avasync logout`.

## Testes

```bash
python -m unittest discover tests
```

Os testes usam respostas simuladas da API; não acessam nenhum Moodle.

## Licença

MIT.
