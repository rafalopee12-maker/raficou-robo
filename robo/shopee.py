"""Shopee — Open API de afiliados (GraphQL), endpoint do Brasil.

O offerLink que volta já é o link de afiliado. A API não informa o preço "de",
então ele é estimado a partir de priceDiscountRate (igual a Shopee mostra no app).
"""
from __future__ import annotations

import hashlib
import json
import time

from .base import Coletor, ColetorErro, env, log
from .modelo import Oferta, calcular_desconto, nome_curto, numero, porcentagem

URL = "https://open-api.affiliate.shopee.com.br/graphql"

CONSULTA = """query ($keyword: String, $sortType: Int, $page: Int, $limit: Int) {
  productOfferV2(keyword: $keyword, sortType: $sortType, page: $page, limit: $limit) {
    nodes {
      itemId shopId productName imageUrl productLink offerLink
      priceMin priceMax priceDiscountRate
      commissionRate sales ratingStar shopName
    }
    pageInfo { page limit hasNextPage }
  }
}"""


def cabecalho(app_id: str, segredo: str, corpo: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    assinatura = hashlib.sha256(f"{app_id}{ts}{corpo}{segredo}".encode()).hexdigest()
    return f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={assinatura}"


class Shopee(Coletor):
    nome = "shopee"
    loja = "Shopee"
    variaveis = ("SHOPEE_APP_ID", "SHOPEE_SECRET")

    def consultar(self, variaveis: dict) -> dict:
        corpo = json.dumps({"query": CONSULTA, "variables": variaveis}, separators=(",", ":"), ensure_ascii=False)
        r = self.http.post(URL, data=corpo.encode("utf-8"), timeout=30, headers={
            "Content-Type": "application/json",
            "Authorization": cabecalho(env("SHOPEE_APP_ID"), env("SHOPEE_SECRET"), corpo),
        })
        try:
            j = r.json()
        except ValueError:
            raise ColetorErro(f"Shopee respondeu HTTP {r.status_code} sem JSON")
        if j.get("errors"):
            e = j["errors"][0]
            codigo = (e.get("extensions") or {}).get("code", "")
            raise ColetorErro(f"Shopee erro {codigo}: {e.get('message')}")
        return (j.get("data") or {}).get("productOfferV2") or {}

    def converter(self, n: dict, termo: dict) -> Oferta | None:
        preco = numero(n.get("priceMin"))
        if not preco:
            return None
        taxa = numero(n.get("priceDiscountRate")) or 0
        antigo = round(preco / (1 - taxa / 100), 2) if 0 < taxa < 95 else None
        cat, emoji = self.categoria(termo.get("categoria", "geral"))
        titulo = n.get("productName", "")
        return Oferta(
            id=f"shp:{n.get('shopId')}_{n.get('itemId')}",
            loja=self.loja,
            nome=nome_curto(titulo),
            nome_completo=titulo,
            preco=preco,
            antigo=antigo,
            desconto=calcular_desconto(preco, antigo),
            link=n.get("offerLink") or n.get("productLink", ""),
            afiliado=bool(n.get("offerLink")),
            url_produto=n.get("productLink", ""),
            imagem_original=n.get("imageUrl", ""),
            comissao=porcentagem(n.get("commissionRate")),
            vendas=int(n["sales"]) if isinstance(n.get("sales"), (int, float)) else None,
            nota=numero(n.get("ratingStar")),
            obs=f"Loja: {n['shopName']}" if n.get("shopName") else "",
            categoria=cat,
            emoji=emoji,
            termo=termo["termo"],
        )

    def coletar(self) -> list[Oferta]:
        cfg = self.config.get("shopee", {})
        saida: list[Oferta] = []
        for termo in self.termos():
            try:
                res = self.consultar({
                    "keyword": termo["termo"],
                    "sortType": cfg.get("ordenar", 2),
                    "page": 1,
                    "limit": cfg.get("por_termo", 50),
                })
            except ColetorErro:
                raise
            except Exception as e:
                log.warning("Shopee falhou em '%s': %s", termo["termo"], e)
                continue
            for n in res.get("nodes") or []:
                o = self.converter(n, termo)
                if o and self.aprovada(o):
                    saida.append(o)
            self.pausa(0.5)
        return saida
