Rodando em Linux (experimental, com degradação graciosa)
O Pipo foi feito para Windows, que é onde ele briga de verdade (andar por cima das janelas, transparência de verdade, sons). Em Linux ele abre e conversa, com estas diferenças:
- Observação de atividade e passeio entre janelas: só no X11, com xdotool instalado (sudo apt install xdotool xprintidle). No Wayland o próprio protocolo não deixa nenhuma aplicação ver as janelas das outras — a observação fica pausada e o passeio usa um chão só.
- Transparência: fora do Windows o Tkinter não tem cor transparente por janela; a janelinha fica levemente translúcida (-alpha).
- Sons: bipes gerados na hora e tocados no paplay/aplay; sem player, silêncio.
- Fontes: DejaVu Sans no lugar das Segoe/Consolas.
Nada para instalar além do Python 3 com Tkinter (sudo apt install python3-tk).

PIPO ML  -  o Pipo com machine learning (sem nenhuma IA externa)
=================================================================

COMO ABRIR
  1. Deixe estes itens na MESMA pasta: pipo_ml.py, cerebro.py e a pasta "dados".
  2. Rode:  python pipo_ml.py
  Não precisa instalar nada nem ter internet. Não existe chave, API, nem download de modelo.

O QUE ELE FAZ
  - Telinha com 6 botões (papo, bilhete, passear, dormir, ver PC, sons), passeia pelos monitores e janelas,
    observa qual programa você usa (só o nome e o tempo), anota bilhetes, faz lembretes e conversa.
  - Cinco personalidades (botão direito > Personalidade): Fofinho, Zen, Sarcástico, Mentor e Revoltado.
  - HORA, DATA, DIA DA SEMANA, MÊS, ANO e CONTAS são calculados pelo código (relógio do PC), então não erram.
    Exemplos: "que horas são", "que dia é hoje", "quanto é 15 vezes 4", "me lembra de beber água em 10 minutos".
    (Os lembretes só valem enquanto o Pipo está aberto.)

PERSONALIDADE AUTOMÁTICA (botão direito > Personalidade > Automática, já vem ligada)
  Ele muda de humor sozinho conforme a convivência: bastante conversa e carinho puxam o Fofinho; horas sem
  falar com ele puxam o Sarcástico e o Revoltado ("abandono"); madrugada e noite puxam o Zen; muito tempo
  no mesmo programa chama o Mentor. Ele avisa com um balão quando troca (no mínimo 15 min entre trocas, e
  nunca no meio de uma conversa). Se você disser que está triste ou estressado, ele sai do Revoltado/Sarcástico
  na hora e fica 2 horas sem voltar para eles. Ele também aprende: o "gostei / não gostei" que você dá conta
  como nota para a personalidade daquela situação. Escolher uma personalidade à mão desliga o automático.
  As regras iniciais ficam no começo do pipo_ml.py (REGRAS_AUTO e AUTO_MIN_MINUTOS).

COMO ELE APRENDE (machine learning leve, tudo no seu PC)
  - Entende o que você quis dizer (Naive Bayes) a partir de dados/intencoes.txt.
  - Reconhece o clima da frase para mudar de expressão (dados/humor.txt).
  - Responde com o que você ensinou (similaridade TF-IDF) em dados/conversas.txt e aprendido.txt.
  - Aprende o que você gosta: use os botões "gostei / não gostei" nos balões, nos bilhetes e no chat
    (ou escreva "gostei" / "não gostei"). Cada frase tem uma nota; as que você aprova aparecem mais.
  - Inventa frases novas (remix) imitando o jeito de cada personalidade. Elas vêm marcadas com "frase nova".
    Se você aprova, a frase vira definitiva; se barra, ela nunca mais volta. Se você não gosta de remix,
    ele passa a usar menos.
  - Guarda fatos que você conta: "meu nome é...", "meu projeto é...", "eu gosto de...", "meu gato se chama...".

COMO ALIMENTAR (o que você vai fazer a partir de agora)
  1. Conversando: quando ele não souber, ele diz. Escreva logo depois:   ensina: <o que ele devia responder>
  2. Veja dados/nao_entendi.txt: tudo que ele não entendeu fica lá. Para cada linha, ensine uma resposta
     (em conversas.txt) ou ensine a intenção (em intencoes.txt).
  3. Edite os arquivos de dados (UTF-8, um item por linha, "coluna | coluna"; linhas com # são comentário):
       intencoes.txt              intenção | frase que você diria         (quanto mais exemplos, melhor ele entende)
       humor.txt                  feliz/triste/surpreso/normal | frase
       conversas.txt              pergunta | resposta | personalidades (opcional)
       respostas_<pers>.txt       intenção | resposta   (aceita {hora} {data} {nome} {app} {tempo_app} {resumo_hoje}
                                  {notas} {projeto} {gosto} {x} ... frases com variável desconhecida são puladas)
       falas_<pers>.txt           fala | bilhete | pausa | manha | tarde | noite | madrugada  |  texto
       vocabulario.txt            textos livres para o remix aprender vocabulário (uma frase por linha)
       vocabulario_<pers>.txt     o mesmo, só para uma personalidade
     Personalidades: fofinho, zen, sarcastico, mentor, revoltado (para criar outra, crie respostas_<nome>.txt
     e falas_<nome>.txt, e acrescente o nome no dicionário PERSONAS no começo do pipo_ml.py).
  4. Depois de editar, clique com o botão direito > "Recarregar dados" (não precisa fechar o Pipo).
  5. "O que o Pipo aprendeu" (menu) mostra quanto ele já sabe, as notas que você deu e os fatos guardados.
     Lá também há o botão para esquecer o que ele aprendeu com você (os arquivos que você editou não são apagados).

COMANDOS NO CHAT
  anota: <texto>          cria um bilhete
  ensina: <resposta>      ensina a última coisa que você disse
  gostei / não gostei     nota para a última frase
  /ajuda                  lista os comandos

MODO REVOLTADO
  É mal-humorado e implicante de brincadeira (dados/respostas_revoltado.txt e falas_revoltado.txt).
  Você pode esquentar ou esfriar o tom editando esses arquivos. Regras que ficam valendo mesmo assim:
  se você disser que está triste, estressado ou mal, ele para de implicar e acolhe; e se você falar de se
  machucar ou de acabar com a própria vida, TODAS as personalidades respondem com acolhimento e indicam o
  CVV (188, 24 horas) e o SAMU (192). Isso está no cerebro.py (CRISE e ACOLHIMENTO).

PRIVACIDADE
  Nada sai do computador. Ele guarda o nome dos programas e o tempo de uso (atividade.json), os bilhetes
  (notas.json), a conversa recente (historico.json), o que aprendeu (cerebro.json) e a posição (estado.json).
  Títulos de janela nunca são gravados. Apague o que quiser; o botão direito > "Parar de observar o PC"
  desliga a observação.

LIMITES (sem IA generativa)
  Ele não responde perguntas abertas ("explique a física quântica") nem escreve textos novos de verdade.
  Fora do que ele aprendeu, ele diz que não sabe e pede para ser ensinado. O remix, no começo, pode
  sair estranho: use "não gostei" e alimente o vocabulario.txt; ele melhora com o uso.
