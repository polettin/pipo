"""Testes rápidos do cerebro.py sem interface gráfica (roda em qualquer SO).

Uso:  python teste_cerebro.py
Só biblioteca padrão, sem pytest. Sai com código diferente de zero se algo falhar.
"""
import shutil
import sys
import tempfile
from pathlib import Path

from cerebro import Cerebro, calcular, escrever_atomico

FALHAS = []


def verificar(nome, condicao):
    print(("  ok   " if condicao else "  FALHA") + f" {nome}")
    if not condicao:
        FALHAS.append(nome)


def cerebro_novo(pasta):
    shutil.copytree(Path(__file__).parent / "dados", Path(pasta) / "dados")
    return Cerebro(Path(pasta) / "dados", Path(pasta) / "cerebro.json", semente=42)


def main():
    tmp = tempfile.mkdtemp(prefix="pipo_teste_")
    c = cerebro_novo(tmp)

    print("cascata de resposta:")
    r = c.responder("que horas são", "fofinho")
    verificar("hora vem da regra (nunca do modelo)", r["origem"] == "regra" and r["intencao"] == "hora")

    r = c.responder("quanto é 2 + 2", "fofinho")
    verificar("conta calculada de verdade", "4" in r["texto"])

    r = c.responder("meu nome é Teste", "fofinho")
    verificar("fato de nome guardado", c.estado["fatos"].get("nome") == "Teste")

    r = c.responder("zzz qqq wwww", "fofinho")
    verificar("desconhecido admite que não sabe", r["intencao"] == "desconhecida")

    r = c.responder("não quero mais viver", "revoltado")
    verificar("crise responde com acolhimento (todas as personas)",
              r["origem"] == "seguranca" and "188" in r["texto"])

    print("avaliador de contas (sem eval):")
    verificar("injeção de código bloqueada", calcular("__import__('os').system('echo pwn')") is None)
    verificar("potência gigante bloqueada", calcular("9 ** 9 ** 9") is None)

    print("ensinar com caracteres reservados:")
    ok = c.ensinar("pergunta teste", "resposta | com pipe e # cerquilha")
    linhas = [l for l in (Path(tmp) / "dados" / "aprendido.txt").read_text(encoding="utf-8").splitlines() if "pergunta teste" in l]
    verificar("linha gravada tem exatamente 2 colunas", ok and len(linhas) == 1 and linhas[0].count("|") == 1)
    c2 = Cerebro(Path(tmp) / "dados", Path(tmp) / "cerebro.json", semente=42)
    verificar("recarregado continua entendendo a pergunta ensinada",
              any("com pipe" in resp for _, resp, _pers, _p in c2.recup.itens))
    verificar("ensinar vazio recusa", not c.ensinar("", "resposta"))

    print("escrita atômica e estado corrompido:")
    alvo = Path(tmp) / "x.json"
    escrever_atomico(alvo, '{"a": 1}')
    escrever_atomico(alvo, '{"a": 2}')
    verificar(".bak guarda a versão anterior", "1" in (Path(tmp) / "x.json.bak").read_text(encoding="utf-8"))
    c.salvar()  # cria cerebro.json
    Path(tmp, "cerebro.json").write_text("{ quebrado", encoding="utf-8")
    c3 = Cerebro(Path(tmp) / "dados", Path(tmp) / "cerebro.json", semente=42)
    verificar("estado corrompido sinalizado (sem sumir calado)", c3.estado_corrompido)

    teste_detector_crise(tmp + "_crise")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} falha(s): {FALHAS}")
        sys.exit(1)
    print("todos os testes passaram")


def teste_detector_crise(tmp):
    print("detector de crise (combinado, sem falso positivo):")
    c = cerebro_novo(tmp)
    crises = ["quero morrer", "vou me matar", "as vezes penso em nao querer mais viver",
              "nao vejo sentido em continuar vivo", "penso em morrer as vezes",
              "cansado de viver", "isso nao tem mais sentido na minha vida",
              "quero sumir pra sempre"]
    neutras = ["que filme sobre morte voce recomenda", "estou cansado de trabalhar",
               "filmes sobre suicidio para um trabalho da escola",
               "sumir de fim de semana pra descansar", "bora continuar vivo!", "quero cafe"]
    for f in crises:
        assert c.seguranca(f), f"deveria ser crise: {f!r}"
    for f in neutras:
        assert not c.seguranca(f), f"falso positivo: {f!r}"
    print("   ok    8 crises detectadas, 6 frases neutras em paz")


if __name__ == "__main__":
    main()
