"""
Cérebro do Pipo: machine learning leve, só com a biblioteca padrão do Python (sem internet,
sem chave, sem modelos para baixar). Tudo o que ele aprende vem dos arquivos da pasta dados/
e do que você ensina conversando com ele.

O que há aqui de aprendizado de máquina de verdade:
  - Classificador de intenções (Naive Bayes): aprende com dados/intencoes.txt a entender o que
    você quis dizer ("que horas são", "tô cansado", "valeu"...).
  - Classificador de humor (Naive Bayes): aprende com dados/humor.txt a reconhecer o clima da frase.
  - Recuperação por similaridade (TF-IDF + cosseno): aprende pares pergunta -> resposta de
    dados/conversas.txt e do que você ensina com "ensina:".
  - Aprendizado por reforço (Thompson sampling): cada resposta tem uma nota que sobe com
    "gostei" e desce com "não gostei", e ele passa a escolher as que você aprova.
  - Modelo de linguagem de trigramas (remix): aprende o jeito de falar de cada personalidade e
    inventa frases novas; o botão "gostei/não gostei" decide se ele continua fazendo isso.
  - Memória de fatos: aprende nome, projeto, gostos e pet quando você conta.
Contas, hora, data, dia da semana, mês e ano NÃO passam por aprendizado: são calculados pelo
código (o relógio do PC), então nunca erram.
"""
import ast
import hashlib
import json
import math
import operator
import os
import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def escrever_atomico(caminho, texto):
    """Escreve em arquivo temporário e troca no lugar: uma queda de energia no
    meio da escrita nunca deixa o JSON pela metade (o que zeraria a memória).
    Se o arquivo antigo existia, guarda uma cópia .bak antes de trocar."""
    caminho = Path(caminho)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    if caminho.exists():
        try:
            backup = caminho.with_name(caminho.name + ".bak")
            backup.write_bytes(caminho.read_bytes())
        except OSError:
            pass                       # backup é cortesia; a troca é o que importa
    os.replace(temporario, caminho)

SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
CONF_INTENCAO = 0.5      # confiança mínima do classificador de intenções
COBERTURA_MIN = 0.4       # fração mínima das palavras da frase que ele já conhece
SIM_CONVERSA = 0.6        # similaridade mínima para usar uma resposta ensinada
RECENTES = 12             # respostas recentes que ele evita repetir
REMIX_MIN_FRASES = 40     # tamanho mínimo do texto de uma personalidade para ele tentar remix
CRISE = ("quero morrer", "vou me matar", "me matar", "suicid", "nao quero mais viver",
         "nao aguento mais viver", "acabar com minha vida", "acabar com tudo", "me machucar",
         "me cortar", "tirar minha vida", "queria sumir para sempre")
# Combinações soltas: o usuário raramente digita a frase exata da lista acima
# ("as vezes penso em nao querer mais viver" não bate com 'nao quero mais viver'
# por causa das palavras no meio). Falso positivo aqui custa um acolhimento a
# mais; falso negativo, com a IA local ligada, mandaria a frase ao modelo.
CRISE_COMBINADA = [("morrer", ("quero", "pens", "melhor", "acho que seria melhor")),
                   ("morte", ("minha", "pra mim", "pro meu")),
                   ("viver", ("nao quero", "nao aguento", "sem vontade", "sem sentido", "cansad", "penso em nao")),
                   # "não faz/cansa/faz doer" + vida, e nunca o elogio "isso sim é vida!"
                   ("vida", ("tirar", "acabar", "nao tem mais sentido", "sem sentido",
                              "cansa essa vida", "truncada", "acabou pra mim")),
                   # verbo junto do desejo ("quero/to/queria sumir"); sem pronome pessoal,
                   # "sumir de fim de semana" comum não dispara.
                   ("sumir", ("quero sumir", "to sumir", "pra sumir", "para sumir", "quiser sumir")),
                   ("acabar", ("comigo", "com a minha vida")),
                   # "continuar vivo" sem vontade; nunca a empolgação ("bora continuar vivo!")
                   ("continuar vivo", ("nao quero", "sem vontade", "penso em nao", "cansad",
                                       "nao vejo sentido", "perdi a vontade")),
                   ("desaparecer", ("pra sempre", "para sempre", "de tudo", "quero"))]
ACOLHIMENTO = [
    "Sinto muito que você esteja assim. Você não precisa passar por isso sozinho: no Brasil, o CVV "
    "atende 24 horas pelo 188 (cvv.org.br). Se houver risco agora, ligue 192 (SAMU) ou chame alguém "
    "de confiança para ficar com você. Eu continuo aqui para conversar.",
    "Obrigado por me contar. O que você sente importa. Se puder, fale com alguém de confiança agora; "
    "o CVV (188, 24 horas) também escuta sem julgar. Se estiver em perigo, ligue 192. Estou aqui.",
]
HUMOR_INTENCAO = {"tristeza": "triste", "estresse": "triste", "crise": "triste", "cansaco": "triste",
                  "alegria": "feliz", "elogio": "feliz", "agradecimento": "feliz", "saudacao": "feliz",
                  "piada": "feliz", "fato_ok": "feliz", "insulto": "surpreso", "reflexo_sentir": "triste"}


# ------------------------------ texto ------------------------------
def simplificar(txt):
    """Minúsculas e sem acentos (mantém a pontuação)."""
    t = unicodedata.normalize("NFD", txt.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def normalizar(txt):
    return re.sub(r"[^a-z0-9 ]+", " ", simplificar(txt))


def tokens(txt):
    out = []
    for w in normalizar(txt).split():
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") else w)   # plural simples
    return out


# palavras muito comuns que não ajudam a descobrir a intenção (ficam de fora do Naive Bayes)
PALAVRAS_COMUNS = {"a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no",
                   "na", "nos", "nas", "e", "eu", "me", "meu", "minha", "estou", "to", "ta", "tou", "muito",
                   "tao", "pra", "para", "por", "com", "isso", "esse", "essa", "mais", "hoje", "ja", "so"}


def palavras_uteis(txt):
    uteis = [t for t in tokens(txt) if t not in PALAVRAS_COMUNS]
    return uteis or tokens(txt)


def pedacos(palavra):
    """Pedaços de 4 letras de uma palavra longa: ajudam a reconhecer variações (obrigado/obrigadão)."""
    return [f"#{palavra[i:i + 4]}" for i in range(len(palavra) - 3)] if len(palavra) >= 5 else []


def caracteristicas(txt):
    t = palavras_uteis(txt)
    return t + [f"{a}_{b}" for a, b in zip(t, t[1:])] + [g for w in t for g in pedacos(w)]


# ------------------------------ modelos ------------------------------
class NaiveBayes:
    """Classificador de texto: conta quais palavras (e pares de palavras) aparecem em cada classe."""

    def __init__(self, alpha=0.02):
        self.alpha = alpha
        self.cont = defaultdict(Counter)
        self.total = Counter()
        self.n = Counter()
        self.vocab = set()

    def treinar(self, exemplos):
        for classe, texto in exemplos:
            self.n[classe] += 1
            for f in caracteristicas(texto):
                self.cont[classe][f] += 1
                self.total[classe] += 1
                self.vocab.add(f)

    def prever(self, texto):
        """-> (classe, probabilidade, cobertura) ou None se não conhece nenhuma palavra."""
        uni = palavras_uteis(texto)
        conhecidas = [f for f in caracteristicas(texto) if f in self.vocab]
        if not conhecidas or not self.n or not uni:
            return None
        exata = sum(1 for w in uni if w in self.vocab) / len(uni)
        parcial = sum(1 for w in uni if w in self.vocab or any(g in self.vocab for g in pedacos(w))) / len(uni)
        cobertura = max(exata, parcial if parcial >= 0.99 else 0.0)   # variações só valem se explicarem a frase toda
        v = len(self.vocab)
        logs = {c: sum(math.log((self.cont[c][f] + self.alpha) / (self.total[c] + self.alpha * v))
                       for f in conhecidas) for c in self.n}
        m = max(logs.values())
        exps = {c: math.exp(x - m) for c, x in logs.items()}
        z = sum(exps.values())
        classe = max(exps, key=exps.get)
        return classe, exps[classe] / z, cobertura


class Recuperador:
    """Acha, entre os pares pergunta -> resposta aprendidos, o mais parecido com o que foi dito."""

    def __init__(self):
        self.itens = []
        self.idf = {}
        self.idf_novo = 1.0

    @staticmethod
    def _vetor(toks, idf, padrao):
        c = Counter(toks)
        v = {w: (1 + math.log(n)) * idf.get(w, padrao) for w, n in c.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norma for w, x in v.items()}

    def treinar(self, pares):
        """pares: lista de (pergunta, resposta, personas ou None)."""
        docs = [tokens(p) for p, _, _ in pares]
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(pares)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.idf_novo = math.log(n + 1) + 1
        self.itens = [(self._vetor(d, self.idf, self.idf_novo), r, pers, p)
                      for d, (p, r, pers) in zip(docs, pares) if d]

    def buscar(self, texto, persona):
        q = self._vetor(tokens(texto), self.idf, self.idf_novo)
        melhor, nota = None, 0.0
        for vec, resp, pers, pergunta in self.itens:
            if pers and persona not in pers:
                continue
            s = sum(x * vec.get(w, 0.0) for w, x in q.items())
            if s > nota:
                melhor, nota = (resp, pergunta), s
        return melhor, nota


class Ngrama:
    """Aprende o jeito de uma personalidade falar (trigramas) e monta frases novas."""

    def __init__(self, rng):
        self.rng = rng
        self.t = defaultdict(Counter)
        self.frases = []
        self.n = 0

    @staticmethod
    def _toks(l):
        return re.findall(r"[\wÀ-ÿ'’-]+|[.,!?;…]", l)

    def treinar(self, linhas):
        for l in linhas:
            l = l.strip()
            if "{" in l or len(l.split()) < 4:
                continue
            seq = ["<s>", "<s>"] + self._toks(l) + ["</s>"]
            for i in range(2, len(seq)):
                self.t[(seq[i - 2], seq[i - 1])][seq[i]] += 1
            self.frases.append(simplificar(l))
            self.n += 1

    def gerar(self, proibidas=(), tentativas=60):
        melhor, nota = None, -1e9
        for _ in range(tentativas):
            a = b = "<s>"
            out, logp = [], 0.0
            for _ in range(32):
                cont = self.t.get((a, b))
                if not cont:
                    break
                ws, pesos = zip(*cont.items())
                w = self.rng.choices(ws, pesos)[0]
                logp += math.log(cont[w] / sum(cont.values()))
                if w == "</s>":
                    break
                out.append(w)
                a, b = b, w
                if w in ".!?…" and sum(1 for x in out if x[0].isalnum()) >= 6:
                    break
            if not out or out[-1] not in ".!?…":
                continue
            palavras = [x for x in out if x[0].isalnum()]
            if not 6 <= len(palavras) <= 28 or any(c > 2 for w, c in Counter(x.lower() for x in palavras if len(x) > 3).items()):
                continue
            texto = re.sub(r"\s+([.,!?;…])", r"\1", " ".join(out))
            texto = texto[0].upper() + texto[1:]
            s = simplificar(texto)
            if s in proibidas or any(s in f or f in s for f in self.frases):
                continue                           # só vale se for realmente uma frase nova
            if logp / len(out) > nota:
                melhor, nota = texto, logp / len(out)
        return melhor


# ------------------------------ contas e lembretes ------------------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _avaliar(no):
    if isinstance(no, ast.Expression):
        return _avaliar(no.body)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
        return no.value
    if isinstance(no, ast.BinOp) and type(no.op) in _OPS:
        a, b = _avaliar(no.left), _avaliar(no.right)
        if isinstance(no.op, ast.Pow) and (abs(b) > 12 or abs(a) > 1e6):
            raise ValueError("potência grande demais")
        return _OPS[type(no.op)](a, b)
    if isinstance(no, ast.UnaryOp) and type(no.op) in _OPS:
        return _OPS[type(no.op)](_avaliar(no.operand))
    raise ValueError("expressão não permitida")


def calcular(texto):
    """Acha uma conta simples na frase e devolve o resultado como texto, ou None."""
    t = simplificar(texto)
    for velho, novo in ((" dividido por ", "/"), (" dividido ", "/"), (" vezes ", "*"), (" mais ", "+"),
                        (" menos ", "-"), (" elevado a ", "**"), (" ao quadrado", "**2")):
        t = t.replace(velho, novo)
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", t)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    for cand in re.findall(r"[\d\s+\-*/().%]{3,}", t):
        cand = cand.strip()
        if re.search(r"\d", cand) and re.search(r"[+\-*/%]", cand.lstrip("-")) and len(re.findall(r"\d+", cand)) >= 1:
            try:
                r = _avaliar(ast.parse(cand, mode="eval"))
            except Exception:
                continue
            if isinstance(r, float):
                r = round(r, 4)
                r = int(r) if r == int(r) else r
            return str(r).replace(".", ",")
    return None


def achar_lembrete(texto):
    """'me lembra de beber água em 10 minutos' -> (600, 'beber água'), ou None."""
    t = simplificar(texto)
    unidade = r"(segundos?|seg|minutos?|min|horas?|h)\b"
    m = (re.search(r"(?:me )?(?:lembr[ae]|avis[ae])(?: de| para| que)? (.*?)\s*(?:daqui a|em) (\d+)\s*" + unidade, t)
         or re.search(r"(?:daqui a|em) (\d+)\s*" + unidade + r"[, ]*(?:me )?(?:lembr[ae]|avis[ae])(?: de| para| que)?\s*(.*)", t))
    if not m:
        return None
    g = m.groups()
    if g[0].isdigit():
        n, u, assunto = int(g[0]), g[1], g[2]
    else:
        assunto, n, u = g[0], int(g[1]), g[2]
    seg = n * (3600 if u.startswith("h") else 60 if u.startswith("m") else 1)
    # recupera o texto com acentos, na mesma posição da frase original
    original = re.search(re.escape(assunto), simplificar(texto)) if assunto else None
    if original:
        assunto = texto[original.start():original.end()]
    return seg, (assunto.strip(" ,.") or "isso"), n, u


# ------------------------------ o cérebro ------------------------------
class Cerebro:
    def __init__(self, pasta_dados, arq_estado, semente=None):
        self.pasta = Path(pasta_dados)
        self.arq = Path(arq_estado)
        self.rng = random.Random(semente)
        self.estado = {"fb": {}, "fatos": {}, "recentes": [], "remix_ruim": [], "pendentes": {},
                       "braco": {"curada": [0, 0], "remix": [0, 0]}}
        self.estado_corrompido = False
        if self.arq.exists():
            try:
                self.estado.update(json.loads(self.arq.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                # estado ilegível: mantém os padrões, mas avisa (a troca guarda o .bak)
                self.estado_corrompido = True
        self.treinar()

    # ---- leitura dos arquivos de dados ----
    def _ler(self, nome):
        arq = self.pasta / nome
        if not arq.exists():
            return []
        out = []
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                out.append([p.strip() for p in linha.split("|")])
        return out

    def _arquivos(self, padrao):
        return sorted(p.name for p in self.pasta.glob(padrao))

    def treinar(self):
        """(Re)lê tudo da pasta dados/ e treina os modelos. Leva uma fração de segundo."""
        self.pastas_ok = self.pasta.exists()
        self.nb_intencao, self.nb_humor = NaiveBayes(), NaiveBayes()
        self.nb_intencao.treinar([(p[0], p[1]) for p in self._ler("intencoes.txt") if len(p) >= 2])
        self.nb_humor.treinar([(p[0], p[1]) for p in self._ler("humor.txt") if len(p) >= 2])
        pares = []
        for nome in ("conversas.txt", "aprendido.txt"):
            for p in self._ler(nome):
                if len(p) >= 2:
                    pers = {x.strip() for x in p[2].split(",") if x.strip()} if len(p) >= 3 else None
                    pares.append((p[0], p[1], pers))
        self.recup = Recuperador()
        self.recup.treinar(pares)
        self.n_pares = len(pares)
        self.respostas = defaultdict(lambda: defaultdict(list))
        self.falas = defaultdict(lambda: defaultdict(list))
        self.ngram = {}
        self.personas = sorted({n[len("respostas_"):-4].split("_")[0] for n in self._arquivos("respostas_*.txt")})
        vocab_geral = [l[0] for l in self._ler("vocabulario.txt")]
        for per in self.personas:
            for nome in self._arquivos(f"respostas_{per}*.txt"):
                for p in self._ler(nome):
                    if len(p) >= 2:
                        self.respostas[per][p[0]].append(p[1])
            for nome in self._arquivos(f"falas_{per}*.txt"):
                for p in self._ler(nome):
                    if len(p) >= 2:
                        self.falas[per][p[0]].append(p[1])
            corpus = [t for v in self.falas[per].values() for t in v] + vocab_geral   # só falas: respostas têm dados de ajuda
            for nome in self._arquivos(f"vocabulario_{per}*.txt"):
                corpus += [l[0] for l in self._ler(nome)]
            ng = Ngrama(self.rng)
            ng.treinar(corpus)
            self.ngram[per] = ng
        self.treinado_em = datetime.now()

    def salvar(self):
        try:
            escrever_atomico(self.arq, json.dumps(self.estado, ensure_ascii=False, indent=1))
        except OSError:
            pass

    # ---- variáveis para preencher as frases ----
    def variaveis(self, ctx, extra=None):
        agora = ctx.get("agora") or datetime.now()
        h = agora.hour
        f = self.estado["fatos"]
        v = {
            "hora": f"{h}h{agora.minute:02d}" if agora.minute else f"{h}h",
            "data": f"{agora.day} de {MESES[agora.month - 1]} de {agora.year}",
            "dia_semana": SEMANA[agora.weekday()], "mes": MESES[agora.month - 1], "ano": str(agora.year),
            "saudacao_hora": "bom dia" if 5 <= h < 12 else "boa tarde" if 12 <= h < 18 else "boa noite",
            "nome": f.get("nome", ""), "projeto": f.get("projeto", ""), "pet": f.get("pet", ""),
            "trabalho": f.get("trabalho", ""),
            "gosto": self.rng.choice(f["gostos"]) if f.get("gostos") else "",
            "desgosto": self.rng.choice(f["desgostos"]) if f.get("desgostos") else "",
            "app": ctx.get("app", ""), "tempo_app": ctx.get("tempo_app", ""),
            "resumo_hoje": ctx.get("resumo_hoje", ""), "proximo": ctx.get("proximo", ""),
            "notas": str(ctx["notas"]) if ctx.get("notas") is not None else "",
        }
        v.update(extra or {})
        return v

    @staticmethod
    def periodo(agora):
        h = agora.hour
        return "madrugada" if h < 5 else "manha" if h < 12 else "tarde" if h < 18 else "noite"

    def rid(self, persona, cat, texto):
        return hashlib.sha1(f"{persona}|{cat}|{texto}".encode("utf-8")).hexdigest()[:10]

    def _escolher(self, persona, cat, textos, vars_):
        """Thompson sampling: sorteia uma nota de cada frase a partir de gostei/não gostei."""
        melhor, melhor_s = None, -1.0
        for t in textos:
            falta = [k for k in re.findall(r"\{(\w+)\}", t) if not vars_.get(k)]
            if falta:
                continue
            rid = self.rid(persona, cat, t)
            up, down = self.estado["fb"].get(rid, [0, 0])
            s = self.rng.betavariate(1 + up, 1 + down)
            if rid in self.estado["recentes"][-RECENTES:]:
                s *= 0.2
            if s > melhor_s:
                melhor, melhor_s = (t, rid), s
        if not melhor:
            return None
        def preencher(m):
            valor = str(vars_[m.group(1)])
            ini = melhor[0][:m.start()].rstrip()
            return valor[:1].upper() + valor[1:] if not ini or ini[-1] in ".!?" else valor
        texto = re.sub(r"\{(\w+)\}", preencher, melhor[0])
        self.estado["recentes"] = (self.estado["recentes"] + [melhor[1]])[-60:]
        return texto, melhor[1]

    # ---- fatos que você conta ----
    PADROES_FATOS = [
        ("nome", r"\bmeu nome (?:é|e)\s+([A-Za-zÀ-ÿ]+)"),
        ("nome", r"\b(?:me chamo|pode me chamar de)\s+([A-Za-zÀ-ÿ]+)"),
        ("projeto", r"\bmeu projeto(?: atual| agora)? (?:é|e|se chama)\s+(.+?)[.!?]*$"),
        ("trabalho", r"\beu trabalho (?:com|como|em|na|no)\s+(.+?)[.!?]*$"),
        ("desgostos", r"\beu (?:não gosto|nao gosto|odeio|detesto) (?:de |do |da |dos |das )?(.+?)[.!?]*$"),
        ("gostos", r"\beu (?:gosto|amo|curto|adoro) (?:muito )?(?:de |do |da |dos |das )?(.+?)[.!?]*$"),
        ("pet", r"\bmeu (?:gato|gata|cachorro|cachorra|cão|pet|bichinho) (?:se chama|chama|é o|é a|e o|e a)\s+([A-Za-zÀ-ÿ]+)"),
    ]

    def extrair_fatos(self, texto):
        achou = {}
        f = self.estado["fatos"]
        for chave, padrao in self.PADROES_FATOS:
            m = re.search(padrao, texto.strip(), re.I)
            if not m or chave in achou:
                continue
            valor = m.group(1).strip()[:60]
            if chave in ("gostos", "desgostos"):
                lista = f.setdefault(chave, [])
                if valor.lower() not in [x.lower() for x in lista]:
                    lista.append(valor)
                del lista[:-8]
            else:
                f[chave] = valor.title() if chave in ("nome", "pet") else valor
            achou[chave] = valor
            if chave in ("gostos", "desgostos"):
                break
        if achou:
            self.salvar()
        return achou

    # ---- conversa ----
    def seguranca(self, texto):
        t = normalizar(texto)
        if "suicid" in t:  # estudar/falar sobre suicídio é assunto sério, não necessariamente crise pessoal
            return any(g in t for g in ("quero", "pens", "vou me", "minha vida", "as vezes"))
        if any(c in t for c in CRISE):
            return True
        return any(alvo in t and any(p in t for p in gatilhos)
                   for alvo, gatilhos in CRISE_COMBINADA)

    REGRAS = [
        ("dia_semana", r"\bdia da semana\b|\bque dia da semana\b|\bhoje e (segunda|terca|quarta|quinta|sexta|sabado|domingo)\b"),
        ("hora", r"\bque horas?\b|\bqual (?:e )?(?:a )?hora\b|\bhoras? sao\b|\bme (?:diz|fala|da) (?:a )?hora\b"),
        ("mes", r"\bque mes\b|\bqual (?:e )?(?:o )?mes\b|\bem que mes\b"),
        ("ano", r"\bque ano\b|\bqual (?:e )?(?:o )?ano\b|\bem que ano\b"),
        ("data", r"\bque dia (?:e|eh) hoje\b|\bqual (?:e )?(?:a )?data\b|\bdata de hoje\b|\bdia do mes\b|\bque dia (?:e|eh)\b"),
    ]

    def _intencao(self, texto, persona):
        t = normalizar(texto)
        for classe, padrao in self.REGRAS:
            if re.search(padrao, t):
                return classe, 1.0, "regra", {}
        lem = achar_lembrete(texto)
        if lem:
            seg, assunto, n, u = lem
            quando = f"{n} {'hora' if u.startswith('h') else 'minuto' if u.startswith('m') else 'segundo'}{'s' if n != 1 else ''}"
            return "lembrete", 1.0, "regra", {"texto_lembrete": assunto, "quando": quando, "_seg": seg}
        r = calcular(texto)
        if r is not None:
            return "conta", 1.0, "regra", {"resultado": r}
        melhor, nota = self.recup.buscar(texto, persona)
        if melhor and nota >= SIM_CONVERSA:
            return "ensinada", nota, "ensinada", {"_resposta": melhor[0]}
        p = self.nb_intencao.prever(texto)
        if p and p[1] >= CONF_INTENCAO and p[2] >= COBERTURA_MIN:
            return p[0], p[1], "ml", {}
        return None

    REFLEXOS = [("reflexo_estar", r"\b(?:eu )?(?:estou|to|tô|ando) (.+)"), ("reflexo_querer", r"\beu (?:quero|queria|preciso de|preciso) (.+)"),
                ("reflexo_sentir", r"\beu (?:me )?sinto (.+)")]
    PRONOMES = {"meu": "seu", "minha": "sua", "meus": "seus", "minhas": "suas", "eu": "você", "me": "te", "mim": "você"}

    def _reflexo(self, texto):
        t = texto.lower()
        for classe, padrao in self.REFLEXOS:
            m = re.search(padrao, t)
            if m:
                x = " ".join(self.PRONOMES.get(w, w) for w in m.group(1).strip(" .!?").split())
                return classe, x[:60]
        return None

    def responder(self, texto, persona, ctx=None):
        """-> dict(texto, humor, intencao, origem, id, conf, acao)"""
        ctx = ctx or {}
        persona = persona if persona in self.respostas else (self.personas[0] if self.personas else "")
        if self.seguranca(texto):
            return {"texto": self.rng.choice(ACOLHIMENTO), "humor": "triste", "intencao": "crise",
                    "origem": "seguranca", "id": None, "conf": 1.0, "acao": None}
        fatos = self.extrair_fatos(texto)
        intencao = self._intencao(texto, persona)
        extra, origem, conf, acao = {}, "ml", 0.0, None
        if fatos and not (intencao and intencao[2] == "regra"):
            nome, extra, origem, conf = "fato_ok", {}, "fatos", 1.0
        elif intencao:
            nome, conf, origem, extra = intencao
        else:
            refl = self._reflexo(texto)
            if refl:
                nome, extra, origem = refl[0], {"x": refl[1]}, "reflexo"
            else:
                nome, origem = "desconhecida", "desconhecida"
                self._registrar_desconhecida(texto)
        if nome == "lembrete":
            acao = {"tipo": "lembrete", "segundos": extra["_seg"], "texto": extra["texto_lembrete"]}
        if nome == "ensinada":
            resp, rid = extra["_resposta"], self.rid(persona, "ensinada", extra["_resposta"])
        else:
            vars_ = self.variaveis(ctx, extra)
            lista = self.respostas[persona].get(nome, [])
            esc = self._escolher(persona, nome, lista, vars_)
            if not esc and nome not in ("desconhecida",):
                alt = "sem_dados" if origem in ("ml", "regra") else "desconhecida"
                esc = self._escolher(persona, alt, self.respostas[persona].get(alt, []), vars_) \
                    or self._escolher(persona, "desconhecida", self.respostas[persona].get("desconhecida", []), vars_)
            resp, rid = esc or ("Hmm... não sei o que dizer. Me ensina? Escreva: ensina: <resposta>", None)
        ph = self.nb_humor.prever(texto) or (None, 0, 0)
        humor = HUMOR_INTENCAO.get(nome) or (ph[0] if ph[1] >= 0.6 and ph[2] >= COBERTURA_MIN else "normal")
        self.salvar()
        return {"texto": resp, "humor": humor, "intencao": nome, "origem": origem, "id": rid,
                "conf": round(conf, 2), "acao": acao}

    def _registrar_desconhecida(self, texto):
        arq = self.pasta / "nao_entendi.txt"
        try:
            ja = arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []
            if texto.strip() and texto.strip() not in ja:
                with open(arq, "a", encoding="utf-8") as f:
                    f.write(texto.strip() + "\n")
        except Exception:
            pass

    # ---- falas espontâneas ----
    def fala(self, persona, tipo, ctx=None):
        """tipo: 'fala', 'bilhete' ou 'pausa'. -> dict(texto, id, origem)"""
        ctx = ctx or {}
        agora = ctx.get("agora") or datetime.now()
        vars_ = self.variaveis(ctx)
        base = list(self.falas[persona].get(tipo, []))
        if tipo == "fala":
            base += self.falas[persona].get(self.periodo(agora), [])
        ng = self.ngram.get(persona)
        usar_remix = False
        if ng and ng.n >= REMIX_MIN_FRASES and tipo != "pausa":
            c, r = self.estado["braco"]["curada"], self.estado["braco"]["remix"]
            usar_remix = self.rng.betavariate(1 + r[0], 3 + r[1]) > self.rng.betavariate(1 + c[0], 1 + c[1])   # começa desconfiado do remix
        if usar_remix:
            ruins = set(self.estado["remix_ruim"])
            novo = ng.gerar(proibidas=ruins)
            if novo:
                rid = self.rid(persona, "remix", novo)
                self.estado["pendentes"][rid] = {"persona": persona, "texto": novo, "tipo": tipo}
                for k in list(self.estado["pendentes"])[:-40]:
                    del self.estado["pendentes"][k]
                self.salvar()
                return {"texto": novo, "id": rid, "origem": "remix"}
        esc = self._escolher(persona, tipo, base, vars_)
        if not esc:
            return None
        self.salvar()
        return {"texto": esc[0], "id": esc[1], "origem": "curada"}

    # ---- personalidade automática: aprende qual você curte em cada situação ----
    def auto_nota(self, contexto, persona):
        up, down = self.estado.setdefault("auto", {}).get(f"{contexto}|{persona}", [0, 0])
        return self.rng.betavariate(1 + up, 1 + down)

    def auto_feedback(self, contexto, persona, positivo):
        v = self.estado.setdefault("auto", {}).setdefault(f"{contexto}|{persona}", [0, 0])
        v[0 if positivo else 1] += 1
        self.salvar()

    # ---- feedback e ensino ----
    def feedback(self, rid, positivo, origem="curada"):
        if not rid:
            return
        up_down = self.estado["fb"].setdefault(rid, [0, 0])
        up_down[0 if positivo else 1] += 1
        pend = self.estado["pendentes"].get(rid)
        braco = "remix" if pend else "curada"
        self.estado["braco"][braco][0 if positivo else 1] += 1
        if pend:
            if positivo:      # frase inventada que você aprovou vira frase de verdade
                try:
                    with open(self.pasta / f"falas_{pend['persona']}_aprendido.txt", "a", encoding="utf-8") as f:
                        f.write(f"{pend['tipo']} | {pend['texto']}\n")
                except Exception:
                    pass
            else:
                self.estado["remix_ruim"].append(simplificar(pend["texto"]))
            del self.estado["pendentes"][rid]
        self.salvar()

    def ensinar(self, pergunta, resposta, persona=None):
        # o formato do arquivo é "pergunta | resposta | personas": "|" no meio
        # quebraria as colunas; "#" no começo faria a linha virar comentário.
        limpar = lambda s: re.sub(r"[|#]", " ", str(s)).strip()
        pergunta, resposta = limpar(pergunta), limpar(resposta)
        if not pergunta or not resposta:
            return False
        linha = f"{pergunta} | {resposta}" + (f" | {limpar(persona)}" if persona else "")
        arq = self.pasta / "aprendido.txt"
        try:
            existente = arq.read_text(encoding="utf-8") if arq.exists() else ""
            # sem "\n" final no arquivo antigo, o append colava a linha nova na última
            prefixo = "" if (not existente or existente.endswith("\n")) else "\n"
            with open(arq, "a", encoding="utf-8") as f:
                f.write(prefixo + linha + "\n")
        except OSError:
            return False
        self.treinar()
        return True

    def esquecer(self):
        arq = self.pasta / "aprendido.txt"
        if arq.exists():
            arq.write_text("# frases ensinadas com 'ensina:' ficam aqui\n", encoding="utf-8")
        for p in self.pasta.glob("falas_*_aprendido.txt"):
            p.unlink()
        self.estado = {"fb": {}, "fatos": {}, "recentes": [], "remix_ruim": [], "pendentes": {},
                       "braco": {"curada": [0, 0], "remix": [0, 0]}}
        self.salvar()
        self.treinar()

    def estatisticas(self):
        e = self.estado
        fb = list(e["fb"].values())
        c, r = e["braco"]["curada"], e["braco"]["remix"]
        f = e["fatos"]
        linhas = ["O QUE ELE JÁ SABE",
                  f"  Exemplos de intenção: {sum(self.nb_intencao.n.values())} em {len(self.nb_intencao.n)} intenções",
                  f"  Exemplos de humor: {sum(self.nb_humor.n.values())}",
                  f"  Pares pergunta → resposta: {self.n_pares}", ""]
        for per in self.personas:
            nf = sum(len(v) for v in self.falas[per].values())
            nr = sum(len(v) for v in self.respostas[per].values())
            linhas.append(f"  {per}: {nr} respostas, {nf} falas, texto para remix: {self.ngram[per].n} frases")
        linhas += ["", "O QUE ELE APRENDEU COM VOCÊ",
                   f"  Notas dadas: {sum(a + b for a, b in fb)} (gostei {sum(a for a, _ in fb)}, não gostei {sum(b for _, b in fb)})",
                   f"  Frases próprias aprovadas: {c[0]} de {c[0] + c[1]} | remix aprovados: {r[0]} de {r[0] + r[1]}",
                   f"  Frases inventadas que você barrou: {len(e['remix_ruim'])}",
                   f"  Notas por situação (personalidade automática): {sum(a + b for a, b in e.get('auto', {}).values())}"]
        if f:
            linhas.append("  Fatos: " + "; ".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in f.items()))
        arq = self.pasta / "nao_entendi.txt"
        pend = len(arq.read_text(encoding="utf-8").splitlines()) if arq.exists() else 0
        linhas += ["", f"Frases que ele não entendeu (dados/nao_entendi.txt): {pend}",
                   f"Treinado em {self.treinado_em:%d/%m %H:%M:%S}"]
        return "\n".join(linhas)

    def resumo_curto(self):
        return f"{sum(self.nb_intencao.n.values()) + self.n_pares} exemplos"
