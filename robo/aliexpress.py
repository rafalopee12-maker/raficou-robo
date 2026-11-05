"""AliExpress — API oficial de afiliados (AliExpress Open Platform / Portals).

Usa aliexpress.affiliate.product.query, que já devolve o link de afiliado (promotion_link)
e, quando existe, o cupom do produto (promo_code_info).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from .base import Coletor, ColetorErro, env, log
from .modelo import Oferta, calcular_desconto, nome_curto, numero, porcentagem

URL = "https://api-sg.aliexpress.com/sync"
METODO = "aliexpress.affiliate.product.query"


def assinar(params: dict, segredo: str, metodo: str = "sha256") -> str:
    """Assinatura do gateway IOP: parâmetros em ordem alfabética, chave+valor concatenados.

    sha256 → HMAC-SHA256 com o App Secret (padrão do SDK oficial).
    md5    → MD5(segredo + texto + segredo), modo antigo, aceito por algumas contas.
    """
    texto = "".join(f"{k}{params[k]}" for k in sorted(params))
    if metodo == "md5":
        return hashlib.md5(f"{segredo}{texto}{segredo}".encode()).hexdigest().upper()
    return hmac.new(segredo.encode(), texto.encode(), hashlib.sha256).hexdigest().upper()


def _cupom(info) -> tuple[str, str, str]:
    if not isinstance(info, dict) or not info.get("promo_code"):
        return "", "", ""
    regra = info.get("code_value") or ""
    minimo = info.get("code_mini_spend")
    if minimo and "acima" not in regra.lower() and "over" not in regra.lower():
        regra = f"{regra} (mínimo {minimo})".strip()
    validade = info.get("code_availabletime_end") or ""
    return str(info["promo_code"]).strip().upper(), regra, validade


class AliExpress(Coletor):
    nome = "aliexpress"
    loja = "AliExpress"
    variaveis = ("ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET", "ALIEXPRESS_TRACKING_ID")

    def chamar(self, metodo: str, negocio: dict) -> dict:
        modo = env("ALIEXPRESS_SIGN_METHOD", "sha256")
        params = {
            "app_key": env("ALIEXPRESS_APP_KEY"),
            "method": metodo,
            "sign_method": modo,
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            **{k: str(v) for k, v in negocio.items() if v not in (None, "")},
        }
        params["sign"] = assinar(params, env("ALIEXPRESS_APP_SECRET"), modo)
        r = self.http.post(URL, data=params, timeout=30)
        try:
            j = r.json()
        except ValueError:
            raise ColetorErro(f"AliExpress respondeu HTTP {r.status_code} sem JSON")
        erro = j.get("error_response") or (j if "code" in j and "type" in j else None)
        if erro:
            codigo = erro.get("code", "?")
            dica = " (confira App Key/Secret ou troque ALIEXPRESS_SIGN_METHOD para md5)" if "Sign" in str(codigo) else ""
            raise ColetorErro(f"AliExpress erro {codigo}: {erro.get('msg') or erro.get('message')}{dica}")
        chave = metodo.replace(".", "_") + "_response"
        resp = (j.get(chave) or {}).get("resp_result") or {}
        if resp and int(resp.get("resp_code", 200)) != 200:
            raise ColetorErro(f"AliExpress resp_code {resp.get('resp_code')}: {resp.get('resp_msg')}")
        return resp.get("result") or {}

    def converter(self, p: dict, termo: dict) -> Oferta | None:
        preco = numero(p.get("target_sale_price") or p.get("sale_price"))
        antigo = numero(p.get("target_original_price") or p.get("original_price"))
        if not preco:
            return None
        if antigo and antigo <= preco:
            antigo = None
        cupom, regra, validade = _cupom(p.get("promo_code_info"))
        cat, emoji = self.categoria(termo.get("categoria", "geral"))
        titulo = p.get("product_title", "")
        nota = porcentagem(p.get("evaluate_rate"))
        return Oferta(
            id=f"ali:{p.get('product_id')}",
            loja=self.loja,
            nome=nome_curto(titulo),
            nome_completo=titulo,
            preco=preco,
            antigo=antigo,
            desconto=calcular_desconto(preco, antigo),
            cupom=cupom,
            cupom_regra=regra,
            cupom_validade=validade,
            link=p.get("promotion_link") or p.get("product_detail_url", ""),
            afiliado=bool(p.get("promotion_link")),
            url_produto=p.get("product_detail_url", ""),
            imagem_original=p.get("product_main_image_url", ""),
            comissao=porcentagem(p.get("commission_rate")),
            vendas=int(p["lastest_volume"]) if str(p.get("lastest_volume", "")).isdigit() else None,
            nota=round(nota / 20, 1) if nota and nota > 5 else nota,   # 97% → 4.9 estrelas
            categoria=cat,
            emoji=emoji,
            termo=termo["termo"],
        )

    def coletar(self) -> list[Oferta]:
        cfg = self.config.get("aliexpress", {})
        saida: list[Oferta] = []
        for termo in self.termos():
            try:
                res = self.chamar(METODO, {
                    "keywords": termo.get("en") or termo["termo"],
                    "page_no": 1,
                    "page_size": cfg.get("por_termo", 50),
                    "sort": cfg.get("ordenar", "LAST_VOLUME_DESC"),
                    "target_currency": "BRL",
                    "target_language": "PT",
                    "ship_to_country": "BR",
                    "tracking_id": env("ALIEXPRESS_TRACKING_ID"),
                })
            except ColetorErro:
                raise
            except Exception as e:  # rede, timeout...
                log.warning("AliExpress falhou em '%s': %s", termo["termo"], e)
                continue
            produtos = ((res.get("products") or {}).get("product")) or []
            for p in produtos:
                o = self.converter(p, termo)
                if o and self.aprovada(o):
                    saida.append(o)
            self.pausa(0.5)
        return saida
