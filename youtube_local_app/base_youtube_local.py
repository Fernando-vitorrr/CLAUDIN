#!/usr/bin/env python3
"""
base_youtube_local.py

Recebe links do YouTube, obtem a transcricao (legenda automatica ou Whisper),
extrai os pontos relevantes com um modelo local executado pelo Ollama e grava uma nota em markdown
dentro da pasta do Google Drive, cruzando com o que ja existe na base.

Uso:
    python base_youtube_local.py https://youtu.be/XXXX
    python base_youtube_local.py https://youtu.be/AAAA https://youtu.be/BBBB
    python base_youtube_local.py --arquivo links.txt
    python base_youtube_local.py https://youtu.be/XXXX --forcar
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import yt_dlp

# --------------------------------------------------------------------------
# CONFIGURACAO
# --------------------------------------------------------------------------

# Pasta da base. Aponte para dentro do Google Drive para Desktop.
# Windows costuma ser  G:/Meu Drive/Base YouTube
# macOS costuma ser    ~/Google Drive/Meu Drive/Base YouTube
BASE_DIR = Path(
    os.environ.get(
        "YTBASE_DIR",
        Path.home() / "Google Drive" / "Meu Drive" / "Base YouTube",
    )
)

MODELO = os.environ.get("YTBASE_MODEL", "qwen3.5:9b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")

# Janela de contexto, em tokens.
# O Ollama NAO usa a janela cheia do modelo por padrao: sem este valor ele roda
# com poucos milhares de tokens e corta o excedente em silencio, produzindo uma
# nota bem formatada baseada em parte do video.
# A janela consome RAM alem do proprio modelo, por isso vem amarrada ao modelo.
CONTEXTO_POR_MODELO = {
    "qwen3.5:4b": 8_192,
    "qwen3.5:9b": 16_384,
    "qwen3.5:27b": 32_768,
}
CONTEXTO_PADRAO = 16_384


def contexto_do_modelo(modelo: str) -> int:
    return CONTEXTO_POR_MODELO.get(modelo, CONTEXTO_PADRAO)


CONTEXTO = int(os.environ.get("YTBASE_CTX") or contexto_do_modelo(MODELO))

# Fracao da janela efetivamente usada. O resto e margem de seguranca: a contagem
# de tokens aqui e estimada por caractere, nao exata, e errar para mais
# significaria o modelo descartar texto sem avisar.
MARGEM = 0.85

# Sobreposicao entre partes consecutivas de um video longo, em caracteres.
# O marcador de tempo nem sempre cai em fim de frase; repetir o final do trecho
# anterior evita perder raciocinio cortado na fronteira.
SOBREPOSICAO_CHARS = 1_500

# Modelo do faster-whisper usado quando o video nao tem legenda.
# Alternativas mais rapidas e menos precisas: "small", "base".
MODELO_WHISPER = os.environ.get("YTBASE_WHISPER", "medium")

# Ordem de preferencia das legendas.
IDIOMAS_LEGENDA = ["pt", "pt-BR", "pt-orig", "en", "en-US", "en-orig"]

# Quantas notas anteriores entram como contexto do cruzamento.
NOTAS_DE_CONTEXTO = 8

# Formato da nota: "aula" ou "podcast".
FORMATO = os.environ.get("YTBASE_FORMATO", "podcast")

# --------------------------------------------------------------------------
# PROMPTS  -  e aqui que voce ajusta o comportamento da base
# --------------------------------------------------------------------------

SISTEMA = """Voce analisa transcricoes de video e produz notas de estudo densas, \
em portugues do Brasil, para uma base de conhecimento pessoal.

Regras:
- Escreva em prosa articulada. Bullet solto sem desenvolvimento nao serve.
- Preserve o raciocinio do autor, nao apenas as conclusoes.
- Marque timestamps no formato [hh:mm:ss] sempre que apontar um trecho especifico.
- Nao invente nada que nao esteja na transcricao. Se algo ficou obscuro na \
legenda automatica, diga que ficou obscuro.
- Separe o que o autor afirma do que voce observa. Observacao sua vai marcada \
com "Nota:" no inicio do paragrafo.
- Nao use expressoes absolutas nem elogios ao conteudo. Avalie a solidez do \
argumento quando ela for fraca."""


ESTRUTURA = """Produza a nota exatamente com estas secoes, nesta ordem:

## Tese central
Um paragrafo unico dizendo o que o video sustenta. Direto, sem preambulo.

## Desenvolvimento
Quatro a oito paragrafos percorrendo o argumento na ordem em que ele e \
construido, com timestamps. Explique os passos intermediarios, nao so o \
resultado.

## Evidencias e exemplos
O que o autor usa para sustentar cada ponto: dados, casos, referencias, \
experiencia propria. Aponte quando a sustentacao for apenas assertiva.

## Trechos relevantes
Ate seis trechos curtos que valem guardar, cada um com timestamp. Sao \
formulacoes aproximadas, reconstruidas de transcricao automatica: nao use \
aspas nem apresente como citacao literal.

## Aplicacao pratica
O que decorre disso para quem vai usar o conteudo. Concreto.

## Conexoes com a base
Convergencias, contradicoes e lacunas em relacao as notas ja existentes \
listadas abaixo. Se nao houver relacao real com nenhuma delas, escreva \
"Sem conexao relevante com a base atual" e pare a secao.

## Tags
Uma unica linha com 3 a 7 tags separadas por virgula, em minusculas."""


ESTRUTURA_PODCAST = """A transcricao e de uma conversa, nao de uma exposicao. \
Ela NAO identifica quem esta falando. Nao atribua fala a pessoa nenhuma, a nao \
ser quando a propria transcricao deixar claro, porque alguem se nomeia ou e \
chamado pelo nome. Na duvida, escreva de forma impessoal.

Produza a nota exatamente com estas secoes, nesta ordem:

## Tese central
Um paragrafo dizendo do que trata a conversa e qual o fio condutor dela. \
Direto, sem preambulo.

## Blocos da conversa
Um bloco para cada assunto tratado, na ordem em que aparecem. Comece cada \
bloco por um titulo em negrito seguido da faixa de tempo, assim: \
**Nome do assunto** [00:12:30 - 00:31:05]. Sob cada titulo, dois a quatro \
paragrafos explicando o que foi dito e como o raciocinio se desenvolve. \
Descarte conversa fiada, digressao e piada que nao acrescentem.

## Afirmacoes e dados
Numeros, casos, referencias e afirmacoes factuais ditas na conversa, com \
timestamp. Marque como "sem sustentacao" o que for afirmado de forma assertiva \
sem qualquer respaldo.

## Trechos relevantes
Ate seis trechos curtos que valem guardar, cada um com timestamp. Sao \
formulacoes aproximadas, reconstruidas de transcricao automatica: nao use \
aspas nem apresente como citacao literal.

## Aplicacao pratica
O que decorre da conversa para quem vai usar o conteudo. Concreto.

## Conexoes com a base
Convergencias, contradicoes e lacunas em relacao as notas ja existentes \
listadas abaixo. Se nao houver relacao real com nenhuma delas, escreva \
"Sem conexao relevante com a base atual" e pare a secao.

## Tags
Uma unica linha com 3 a 7 tags separadas por virgula, em minusculas."""


def escolher_estrutura():
    """A escolha e sempre explicita. Adivinhar pela duracao classificava mal
    aula longa, palestra, sustentacao oral e curso gravado."""
    formato = FORMATO if FORMATO in ("aula", "podcast") else "podcast"
    return (ESTRUTURA_PODCAST if formato == "podcast" else ESTRUTURA), formato


def resposta_max() -> int:
    """Teto da resposta, proporcional a janela. Fixar 6000 tokens quebrava a
    configuracao de 8.192, onde nao sobrava espaco para a transcricao."""
    return max(1_800, min(6_000, int(CONTEXTO * MARGEM) // 3))


def conferir_secoes(nota: str, estrutura: str):
    esperadas = re.findall(r"^## (.+)$", estrutura, re.M)
    faltando = [s for s in esperadas if f"## {s}" not in nota]
    if faltando:
        print("  AVISO: nota incompleta, faltam as secoes: " + ", ".join(faltando))


# --------------------------------------------------------------------------
# TRANSCRICAO
# --------------------------------------------------------------------------

TIMECODE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,]\d{3}\s+-->")
TAG_INLINE = re.compile(r"<[^>]+>")


def fmt_tempo(segundos: int) -> str:
    h, resto = divmod(int(segundos), 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def metadados(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "id": info.get("id", ""),
        "titulo": info.get("title", "sem titulo"),
        "canal": info.get("uploader", "desconhecido"),
        "duracao": int(info.get("duration") or 0),
        "publicado": info.get("upload_date", ""),
        "url": info.get("webpage_url", url),
    }


def baixar_legenda(url: str, tmp: Path):
    """Devolve o caminho do .vtt preferido, ou None."""
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": IDIOMAS_LEGENDA,
        "subtitlesformat": "vtt",
        "outtmpl": str(tmp / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"  aviso: falha ao baixar legenda ({e})")
        return None

    arquivos = list(tmp.glob("*.vtt"))
    if not arquivos:
        return None
    for idioma in IDIOMAS_LEGENDA:
        for arq in arquivos:
            if f".{idioma}." in arq.name:
                return arq
    return arquivos[0]


def parse_vtt(caminho: Path):
    """Converte VTT em [(segundo, texto)], removendo a duplicacao das
    legendas automaticas do YouTube (cada bloco repete a linha anterior)."""
    linhas = caminho.read_text(encoding="utf-8", errors="ignore").splitlines()
    segmentos, anterior = [], []
    i = 0
    while i < len(linhas):
        m = TIMECODE.match(linhas[i].strip())
        if not m:
            i += 1
            continue
        segundo = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        i += 1
        bloco = []
        while i < len(linhas) and linhas[i].strip() and not TIMECODE.match(linhas[i].strip()):
            texto = TAG_INLINE.sub("", linhas[i]).strip()
            if texto and texto not in anterior and texto not in bloco:
                bloco.append(texto)
            i += 1
        if bloco:
            segmentos.append((segundo, " ".join(bloco)))
            anterior = bloco
    return segmentos


def transcrever_audio(url: str, tmp: Path):
    """Fallback: baixa o audio e transcreve local com faster-whisper.
    Exige `pip install faster-whisper`."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  faster-whisper nao instalado; nao ha como transcrever sem legenda.")
        return []

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp / "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    audios = list(tmp.glob("audio.*"))
    if not audios:
        return []

    print(f"  transcrevendo com Whisper ({MODELO_WHISPER}); pode demorar bastante...")
    print("  na primeira execucao o modelo e baixado, o que leva alguns minutos.")
    modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    trechos, _ = modelo.transcribe(str(audios[0]), language=None, vad_filter=True)
    return [(int(t.start), t.text.strip()) for t in trechos if t.text.strip()]


def montar_transcricao(segmentos, passo=45) -> str:
    """Texto corrido com marcador de tempo a cada `passo` segundos."""
    partes, proximo = [], 0
    for segundo, texto in segmentos:
        if segundo >= proximo:
            partes.append(f"\n\n[{fmt_tempo(segundo)}] ")
            proximo = segundo + passo
        partes.append(texto + " ")
    return "".join(partes).strip()


# --------------------------------------------------------------------------
# BASE EXISTENTE
# --------------------------------------------------------------------------

def campo_frontmatter(texto: str, campo: str):
    m = re.search(rf"^{re.escape(campo)}:\s*(.+)$", texto, re.M)
    if not m:
        return None
    valor = m.group(1).strip()
    try:
        return str(json.loads(valor))
    except (json.JSONDecodeError, TypeError):
        return valor


def contexto_da_base() -> str:
    if not BASE_DIR.exists():
        return "A base ainda esta vazia."

    notas = [p for p in BASE_DIR.glob("*.md") if not p.name.startswith("_")]
    notas.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    linhas = []
    for nota in notas[:NOTAS_DE_CONTEXTO]:
        texto = nota.read_text(encoding="utf-8", errors="ignore")
        titulo = campo_frontmatter(texto, "titulo")
        tags = campo_frontmatter(texto, "tags")
        tese = re.search(r"## Tese central\s*\n+(.+)", texto)
        linhas.append(
            "- {t} [{g}]: {s}".format(
                t=titulo or nota.stem,
                g=tags or "sem tags",
                s=(tese.group(1).strip()[:400] if tese else "sem tese registrada"),
            )
        )
    return "\n".join(linhas) if linhas else "A base ainda esta vazia."


# --------------------------------------------------------------------------
# CHAMADAS AO MODELO LOCAL
# --------------------------------------------------------------------------

def estimar_tokens(texto: str) -> int:
    """Estimativa grosseira para portugues: cerca de 3,5 caracteres por token."""
    return int(len(texto) / 3.5)


def chamar(prompt: str, max_tokens: int = 0) -> str:
    """Envia o prompt ao Ollama local. Nenhum conteudo sai do computador."""
    max_tokens = max_tokens or resposta_max()
    util = int(CONTEXTO * MARGEM)
    entrada = estimar_tokens(prompt) + estimar_tokens(SISTEMA)
    if entrada + max_tokens > util:
        # Interrompe em vez de avisar: o Ollama truncaria o excedente em
        # silencio e a nota sairia completa na aparencia, parcial no conteudo.
        raise RuntimeError(
            f"prompt de ~{entrada:,} tokens mais {max_tokens:,} de resposta excedem "
            f"a area util de {util:,} tokens (janela de {CONTEXTO:,}). "
            "Use um modelo com janela maior ou processe o video em trechos."
        )
    payload = json.dumps(
        {
            "model": MODELO,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "num_ctx": CONTEXTO,
                "num_predict": max_tokens,
                "temperature": 0.2,
            },
        }
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=3600) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Nao foi possivel falar com o Ollama. Confirme que ele esta instalado "
            "e aberto no computador."
        ) from exc
    conteudo = dados.get("message", {}).get("content", "").strip()
    if not conteudo:
        raise RuntimeError(f"O Ollama nao devolveu texto: {dados}")
    return conteudo


MARCADOR = re.compile(r"(?=\n\n\[\d{2}:\d{2}:\d{2}\] )")


def dividir(texto: str, tamanho: int, sobreposicao: int = 0):
    """Divide a transcricao em partes equilibradas, cortando em marcador de
    tempo e repetindo o final da parte anterior. O marcador reduz muito a
    chance de cortar no meio de uma frase, mas nao elimina: ele pode cair em
    raciocinio ainda em construcao, e e para isso que serve a sobreposicao."""
    if len(texto) <= tamanho:
        return [texto]
    quantidade = -(-len(texto) // tamanho)
    alvo = -(-len(texto) // quantidade)
    # Um pedaco entre marcadores maior que o alvo (trecho longo sem legenda,
    # marcador ausente) precisa ser cortado no caractere, senao a parte inteira
    # passa direto e estoura a janela.
    pedacos = []
    for bruto in MARCADOR.split(texto):
        if len(bruto) <= alvo:
            pedacos.append(bruto)
        else:
            pedacos += [bruto[i : i + alvo] for i in range(0, len(bruto), alvo)]

    partes, atual = [], ""
    for pedaco in pedacos:
        if atual and len(atual) + len(pedaco) > alvo:
            partes.append(atual)
            atual = pedaco
        else:
            atual += pedaco
    if atual.strip():
        partes.append(atual)
    if sobreposicao:
        partes = [partes[0]] + [
            anterior[-sobreposicao:] + parte
            for anterior, parte in zip(partes, partes[1:])
        ]
    return partes


def gerar_nota(meta: dict, transcricao: str, contexto: str) -> str:
    cabecalho = (
        f"Video: {meta['titulo']}\n"
        f"Canal: {meta['canal']}\n"
        f"Duracao: {fmt_tempo(meta['duracao'])}\n"
        f"URL: {meta['url']}\n"
    )

    estrutura, formato = escolher_estrutura()
    print(f"  formato da nota: {formato}")

    # Todo o orcamento sai da janela, nunca de constante fixa.
    util = int(CONTEXTO * MARGEM)
    resposta = resposta_max()
    reserva = estimar_tokens(SISTEMA + estrutura + contexto + cabecalho) + 400
    entrada_max = util - resposta - reserva
    if entrada_max < 800:
        raise RuntimeError(
            f"a janela de {CONTEXTO:,} tokens nao comporta nem o cabecalho da nota. "
            "Use um modelo com janela maior ou reduza NOTAS_DE_CONTEXTO."
        )
    limite_chars = int(entrada_max * 3.5)

    if len(transcricao) <= limite_chars:
        corpo = transcricao
    else:
        # Video longo: resume por partes e depois sintetiza. A sintese final
        # rele todas as notas brutas de uma vez, entao o teto de cada uma sai
        # do orcamento de entrada dividido pelo numero de partes, com folga.
        partes = dividir(
            transcricao,
            max(4_000, limite_chars - SOBREPOSICAO_CHARS),
            SOBREPOSICAO_CHARS,
        )
        teto = max(600, int(entrada_max * 0.9) // len(partes))
        palavras = max(250, int(teto / 1.8))
        print(
            f"  transcricao longa; {len(partes)} partes de ate {teto:,} tokens cada"
        )
        notas_brutas = []
        for n, parte in enumerate(partes, 1):
            p = (
                f"{cabecalho}\n"
                f"Este e o trecho {n} de {len(partes)} da transcricao.\n"
                "Registre em notas densas, com timestamps, tudo que for relevante "
                "neste trecho: argumentos, exemplos, dados, formulacoes marcantes. "
                "Nao conclua nada ainda, apenas registre. Seja economico: no "
                f"maximo {palavras} palavras.\n\n"
                f"---\n{parte}"
            )
            notas_brutas.append(chamar(p, max_tokens=min(teto, resposta)))
            print(f"  parte {n}/{len(partes)} lida")

        # Em janelas pequenas, muitas partes somadas ainda nao cabem na sintese
        # final. Compacta em rodadas, juntando de duas em duas, ate caber.
        rodada = 0
        while len(notas_brutas) > 1 and estimar_tokens(
            "\n\n".join(notas_brutas)
        ) > entrada_max:
            rodada += 1
            grupos = [
                "\n\n".join(notas_brutas[i : i + 2])
                for i in range(0, len(notas_brutas), 2)
            ]
            teto_g = max(400, int(entrada_max * 0.9) // len(grupos))
            print(
                f"  notas ainda extensas; compactacao {rodada}: "
                f"{len(notas_brutas)} -> {len(grupos)}"
            )
            notas_brutas = [
                chamar(
                    f"{cabecalho}\n"
                    "Condense as notas abaixo em um texto unico, preservando "
                    "timestamps, numeros e formulacoes marcantes. Nao acrescente "
                    f"nada. No maximo {max(200, int(teto_g / 1.8))} palavras.\n\n"
                    f"---\n{grupo}",
                    max_tokens=min(teto_g, resposta),
                )
                for grupo in grupos
            ]

        corpo = "\n\n".join(notas_brutas)
        if estimar_tokens(corpo) > entrada_max:
            raise RuntimeError(
                f"video longo demais para a janela de {CONTEXTO:,} tokens, mesmo "
                "apos compactacao. Use um modelo com janela maior."
            )

    prompt = (
        f"{cabecalho}\n"
        f"Notas ja existentes na base:\n{contexto}\n\n"
        f"{estrutura}\n\n"
        "Responda apenas com a nota em markdown, comecando direto em "
        "'## Tese central'. Sem preambulo, sem comentario final.\n\n"
        f"--- TRANSCRICAO ---\n{corpo}"
    )
    nota = chamar(prompt, max_tokens=resposta)
    conferir_secoes(nota, estrutura)
    return nota, formato


# --------------------------------------------------------------------------
# GRAVACAO
# --------------------------------------------------------------------------

def limpar_nome(texto: str) -> str:
    texto = re.sub(r"[\\/:*?\"<>|]", "-", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:90]


def extrair_tags(nota: str) -> str:
    m = re.search(r"## Tags\s*\n+(.+)", nota)
    return m.group(1).strip() if m else "sem tags"


def valor_yaml(valor) -> str:
    """Usa uma string JSON, que tambem e valida em YAML."""
    return json.dumps(str(valor), ensure_ascii=False)


def escrever_atomico(caminho: Path, conteudo: str):
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    os.replace(temporario, caminho)


def salvar(meta: dict, nota: str, transcricao: str, caminho_existente=None, extras=None) -> Path:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "_transcricoes").mkdir(exist_ok=True)

    hoje = datetime.now().strftime("%Y-%m-%d")
    caminho = caminho_existente or (
        BASE_DIR / f"{hoje} - {limpar_nome(meta['titulo'])} [{meta['id']}].md"
    )

    frontmatter = (
        "---\n"
        f"titulo: {valor_yaml(meta['titulo'])}\n"
        f"canal: {valor_yaml(meta['canal'])}\n"
        f"url: {valor_yaml(meta['url'])}\n"
        f"duracao: {valor_yaml(fmt_tempo(meta['duracao']))}\n"
        f"publicado_em: {valor_yaml(meta.get('publicado', ''))}\n"
        f"processado_em: {valor_yaml(hoje)}\n"
        f"video_id: {valor_yaml(meta['id'])}\n"
        f"tags: {valor_yaml(extrair_tags(nota))}\n"
        + "".join(f"{c}: {valor_yaml(str(v))}\n" for c, v in (extras or {}).items())
        + "---\n\n"
        f"# {meta['titulo']}\n\n"
    )
    escrever_atomico(caminho, frontmatter + nota + "\n")

    escrever_atomico(
        BASE_DIR / "_transcricoes" / f"{meta['id']}.txt",
        transcricao,
    )
    return caminho


def reconstruir_indice():
    notas = [p for p in BASE_DIR.glob("*.md") if not p.name.startswith("_")]
    notas.sort(key=lambda p: p.name, reverse=True)

    linhas = ["# Indice da base", "", f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}", ""]
    por_tag = {}
    for nota in notas:
        texto = nota.read_text(encoding="utf-8", errors="ignore")
        titulo = campo_frontmatter(texto, "titulo")
        tags = campo_frontmatter(texto, "tags")
        url = campo_frontmatter(texto, "url")
        nome = titulo or nota.stem
        alvo = urllib.parse.quote(nota.name)
        linhas.append(f"- [{nome}]({alvo}) — {url or ''}")
        for tag in (tags or "").split(","):
            tag = tag.strip().lower()
            if tag:
                por_tag.setdefault(tag, []).append((nome, nota.name))

    linhas += ["", "## Por tema", ""]
    for tag in sorted(por_tag):
        linhas.append(f"**{tag}**")
        for nome, arq in por_tag[tag]:
            linhas.append(f"- [{nome}]({urllib.parse.quote(arq)})")
        linhas.append("")

    escrever_atomico(BASE_DIR / "_indice.md", "\n".join(linhas))


def ja_processado(video_id: str):
    return next(BASE_DIR.glob(f"*[[]{video_id}[]].md"), None) if BASE_DIR.exists() else None


def verificar_ambiente() -> bool:
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    print(f"Base: {BASE_DIR}")
    print(f"Contexto: {CONTEXTO:,} tokens")
    try:
        import faster_whisper  # noqa: F401

        print("faster-whisper: instalado (usado so em video sem legenda)")
    except ImportError:
        print("faster-whisper: ausente. Video sem legenda nao sera transcrito.")
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        nomes = {m.get("name", "") for m in dados.get("models", [])}
        disponivel = MODELO in nomes or f"{MODELO}:latest" in nomes
        print(f"Ollama: conectado em {OLLAMA_URL}")
        if disponivel:
            print(f"Modelo: {MODELO} instalado")
        else:
            print(f"Modelo: {MODELO} ainda nao instalado")
            print(f"Execute: ollama pull {MODELO}")
            ok = False
    except Exception:
        print("Ollama: nao foi possivel conectar. Abra ou instale o Ollama.")
        ok = False
    return ok


# --------------------------------------------------------------------------
# FLUXO
# --------------------------------------------------------------------------

def expandir(url: str):
    """Playlist vira a lista de videos que a compoem."""
    if "list=" not in url:
        return [url]
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") != "playlist":
        return [url]
    links = [
        f"https://www.youtube.com/watch?v={e['id']}"
        for e in info.get("entries") or []
        if e and e.get("id")
    ]
    print(f"Playlist \"{info.get('title', '')}\" com {len(links)} videos")
    return links or [url]


def processar(url: str, forcar: bool) -> str:
    """Devolve 'concluido', 'ignorado' ou levanta excecao."""
    print(f"\n> {url}")
    meta = metadados(url)
    print(f"  {meta['titulo']} ({fmt_tempo(meta['duracao'])})")

    existente = ja_processado(meta["id"])
    if existente and not forcar:
        print(f"  ja existe na base: {existente.name}  (use --forcar para refazer)")
        return "ignorado"

    tmp = Path(tempfile.mkdtemp())
    try:
        legenda = baixar_legenda(url, tmp)
        if legenda:
            print(f"  legenda encontrada: {legenda.name}")
            segmentos = parse_vtt(legenda)
            origem = f"legenda {legenda.name.split('.')[-2]}"
        else:
            print("  sem legenda disponivel; caindo para o audio")
            segmentos = transcrever_audio(url, tmp)
            origem = f"whisper {MODELO_WHISPER}"

        if not segmentos:
            raise RuntimeError("nao foi possivel obter transcricao (sem legenda e sem audio)")

        transcricao = montar_transcricao(segmentos)
        print(f"  transcricao com {len(transcricao):,} caracteres")

        nota, formato = gerar_nota(meta, transcricao, contexto_da_base())
        caminho = salvar(
            meta,
            nota,
            transcricao,
            existente if forcar else None,
            {
                "formato": formato,
                "modelo": MODELO,
                "contexto": CONTEXTO,
                "transcricao": origem,
            },
        )
        print(f"  gravado: {caminho.name}")
        return "concluido"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    global BASE_DIR, MODELO, CONTEXTO, FORMATO
    p = argparse.ArgumentParser(description="Base de conhecimento a partir de videos do YouTube")
    p.add_argument("urls", nargs="*", help="um ou mais links do YouTube")
    p.add_argument("--arquivo", help="arquivo txt com um link por linha")
    p.add_argument("--forcar", action="store_true", help="reprocessa video ja existente")
    p.add_argument("--base", default=str(BASE_DIR), help="pasta onde a base sera gravada")
    p.add_argument("--modelo", default=MODELO, help="modelo local instalado no Ollama")
    p.add_argument(
        "--contexto",
        type=int,
        default=0,
        help="janela em tokens; por padrao vem do modelo "
        "(4b=8192, 9b=16384, 27b=32768)",
    )
    p.add_argument(
        "--formato",
        choices=("aula", "podcast"),
        default=FORMATO,
        help="estrutura da nota: podcast organiza por blocos tematicos",
    )
    p.add_argument("--verificar", action="store_true", help="verifica o ambiente e encerra")
    args = p.parse_args()

    BASE_DIR = Path(args.base).expanduser()
    MODELO = args.modelo
    CONTEXTO = args.contexto or int(
        os.environ.get("YTBASE_CTX") or contexto_do_modelo(MODELO)
    )
    FORMATO = args.formato
    if args.verificar:
        sys.exit(0 if verificar_ambiente() else 1)

    urls = list(args.urls)
    if args.arquivo:
        urls += [
            l.strip()
            for l in Path(args.arquivo).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
    if not urls:
        p.print_help()
        sys.exit(1)

    print(f"Base: {BASE_DIR}")
    print(
        f"Modelo local: {MODELO} (janela de {CONTEXTO:,} tokens, "
        f"resposta ate {resposta_max():,})"
    )

    alvos = []
    for url in urls:
        try:
            alvos.extend(expandir(url))
        except Exception as e:
            print(f"ERRO ao ler {url}: {e}")
            alvos.append(url)

    concluidos, ignorados, falhas = 0, 0, []
    for url in alvos:
        try:
            if processar(url, args.forcar) == "ignorado":
                ignorados += 1
            else:
                concluidos += 1
        except Exception as e:
            print(f"  ERRO em {url}: {e}")
            falhas.append(url)

    if BASE_DIR.exists():
        reconstruir_indice()
        print(f"\nIndice atualizado: {BASE_DIR / '_indice.md'}")

    partes = [f"{concluidos} concluido(s)"]
    if ignorados:
        partes.append(f"{ignorados} ja existente(s)")
    if falhas:
        partes.append(f"{len(falhas)} com erro")
    print("\nResumo: " + ", ".join(partes) + ".")
    for url in falhas:
        print(f"  falhou: {url}")

    # Codigo diferente de zero para a interface nao anunciar sucesso apos falha.
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
