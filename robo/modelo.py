"""Estrutura de uma oferta e funções de limpeza usadas por todos os coletores."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Oferta:
    id: str                      # "ali:123", "shp:shop_item", "amz:ASIN", "ml:MLB123"
    loja: str                    # tem que bater com a lista LOJAS do app
    nome: str                    # nome curto, pronto para o post
    preco: float
    link: str                    # link de afiliado (ou da loja, se não houver)
    antigo: Optional[float] = None
    desconto: Optional[int] = None
    cupom: str = ""
    cupom_regra: str = ""
    cupom_validade: str = ""
    obs: str = ""
    forma: str = ""
    categoria: str = "geral"
    emoji: str = "🔥"
    nome_completo: str = ""
    url_produto: str = ""
    imagem: str = ""             # caminho no site (img/xxx.jpg), preenchido na publicação
    imagem_original: str = ""
    comissao: Optional[float] = None   # % de comissão, quando a API informa
    vendas: Optional[int] = None
    nota: Optional[float] = None
    termo: str = ""
    afiliado: bool = True        # False quando o link ainda não é de afiliado (ex.: Mercado Livre sem link)
    menor_preco_30d: bool = False
    alerta: str = ""
    novo: bool = False
    visto_em: str = field(default_factory=agora_iso)
    primeiro_visto: str = ""
    pontos: float = 0.0

    def para_json(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "")}


def sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn").lower()


def numero(valor) -> Optional[float]:
    """Converte '1.299,90', '1299.90', 'R$ 129', 129 → float."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d.,]", "", str(valor))
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def porcentagem(valor) -> Optional[float]:
    """'35%' → 35.0 ; 0.35 → 35.0 ; 35 → 35.0"""
    n = numero(valor)
    if n is None:
        return None
    if isinstance(valor, (int, float)) and 0 < n < 1:
        return round(n * 100, 2)
    if isinstance(valor, str) and "%" not in valor and 0 < n < 1:
        return round(n * 100, 2)
    return n


def calcular_desconto(preco: Optional[float], antigo: Optional[float]) -> Optional[int]:
    if preco and antigo and antigo > preco:
        return round((1 - preco / antigo) * 100)
    return None


_LIXO = [
    r"【[^】]*】", r"\[[^\]]*\]", r"\{[^}]*\}",
    r"\b(20\d\d)\s*(new|novo|nova)\b", r"\b(new|novo|nova)\s*(20\d\d)\b",
    r"\bfrete gr[aá]tis\b", r"\bfree shipping\b", r"\bpronta entrega\b", r"\benvio imediato\b",
    r"\bhot sale\b", r"\bbest seller\b", r"\boriginal\b(?=.*\boriginal\b)",
]


def nome_curto(titulo: str, limite: int = 72) -> str:
    """Tira excesso de palavras de marketing e corta em limite de caracteres sem quebrar palavra."""
    t = titulo or ""
    for padrao in _LIXO:
        t = re.sub(padrao, " ", t, flags=re.I)
    t = re.sub(r"\s*[|/,;]\s*$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -|,;/")
    if len(t) <= limite:
        return t
    corte = t[:limite]
    if " " in corte:
        corte = corte[: corte.rfind(" ")]
    return corte.rstrip(" -|,;/(") + "…"


def bloqueado(titulo: str, palavras: list[str]) -> bool:
    t = " " + sem_acento(titulo) + " "
    return any(sem_acento(p) in t for p in palavras)


def slug(txt: str, limite: int = 60) -> str:
    s = sem_acento(txt)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:limite] or "oferta"
