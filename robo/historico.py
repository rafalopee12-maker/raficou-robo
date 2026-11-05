"""Histórico de preços: menor preço em 30 dias e alerta de desconto inflado."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .modelo import Oferta, agora_iso

DIAS_GUARDADOS = 60


def _brl(n: float) -> str:
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Historico:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        try:
            self.dados: dict = json.loads(caminho.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.dados = {}

    def registrar(self, o: Oferta, hoje: date | None = None) -> None:
        """Atualiza o histórico com o preço de hoje e marca a oferta (menor preço, alerta, novo)."""
        hoje = hoje or datetime.now(timezone.utc).date()
        h = self.dados.setdefault(o.id, {"precos": {}, "primeiro": agora_iso()})
        precos: dict[str, float] = h["precos"]
        anteriores = {d: p for d, p in precos.items() if d != hoje.isoformat()}

        limite_30 = (hoje - timedelta(days=30)).isoformat()
        janela = [p for d, p in anteriores.items() if d >= limite_30]
        o.primeiro_visto = h["primeiro"]
        o.novo = not anteriores

        if len(janela) >= 3:
            menor, maior = min(janela), max(janela)
            o.menor_preco_30d = o.preco <= menor
            if o.antigo and maior < o.antigo * 0.9:
                o.alerta = f"O preço 'de' nunca apareceu: o maior que vimos em 30 dias foi {_brl(maior)}"
            elif o.preco > menor * 1.05:
                dia = max(d for d, p in anteriores.items() if p == menor)
                o.alerta = f"Já esteve mais barato: {_brl(menor)} em {dia[8:10]}/{dia[5:7]}"

        precos[hoje.isoformat()] = min(o.preco, precos.get(hoje.isoformat(), o.preco))
        h["ultimo"] = agora_iso()
        h["nome"] = o.nome

    def caiu_de_preco(self, o: Oferta) -> bool:
        precos = self.dados.get(o.id, {}).get("precos", {})
        dias = sorted(precos)
        return len(dias) >= 2 and precos[dias[-1]] < precos[dias[-2]]

    def limpar(self, hoje: date | None = None) -> None:
        hoje = hoje or datetime.now(timezone.utc).date()
        corte = (hoje - timedelta(days=DIAS_GUARDADOS)).isoformat()
        for chave in list(self.dados):
            h = self.dados[chave]
            h["precos"] = {d: p for d, p in h["precos"].items() if d >= corte}
            if not h["precos"]:
                del self.dados[chave]

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(self.dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def pontuar(o: Oferta) -> float:
    """Ordem padrão do feed: desconto, cupom, menor preço e novidade pesam; alerta derruba."""
    p = float(o.desconto or 0)
    if o.cupom:
        p += 12
    if o.menor_preco_30d:
        p += 15
    if o.novo:
        p += 5
    if o.alerta:
        p -= 25
    if o.nota:
        p += (o.nota - 4.5) * 4
    return round(p, 1)
