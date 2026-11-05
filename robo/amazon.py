"""Amazon — Creators API (substituta da PA-API 5.0).

Exige conta de Associado aprovada e pelo menos 10 vendas qualificadas nos últimos 30 dias.
O detailPageURL devolvido já carrega a sua tag de associado.
A API não informa cupons de "clique para aplicar"; informa economia e ofertas relâmpago.
"""
from __future__ import annotations

import time

from .base import Coletor, ColetorErro, env, log
from .modelo import Oferta, calcular_desconto, nome_curto, numero

TOKEN_URL = "https://api.amazon.com/auth/o2/token"     # região NA (versão 3.1), que inclui o Brasil
API = "https://creatorsapi.amazon/catalog/v1/searchItems"

RECURSOS = [
    "images.primary.large",
    "itemInfo.title",
    "offersV2.listings.price",
    "offersV2.listings.dealDetails",
    "offersV2.listings.availability",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.merchantInfo",
]

SELO = {
    "PRIME_EXCLUSIVE": "Exclusivo Prime",
    "PRIME_EARLY_ACCESS": "Acesso antecipado Prime",
}


class Amazon(Coletor):
    nome = "amazon"
    loja = "Amazon"
    variaveis = ("AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_PARTNER_TAG")

    _token: str = ""
    _expira: float = 0

    def token(self) -> str:
        if self._token and time.time() < self._expira - 60:
            return self._token
        r = self.http.post(env("AMAZON_TOKEN_URL", TOKEN_URL), timeout=30, json={
            "grant_type": "client_credentials",
            "client_id": env("AMAZON_CREDENTIAL_ID"),
            "client_secret": env("AMAZON_CREDENTIAL_SECRET"),
            "scope": "creatorsapi::default",
        })
        if r.status_code != 200:
            raise ColetorErro(f"Amazon recusou o login (HTTP {r.status_code}): {r.text[:200]}")
        j = r.json()
        self._token = j["access_token"]
        self._expira = time.time() + int(j.get("expires_in", 3600))
        return self._token

    def buscar(self, corpo: dict) -> dict:
        mkt = self.config.get("amazon", {}).get("marketplace", "www.amazon.com.br")
        r = self.http.post(API, json={**corpo, "marketplace": mkt}, timeout=30, headers={
            "Authorization": f"Bearer {self.token()}",
            "x-marketplace": mkt,
        })
        j = r.json() if r.content else {}
        if r.status_code in (401, 403):
            msg = str(j)[:300]
            dica = " (a conta precisa de 10 vendas em 30 dias)" if "Eligib" in msg else ""
            raise ColetorErro(f"Amazon negou acesso (HTTP {r.status_code}){dica}: {msg}")
        if r.status_code == 429:
            log.warning("Amazon pediu calma (429); pulando este termo")
            return {}
        if r.status_code != 200:
            raise ColetorErro(f"Amazon HTTP {r.status_code}: {str(j)[:300]}")
        return j.get("searchResult") or {}

    def converter(self, it: dict, termo: dict) -> Oferta | None:
        listas = (it.get("offersV2") or {}).get("listings") or []
        if not listas:
            return None
        lst = next((x for x in listas if x.get("isBuyBoxWinner")), listas[0])
        preco_c = lst.get("price") or {}
        preco = numero((preco_c.get("money") or {}).get("amount"))
        if not preco:
            return None
        antigo = numero(((preco_c.get("savingBasis") or {}).get("money") or {}).get("amount"))
        if antigo and antigo <= preco:
            antigo = None
        titulo = ((it.get("itemInfo") or {}).get("title") or {}).get("displayValue", "")
        imgs = (it.get("images") or {}).get("primary") or {}
        img = (imgs.get("large") or imgs.get("medium") or imgs.get("small") or {}).get("url", "")
        deal = lst.get("dealDetails") or {}
        obs = deal.get("badge") or SELO.get(deal.get("accessType", ""), "")
        if deal.get("percentClaimed"):
            obs = f"{obs} · {deal['percentClaimed']}% vendido".strip(" ·")
        cat, emoji = self.categoria(termo.get("categoria", "geral"))
        return Oferta(
            id=f"amz:{it.get('asin')}",
            loja=self.loja,
            nome=nome_curto(titulo),
            nome_completo=titulo,
            preco=preco,
            antigo=antigo,
            desconto=calcular_desconto(preco, antigo),
            obs=obs,
            link=it.get("detailPageURL", ""),
            url_produto=it.get("detailPageURL", ""),
            imagem_original=img,
            categoria=cat,
            emoji=emoji,
            termo=termo["termo"],
        )

    def coletar(self) -> list[Oferta]:
        cfg = self.config.get("amazon", {})
        f = self.filtros
        saida: list[Oferta] = []
        for termo in self.termos():
            corpo = {
                "keywords": termo["termo"],
                "searchIndex": termo.get("indice_amazon") or cfg.get("indice", "All"),
                "itemCount": min(10, cfg.get("por_termo", 10)),
                "partnerTag": env("AMAZON_PARTNER_TAG"),
                "resources": RECURSOS,
                "minSavingPercent": max(1, int(f.get("desconto_minimo", 10))),
                "minPrice": int(f.get("preco_minimo", 0) * 100) or None,
            }
            corpo = {k: v for k, v in corpo.items() if v is not None}
            try:
                res = self.buscar(corpo)
            except ColetorErro:
                raise
            except Exception as e:
                log.warning("Amazon falhou em '%s': %s", termo["termo"], e)
                continue
            for it in res.get("items") or []:
                o = self.converter(it, termo)
                if o and self.aprovada(o):
                    saida.append(o)
            self.pausa(1.1)   # a cota inicial é de 1 chamada por segundo
        return saida
