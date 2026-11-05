"""Peças comuns: sessão HTTP com novas tentativas, log e a classe base dos coletores."""
from __future__ import annotations

import json
import logging
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .modelo import Oferta, bloqueado

log = logging.getLogger("robo")


def carregar_segredos() -> None:
    """No GitHub Actions os segredos e variáveis chegam juntos em JSON (SEGREDOS / VARIAVEIS)."""
    for nome in ("SEGREDOS", "VARIAVEIS"):
        bruto = os.environ.get(nome)
        if not bruto:
            continue
        try:
            for chave, valor in json.loads(bruto).items():
                if isinstance(valor, str) and valor and not os.environ.get(chave):
                    os.environ[chave] = valor
        except ValueError:
            log.warning("não consegui ler %s", nome)


carregar_segredos()

AGENTE = "RaficouRobo/1.0 (+https://github.com)"


class ColetorErro(Exception):
    """Erro que vale mostrar no resumo da execução (credencial errada, API fora do ar...)."""


def sessao() -> requests.Session:
    s = requests.Session()
    tentativas = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                       allowed_methods=frozenset(["GET", "POST"]))
    s.mount("https://", HTTPAdapter(max_retries=tentativas))
    s.headers["User-Agent"] = AGENTE
    return s


def env(nome: str, padrao: str = "") -> str:
    return (os.environ.get(nome) or padrao).strip()


class Coletor:
    nome = "base"
    loja = ""
    variaveis: tuple[str, ...] = ()

    def __init__(self, config: dict, http: requests.Session | None = None):
        self.config = config
        self.http = http or sessao()
        self.filtros = config.get("filtros", {})
        self.bloqueio = config.get("palavras_bloqueadas", [])

    # --- configuração ---
    def faltando(self) -> list[str]:
        return [v for v in self.variaveis if not env(v)]

    def termos(self) -> list[dict]:
        return [t for t in self.config.get("termos", []) if self.nome in t.get("lojas", [self.nome])]

    def categoria(self, chave: str) -> tuple[str, str]:
        cats = self.config.get("categorias", {})
        c = cats.get(chave) or cats.get("geral") or {"emoji": "🔥"}
        return chave if chave in cats else "geral", c["emoji"]

    # --- filtro comum ---
    def aprovada(self, o: Oferta) -> bool:
        f = self.filtros
        if bloqueado(o.nome_completo or o.nome, self.bloqueio):
            return False
        if o.preco is None or o.preco < f.get("preco_minimo", 0) or o.preco > f.get("preco_maximo", 1e9):
            return False
        if (o.desconto or 0) < f.get("desconto_minimo", 0) and not o.cupom:
            return False
        if o.nota is not None and o.nota < f.get("nota_minima", 0):
            return False
        if o.vendas is not None and o.vendas < f.get("vendas_minimas", 0):
            return False
        return True

    def coletar(self) -> list[Oferta]:
        raise NotImplementedError

    @staticmethod
    def pausa(segundos: float) -> None:
        if segundos > 0:
            time.sleep(segundos)
