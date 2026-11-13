# Contrato para agentes de IA

Este arquivo explica para **qualquer agente de IA** (Claude, ChatGPT/Codex, Gemini CLI,
Copilot, um modelo local etc.) como ler os dados gerados pelo `ava-sync` e como escrever
conteúdo que aparece no painel. Não é preciso mexer em código.

## Regras

1. **Não fale com o Moodle diretamente.** Não rode `python -m avasync enviar`, não chame a API,
   não responda questionários, não faça login nem peça senha/token. Os dados já estão nas pastas.
   Para entregar algo, **deixe um pedido na fila** (seção abaixo): a pessoa aprova no painel.
2. **Não altere** os arquivos gerados pelo sync (`Atividades/`, `Provas/`, `Anuncios/`,
   `Materiais/`, `CONTEUDO_DA_DISCIPLINA.md`, `02_CALENDARIO/`, `03_RELATORIOS/`).
   Eles são sobrescritos a cada sincronização.
3. Escreva **apenas** em `01_DISCIPLINAS/<materia>/Guias/`, em `04_ENVIOS/fila/` e, se quiser,
   em `03_RELATORIOS/ia/`.
4. **Ajude a aprender, não entregue a resposta pronta.** Guias explicam o que é pedido,
   os conceitos, um passo a passo e um checklist; não escrevem o trabalho final.

## Onde ler (dentro de `pasta_saida`)

| Caminho | Conteúdo |
|---|---|
| `03_RELATORIOS/ultima_sincronizacao.json` | resumo estruturado: matérias, tarefas (id, nome, entrega em timestamp, situação, arquivo), questionários, avisos, novidades |
| `03_RELATORIOS/novidades.md` | histórico do que apareceu de novo |
| `03_RELATORIOS/STATUS.md` | se a última sincronização deu certo |
| `02_CALENDARIO/prazos.md` | todos os prazos em ordem |
| `01_DISCIPLINAS/<materia>/Atividades/AAAA-MM-DD_<nome>.md` | enunciado completo, datas, situação, nota |
| `01_DISCIPLINAS/<materia>/Atividades/<mesmo nome>_anexos/` | anexos do professor |
| `01_DISCIPLINAS/<materia>/Provas/*.md` | questionários/provas online |
| `01_DISCIPLINAS/<materia>/Anuncios/*.md` | avisos e fóruns |
| `01_DISCIPLINAS/<materia>/Materiais/` | arquivos baixados (por seção) e páginas de texto |
| `01_DISCIPLINAS/<materia>/CONTEUDO_DA_DISCIPLINA.md` | todas as seções com os textos do professor |

## Como escrever um guia

Arquivo: `01_DISCIPLINAS/<materia>/Guias/<mesmo nome do .md da atividade>.md`

Comece com este cabeçalho (o painel esconde o cabeçalho e mostra o resto):

```
---
gerado_por: <seu-nome-de-agente>      # ex.: claude-cowork, codex, gemini-cli
fonte: Atividades/<arquivo da atividade>.md
gerado_em: <data ISO>
---
# Guia: <nome da atividade>
...
```

- Use `gerado_por` diferente de `avasync-ia`. Guias com outro valor **nunca** são
  sobrescritos pelo comando `python -m avasync guias`.
- Depois de escrever, rode `python -m avasync painel` para atualizar o painel
  (ou espere a próxima sincronização).

Estrutura sugerida do guia: veja `prompts/guia_atividade.md`.

## Como pedir um envio (fila)

Crie uma pasta nova em `04_ENVIOS/fila/<AAAAMMDD-HHMM>_<nome-curto>/` com os arquivos a
entregar e um `pedido.json`:

```json
{
  "tarefa_id": 12345,
  "titulo": "Trabalho 2 - Diagrama de Classes",
  "arquivos": ["trabalho2.pdf"],
  "texto_arquivo": null,
  "agente": "nome-do-agente",
  "observacao": "o que foi feito e o que a pessoa deve conferir"
}
```

- `tarefa_id` é o `id` da tarefa em `03_RELATORIOS/ultima_sincronizacao.json`.
- `arquivos` são nomes de arquivos dentro da própria pasta do pedido.
- `texto_arquivo` (opcional) é um .md/.txt na pasta, enviado como texto online.

O que acontece depois:

- O pedido aparece no painel (`python -m avasync servidor`, menu **Envios da IA**). A pessoa
  revisa e aprova ou rejeita. A aprovação é a única forma de **finalizar** a entrega e de
  aceitar a **declaração de autoria**, que é uma declaração da pessoa e nunca do agente.
- Se o config tiver `[envio] auto_rascunho = true`, o pedido é salvo sozinho no Moodle **como
  rascunho**, mas só em tarefas que usam rascunho (onde salvar ainda não é entregar).
- Depois de processados, os pedidos vão para `04_ENVIOS/enviados/` ou `04_ENVIOS/rejeitados/`.
