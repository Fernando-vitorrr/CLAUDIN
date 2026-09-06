# Base de conhecimento local a partir do YouTube

Esta versão funciona sem chave de API e sem cobrança por vídeo. A análise é
realizada pelo Ollama no próprio computador. As notas podem ser gravadas em uma
pasta sincronizada pelo Google Drive para Desktop.

## Instalação inicial

1. Instale o **Python 3.11 ou superior** por meio de
   <https://www.python.org/downloads/>. Durante a instalação, marque a opção
   **Add Python to PATH**.
2. Instale o **Ollama para Windows** por meio de
   <https://ollama.com/download/windows> e abra o programa ao menos uma vez.
3. Extraia todos os arquivos deste pacote para uma pasta comum do computador.
4. Dê dois cliques em `INSTALAR_WINDOWS.bat`.
5. Aguarde os downloads. São dois: o modelo de análise (`qwen3.5:9b`, cerca de
   6,6 GB) e o modelo de transcrição de áudio (cerca de 1,5 GB, usado somente
   em vídeos sem legenda).

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

- `qwen3.5:4b`: computadores com 8 GB de RAM. Para instalar, execute
  `ollama pull qwen3.5:4b` no Prompt de Comando.
- `qwen3.5:9b`: opção padrão, recomendada para 16 GB de RAM.
- `qwen3.5:27b`: computadores com pelo menos 32 GB de RAM. Para instalar,
  execute `ollama pull qwen3.5:27b`.

Depois de instalar outro modelo, selecione-o na interface antes de processar.

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

Comportamento observado em teste, por janela:

| Duração | Janela 8.192 | Janela 16.384 | Janela 32.768 |
|---|---|---|---|
| 20 min | 3 partes | passada única | passada única |
| 1h43 | 9 partes + 1 compactação | 4 partes | 2 partes |
| 2 h | 10 partes + 1 compactação | 5 partes | 2 partes |
| 4 h | 18 partes + 2 compactações | 8 partes | 4 partes |

Quanto mais partes e compactações, mais detalhe se perde. Para podcasts longos,
janela maior significa nota melhor.

## Funcionamento

- Quando o vídeo possui legenda, ela é utilizada diretamente.
- Quando não há legenda, o aplicativo baixa o áudio e usa o faster-whisper no
  próprio computador. Esse procedimento pode demorar em computadores sem placa
  de vídeo dedicada.
- Vídeos já processados são ignorados. Marque **Refazer vídeo já processado**
  para atualizar a nota existente.
- Nenhuma chave de API é necessária.

## Execução pelo terminal, se desejar

```powershell
python base_youtube_local.py --verificar
python base_youtube_local.py "https://youtu.be/ID_DO_VIDEO"
```

Para indicar outra pasta e outro modelo:

```powershell
python base_youtube_local.py --base "G:\Meu Drive\Base YouTube" --modelo qwen3.5:9b "LINK"
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
  contexto. Verifique se houve aviso no painel e reduza `LIMITE_CHARS`.
- **Google Drive não atualizou:** confirme que a sincronização do Drive para
  Desktop está ativa e que a pasta escolhida pertence ao Drive.


## Qualidade esperada

O processamento é inteiramente local e sem custo, mas um modelo de 9 bilhões de
parâmetros em processador comum é lento: em uma máquina de 16 GB sem placa de
vídeo dedicada, um vídeo de 20 minutos costuma levar entre dez e vinte e cinco
minutos. Computadores com placa de vídeo dedicada são
consideravelmente mais rápidos.

A seção **Conexões com a base** é a mais frágil, porque exige que o modelo
mantenha em mente as notas anteriores e a transcrição ao mesmo tempo. Leia essa
seção com atenção nos primeiros vídeos: modelo pequeno tende a afirmar relações
que não existem. As demais seções são bem mais confiáveis.
