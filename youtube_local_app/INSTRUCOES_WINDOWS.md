# Base de conhecimento local a partir do YouTube

O programa tem dois motores de análise, escolhidos na própria interface:

- **Ollama** (padrão): roda o modelo local no computador. Sem custo, sem
  chave de API, mas usa a RAM e o processador da máquina — mais lento num
  notebook sem placa de vídeo dedicada.
- **Claude**: usa a API da Anthropic pela internet. Cobra por token (poucos
  centavos de dólar por vídeo, no uso típico), mas não usa RAM local e é bem
  mais rápido, porque a maior parte de um vídeo cabe numa única chamada em
  vez de ser dividida em partes.

A transcrição (legenda do YouTube ou Whisper local, quando não há legenda)
roda sempre no computador, nos dois motores. As notas podem ser gravadas em
uma pasta sincronizada pelo Google Drive para Desktop.

## Instalação inicial

1. Instale o **Python 3.11 ou superior** por meio de
   <https://www.python.org/downloads/>. Durante a instalação, marque a opção
   **Add Python to PATH**.
2. Instale o **Ollama para Windows** por meio de
   <https://ollama.com/download/windows> e abra o programa ao menos uma vez.
   (Pule este passo se pretende usar só o motor Claude.)
3. Extraia todos os arquivos deste pacote para uma pasta comum do computador.
4. Dê dois cliques em `INSTALAR_WINDOWS.bat`.
5. Aguarde os downloads. São dois: o modelo de análise (`qwen3.5:9b`, cerca de
   6,6 GB) e o modelo de transcrição de áudio (`small`, cerca de 500 MB,
   usado somente em vídeos sem legenda).
6. Se quiser usar o motor Claude, obtenha uma chave em
   <https://console.anthropic.com/> e cole-a no campo **Chave API Claude** da
   interface (ou defina a variável de ambiente `ANTHROPIC_API_KEY` no
   Windows, para não precisar colar a cada vez).

A instalação dos componentes e dos modelos acontece apenas na primeira vez.

## Como executar

1. Dê dois cliques em `ABRIR_APP.bat`.
2. Cole um ou mais links do YouTube, sempre um por linha.
3. Escolha a pasta onde as notas deverão ser salvas. Se quiser sincronização,
   selecione uma pasta que esteja dentro do Google Drive para Desktop.
4. Clique em **Verificar instalação**. O painel deverá informar que o Ollama
   está conectado e o modelo está instalado.
5. Clique em **Processar vídeos**.
6. Ao final, use **Abrir pasta** para acessar as notas e o `_indice.md`.

## Escolha do modelo

### Motor Ollama (local)

- `qwen3.5:4b`: computadores com 8 GB de RAM, ou notebooks de 16 GB em que o
  `qwen3.5:9b` deixar a RAM muito apertada. Para instalar, execute
  `ollama pull qwen3.5:4b` no Prompt de Comando.
- `qwen3.5:9b`: opção padrão, recomendada para 16 GB de RAM — mas em
  notebook sem placa de vídeo dedicada é pesado; se notar RAM acima de 90%
  ou o processamento passar de meia hora para um vídeo curto, teste o 4b.
- `qwen3.5:27b`: computadores com pelo menos 32 GB de RAM. Para instalar,
  execute `ollama pull qwen3.5:27b`.

Depois de instalar outro modelo, selecione-o na interface antes de processar.

### Motor Claude (API)

- `claude-haiku-4-5-20251001`: rápido e econômico, recomendado para uso do
  dia a dia.
- `claude-sonnet-5`: análise mais forte, para conteúdo que você quer tratar
  com mais cuidado.
- `claude-opus-5`: o mais caro; normalmente não compensa para esta tarefa.

Ao trocar o motor na interface, a lista de modelos e a janela mudam junto.

## Modelo, memória e janela

A janela de contexto consome memória além do próprio modelo, por isso ela vem
amarrada ao modelo escolhido. Ao trocar o modelo na interface, a janela é
ajustada sozinha; o campo **Janela** permite sobrepor esse valor.

| RAM | Modelo | Janela | Resposta |
|---|---|---|---|
| 8 GB | `qwen3.5:4b` | 8.192 | até 2.300 tokens |
| 16 GB | `qwen3.5:9b` | 16.384 | até 4.600 tokens |
| 32 GB ou mais | `qwen3.5:27b` | 32.768 | até 6.000 tokens |

O aplicativo usa 85% da janela e reserva o restante como margem, porque a
contagem de tokens é estimada por caractere, não exata. Todo o resto — tamanho
de cada parte, teto de cada resumo intermediário, teto da nota final — é
calculado a partir desse valor. Não há número fixo a ajustar.

Em 8 GB a nota final é necessariamente mais curta, porque sobra menos espaço
para a resposta. É uma limitação real da configuração, não um defeito.

### Reduzindo o consumo

O Ollama sabe comprimir o cache da janela:

```powershell
setx OLLAMA_KV_CACHE_TYPE q8_0
```

Feche e reabra o Ollama depois. A economia costuma aproximar-se da metade, mas
depende de Flash Attention estar ativo e varia conforme o modelo e o
equipamento; o impacto na qualidade também depende do modelo. Trate como
tentativa a verificar na sua máquina, não como garantia.

## Vídeos longos e podcasts

Vídeos que não cabem em uma passada são divididos automaticamente. Cada trecho
vira uma nota intermediária e, no fim, todas são lidas juntas para produzir a
nota definitiva. Quando as notas intermediárias somadas ainda não couberem, o
aplicativo faz rodadas de compactação, juntando-as duas a duas até caber. O
painel informa cada etapa.

O corte entre as partes cai em um marcador de tempo, o que reduz muito a chance
de partir uma frase ao meio — mas não elimina, porque o marcador pode cair em
um raciocínio ainda em construção. Por isso cada parte repete os últimos
instantes da anterior.

Se ainda assim o conteúdo não couber, o processamento é interrompido com erro
explícito. O aplicativo nunca segue adiante truncando texto em silêncio.

Comportamento observado em teste, por janela (motor Ollama):

| Duração | Janela 8.192 | Janela 16.384 | Janela 32.768 | Motor Claude (190.000) |
|---|---|---|---|---|
| 20 min | 3 partes | passada única | passada única | passada única |
| 1h43 | 9 partes + 1 compactação | 4 partes | 2 partes | passada única |
| 2 h | 10 partes + 1 compactação | 5 partes | 2 partes | passada única |
| 4 h | 18 partes + 2 compactações | 8 partes | 4 partes | 1-2 partes |

Quanto mais partes e compactações, mais detalhe se perde. Para podcasts longos
no motor Ollama, janela maior significa nota melhor; no motor Claude a janela
já é grande o bastante para a esmagadora maioria dos vídeos caber numa única
passada, sem esse custo.

As notas intermediárias (geradas quando o vídeo precisa ser dividido) têm um
teto de tamanho próprio, mais curto que o da nota final — elas são descartadas
assim que a nota definitiva sai, então gerar mais texto ali não melhora nada,
só custa tempo. Ajustável pela variável `YTBASE_TETO_PARTE` (padrão: 900
tokens).

## Funcionamento

- Quando o vídeo possui legenda, ela é utilizada diretamente. O aplicativo
  tenta os idiomas na ordem `pt, pt-BR, pt-orig, en, en-US, en-orig` e para no
  primeiro que existir — se um idioma mais adiante na lista falhar (por
  exemplo, o YouTube devolver "HTTP 429" ao tentar `en`), isso não descarta a
  legenda que porventura já tenha sido baixada com sucesso num idioma anterior.
- Quando não há legenda, o aplicativo baixa o áudio e usa o faster-whisper no
  próprio computador, com o modelo `small` por padrão (mais rápido que
  `medium`, com perda de qualidade pequena; ajustável na interface ou pela
  variável `YTBASE_WHISPER`). Assim que a transcrição termina, a memória do
  Whisper é liberada antes de começar a análise.
- Vídeos já processados são ignorados. Marque **Refazer vídeo já processado**
  para atualizar a nota existente.
- Com o motor Ollama, nenhuma chave de API é necessária e nada sai do
  computador. Ao final do processamento de todos os vídeos, o programa pede
  ao Ollama para liberar o modelo da RAM.
- O painel mostra, ao final de cada vídeo, o tempo gasto em cada etapa
  (legenda, Whisper, análise, gravação) e o total — útil para comparar
  modelos e configurações na prática, em vez de "pareceu mais rápido".

## Execução pelo terminal, se desejar

```powershell
python base_youtube_local.py --verificar
python base_youtube_local.py "https://youtu.be/ID_DO_VIDEO"
```

Para indicar outra pasta e outro modelo:

```powershell
python base_youtube_local.py --base "G:\Meu Drive\Base YouTube" --modelo qwen3.5:9b "LINK"
```

Para usar o motor Claude em vez do Ollama:

```powershell
setx ANTHROPIC_API_KEY "sua-chave-aqui"
python base_youtube_local.py --motor claude --modelo claude-haiku-4-5-20251001 "LINK"
```

## Solução rápida de problemas

- **Python não encontrado:** reinstale-o marcando `Add Python to PATH`.
- **Ollama não conectado:** abra o Ollama pelo menu Iniciar e tente novamente.
- **Modelo não instalado:** abra o Prompt de Comando e execute
  `ollama pull qwen3.5:9b`.
- **Vídeo sem transcrição:** confirme que o faster-whisper foi instalado pelo
  instalador e tente novamente.
- **Parece travado no primeiro vídeo sem legenda:** o modelo de áudio está
  sendo baixado. Aguarde e observe o painel.
- **Nota curta ou fora do assunto:** provavelmente a transcrição excedeu o
  contexto. Verifique se houve aviso no painel; no motor Ollama, considere
  usar um modelo com janela maior.
- **Motor Claude reclamando de chave ausente:** confirme que colou a chave no
  campo da interface ou que `ANTHROPIC_API_KEY` está definida no Windows.
- **Google Drive não atualizou:** confirme que a sincronização do Drive para
  Desktop está ativa e que a pasta escolhida pertence ao Drive.


## Qualidade esperada

No motor Ollama, o processamento é inteiramente local e sem custo, mas um
modelo de 9 bilhões de parâmetros em processador comum é lento: em uma
máquina de 16 GB sem placa de vídeo dedicada, um vídeo de 20 minutos com
legenda costuma levar de alguns minutos a um quarto de hora; sem legenda
(recorrendo ao Whisper) soma-se o tempo da transcrição. Computadores com
placa de vídeo dedicada são consideravelmente mais rápidos. Se a RAM chegar
perto de 90% durante o processamento, é sinal de trocar para `qwen3.5:4b`
com janela 8.192.

No motor Claude, a etapa de análise deixa de pesar na RAM e no tempo do
computador: ela acontece nos servidores da Anthropic, tipicamente em
segundos a poucos minutos por vídeo, independentemente do tamanho da máquina.
O tempo total do motor Claude fica dominado pela transcrição (quando não há
legenda) e pela conexão de internet, não pela análise.

A seção **Conexões com a base** é a mais frágil, porque exige que o modelo
mantenha em mente as notas anteriores e a transcrição ao mesmo tempo. Leia essa
seção com atenção nos primeiros vídeos: modelo pequeno tende a afirmar relações
que não existem. As demais seções são bem mais confiáveis.
