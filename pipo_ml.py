"""
Pipo ML - amiguinho de mesa numa telinha moderna, que também sai para passear pelos monitores
e pelas janelas. Roda 100% no seu PC, SEM nenhuma IA externa (sem chave, sem internet, sem
modelos para baixar): quem pensa é o cerebro.py, um cérebro de machine learning leve que
aprende com os arquivos da pasta dados/ e com o que você ensina conversando.

Requisitos: Python 3.9+ no Windows. Não precisa instalar nada (só a biblioteca padrão).
Para abrir:  python pipo_ml.py      (cerebro.py e a pasta dados precisam estar ao lado)

A telinha (arraste pelo corpo dela, funciona entre os dois monitores):
  papo     abre o chat (se ele estiver dormindo, acorda)
  bilhete  cria um post-it
  passear  a telinha some e só o bichinho sai andando pelo chão dos monitores e pelo topo das
           janelas abertas. Clique nele para a telinha voltar; arraste-o para pegá-lo no colo.
  dormir   silencia e pausa a observação
  ver PC   mostra o que ele registrou da sua atividade (e permite apagar)
  sons     liga e desliga os bipes
Botão direito: menu com tudo isso mais "falar agora", a personalidade (Fofinho, Zen,
Sarcástico, Mentor ou Revoltado), "O que o Pipo aprendeu" e "Recarregar dados".

COMO ALIMENTAR O PIPO (leia o LEIAME.txt):
  - Converse com ele. Nos balões e no chat, use "gostei" e "não gostei": ele aprende o que você curte.
  - Escreva  ensina: <resposta>  logo depois de uma pergunta que ele não soube responder.
  - Edite os arquivos da pasta dados/ (intenções, respostas, falas, humor, conversas, vocabulário)
    e use "Recarregar dados" no menu.
  - Tudo o que ele não entende é anotado em dados/nao_entendi.txt, para você ensinar depois.
"""
import collections
import ctypes
import json
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

WINDOWS = sys.platform == "win32"

try:
    import winsound  # sons (só existe no Windows)
except ImportError:
    winsound = None

from cerebro import Cerebro, simplificar

# ------------------------------- configuração -------------------------------
NOME = "Pipo"
INTERVALO_MIN, INTERVALO_MAX = 1, 10    # minutos entre falas espontâneas
SILENCIO = (23, 7)               # sem falas espontâneas entre 23h e 7h
CHANCE_BILHETE = 0.25            # chance de a fala espontânea virar bilhete
SONS = True                      # sons discretos (também dá para ligar/desligar no menu)
OBSERVAR = True                  # observar qual programa está em uso (liga/desliga no menu)
INTERVALO_OBS = 5                # a cada quantos segundos olhar a janela em foco
OCIOSO_MAX = 300                 # segundos sem mexer no PC = ausente (não conta tempo)
PAUSA_APOS_MIN = 90              # minutos seguidos no mesmo programa para sugerir uma pausa
RETENCAO_DIAS = 60               # quantos dias de histórico manter
IGNORAR_EXES = {"keepass.exe", "keepassxc.exe", "bitwarden.exe", "1password.exe", "lastpass.exe"}
IGNORAR_TITULOS = ("senha", "password", "banco ", "nubank", "itaú", "bradesco", "santander",
                   "incógnito", "incognito", "inprivate", "navegação privada", "private browsing")
ESCALA = 0.85                    # tamanho da telinha (1.0 = 320x350 px; use mais em telas grandes)
ESCALA_PASSEIO = 1.0             # tamanho do bichinho passeando
AJUDA = ('Comandos: anota: <texto> | ensina: <resposta> (ensina a última coisa que você disse) | '
         'gostei / não gostei | me lembra de <algo> em 10 minutos | quanto é 2+2 | que horas são | /ajuda')

AUTO_MIN_MINUTOS = 15            # tempo mínimo entre duas trocas automáticas de personalidade
# Pontos que cada personalidade ganha em cada situação no modo automático (ajuste à vontade).
# Além disso ele aprende com seus "gostei/não gostei": o que você aprova em cada situação ganha força.
REGRAS_AUTO = {
    "periodo": {"madrugada": {"zen": 2.0, "fofinho": 0.5}, "manha": {"mentor": 1.0, "fofinho": 0.8},
                "tarde": {"sarcastico": 0.5, "mentor": 0.5}, "noite": {"zen": 1.2, "fofinho": 0.6}},
    "nivel": {"alta": {"fofinho": 1.5, "sarcastico": 0.8},
              "media": {"fofinho": 0.5, "mentor": 0.5, "sarcastico": 0.3},
              "ausente": {"revoltado": 1.8, "sarcastico": 1.0}},      # muito tempo sem falar com ele
    "foco": {"mentor": 1.5, "zen": 1.0},                              # 60 min ou mais no mesmo programa
}

PERSONA_PADRAO = "fofinho"
PERSONAS = {
    "fofinho": {"nome": "Fofinho", "resumo": "carinhoso e bem-humorado", "cor": "#f6f2d2", "cor_sono": "#c9c9a0",
                "saudacao": "Oi, oi! Voltei ao meu jeitinho fofo!",
                "prontas": ["Ei, já bebeu água hoje?", "Só passando pra dizer que você está indo bem!"],
                "pausa": ["Faz um tempão que você está aí! Que tal esticar as pernas?"]},
    "zen": {"nome": "Zen", "resumo": "calmo e tranquilo", "cor": "#d8efe0", "cor_sono": "#a9c4b2",
            "saudacao": "Respira fundo... agora sou o Pipo zen.",
            "prontas": ["Respira fundo comigo: inspira... e solta devagarinho."],
            "pausa": ["O trabalho espera um minutinho. Você merece esse respiro."]},
    "sarcastico": {"nome": "Sarcástico", "resumo": "debochado, com ironia leve", "cor": "#e4d9f2", "cor_sono": "#b5aac4",
                   "saudacao": "Ah, então agora eu sou o debochado. Vai se arrepender.",
                   "prontas": ["Ei, ainda está vivo? Bebe uma água."],
                   "pausa": ["Você e essa cadeira estão juntos há tempo demais. Levanta um pouco."]},
    "mentor": {"nome": "Mentor", "resumo": "focado e prático", "cor": "#f7dfae", "cor_sono": "#c9b585",
               "saudacao": "Modo mentor ativado. Qual é o próximo passo?",
               "prontas": ["Qual é a próxima tarefa pequena que você consegue fechar agora?"],
               "pausa": ["Pausa também é produtividade. Levanta, bebe água e volta."]},
    "revoltado": {"nome": "Revoltado", "resumo": "mal-humorado e implicante (de brincadeira)",
                  "cor": "#f3b8b0", "cor_sono": "#c18b86",
                  "saudacao": "Ah, voltou. Que pena. Quer dizer... que ótimo.",
                  "prontas": ["Ainda aí? Achei que tinha desistido.", "Já bebeu água ou prefere secar igual planta esquecida?"],
                  "pausa": ["Pausa. Agora. Não discute."]},
}

try:  # evita personagem borrado/errado em monitores com escalas diferentes (só Windows)
    if WINDOWS:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # type: ignore[attr-defined]
except Exception:
    pass

# Fontes por plataforma: Segoe é exclusiva do Windows; fora dele, as equivalentes do sistema.
if WINDOWS:
    F_TEXTO, F_SIMBOLO, F_MONO, F_CANETA = "Segoe UI", "Segoe UI Symbol", "Consolas", "Segoe Print"
else:
    F_TEXTO = F_SIMBOLO = F_MONO = F_CANETA = "DejaVu Sans"


def abrir_pasta(caminho):
    """Abre a pasta de dados no gerenciador de arquivos de cada sistema."""
    try:
        if WINDOWS:
            os.startfile(caminho)                    # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(caminho)])
        else:
            subprocess.Popen(["xdg-open", str(caminho)])
    except (OSError, FileNotFoundError):
        pass

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados"
ARQ_NOTAS = PASTA / "notas.json"
ARQ_HIST = PASTA / "historico.json"
ARQ_ESTADO = PASTA / "estado.json"
ARQ_ATIVIDADE = PASTA / "atividade.json"
ARQ_CEREBRO = PASTA / "cerebro.json"
TRANSP = "#ff00ff"


def carregar(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def salvar(arq, dados):
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


LARGURA = int(320 * ESCALA)
ALTURA = int(350 * ESCALA)


def F(n):
    """Tamanho de fonte acompanhando a escala."""
    return max(6, round(n * ESCALA))


BTN_COR, BTN_PRESS, BTN_BORDA = "#f2674f", "#c94a35", "#b23a28"
P = 4  # tamanho de cada "pixel" do bichinho

SPRITE = [
    "..##........##..",
    ".#oo#......#oo#.",
    ".#ooo######ooo#.",
    ".#oooooooooooo#.",
    ".#oooooooooooo#.",
    ".#ooEooooooEoo#.",
    ".#ooEooooooEoo#.",
    ".#oooooMMooooo#.",
    ".#oooooooooooo#.",
    ".#oooooooooooo#.",
    ".#oooooooooooo#.",
    ".##oooooooooo##.",
    "..############..",
    "..#oo#....#oo#..",
    "..####....####..",
]


def classe_cor(ch):
    return ch if ch in "obt" else "k"   # o=miolo, b=bochecha, t=lágrima, k=contorno/olhos/boca


def trechos(linha):
    """Agrupa pixels vizinhos da mesma cor para desenhar menos retângulos."""
    out, c = [], 0
    while c < len(linha):
        if linha[c] == ".":
            c += 1
            continue
        cl = classe_cor(linha[c])
        d = c
        while d < len(linha) and linha[d] != "." and classe_cor(linha[d]) == cl:
            d += 1
        out.append((c, d, cl))
        c = d
    return out


# posições (linha, coluna) dos olhos e da boca em cada expressão
OLHOS = {
    "normal": [(5, 4), (6, 4), (5, 11), (6, 11)],
    "fechado": [(6, 3), (6, 4), (6, 11), (6, 12)],
    "feliz": [(5, 4), (6, 3), (6, 5), (5, 11), (6, 10), (6, 12)],
    "surpreso": [(4, 4), (5, 4), (6, 4), (4, 11), (5, 11), (6, 11)],
}
BOCAS = {
    "normal": [(7, 7), (7, 8)],
    "feliz": [(7, 6), (7, 9), (8, 7), (8, 8)],
    "surpreso": [(7, 7), (7, 8), (8, 7), (8, 8)],
    "triste": [(7, 7), (7, 8), (8, 6), (8, 9)],
    "sonolento": [(8, 7), (8, 8)],
    "falando": [(7, 7), (7, 8), (8, 7), (8, 8)],
}
HUMORES_LLM = ("normal", "feliz", "triste", "surpreso")

# sons discretos: lista de (frequência em Hz, duração em ms)
MELODIAS = {
    "clique": [(1200, 25)],
    "msg": [(880, 55), (1175, 70)],
    "bilhete": [(988, 60), (1319, 80)],
    "dormir": [(660, 90), (523, 90), (392, 140)],
    "acordar": [(523, 70), (659, 70), (784, 110)],
    "carinho": [(1047, 50), (1319, 50), (1568, 90)],
    "triste": [(392, 120), (330, 180)],
}


def area_virtual():
    """(x, y, largura, altura) de todos os monitores juntos, ou None se não der para saber."""
    try:
        if WINDOWS:
            u = ctypes.windll.user32                     # type: ignore[attr-defined]
            return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                    u.GetSystemMetrics(78), u.GetSystemMetrics(79))
        if sys.platform == "linux" and os.environ.get("DISPLAY") and shutil.which("xdotool"):
            tam = subprocess.run(["xdotool", "getdisplaygeometry"],
                                 capture_output=True, text=True, timeout=2).stdout.split()
            if len(tam) == 2:                            # área virtual no X11 começa em (0,0)
                return (0, 0, int(tam[0]), int(tam[1]))
        return None
    except Exception:
        return None


def posicao_valida(x, y):
    a = area_virtual()
    if not a:
        return True
    vx, vy, vw, vh = a
    return (vx - LARGURA // 2 <= x <= vx + vw - LARGURA // 2
            and vy <= y <= vy + vh - ALTURA // 2)


def pontos_ovo(cx, cy, a, b, n=96):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        s, c = math.sin(t), math.cos(t)
        pts += [cx + a * c * (1 - 0.2 * s), cy - b * s]
    return pts


def pontos_arredondado(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# --------------------- observação da atividade no PC ---------------------
APPS = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "brave.exe": "Brave",
    "code.exe": "VS Code", "explorer.exe": "Explorador de Arquivos",
    "windowsterminal.exe": "Terminal", "powershell.exe": "PowerShell", "cmd.exe": "Prompt de Comando",
    "python.exe": "Python", "pythonw.exe": "Python", "discord.exe": "Discord",
    "spotify.exe": "Spotify", "steam.exe": "Steam", "whatsapp.exe": "WhatsApp",
    "orca-slicer.exe": "Orca Slicer", "orcaslicer.exe": "Orca Slicer",
    "ultimaker-cura.exe": "Cura", "cura.exe": "Cura", "prusa-slicer.exe": "PrusaSlicer",
    "blender.exe": "Blender", "fusion360.exe": "Fusion 360", "notepad.exe": "Bloco de Notas",
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint",
    "vlc.exe": "VLC", "obs64.exe": "OBS", "?": "Outro programa",
}

try:  # funções do Windows para descobrir a janela em foco e o tempo sem mexer no PC
    _U = ctypes.WinDLL("user32")
    _K = ctypes.WinDLL("kernel32")
    _U.GetForegroundWindow.restype = ctypes.c_void_p
    _U.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    _U.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _U.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    _K.OpenProcess.restype = ctypes.c_void_p
    _K.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    _K.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                              ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    _K.CloseHandle.argtypes = [ctypes.c_void_p]
    _K.GetTickCount.restype = ctypes.c_uint
    WIN_OK = True
except Exception:
    WIN_OK = False


class _UltimaEntrada(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _janela_x11():
    """(programa, título, pid) da janela em foco no X11 via xdotool (None fora do X11).
    No Wayland isso é bloqueado pelo próprio protocolo — o Pipo segue sem observar."""
    if not os.environ.get("DISPLAY") or shutil.which("xdotool") is None:
        return None
    try:
        wid = subprocess.run(["xdotool", "getactivewindow"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        if not wid.isdigit():
            return None
        pid = subprocess.run(["xdotool", "getwindowpid", wid], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        titulo = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True,
                                text=True, timeout=2).stdout.strip()
        exe = "?"
        if pid.isdigit():
            nome = Path(f"/proc/{pid}/comm")
            if nome.exists():
                exe = nome.read_text().strip().lower() or "?"
        return exe, titulo, int(pid) if pid.isdigit() else 0
    except Exception:
        return None


def _ocioso_x11():
    """Segundos sem entrada no X11 (xprintidle); 0.0 se a ferramenta não existir."""
    if not os.environ.get("DISPLAY") or shutil.which("xprintidle") is None:
        return 0.0
    try:
        ms = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2).stdout.strip()
        return int(ms) / 1000.0 if ms.isdigit() else 0.0
    except Exception:
        return 0.0


def janela_ativa():
    """(programa.exe, título, pid) da janela em foco, ou None se não der para saber."""
    if not WIN_OK:
        return _janela_x11()
    try:
        hwnd = _U.GetForegroundWindow()
        if not hwnd:
            return None
        n = _U.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        _U.GetWindowTextW(hwnd, buf, n + 1)
        pid = ctypes.c_ulong()
        _U.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = "?"
        h = _K.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                tam = ctypes.c_ulong(520)
                nome = ctypes.create_unicode_buffer(520)
                if _K.QueryFullProcessImageNameW(h, 0, nome, ctypes.byref(tam)):
                    exe = Path(nome.value).name.lower()
            finally:
                _K.CloseHandle(h)
        return exe, buf.value, pid.value
    except Exception:
        return None


def segundos_ocioso():
    """Há quantos segundos o usuário não mexe no mouse nem no teclado."""
    if not WIN_OK:
        return _ocioso_x11()
    try:
        li = _UltimaEntrada()
        li.cbSize = ctypes.sizeof(li)
        if not _U.GetLastInputInfo(ctypes.byref(li)):
            return 0.0
        return ((_K.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0.0


def nome_amigavel(exe):
    return APPS.get(exe, Path(exe).stem.replace("-", " ").replace("_", " ").title() or "Outro programa")


def fmt(seg):
    m = int(seg // 60)
    if m < 1:
        return "<1 min"
    if m < 60:
        return f"{m} min"
    return f"{m // 60}h{m % 60:02d}"


class Observador:
    """Registra só o NOME do programa em foco e o tempo de uso (nunca o título das janelas)."""

    def __init__(self):
        d = carregar(ARQ_ATIVIDADE, {})
        self.dias = d.get("dias", {})      # {"2026-11-01": {"Chrome": segundos}}
        self.trans = d.get("trans", {})    # {"Chrome>Cura": quantas vezes}
        self.amostras = collections.deque(maxlen=800)
        self.app = None
        self.titulo = ""                   # só na memória, nunca vai para o arquivo
        self.estado = "parado"             # ativo | ausente | privado | parado
        self.inicio_app = time.time()
        self.ultimo_longo = None
        self.ultimo_salvo = time.time()
        for dia in sorted(self.dias)[:-RETENCAO_DIAS]:
            del self.dias[dia]

    def parar(self, estado="parado"):
        self.app, self.titulo, self.estado = None, "", estado
        self.ultimo_longo = None

    def amostrar(self, janela, ocioso, dt):
        agora = time.time()
        if janela is None or ocioso > OCIOSO_MAX:
            self.parar("ausente")
            return
        exe, titulo, pid = janela
        if pid == os.getpid():      # conversar com o próprio Pipo não conta como outro programa
            return
        baixo = titulo.lower()
        if exe in IGNORAR_EXES or any(t in baixo for t in IGNORAR_TITULOS):
            self.parar("privado")
            return
        app = nome_amigavel(exe)
        if app != self.app:
            self.app, self.inicio_app = app, agora
        self.titulo, self.estado = titulo, "ativo"
        d = self.dias.setdefault(datetime.now().strftime("%Y-%m-%d"), {})
        d[app] = d.get(app, 0) + dt
        self.amostras.append((agora, app, dt))
        if agora - self.inicio_app >= 20 and self.ultimo_longo != app:  # ignora alt-tab rápido
            if self.ultimo_longo:
                k = f"{self.ultimo_longo}>{app}"
                self.trans[k] = self.trans.get(k, 0) + 1
            self.ultimo_longo = app
        if agora - self.ultimo_salvo > 60:
            self.salvar()

    def salvar(self):
        self.ultimo_salvo = time.time()
        dias = {dia: {a: int(s) for a, s in d.items()} for dia, d in self.dias.items()}
        try:
            salvar(ARQ_ATIVIDADE, {"dias": dias, "trans": self.trans})
        except Exception:
            pass

    def apagar(self):
        self.dias.clear()
        self.trans.clear()
        self.amostras.clear()
        self.salvar()

    def seguidos(self):
        return time.time() - self.inicio_app if self.estado == "ativo" else 0.0

    def ultimos(self, minutos=30):
        corte = time.time() - minutos * 60
        acc = {}
        for ts, app, dt in self.amostras:
            if ts >= corte:
                acc[app] = acc.get(app, 0) + dt
        return sorted(acc.items(), key=lambda kv: -kv[1])

    def hoje(self):
        d = self.dias.get(datetime.now().strftime("%Y-%m-%d"), {})
        return sorted(d.items(), key=lambda kv: -kv[1])

    def proximos(self, app, n=2):
        c = [(k.split(">", 1)[1], v) for k, v in self.trans.items() if k.startswith(app + ">")]
        return sorted(c, key=lambda kv: -kv[1])[:n]

    def contexto(self, titulos=False):
        """Resumo curto em texto para a IA."""
        if self.estado == "ativo":
            linha = f"Agora: {self.app}, há {fmt(self.seguidos())} seguidos."
            if titulos and self.titulo:
                linha += f' Janela: "{self.titulo[:60]}".'
        elif self.estado == "ausente":
            linha = "Agora: o usuário está ausente (sem mexer no PC)."
        elif self.estado == "privado":
            linha = "Agora: o usuário está numa janela privada, que não é observada."
        else:
            linha = "Agora: observação pausada."
        partes = [linha]
        rec = self.ultimos(30)[:4]
        if rec:
            partes.append("Últimos 30 min: " + ", ".join(f"{a} {fmt(s)}" for a, s in rec) + ".")
        hj = self.hoje()[:5]
        if hj:
            partes.append("Hoje: " + ", " .join(f"{a} {fmt(s)}" for a, s in hj) + ".")
        if self.app:
            prox = self.proximos(self.app)
            if prox:
                partes.append(f"Costuma abrir depois do {self.app}: "
                              + ", ".join(f"{a} ({n}x)" for a, n in prox) + ".")
        return "\n".join(partes)

    def relatorio(self):
        linhas = ["HOJE"]
        hj = self.hoje()
        linhas += [f"  {fmt(s):>8}  {a}" for a, s in hj] if hj else ["  (nada registrado ainda)"]
        total = {}
        for dia in sorted(self.dias)[-7:]:
            for a, s in self.dias[dia].items():
                total[a] = total.get(a, 0) + s
        linhas += ["", "ÚLTIMOS 7 DIAS (mais usados)"]
        top = sorted(total.items(), key=lambda kv: -kv[1])[:8]
        linhas += [f"  {fmt(s):>8}  {a}" for a, s in top] if top else ["  (nada registrado ainda)"]
        linhas += ["", "HÁBITOS (o que costuma vir depois de quê)"]
        tr = sorted(self.trans.items(), key=lambda kv: -kv[1])[:6]
        linhas += [f"  {k.replace('>', ' → ')}  ({n}x)" for k, n in tr] if tr else ["  (ainda aprendendo)"]
        linhas += ["", f"Só nomes de programas e tempos ficam salvos, em {ARQ_ATIVIDADE.name}.",
                   "Títulos de janelas nunca são gravados."]
        return "\n".join(linhas)


# ------------------------- telinha: botões e passeio -------------------------
BOTOES = [("papo", "papo"), ("bilhete", "bilhete"), ("passear", "passear"),
          ("dormir", "dormir"), ("ver", "ver PC"), ("sons", "sons")]
COR_BTN = {("btn_" + n): (("#f6e23f", "#ffe96b", "#d1bf2a") if n == "papo"
                          else ("#3a3646", "#4a4560", "#2d2a37")) for n, _ in BOTOES}
PW0, PH0, PE_Y = 112, 80, 76   # janela do bichinho passeando e a linha dos "pés" nela
ALT_PULO = 480                # altura máxima de um pulo, em pixels


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


try:  # funções do Windows para descobrir monitores e janelas
    _D = ctypes.WinDLL("dwmapi")
    _D.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
    _ENUM_MON = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.POINTER(_RECT), ctypes.c_void_p)
    _ENUM_WIN = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    _U.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _ENUM_MON, ctypes.c_void_p]
    _U.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONINFO)]
    _U.EnumWindows.argtypes = [_ENUM_WIN, ctypes.c_void_p]
    _U.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _U.IsIconic.argtypes = [ctypes.c_void_p]
    _U.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _U.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
    _U.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    PASSEIO_OK = WIN_OK
except Exception:
    PASSEIO_OK = False

IGNORAR_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                   "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow"}


def monitores():
    """Monitores: x1/x2/topo/base (tela inteira) e wtopo/wbase (área útil, sem a barra de tarefas)."""
    out = []
    if not PASSEIO_OK:
        return out

    def cb(hmon, hdc, rect, data):
        info = _MONINFO()
        info.cbSize = ctypes.sizeof(info)
        if _U.GetMonitorInfoW(hmon, ctypes.byref(info)):
            m, w = info.rcMonitor, info.rcWork
            out.append({"x1": m.left, "x2": m.right, "topo": m.top, "base": m.bottom,
                        "wtopo": w.top, "wbase": w.bottom})
        return 1
    try:
        _U.EnumDisplayMonitors(None, None, _ENUM_MON(cb), None)
    except Exception:
        return []
    return out


def superficies(mons):
    """Onde o bichinho pode pisar: o chão de cada monitor e o topo das janelas abertas."""
    sups = [{"id": f"m{i}", "tipo": "chao", "x1": m["x1"], "x2": m["x2"], "y": m["wbase"]}
            for i, m in enumerate(mons)]
    if not PASSEIO_OK or not mons:
        return sups
    meu = os.getpid()

    def cb(hwnd, _):
        try:
            if not _U.IsWindowVisible(hwnd) or _U.IsIconic(hwnd):
                return 1
            if _U.GetWindowLongW(hwnd, -20) & 0x80 or _U.GetWindowTextLengthW(hwnd) == 0:
                return 1                                   # janela de ferramenta ou sem título
            oculta = ctypes.c_ulong(0)
            _D.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(oculta), 4)   # DWMWA_CLOAKED
            if oculta.value:
                return 1
            pid = ctypes.c_ulong()
            _U.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == meu:
                return 1
            cls = ctypes.create_unicode_buffer(80)
            _U.GetClassNameW(hwnd, cls, 80)
            if cls.value in IGNORAR_CLASSES:
                return 1
            r = _RECT()
            if _D.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
                _U.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left < 140 or r.bottom - r.top < 70:
                return 1
            cx = (r.left + r.right) // 2
            mon = next((m for m in mons if m["x1"] <= cx < m["x2"] and m["topo"] <= r.top < m["base"]), None)
            if mon is None or r.top < mon["wtopo"] + 90:   # maximizada ou colada no topo: sem lugar
                return 1
            sups.append({"id": int(hwnd), "tipo": "janela",
                         "x1": r.left + 10, "x2": r.right - 10, "y": r.top})
        except Exception:
            pass
        return 1
    try:
        _U.EnumWindows(_ENUM_WIN(cb), None)
    except Exception:
        pass
    return sups


class Passeador:
    """Física simples do bichinho: anda, para, pula para cima, cai das bordas e acompanha janelas."""
    G = 0.9      # gravidade (px por tick ao quadrado)
    VEL = 2.4    # velocidade ao andar (px por tick)

    def __init__(self, x, y, sups):
        self.x, self.y = float(x), float(y)       # y = onde estão os pés
        self.vx = self.vy = 0.0
        self.sups = sups
        self.chao = None
        self.dir = random.choice((-1, 1))
        self.estado = "caindo"                    # andando | parado | caindo | pulando | agarrado
        self.pausa = 0

    @staticmethod
    def dist_x(x, s):
        return 0 if s["x1"] <= x <= s["x2"] else min(abs(x - s["x1"]), abs(x - s["x2"]))

    def pousar(self, s):
        self.y, self.chao = float(s["y"]), s
        self.vx = self.vy = 0.0
        self.estado = "andando"

    def soltar(self, x, y):
        self.x, self.y = float(x), float(y)
        self.chao = None
        self.vx = self.vy = 0.0
        self.estado = "caindo"

    def definir_superficies(self, sups):
        self.sups = sups
        if not self.chao:
            return
        novo = next((s for s in sups if s["id"] == self.chao["id"]), None)
        if novo is None:                            # a janela fechou ou sumiu: ele cai
            self.chao, self.estado, self.vx, self.vy = None, "caindo", 0.0, 0.0
            return
        x = self.x + (novo["x1"] - self.chao["x1"])   # acompanha a janela se ela for arrastada
        if not (novo["x1"] - 4 <= x <= novo["x2"] + 4):
            self.chao, self.estado, self.vx, self.vy = None, "caindo", 0.0, 0.0
            return
        self.x, self.y, self.chao = x, float(novo["y"]), novo

    def _pular(self, alvo):
        h = max(self.y - alvo["y"], 0)
        xt = min(max(self.x, alvo["x1"] + 16), alvo["x2"] - 16)
        vy0 = -math.sqrt(2 * self.G * (h + 36))
        t = -vy0 / self.G + math.sqrt(2 * 36 / self.G)
        self.vx = max(-12.0, min(12.0, (xt - self.x) / t))
        self.vy = vy0
        if abs(self.vx) > 0.3:
            self.dir = 1 if self.vx > 0 else -1
        self.chao, self.estado = None, "pulando"

    def pular_para_cima(self):
        meu = self.chao["id"] if self.chao else None
        alvos = [s for s in self.sups if s["id"] != meu and 8 < self.y - s["y"] <= ALT_PULO
                 and self.dist_x(self.x, s) <= 220 and s["x2"] - s["x1"] >= 80]
        if alvos:
            self._pular(random.choice(alvos))

    def _borda(self, c):
        d = self.dir
        borda = c["x2"] if d > 0 else c["x1"]
        viz = [s for s in self.sups if s["id"] != c["id"] and self.dist_x(borda + d * 10, s) <= 24]
        for s in viz:                               # monitor vizinho na mesma altura: segue andando
            if abs(s["y"] - c["y"]) <= 6 and s["x1"] - 1 <= borda + d * 2 <= s["x2"] + 1:
                self.x, self.y, self.chao = borda + d * 2, float(s["y"]), s
                return
        acima = [s for s in viz if 8 < c["y"] - s["y"] <= ALT_PULO and s["x2"] - s["x1"] >= 80]
        abaixo = [s for s in viz if s["y"] - c["y"] > 8]
        if acima and random.random() < 0.7:
            self.x = borda
            self._pular(random.choice(acima))
        elif abaixo and random.random() < 0.5:      # anda para fora da borda e cai
            self.x = borda + d * 8
            self.vx, self.vy, self.chao, self.estado = d * self.VEL * 0.6, 0.0, None, "caindo"
        else:
            self.x, self.dir = borda, -d

    def passo(self):
        e = self.estado
        if e == "agarrado":
            return
        if e == "parado":
            self.pausa -= 1
            if self.pausa <= 0:
                self.estado = "andando"
                if random.random() < 0.5:
                    self.dir = -self.dir
            return
        if e == "andando":
            c = self.chao
            if c is None:
                self.estado = "caindo"
                return
            self.x += self.dir * self.VEL
            if self.x < c["x1"] or self.x > c["x2"]:
                self._borda(c)
                return
            r = random.random()
            if r < 0.004:
                self.estado, self.pausa = "parado", random.randint(30, 130)
            elif r < 0.007:
                self.dir = -self.dir
            elif r < 0.016:
                self.pular_para_cima()
            return
        ant = self.y                                # no ar: caindo ou pulando
        self.vy = min(self.vy + self.G, 28.0)   # velocidade máxima de queda
        self.x += self.vx
        self.y += self.vy
        if not self.sups:
            return
        self.x = min(max(self.x, min(s["x1"] for s in self.sups)), max(s["x2"] for s in self.sups))
        if self.vy > 0:
            pousos = [s for s in self.sups
                      if ant - 0.5 <= s["y"] <= self.y + 0.5 and s["x1"] - 6 <= self.x <= s["x2"] + 6]
            if pousos:
                self.pousar(min(pousos, key=lambda s: s["y"]))
                return
        chaos = [s for s in self.sups if s["tipo"] == "chao"] or self.sups
        if self.y > max(s["y"] for s in self.sups) + 400:   # perdido fora da tela: volta ao chão
            s = random.choice(chaos)
            self.x = random.uniform(s["x1"] + 20, s["x2"] - 20)
            self.pousar(s)


class Pipo:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(NOME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", TRANSP)
        except tk.TclError:
            pass  # só existe no Windows; fora dele a janela fica com o fundo magenta
                  # atenuado por -alpha, que qualquer compositor entende
            if not WINDOWS:
                try:
                    self.root.attributes("-alpha", 0.92)
                except tk.TclError:
                    pass
        self.root.config(bg=TRANSP)
        est = carregar(ARQ_ESTADO, {})
        self.sons = bool(est.get("sons", SONS))
        self.observar = bool(est.get("observar", OBSERVAR))
        self.persona = est.get("persona") if est.get("persona") in PERSONAS else PERSONA_PADRAO
        self.auto = bool(est.get("auto", True))
        self.var_persona = tk.StringVar(value="auto" if self.auto else self.persona)
        self.interacoes = collections.deque(maxlen=60)
        self.ultima_interacao = time.time()
        self.ultima_troca = 0.0
        self.cuidado_ate = 0.0
        x, y = 200, 200
        if isinstance(est.get("x"), int) and isinstance(est.get("y"), int) \
                and posicao_valida(est["x"], est["y"]):
            x, y = est["x"], est["y"]
        self.root.geometry(f"{LARGURA}x{ALTURA}+{x}+{y}")
        self.cv = tk.Canvas(self.root, width=LARGURA, height=ALTURA,
                            bg=TRANSP, highlightthickness=0)
        self.cv.pack()

        self.modo = "tela"          # tela (a telinha) ou passeio (só o bichinho andando)
        self.esc = ESCALA
        self.larg, self.alt = LARGURA, ALTURA
        self.pos_widget = (x, y)
        self.walker = None
        self.mons = []
        self.cont = 0
        self.anim = 0
        self.olhar = 1
        self.andando = False
        self.ultimo_visual = None
        self.balao_j = None
        self.hover = None
        self.notas = carregar(ARQ_NOTAS, [])
        self.hist = carregar(ARQ_HIST, [])
        self.dormindo = False
        self.fase = 0
        self.piscando = False
        self.falando_ate = 0.0
        self.humor = "normal"
        self.humor_ate = 0.0
        self.moveu = False
        self.inicio = (0, 0)
        self.btn = None
        self.circ = {}
        self.chat = None
        self.fila = queue.Queue()
        self.obs = Observador()
        self.ultima_pausa = 0.0
        self.cerebro = Cerebro(DADOS, ARQ_CEREBRO)
        self.ultimo_id = None          # id da última frase mostrada (para o gostei/não gostei)
        self.ultima_pergunta = ""      # a última coisa que você disse (para o ensina:)
        self.arrasto = None

        self.desenhar_widget()
        self.desenhar_dinamico()

        self.cv.bind("<ButtonPress-1>", self.iniciar_arrasto)
        self.cv.bind("<B1-Motion>", self.arrastar)
        self.cv.bind("<ButtonRelease-1>", self.soltar)
        self.cv.bind("<Button-3>", self.menu)
        self.cv.bind("<Motion>", self.passar_mouse)
        self.cv.bind("<Leave>", lambda _e: self.destacar(None))

        self.root.after(200, self.processar_fila)
        self.root.after(500, self.tick)
        self.root.after(INTERVALO_OBS * 1000, self.ciclo_observacao)
        self.root.after(60000, self.ciclo_auto)
        self.agendar()

    def fpx(self, n):
        """Tamanho de fonte em pixels, acompanhando a escala do modo atual."""
        return max(6, round(n * self.esc))

    # ------------------------------ a telinha ------------------------------
    def desenhar_widget(self):
        c = self.cv
        c.delete("all")
        z = self.dormindo
        c.create_polygon(pontos_arredondado(2, 2, 318, 348, 30), smooth=True,
                         fill="#24212c", outline="#3a3646", width=2)
        self.tela_id = c.create_polygon(pontos_arredondado(16, 48, 304, 238, 18), smooth=True,
                                        fill="#1d2f33" if z else "#27454b", outline="")
        c.create_line(44, 202, 276, 202, fill="#35606a", width=2)
        self.circ = {}
        for i, (nome, rotulo) in enumerate(BOTOES):
            tag = "btn_" + nome
            cx, cy = 30 + i * 52, 284
            tinta = "#2a2430" if nome == "papo" else "#f6f2d2"
            self.circ[tag] = c.create_polygon(
                pontos_arredondado(cx - 22, cy - 22, cx + 22, cy + 22, 12), smooth=True,
                fill=COR_BTN[tag][0], outline="", tags=tag)
            self.icone(nome, cx, cy, tinta, tag)
            if nome == "dormir" and z:
                rotulo = "acordar"
            rot = c.create_text(cx, cy + 36, text=rotulo, fill="#d9d4e0",
                                font=(F_TEXTO, -self.fpx(12)), tags=tag)
            if nome == "dormir":
                self.rot_dormir = rot
        c.scale("all", 0, 0, self.esc, self.esc)

    def icone(self, nome, cx, cy, cor, tag):
        c = self.cv
        if nome == "papo":
            c.create_polygon(cx - 10, cy - 9, cx + 10, cy - 9, cx + 10, cy + 5, cx - 1, cy + 5,
                             cx - 7, cy + 10, cx - 7, cy + 5, cx - 10, cy + 5,
                             outline=cor, fill="", width=2, tags=tag)
        elif nome == "bilhete":
            c.create_polygon(cx - 8, cy - 10, cx + 8, cy - 10, cx + 8, cy + 3, cx + 2, cy + 10,
                             cx - 8, cy + 10, outline=cor, fill="", width=2, tags=tag)
            c.create_line(cx + 2, cy + 10, cx + 2, cy + 3, cx + 8, cy + 3, fill=cor, width=2, tags=tag)
        elif nome == "passear":
            c.create_line(cx - 10, cy, cx + 10, cy, arrow="both", arrowshape=(7, 8, 4),
                          fill=cor, width=2, tags=tag)
        elif nome == "dormir":
            self.glifo_dormir = c.create_text(
                cx, cy, text="☀" if self.dormindo else "☾", fill=cor,
                font=(F_SIMBOLO, -self.fpx(22)), tags=tag)
        elif nome == "ver":
            c.create_oval(cx - 11, cy - 7, cx + 11, cy + 7, outline=cor, width=2, tags=tag)
            c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=cor, outline="", tags=tag)
        else:  # sons
            c.create_polygon(cx - 10, cy - 3, cx - 5, cy - 3, cx, cy - 8, cx, cy + 8, cx - 5, cy + 3,
                             cx - 10, cy + 3, outline=cor, fill="", width=2, tags=tag)
            c.create_arc(cx - 3, cy - 6, cx + 7, cy + 6, start=-55, extent=110, style="arc",
                         outline=cor, width=2, tags=tag)
            self.slash = c.create_line(cx - 11, cy + 10, cx + 11, cy - 10, fill=cor, width=2,
                                       state="hidden" if self.sons else "normal", tags=tag)

    # ------------------------- humor, sprite e desenho -------------------------
    def humor_atual(self):
        if self.dormindo:
            return "dormindo"
        if time.time() < self.humor_ate:
            return self.humor
        return "sonolento" if self.em_silencio() else "normal"

    def definir_humor(self, humor, seg=3.0):
        antes = self.humor_atual()
        self.humor, self.humor_ate = humor, time.time() + seg
        if self.humor_atual() != antes:
            self.desenhar_dinamico()

    def sprite(self):
        s = [["o" if ch in "EM" else ch for ch in r] for r in SPRITE]
        h = self.humor_atual()
        falando = time.time() < self.falando_ate and self.fase == 1
        fechado = h in ("dormindo", "sonolento") or (self.piscando and h in ("normal", "triste"))
        olhos = OLHOS["fechado"] if fechado else OLHOS.get(h, OLHOS["normal"])
        boca = (BOCAS["falando"] if falando and h in ("normal", "feliz", "triste")
                else BOCAS.get(h, BOCAS["normal"]))
        desl = self.olhar if self.modo == "passeio" else 0   # olha para onde está andando
        for r, c in olhos:
            s[r][min(max(c + desl, 2), 13)] = "E"
        for r, c in boca:
            s[r][c] = "M"
        if h == "feliz":
            s[7][3] = s[7][12] = "b"
        elif h == "triste":
            s[7][4] = s[7][11] = "t"
        if self.modo == "passeio" and self.andando and self.anim:   # passinho: pés alternados
            s[13], s[14] = list("...#oo#..#oo#..."), list("...####..####...")
        return s

    def desenhar_pet(self, x0, y0, p):
        cores = {"o": PERSONAS[self.persona]["cor_sono" if self.dormindo else "cor"],
                 "b": "#f19db0", "t": "#5fb4e0", "k": "#1b1b1b"}
        for r, linha in enumerate(self.sprite()):
            for ini, fim, cl in trechos(linha):
                self.cv.create_rectangle(x0 + ini * p, y0 + r * p, x0 + fim * p, y0 + (r + 1) * p,
                                         fill=cores[cl], outline="", tags="din")

    def desenhar_dinamico(self):
        c = self.cv
        c.delete("din")
        h = self.humor_atual()
        tinta = "#ffffff"
        if self.modo == "tela":
            c.create_text(22, 26, text=datetime.now().strftime("%H:%M"), anchor="w", fill="#ffffff",
                          font=(F_TEXTO, -self.fpx(15), "bold"), tags="din")
            if self.dormindo:
                txt, cor = "pausado", "#9aa0b4"
            elif self.observar:
                txt, cor = "observando", "#7bd88f"
            else:
                txt, cor = "não observa", "#d9d4e0"
            c.create_oval(206, 20, 214, 28, fill=cor, outline="", tags="din")
            c.create_text(220, 24, text=txt, anchor="w", fill="#d9d4e0",
                          font=(F_TEXTO, -self.fpx(13)), tags="din")
            if self.notas:
                c.create_text(120, 24, text=f"✎ {len(self.notas)}", anchor="w", fill="#d9d4e0",
                              font=(F_SIMBOLO, -self.fpx(13)), tags="din")
            c.create_text(22, 224, text=self.cerebro.resumo_curto(), anchor="w",
                          fill="#8fb4b9", font=(F_TEXTO, -self.fpx(12)), tags="din")
            c.create_text(298, 224, text=PERSONAS[self.persona]["nome"].lower() + (" · auto" if self.auto else ""), anchor="e",
                          fill="#8fb4b9", font=(F_TEXTO, -self.fpx(12)), tags="din")
            pulo = 4 if (self.fase and not self.dormindo) else 0
            self.desenhar_pet(112, 110 - pulo, 6)
            ox, oy, fs = 218, 126, 20
        else:
            pulo = 2 if (self.andando and self.anim) else 0
            self.desenhar_pet(24, 16 - pulo, 4)
            ox, oy, fs = 100, 30, 12
            tinta = "#ffffff"
            if h in ("dormindo", "sonolento", "feliz", "surpreso"):   # fundo para o símbolo aparecer em qualquer papel de parede
                c.create_oval(ox - 13, 12, ox + 13, 38, fill="#24212c", outline="", tags="din")
        if self.modo == "tela":
            xz, yz, ys, yf, yx = ox + 6 * self.fase, oy - 8 - 6 * self.fase, oy - 4 * self.fase, oy - 4 * self.fase, oy
        else:
            xz, yz = ox, 26 - 2 * self.fase
            ys = yf = yx = yz
        if h == "dormindo":
            c.create_text(xz, yz, text="Z" if self.fase else "z", fill=tinta, tags="din",
                          font=(F_MONO, -self.fpx(fs), "bold"))
        elif h == "sonolento":
            c.create_text(ox, ys, text="z", fill=tinta, tags="din",
                          font=(F_MONO, -self.fpx(fs), "bold"))
        elif h == "feliz":
            c.create_text(ox, yf, text="♥", fill="#ff6b81", tags="din",
                          font=(F_SIMBOLO, -self.fpx(fs), "bold"))
        elif h == "surpreso":
            c.create_text(ox, yx, text="!", fill=tinta, tags="din",
                          font=(F_MONO, -self.fpx(fs + 2), "bold"))
        c.scale("din", 0, 0, self.esc, self.esc)

    def tick(self):
        self.fase ^= 1
        self.piscando = (not self.dormindo) and random.random() < 0.1
        self.desenhar_dinamico()
        self.seguir_balao()
        self.root.after(500, self.tick)

    def tocar(self, nome):
        if not self.sons:
            return
        if winsound:
            melodias = MELODIAS[nome]

            def run():
                for freq, ms in melodias:
                    try:
                        winsound.Beep(freq, ms)
                    except Exception:
                        return
            threading.Thread(target=run, daemon=True).start()
        else:
            self._tocar_linux(nome)

    def _tocar_linux(self, nome):
        """Bipes no Linux/macOS: beep do sistema se houver player, senão silêncio."""
        tocador = shutil.which("paplay") or shutil.which("aplay") or shutil.which("pw-play")
        if not tocador:
            return
        try:  # bipe curto pelo beep do sistema; some se o som do PC estiver mudo
            subprocess.run(["beep", "-f", "880", "-l", "60"], capture_output=True, timeout=1) \
                if shutil.which("beep") else self._bipe_wav(tocador, MELODIAS[nome])
        except Exception:
            pass

    @staticmethod
    def _bipe_wav(tocador, melodias):
        """Gera um WAV de bipes em memória (biblioteca padrão) e toca no player do sistema."""
        import math as _m
        import struct
        import tempfile
        taxa = 22050
        amostras = bytearray()
        for freq, ms in melodias:
            n = int(taxa * ms / 1000)
            for i in range(n):
                valor = int(12000 * _m.sin(2 * _m.pi * freq * i / taxa))
                amostras += struct.pack("<h", valor)
        cab = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(amostras), b"WAVE",
                          b"fmt ", 16, 1, 1, taxa, taxa * 2, 2, 16, b"data", len(amostras))
        caminho = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as arq:
                arq.write(cab + bytes(amostras))
                caminho = arq.name
            subprocess.Popen([tocador, caminho], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL).communicate(timeout=5)
        except Exception:
            pass
        finally:
            if caminho:
                try:
                    os.unlink(caminho)
                except OSError:
                    pass

    def ciclo_observacao(self):
        if self.observar and not self.dormindo:
            self.obs.amostrar(janela_ativa(), segundos_ocioso(), INTERVALO_OBS)
            self.checar_pausa()
        else:
            self.obs.parar("parado")
        self.root.after(INTERVALO_OBS * 1000, self.ciclo_observacao)

    def checar_pausa(self):
        o = self.obs
        if o.estado != "ativo" or self.em_silencio():
            return
        agora = time.time()
        if o.seguidos() >= PAUSA_APOS_MIN * 60 and agora - self.ultima_pausa >= PAUSA_APOS_MIN * 60:
            self.ultima_pausa = agora
            self.falar(tipo="pausa")

    def alternar_observacao(self):
        self.observar = not self.observar
        if not self.observar:
            self.obs.parar("parado")
            self.obs.salvar()
        self.salvar_estado()
        self.desenhar_dinamico()
        self.tocar("clique")

    def ver_atividade(self):
        j = tk.Toplevel(self.root)
        j.title("Atividade no PC")
        j.attributes("-topmost", True)
        j.geometry("430x470")
        caixa = tk.Text(j, wrap="word", font=(F_MONO, 10), bg="#f7f9fc")
        caixa.pack(fill="both", expand=True, padx=6, pady=6)
        botao = tk.Button(j, text="Apagar todo o histórico")
        botao.pack(pady=(0, 6))
        confirma = {"sim": False}

        def atualizar():
            caixa.config(state="normal")
            caixa.delete("1.0", "end")
            caixa.insert("1.0", self.obs.relatorio())
            caixa.config(state="disabled")

        def apagar():
            if not confirma["sim"]:
                confirma["sim"] = True
                botao.config(text="Clique de novo para confirmar")
                return
            confirma["sim"] = False
            self.obs.apagar()
            botao.config(text="Apagar todo o histórico")
            atualizar()
        botao.config(command=apagar)
        atualizar()

    def alternar_sons(self):
        self.sons = not self.sons
        if self.modo == "tela":
            self.cv.itemconfig(self.slash, state="hidden" if self.sons else "normal")
        self.salvar_estado()
        self.tocar("clique")

    def salvar_estado(self):
        try:
            self.root.update_idletasks()
            px, py = self.pos_widget if self.modo == "passeio" else (self.root.winfo_x(), self.root.winfo_y())
            salvar(ARQ_ESTADO, {"x": px, "y": py,
                                "sons": self.sons, "observar": self.observar,
                                "persona": self.persona, "auto": self.auto})
        except Exception:
            pass

    def animar_fala(self, segundos):
        if not self.dormindo:
            self.falando_ate = time.time() + segundos

    # ------------------------ mouse: arrastar e botões ------------------------
    def _alvo(self):
        ids = self.cv.find_withtag("current")
        if not ids:
            return None
        for t in self.cv.gettags(ids[0]):
            if t.startswith("btn_"):
                return t
        return None

    def destacar(self, alvo):
        if self.modo != "tela" or alvo == self.hover:
            return
        if self.hover in self.circ:
            self.cv.itemconfig(self.circ[self.hover], fill=COR_BTN[self.hover][0])
        self.hover = alvo
        if alvo in self.circ:
            self.cv.itemconfig(self.circ[alvo], fill=COR_BTN[alvo][1])
        self.cv.config(cursor="hand2" if alvo else "")

    def passar_mouse(self, _e):
        if not (self.arrasto or self.btn):
            self.destacar(self._alvo())

    def iniciar_arrasto(self, e):
        self.btn = self._alvo() if self.modo == "tela" else None
        if self.btn:
            self.cv.itemconfig(self.circ[self.btn], fill=COR_BTN[self.btn][2])
            if self.btn != "btn_dormir":
                self.tocar("clique")
            return
        self.moveu = False
        self.inicio = (e.x_root, e.y_root)
        self.arrasto = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        if self.modo == "passeio" and self.walker:
            self.walker.estado = "agarrado"

    def arrastar(self, e):
        if self.btn or not self.arrasto:
            return
        if abs(e.x_root - self.inicio[0]) + abs(e.y_root - self.inicio[1]) > 4:
            self.moveu = True
        if self.moveu:
            self.definir_humor("surpreso", 0.8)
        x = e.x_root - self.arrasto[0]
        y = e.y_root - self.arrasto[1]
        # "+-100" é válido no Tk e permite monitores à esquerda/acima do principal
        self.root.geometry(f"+{x}+{y}")

    def soltar(self, _e):
        if self.btn:
            nome, self.btn = self.btn, None
            self.cv.itemconfig(self.circ[nome], fill=COR_BTN[nome][1 if self._alvo() == nome else 0])
            if self._alvo() == nome:
                self.acionar(nome)
            return
        if self.arrasto:
            self.arrasto = None
            if self.modo == "passeio":
                if self.moveu and self.walker:   # largou o bichinho: ele cai de onde foi solto
                    self.walker.soltar(self.root.winfo_x() + self.larg / 2,
                                       self.root.winfo_y() + PE_Y * self.esc)
                else:                            # clique: volta para a telinha
                    self.sair_passeio()
            elif self.moveu:
                self.salvar_estado()
            else:  # clique rápido na telinha = carinho
                self.definir_humor("feliz", 2.5)
                self.tocar("carinho")
                self.registrar_interacao()

    def acionar(self, nome):
        self.registrar_interacao()
        if nome == "btn_papo":
            if self.dormindo:
                self.alternar_sono(falar=False)
            self.abrir_chat()
        elif nome == "btn_bilhete":
            self.nota_manual()
        elif nome == "btn_passear":
            self.sair_passeio() if self.modo == "passeio" else self.entrar_passeio()
        elif nome == "btn_dormir":
            self.alternar_sono()
        elif nome == "btn_ver":
            self.ver_atividade()
        elif nome == "btn_sons":
            self.alternar_sons()

    def alternar_sono(self, falar=True):
        self.dormindo = not self.dormindo
        self.piscando = False
        self.falando_ate = 0.0
        self.humor_ate = 0.0
        self.tocar("dormir" if self.dormindo else "acordar")
        if self.modo == "tela":
            self.cv.itemconfig(self.glifo_dormir, text="☀" if self.dormindo else "☾")
            self.cv.itemconfig(self.rot_dormir, text="acordar" if self.dormindo else "dormir")
            self.cv.itemconfig(self.tela_id, fill="#1d2f33" if self.dormindo else "#27454b")
        self.desenhar_dinamico()
        if not self.dormindo:
            self.definir_humor("feliz", 3)
        if falar:
            self.balao("Zzz... boa noite! Me chama quando quiser."
                       if self.dormindo else "Bom dia! Voltei!", som=False)
            self.animar_fala(2)

    # ---------------------- passeio: sair da telinha e andar ----------------------
    def chao_tk(self):
        """Plano B (fora do Windows): um chão só, na base da tela."""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.mons = [{"x1": 0, "x2": sw, "topo": 0, "base": sh, "wtopo": 0, "wbase": sh - 48}]
        return [{"id": "tk", "tipo": "chao", "x1": 0, "x2": sw, "y": sh - 48}]

    def pegar_superficies(self):
        self.mons = monitores()
        return superficies(self.mons) if self.mons else self.chao_tk()

    def entrar_passeio(self):
        if self.modo == "passeio":
            return
        self.root.update_idletasks()
        self.pos_widget = (self.root.winfo_x(), self.root.winfo_y())
        if self.dormindo:
            self.alternar_sono(falar=False)
        sups = self.pegar_superficies()
        self.modo, self.esc = "passeio", ESCALA_PASSEIO
        self.larg, self.alt = int(PW0 * self.esc), int(PH0 * self.esc)
        self.hover = self.btn = None
        self.cv.config(cursor="")
        self.cv.delete("all")
        self.cv.config(width=self.larg, height=self.alt)
        px = self.pos_widget[0] + LARGURA / 2
        py = self.pos_widget[1] + ALTURA * 0.6
        self.walker = Passeador(px, py, sups)
        self.root.geometry(f"{self.larg}x{self.alt}+{int(px - self.larg / 2)}+{int(py - PE_Y * self.esc)}")
        self.cont, self.ultimo_visual, self.andando = 0, None, False
        self.definir_humor("feliz", 2)
        self.tocar("acordar")
        self.desenhar_dinamico()
        self.root.after(30, self.loop_passeio)

    def sair_passeio(self):
        if self.modo != "passeio":
            return
        w = self.walker
        mon = next((m for m in self.mons if m["x1"] <= w.x < m["x2"]), None)
        x, y = int(w.x - LARGURA / 2), int(w.y - ALTURA + 24)
        if mon:   # a telinha reaparece onde ele estava, mas sempre dentro do monitor
            x = max(mon["x1"] + 10, min(x, mon["x2"] - LARGURA - 10))
            y = max(mon["wtopo"] + 10, min(y, mon["wbase"] - ALTURA - 10))
        self.modo, self.esc, self.walker = "tela", ESCALA, None
        self.larg, self.alt, self.andando, self.olhar = LARGURA, ALTURA, False, 1
        self.cv.config(width=LARGURA, height=ALTURA)
        self.root.geometry(f"{LARGURA}x{ALTURA}+{x}+{y}")
        self.pos_widget = (x, y)
        self.desenhar_widget()
        self.desenhar_dinamico()
        self.definir_humor("feliz", 2.5)
        self.tocar("carinho")
        self.salvar_estado()

    def loop_passeio(self):
        if self.modo != "passeio" or self.walker is None:
            return
        w = self.walker
        self.cont += 1
        if self.cont % 16 == 0:     # a cada ~0,5 s confere onde estão as janelas
            w.definir_superficies(self.pegar_superficies())
        if w.estado != "agarrado":
            if not (self.dormindo and w.estado in ("andando", "parado")):
                w.passo()
            self.root.geometry(f"+{int(w.x - self.larg / 2)}+{int(w.y - PE_Y * self.esc)}")
        if self.cont % 6 == 0:
            self.anim ^= 1
        self.andando = w.estado == "andando" and not self.dormindo
        visual = (self.anim if self.andando else 0, w.dir, w.estado)
        if visual != self.ultimo_visual:
            self.ultimo_visual, self.olhar = visual, w.dir
            self.desenhar_dinamico()
        self.seguir_balao()
        self.root.after(30, self.loop_passeio)

    def seguir_balao(self):
        j = self.balao_j
        if j is None:
            return
        try:
            if j.winfo_exists():
                self.posicionar(j, self.larg // 2 - 115, 0, acima=True)
            else:
                self.balao_j = None
        except tk.TclError:
            self.balao_j = None

    # ----------------------- janelinhas auxiliares -----------------------
    def posicionar(self, janela, dx, dy, acima=False):
        janela.update_idletasks()
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        if acima:
            y -= janela.winfo_height() + 6
        janela.geometry(f"+{x}+{y}")

    def balao(self, texto, som=True, fb=None, remix=False):
        if som:
            self.tocar("msg")
        j = tk.Toplevel(self.root)
        j.overrideredirect(True)
        j.attributes("-topmost", True)
        lab = tk.Label(j, text=texto, wraplength=230, justify="left", bg="#ffffff",
                       fg="#222", font=(F_TEXTO, 10), padx=10, pady=8, relief="solid", bd=1)
        lab.pack()
        if fb:
            barra = tk.Frame(j, bg="#ffffff", highlightbackground="#999", highlightthickness=1)
            barra.pack(fill="x")
            if remix:
                tk.Label(barra, text="frase nova", bg="#ffffff", fg="#888", font=(F_TEXTO, 8)).pack(side="left", padx=6)
            for rotulo, ok in (("não gostei", False), ("gostei", True)):
                tk.Button(barra, text=rotulo, bd=0, bg="#ffffff", fg="#444", font=(F_TEXTO, 8),
                          command=lambda ok=ok: (self.dar_feedback(ok, fb), j.destroy())).pack(side="right", padx=4)
        self.balao_j = j
        self.posicionar(j, self.larg // 2 - 115, 0, acima=True)
        lab.bind("<Button-1>", lambda _e: j.destroy())
        j.after(20000 if fb else 12000, lambda: j.winfo_exists() and j.destroy())

    def postit(self, texto, fb=None):
        self.tocar("bilhete")
        j = tk.Toplevel(self.root)
        j.overrideredirect(True)
        j.attributes("-topmost", True)
        cima = tk.Frame(j, bg="#f9e66b")
        cima.pack(fill="x")
        tk.Button(cima, text="×", bd=0, bg="#f9e66b", command=j.destroy).pack(side="right")
        if fb:
            for rotulo, ok in (("não gostei", False), ("gostei", True)):
                tk.Button(cima, text=rotulo, bd=0, bg="#f9e66b", fg="#554", font=(F_TEXTO, 8),
                          command=lambda ok=ok: (self.dar_feedback(ok, fb), j.destroy())).pack(side="left", padx=3)
        tk.Label(j, text=texto, wraplength=200, justify="left", bg="#fff59d",
                 fg="#333", font=(F_CANETA, 10), padx=10, pady=8).pack()
        self.posicionar(j, self.larg + 8, random.randint(-60, 40))

    # ----------------------------- notas -----------------------------
    def nova_nota(self, texto):
        self.registrar_interacao()
        self.notas.append({"texto": texto, "quando": datetime.now().strftime("%d/%m %H:%M")})
        salvar(ARQ_NOTAS, self.notas)
        self.definir_humor("feliz", 3)
        self.postit(texto)

    def nota_manual(self):
        j = tk.Toplevel(self.root)
        j.title("Novo bilhete")
        j.attributes("-topmost", True)
        j.geometry("320x120")
        tk.Label(j, text="O que eu anoto no bilhete?").pack(pady=(10, 4))
        e = tk.Entry(j, font=(F_TEXTO, 11))
        e.pack(fill="x", padx=12)

        def ok(_e=None):
            t = e.get().strip()
            j.destroy()
            if t:
                self.nova_nota(t)
        e.bind("<Return>", ok)
        tk.Button(j, text="Anotar", command=ok).pack(pady=8)
        j.update_idletasks()
        j.lift()
        j.focus_force()
        e.focus_force()

    def ver_notas(self):
        j = tk.Toplevel(self.root)
        j.title("Bilhetes")
        j.attributes("-topmost", True)
        j.geometry("360x300")
        lb = tk.Listbox(j, font=(F_TEXTO, 10))
        lb.pack(fill="both", expand=True, padx=6, pady=6)
        for n in self.notas:
            lb.insert("end", f"[{n['quando']}] {n['texto']}")

        def apagar():
            sel = lb.curselection()
            if sel:
                self.notas.pop(sel[0])
                salvar(ARQ_NOTAS, self.notas)
                lb.delete(sel[0])
        tk.Button(j, text="Apagar selecionado", command=apagar).pack(pady=(0, 6))

    # ------------------------------ chat ------------------------------
    def abrir_chat(self):
        if self.chat and self.chat.winfo_exists():
            self.chat.lift()
            self.chat.focus_force()
            self.entrada.focus_force()
            return
        j = self.chat = tk.Toplevel(self.root)
        j.title(f"Conversa com {NOME}")
        j.attributes("-topmost", True)
        j.geometry("360x420")
        # o campo de digitar entra primeiro, fixo embaixo, para nunca ser empurrado para fora
        self.entrada = tk.Entry(j, font=(F_TEXTO, 11), relief="solid", bd=1)
        self.entrada.pack(side="bottom", fill="x", padx=6, pady=6, ipady=4)
        barra = tk.Frame(j)
        barra.pack(side="bottom", fill="x", padx=6)
        tk.Button(barra, text="gostei", command=lambda: self.dar_feedback(True)).pack(side="left")
        tk.Button(barra, text="não gostei", command=lambda: self.dar_feedback(False)).pack(side="left", padx=6)
        tk.Label(barra, text="anota:  ensina:  /ajuda", fg="#777", font=(F_TEXTO, 8)).pack(side="right")
        self.texto = tk.Text(j, wrap="word", state="disabled", bg="#f7f9fc",
                             font=(F_TEXTO, 10), width=10, height=5)
        self.texto.pack(side="top", fill="both", expand=True, padx=6, pady=(6, 0))
        self.entrada.bind("<Return>", self.enviar)
        self.entrada.bind("<Button-1>", lambda _e: self.entrada.focus_force())
        j.update_idletasks()
        j.lift()
        j.focus_force()
        self.entrada.focus_force()
        for papel, t in self.hist[-6:]:
            self.escrever("Você" if papel == "user" else NOME, t)

    def escrever(self, quem, t):
        if not (self.chat and self.chat.winfo_exists()):
            return
        self.texto.config(state="normal")
        self.texto.insert("end", f"{quem}: {t}\n\n")
        self.texto.config(state="disabled")
        self.texto.see("end")

    # ------------------------ falas espontâneas ------------------------
    def em_silencio(self):
        h = datetime.now().hour
        ini, fim = SILENCIO
        return h >= ini or h < fim

    def agendar(self):
        ms = random.randint(INTERVALO_MIN, INTERVALO_MAX) * 60 * 1000
        self.root.after(ms, self.espontanea)

    def espontanea(self):
        self.agendar()
        if not self.dormindo and not self.em_silencio():
            self.falar()

    def falar_agora(self):
        if self.dormindo:
            self.alternar_sono(falar=False)
        self.falar()

    # ---------------------- conversa, falas e aprendizado (cérebro ML) ----------------------
    def ctx_cerebro(self):
        """O que o Pipo sabe agora (hora, programa em uso, resumo do dia) para preencher as frases."""
        o = self.obs
        ctx = {"agora": datetime.now(), "notas": len(self.notas)}
        if self.observar and not self.dormindo and o.estado == "ativo" and o.app:
            ctx["app"], ctx["tempo_app"] = o.app, fmt(o.seguidos())
            prox = o.proximos(o.app, 1)
            if prox:
                ctx["proximo"] = prox[0][0]
        hoje = o.hoje()[:3]
        if self.observar and hoje:
            ctx["resumo_hoje"] = ", ".join(f"{a} {fmt(s)}" for a, s in hoje)
        return ctx

    def enviar(self, _e=None):
        t = self.entrada.get().strip()
        if not t:
            return
        self.entrada.delete(0, "end")
        self.escrever("Você", t)
        self.registrar_interacao()
        partes = t.split(None, 1)
        cmd = partes[0].lower().rstrip(":;") if partes else ""
        corpo = partes[1].lstrip(":;- ") if len(partes) > 1 else ""
        if cmd.startswith("anota"):
            if corpo:
                self.nova_nota(corpo)
                self.escrever(NOME, "Anotado! 📝")
            else:
                self.escrever(NOME, "O que eu anoto? Escreva: anota: <texto>")
            return
        if cmd in ("ensina", "ensinar"):
            if corpo and self.ultima_pergunta:
                if self.cerebro.ensinar(self.ultima_pergunta, corpo):
                    self.escrever(NOME, f'Aprendi! Quando disserem algo como "{self.ultima_pergunta}", eu respondo: {corpo}')
                    self.definir_humor("feliz", 3)
                    self.tocar("carinho")
                else:
                    self.escrever(NOME, "Não consegui gravar o que você ensinou.")
            else:
                self.escrever(NOME, "Primeiro diga algo que eu não saiba responder, depois escreva: ensina: <o que eu devia dizer>")
            return
        if cmd == "/ajuda":
            self.escrever(NOME, AJUDA)
            return
        norm = simplificar(t).strip(" .!?")
        if norm in ("gostei", "curti", "gostei dessa"):
            self.dar_feedback(True)
            return
        if norm in ("nao gostei", "nao curti", "ruim", "nao gostei dessa"):
            self.dar_feedback(False)
            return
        self.ultima_pergunta = t
        self.responder(t, self.cerebro.responder(t, self.persona, self.ctx_cerebro()))

    def responder(self, pergunta, r):
        self.hist = (self.hist + [["user", pergunta], ["model", r["texto"]]])[-20:]
        salvar(ARQ_HIST, self.hist)
        self.escrever(NOME, r["texto"])
        self.ultimo_id = r["id"]
        if r["humor"] != "normal":
            self.definir_humor(r["humor"], 5)
        acao = r.get("acao")
        if acao and acao["tipo"] == "lembrete":
            self.agendar_lembrete(acao["segundos"], acao["texto"])
        if r["origem"] != "seguranca":
            self.tocar("msg")
        self.animar_fala(min(6, 1 + len(r["texto"]) / 25))
        if r["intencao"] in ("tristeza", "estresse", "crise"):
            self.cuidado_ate = time.time() + 2 * 3600      # por 2 horas, nada de implicância
            self.avaliar_auto()

    def agendar_lembrete(self, segundos, texto):
        self.root.after(int(segundos * 1000), lambda: self.avisar_lembrete(texto))

    def avisar_lembrete(self, texto):
        self.definir_humor("surpreso", 4)
        self.postit(f"Lembrete: {texto}")

    def dar_feedback(self, positivo, rid=None):
        rid = rid or self.ultimo_id
        if not rid:
            return
        self.cerebro.feedback(rid, positivo)
        self.registrar_interacao()
        if self.auto:      # aprende qual personalidade você curte em cada situação
            self.cerebro.auto_feedback(self.contexto_auto()["chave"], self.persona, positivo)
        if rid == self.ultimo_id:
            self.ultimo_id = None
        self.definir_humor("feliz" if positivo else "triste", 2.5)
        self.tocar("carinho" if positivo else "triste")
        self.escrever(NOME, "Valeu! Vou falar mais assim." if positivo else "Anotado. Vou falar menos assim.")

    def falar(self, tipo=None):
        """Fala espontânea: o cérebro escolhe uma frase (curada ou inventada) e o Pipo mostra."""
        tipo = tipo or ("bilhete" if random.random() < CHANCE_BILHETE else "fala")
        f = self.cerebro.fala(self.persona, tipo, self.ctx_cerebro())
        if not f:   # a pasta dados está vazia para essa personalidade: usa as frases de reserva
            f = {"texto": random.choice(PERSONAS[self.persona]["pausa" if tipo == "pausa" else "prontas"]),
                 "id": None, "origem": "reserva"}
        self.ultimo_id = f["id"]
        if tipo == "bilhete":
            self.postit(f["texto"], fb=f["id"])
        else:
            self.balao(f["texto"], fb=f["id"], remix=f["origem"] == "remix")
        self.animar_fala(min(6, 1 + len(f["texto"]) / 25))

    def recarregar_dados(self):
        self.cerebro.treinar()
        self.balao(f"Dados recarregados: {self.cerebro.resumo_curto()}.", som=False)

    def ver_aprendizado(self):
        j = tk.Toplevel(self.root)
        j.title("O que o Pipo aprendeu")
        j.attributes("-topmost", True)
        j.geometry("520x470")
        caixa = tk.Text(j, wrap="word", font=(F_MONO, 10), bg="#f7f9fc")
        caixa.pack(fill="both", expand=True, padx=6, pady=6)
        barra = tk.Frame(j)
        barra.pack(pady=(0, 6))
        confirma = {"sim": False}

        def atualizar():
            caixa.config(state="normal")
            caixa.delete("1.0", "end")
            caixa.insert("1.0", self.cerebro.estatisticas())
            caixa.config(state="disabled")

        def recarregar():
            self.cerebro.treinar()
            atualizar()

        def abrir_pasta_local():
            abrir_pasta(DADOS)

        def esquecer():
            if not confirma["sim"]:
                confirma["sim"] = True
                b_esq.config(text="Clique de novo para confirmar")
                return
            confirma["sim"] = False
            self.cerebro.esquecer()
            b_esq.config(text="Esquecer o que aprendi com você")
            atualizar()
        tk.Button(barra, text="Recarregar dados", command=recarregar).pack(side="left", padx=4)
        tk.Button(barra, text="Abrir pasta de dados", command=abrir_pasta_local).pack(side="left", padx=4)
        b_esq = tk.Button(barra, text="Esquecer o que aprendi com você", command=esquecer)
        b_esq.pack(side="left", padx=4)
        atualizar()

    # ---------------- personalidade automática (muda conforme as interações) ----------------
    def registrar_interacao(self):
        t = time.time()
        self.interacoes.append(t)
        self.ultima_interacao = t

    def contexto_auto(self):
        agora = time.time()
        periodo = self.cerebro.periodo(datetime.now())
        recentes = sum(1 for t in self.interacoes if agora - t < 1800)
        sem = agora - self.ultima_interacao
        nivel = "alta" if recentes >= 6 else "media" if recentes >= 1 or sem <= 3600 else "ausente"
        foco = self.obs.seguidos() / 60 if self.observar and not self.dormindo else 0
        return {"periodo": periodo, "nivel": nivel, "foco": foco, "chave": f"{periodo}|{nivel}"}

    def avaliar_auto(self, forcar=False):
        """Escolhe a personalidade da vez: regras simples + o que você já aprovou em cada situação."""
        if not self.auto or self.dormindo:
            return
        agora = time.time()
        cuidado = agora < self.cuidado_ate      # você disse que estava mal: nada de implicância
        if not forcar and not cuidado:
            if agora - self.ultima_troca < AUTO_MIN_MINUTOS * 60:
                return
            if self.chat and self.chat.winfo_exists() and agora - self.ultima_interacao < 120:
                return                           # não muda de humor no meio de uma conversa
        ctx = self.contexto_auto()
        pontos = {}
        for per in PERSONAS:
            if cuidado and per in ("revoltado", "sarcastico"):
                continue
            ponto = REGRAS_AUTO["periodo"].get(ctx["periodo"], {}).get(per, 0) + \
                REGRAS_AUTO["nivel"].get(ctx["nivel"], {}).get(per, 0)
            if ctx["foco"] >= 60:
                ponto += REGRAS_AUTO["foco"].get(per, 0)
            pontos[per] = ponto + 1.5 * self.cerebro.auto_nota(ctx["chave"], per)
        nova = max(pontos, key=pontos.get)
        atual = pontos.get(self.persona)
        if nova != self.persona and (forcar or atual is None or pontos[nova] - atual > 0.5):
            self.mudar_persona_auto(nova)

    def mudar_persona_auto(self, nova):
        self.persona = nova
        self.ultima_troca = time.time()
        self.salvar_estado()
        self.definir_humor("surpreso", 3)
        self.desenhar_dinamico()
        texto = f"({PERSONAS[nova]['nome']}) {PERSONAS[nova]['saudacao']}"
        self.balao(texto, som=False)
        self.animar_fala(3)
        self.escrever(NOME, texto)

    def ciclo_auto(self):
        self.avaliar_auto()
        self.root.after(60000, self.ciclo_auto)

    def trocar_persona(self, chave):
        if chave == "auto":
            self.auto = True
            self.var_persona.set("auto")
            self.salvar_estado()
            self.balao("Modo automático: eu mudo de humor sozinho, conforme a nossa convivência.", som=False)
            self.avaliar_auto(forcar=True)
            return
        if chave not in PERSONAS:
            return
        self.auto = False
        self.persona = chave
        self.var_persona.set(chave)
        self.salvar_estado()
        if self.dormindo:
            self.alternar_sono(falar=False)
        self.definir_humor("feliz", 3)
        self.desenhar_dinamico()
        saudacao = PERSONAS[chave]["saudacao"]
        self.balao(saudacao)
        self.animar_fala(3)
        self.escrever(NOME, saudacao)

    # ------------------------------ menu ------------------------------
    def menu(self, e):
        m = self.montar_menu()
        m.tk_popup(e.x_root, e.y_root)

    def montar_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Conversar", command=lambda: self.acionar("btn_papo"))
        m.add_command(label="Novo bilhete", command=self.nota_manual)
        m.add_command(label="Ver bilhetes", command=self.ver_notas)
        m.add_command(label="Falar agora", command=self.falar_agora)
        sub = tk.Menu(m, tearoff=0)
        sub.add_radiobutton(label="Automática — muda sozinho conforme as interações", variable=self.var_persona,
                            value="auto", command=lambda: self.trocar_persona("auto"))
        sub.add_separator()
        for chave, pers in PERSONAS.items():
            sub.add_radiobutton(label=f"{pers['nome']} — {pers['resumo']}", variable=self.var_persona,
                                value=chave, command=lambda c=chave: self.trocar_persona(c))
        m.add_cascade(label="Personalidade", menu=sub)
        m.add_command(label="Voltar à telinha" if self.modo == "passeio" else "Passear",
                      command=lambda: self.acionar("btn_passear"))
        m.add_command(label="Acordar" if self.dormindo else "Dormir",
                      command=self.alternar_sono)
        m.add_command(label="Desligar sons" if self.sons else "Ligar sons",
                      command=self.alternar_sons)
        m.add_separator()
        m.add_command(label="Parar de observar o PC" if self.observar else "Observar o PC",
                      command=self.alternar_observacao)
        m.add_command(label="Ver atividade", command=self.ver_atividade)
        m.add_command(label="O que o Pipo aprendeu", command=self.ver_aprendizado)
        m.add_command(label="Recarregar dados", command=self.recarregar_dados)
        m.add_separator()
        m.add_command(label="Sair", command=self.sair)
        return m

    def sair(self):
        self.cerebro.salvar()
        self.salvar_estado()
        self.obs.salvar()
        salvar(ARQ_HIST, self.hist[-20:])
        salvar(ARQ_NOTAS, self.notas)
        self.root.destroy()

    def processar_fila(self):
        while not self.fila.empty():
            try:
                self.fila.get_nowait()()
            except Exception:
                pass
        self.root.after(200, self.processar_fila)

    def rodar(self):
        self.root.mainloop()


if __name__ == "__main__":
    Pipo().rodar()
