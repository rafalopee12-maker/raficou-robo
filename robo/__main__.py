"""Roda o robô: python -m robo  (ou python -m robo --demo para testar sem credenciais)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .aliexpress import AliExpress
from .amazon import Amazon
from .base import ColetorErro, log
from .historico import Historico, pontuar
from .mercadolivre import MercadoLivre
from .modelo import Oferta
from .publicar import publicar
from .shopee import Shopee

COLETORES = {"aliexpress": AliExpress, "shopee": Shopee, "amazon": Amazon, "mercadolivre": MercadoLivre}
RAIZ = Path(__file__).resolve().parent.parent


def deduplicar(ofertas: list[Oferta]) -> list[Oferta]:
    melhor: dict[str, Oferta] = {}
    for o in ofertas:
        atual = melhor.get(o.id)
        if not atual or (o.desconto or 0) > (atual.desconto or 0) or (o.cupom and not atual.cupom):
            melhor[o.id] = o
    return list(melhor.values())


def coletar(config: dict, estado: Path) -> tuple[list[Oferta], dict]:
    resumo: dict[str, dict] = {}
    todas: list[Oferta] = []
    for nome in config.get("lojas_ativas", []):
        cls = COLETORES.get(nome)
        if not cls:
            continue
        col = cls(config, pasta_estado=estado, lista=RAIZ / "mercadolivre.txt") if cls is MercadoLivre else cls(config)
        faltando = col.faltando()
        if faltando:
            resumo[nome] = {"status": "sem credenciais", "faltando": faltando}
            log.info("%s: pulado, faltam %s", col.loja, ", ".join(faltando))
            continue
        try:
            achadas = col.coletar()
            resumo[nome] = {"status": "ok", "ofertas": len(achadas)}
            log.info("%s: %d ofertas", col.loja, len(achadas))
            todas.extend(achadas)
        except ColetorErro as e:
            resumo[nome] = {"status": "erro", "mensagem": str(e)}
            log.error("%s: %s", col.loja, e)
        except Exception as e:  # nunca deixa uma loja derrubar as outras
            resumo[nome] = {"status": "erro", "mensagem": f"{type(e).__name__}: {e}"}
            log.exception("%s falhou", col.loja)
    return todas, resumo


def processar(ofertas: list[Oferta], hist: Historico, config: dict) -> list[Oferta]:
    f = config.get("filtros", {})
    mostrar_ml = config.get("mercadolivre", {}).get("mostrar_sempre", False)
    final = []
    for o in deduplicar(ofertas):
        hist.registrar(o)
        if o.termo == "lista":   # lista de acompanhamento: entra se estiver em promoção ou no menor preço
            em_promo = (o.desconto or 0) >= f.get("desconto_minimo", 0)
            if not (mostrar_ml or em_promo or (o.menor_preco_30d and hist.caiu_de_preco(o))):
                continue
        o.pontos = pontuar(o)
        final.append(o)
    return final


def escrever_resumo(feed: dict, resumo: dict) -> None:
    linhas = [f"## Robô RAFICOU! — {feed['total']} ofertas no feed", "", "| Loja | Situação |", "|---|---|"]
    for loja, r in resumo.items():
        if r["status"] == "ok":
            txt = f"✅ {r['ofertas']} ofertas"
        elif r["status"] == "sem credenciais":
            txt = "⏸️ sem credenciais: " + ", ".join(r["faltando"])
        else:
            txt = "❌ " + r["mensagem"]
        linhas.append(f"| {loja} | {txt} |")
    texto = "\n".join(linhas)
    print(texto)
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Robô de ofertas gamer do RAFICOU!")
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    ap.add_argument("--saida", default=str(RAIZ / "saida"), help="pasta do site gerado")
    ap.add_argument("--estado", default=str(RAIZ / "estado"), help="histórico e tokens (guardado entre execuções)")
    ap.add_argument("--demo", action="store_true", help="gera ofertas de exemplo, sem acessar as lojas")
    ap.add_argument("-v", "--verboso", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verboso else logging.INFO, format="%(levelname)s %(message)s")

    config = json.loads(Path(a.config).read_text(encoding="utf-8"))
    estado, saida = Path(a.estado), Path(a.saida)
    hist = Historico(estado / "historico.json")

    if a.demo:
        from .demo import ofertas_demo
        brutas, resumo = ofertas_demo(config, saida / "img"), {"demo": {"status": "ok", "ofertas": 0}}
    else:
        brutas, resumo = coletar(config, estado)

    ofertas = processar(brutas, hist, config)
    if a.demo:
        resumo["demo"]["ofertas"] = len(ofertas)
    feed = publicar(ofertas, saida, RAIZ / "site", config, resumo, anterior=estado / "ultimo_feed.json")
    hist.limpar()
    hist.salvar()
    escrever_resumo(feed, resumo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
