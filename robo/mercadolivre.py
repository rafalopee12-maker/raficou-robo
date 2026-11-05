"""Mercado Livre — lista de acompanhamento.

Desde 2025 o Mercado Livre bloqueia a busca pública da API para apps de terceiros (HTTP 403),
então aqui o robô acompanha os produtos que você colocar em mercadolivre.txt e avisa quando
entram em promoção ou chegam no menor preço. Precisa de um app no DevCenter com permissão de
leitura de itens e de um refresh_token (o passo a passo está no LEIAME).

O refresh_token do Mercado Livre só pode ser usado uma vez: a cada execução o robô recebe um
novo e guarda criptografado em estado/ml_token.enc (com a chave CHAVE_ESTADO).
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from .base import Coletor, ColetorErro, env, log
from .modelo import Oferta, calcular_desconto, nome_curto, numero

API = "https://api.mercadolibre.com"
RE_PRODUTO = re.compile(r"/p/(MLB\d{6,})", re.I)
RE_ITEM = re.compile(r"\b(MLB)-?(\d{6,})\b", re.I)


def ler_lista(caminho: Path) -> list[dict]:
    """Cada linha: <link ou código do produto>  [link de afiliado meli.la opcional]  # comentário"""
    itens = []
    if not caminho.exists():
        return itens
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        partes = re.split(r"[\s;|]+", linha)
        alvo, afiliado = partes[0], next((p for p in partes[1:] if p.startswith("http")), "")
        m = RE_PRODUTO.search(alvo)
        if m:
            itens.append({"tipo": "produto", "id": m.group(1).upper(), "url": alvo, "afiliado": afiliado})
            continue
        m = RE_ITEM.search(alvo)
        if m:
            itens.append({"tipo": "item", "id": f"MLB{m.group(2)}", "url": alvo, "afiliado": afiliado})
        else:
            log.warning("Mercado Livre: não entendi a linha '%s'", linha)
    return itens


def _fernet():
    chave = env("CHAVE_ESTADO")
    if not chave:
        return None
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(chave.encode()).digest()))


def foto_grande(url: str) -> str:
    return re.sub(r"-[A-Z]\.(jpg|webp|png)$", r"-O.\1", url or "")


class MercadoLivre(Coletor):
    nome = "mercadolivre"
    loja = "Mercado Livre"
    variaveis = ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "CHAVE_ESTADO")

    def __init__(self, config, http=None, pasta_estado: Path = Path("estado"), lista: Path = Path("mercadolivre.txt")):
        super().__init__(config, http)
        self.arquivo_token = pasta_estado / "ml_token.enc"
        self.lista = lista
        self._token = ""

    def faltando(self) -> list[str]:
        falta = super().faltando()
        if not self.arquivo_token.exists() and not env("ML_REFRESH_TOKEN"):
            falta.append("conexão (rode o Robô de ofertas com o código do Mercado Livre)")
        return falta

    # ---------- login ----------
    def _refresh_guardado(self) -> str:
        f = _fernet()
        if f and self.arquivo_token.exists():
            try:
                return f.decrypt(self.arquivo_token.read_bytes()).decode()
            except Exception:
                log.warning("Mercado Livre: não consegui ler o token guardado; usando ML_REFRESH_TOKEN")
        return env("ML_REFRESH_TOKEN")

    def _guardar_refresh(self, token: str) -> None:
        f = _fernet()
        if not f:
            return
        self.arquivo_token.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo_token.write_bytes(f.encrypt(token.encode()))

    def token(self) -> str:
        if self._token:
            return self._token
        r = self.http.post(f"{API}/oauth/token", timeout=30, data={
            "grant_type": "refresh_token",
            "client_id": env("ML_CLIENT_ID"),
            "client_secret": env("ML_CLIENT_SECRET"),
            "refresh_token": self._refresh_guardado(),
        }, headers={"Accept": "application/json"})
        j = r.json() if r.content else {}
        if r.status_code != 200 or "access_token" not in j:
            raise ColetorErro(
                f"Mercado Livre recusou o login (HTTP {r.status_code}: {j.get('message') or j.get('error')}). "
                "Gere um refresh_token novo e atualize o segredo ML_REFRESH_TOKEN (veja o LEIAME).")
        if j.get("refresh_token"):
            self._guardar_refresh(j["refresh_token"])
        self._token = j["access_token"]
        return self._token

    def get(self, caminho: str, **params):
        r = self.http.get(f"{API}{caminho}", params=params or None, timeout=30,
                          headers={"Authorization": f"Bearer {self.token()}"})
        if r.status_code == 403:
            raise ColetorErro("Mercado Livre 403: ative a permissão de leitura de itens no DevCenter e gere um token novo")
        if r.status_code != 200:
            return None
        return r.json()

    # ---------- leitura ----------
    def _preco_promocional(self, item_id: str) -> tuple[float | None, float | None]:
        j = self.get(f"/items/{item_id}/sale_price", context="channel_marketplace")
        if not j:
            return None, None
        return numero(j.get("amount")), numero(j.get("regular_amount"))

    def _oferta(self, alvo: dict, titulo: str, preco, antigo, foto: str, link_loja: str) -> Oferta | None:
        preco, antigo = numero(preco), numero(antigo)
        if not preco:
            return None
        if antigo and antigo <= preco:
            antigo = None
        cat, emoji = self.categoria(alvo.get("categoria", "geral"))
        return Oferta(
            id=f"ml:{alvo['id']}",
            loja=self.loja,
            nome=nome_curto(titulo),
            nome_completo=titulo,
            preco=preco,
            antigo=antigo,
            desconto=calcular_desconto(preco, antigo),
            link=alvo["afiliado"] or link_loja or alvo["url"],
            afiliado=bool(alvo["afiliado"]),
            url_produto=link_loja or alvo["url"],
            imagem_original=foto_grande(foto),
            categoria=cat,
            emoji=emoji,
            termo="lista",
        )

    def coletar(self) -> list[Oferta]:
        alvos = ler_lista(self.lista)
        if not alvos:
            log.info("Mercado Livre: mercadolivre.txt está vazio; nada para acompanhar")
            return []
        saida: list[Oferta] = []
        itens = [a for a in alvos if a["tipo"] == "item"]
        for i in range(0, len(itens), 20):
            lote = itens[i:i + 20]
            resp = self.get("/items", ids=",".join(a["id"] for a in lote),
                            attributes="id,title,price,original_price,pictures,thumbnail,permalink,status") or []
            por_id = {x.get("body", {}).get("id"): x.get("body") for x in resp if x.get("code") == 200}
            for a in lote:
                b = por_id.get(a["id"])
                if not b or b.get("status") not in (None, "active"):
                    continue
                promo, regular = self._preco_promocional(a["id"])
                foto = ((b.get("pictures") or [{}])[0].get("secure_url")) or b.get("thumbnail", "")
                o = self._oferta(a, b.get("title", ""), promo or b.get("price"),
                                 regular or b.get("original_price"), foto, b.get("permalink", ""))
                if o:
                    saida.append(o)
        for a in (x for x in alvos if x["tipo"] == "produto"):
            p = self.get(f"/products/{a['id']}")
            if not p:
                continue
            bb = p.get("buy_box_winner") or {}
            promo = regular = None
            if bb.get("item_id"):
                promo, regular = self._preco_promocional(bb["item_id"])
            foto = ((p.get("pictures") or [{}])[0].get("url")) or ""
            o = self._oferta(a, p.get("name", ""), promo or bb.get("price"),
                             regular or bb.get("original_price"), foto, p.get("permalink", ""))
            if o:
                saida.append(o)
        return saida
