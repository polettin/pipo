"""IA local opcional para o Pipo (API no formato OpenAI: llama.cpp, vLLM, llama-swap...).

Tudo continua funcionando SEM nada disso: se não existir llm.json nem a variável
de ambiente PIPO_LLM_URL, o Pipo behave exatamente como sempre foi (100% offline,
zero dependências — aqui só tem biblioteca padrão).

Como ligar (opcional):
  1. Sirva um modelo com API OpenAI-compatible. Exemplo com llama.cpp:
       llama-server -m qwen3.5-0.8b.Q4_K_M.gguf --port 8080
  2. Crie um arquivo llm.json ao lado do pipo_ml.py:
       {"url": "http://127.0.0.1:8080/v1", "modelo": "qwen3.5-0.8b"}
     (ou exporte PIPO_LLM_URL / PIPO_LLM_MODEL antes de abrir o Pipo)

O que a IA local faz: quando o Pipo não sabe responder ("desconhecida"), ele
pergunta ao modelo em vez de admitir na hora. O modo automático NUNCA manda:
  - o que você fala quando está mal (o acolhimento curado continua mandando);
  - nada para a internet — a URL configurada é sempre local, sua máquina decide.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT_PADRAO = 8          # segundos: modelo local preso não pode travar o Pipo
MAX_TOKENS = 220
PERSONA_DESCRICAO = {       # o mesmo texto que aparece no menu, para o prompt ficar curto
    "fofinho": "carinhoso e bem-humorado",
    "zen": "calmo e tranquilo",
    "sarcastico": "debochado, com ironia leve",
    "mentor": "focado e prático",
    "revoltado": "mal-humorado e implicante de brincadeira, mas acolhe quem está mal",
}


class ClienteLLM:
    """Cliente mínimo de /chat/completions. ligar() devolve None se desligado."""

    def __init__(self, url, modelo="model", chave=None, timeout=TIMEOUT_PADRAO):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.chave = chave
        self.timeout = timeout

    @classmethod
    def ligar(cls, pasta=None):
        """Lê llm.json (na pasta do programa) ou as variáveis PIPO_LLM_*. None = desligado."""
        config = {}
        arq = Path(pasta) / "llm.json" if pasta else Path(__file__).parent / "llm.json"
        if arq.exists():
            try:
                config = json.loads(arq.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        url = config.get("url") or os.environ.get("PIPO_LLM_URL")
        if not url:
            return None
        return cls(url,
                   modelo=config.get("modelo") or os.environ.get("PIPO_LLM_MODEL") or "model",
                   chave=config.get("chave") or os.environ.get("PIPO_LLM_CHAVE"),
                   timeout=int(config.get("timeout", TIMEOUT_PADRAO)))

    def perguntar(self, instrucao, mensagens):
        """instrucao: prompt de sistema. mensagens: [{'role','conteudo'}...] (papel 'user'/'model').
        Devolve o texto da resposta, ou None em qualquer falha (o chamador usa o fallback)."""
        corpo = {
            "model": self.modelo,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
            "messages": [{"role": "system", "content": instrucao}] + [
                {"role": "user" if m["role"] == "user" else "assistant", "content": m["conteudo"]}
                for m in mensagens],
        }
        cabecalhos = {"Content-Type": "application/json"}
        if self.chave:
            cabecalhos["Authorization"] = f"Bearer {self.chave}"
        requisicao = urllib.request.Request(
            f"{self.url}/chat/completions",
            data=json.dumps(corpo).encode("utf-8"),
            headers=cabecalhos, method="POST")
        try:
            with urllib.request.urlopen(requisicao, timeout=self.timeout) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            texto = dados["choices"][0]["message"]["content"].strip()
            return texto or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, ValueError):
            return None


def montar_instrucao(persona, fatos, resumo_ctx=""):
    """Prompt de sistema curto (modelos de 0.8B se perdem em prompt grande)."""
    descricao = PERSONA_DESCRICAO.get(persona, persona)
    linhas = [f"Você é o Pipo, um bichinho de tela {descricao}. "
              "Responda em português do Brasil, no máximo 3 frases, sem markdown. "
              "Se não souber, admita com bom humor e peça para ser ensinado."]
    conhecidos = [f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                  for k, v in (fatos or {}).items() if v]
    if conhecidos:
        linhas.append("Fatos do usuário: " + "; ".join(conhecidos[:6]))
    if resumo_ctx:
        linhas.append(resumo_ctx)
    return "\n".join(linhas)
