"""Ofertas de exemplo para testar o robô e o app sem credenciais (python -m robo --demo)."""
from __future__ import annotations

from pathlib import Path

from .modelo import Oferta, calcular_desconto, slug

EXEMPLOS = [
    ("AliExpress", "Headset Gamer Sem Fio 2.4G com Microfone Removível e RGB", 189.90, 329.90, "BRGAMER20", "R$ 20 off acima de R$ 150", "audio"),
    ("Shopee", "Teclado Mecânico 75% Hot-Swap Switch Marrom RGB", 219.00, 299.00, "", "", "periferico"),
    ("Amazon", "Controle DualSense Branco - PS5", 349.00, 469.00, "", "", "games"),
    ("Mercado Livre", "SSD NVMe 1TB PCIe 4.0 Leitura 7000MB/s", 379.99, 519.90, "", "", "pc"),
    ("AliExpress", "Mouse Gamer Sem Fio 26000 DPI 59g Tri-mode", 129.90, 239.90, "AEBR15", "R$ 15 off acima de R$ 100", "periferico"),
    ("Amazon", "Monitor Gamer 27\" QHD 180Hz IPS 1ms", 1299.00, 1799.00, "", "", "pc"),
    ("Shopee", "Cadeira Gamer Reclinável com Apoio para os Pés", 699.90, 1099.90, "", "", "periferico"),
    ("Mercado Livre", "Memória RAM DDR5 32GB (2x16) 6000MHz", 649.00, 799.00, "", "", "pc"),
    ("AliExpress", "Controle Sem Fio para PC e Switch com Hall Effect", 159.90, 249.90, "", "", "games"),
    ("Amazon", "Jogo EA Sports FC 27 - PS5", 262.45, 349.90, "", "", "games"),
]

CORES = {"audio": "#FFD12E", "periferico": "#D9D4EA", "games": "#FFFFFF", "pc": "#F3F1F8"}
ROTULO = {"audio": "HEADSET", "periferico": "PERIFÉRICO", "games": "GAMES", "pc": "HARDWARE"}


def _foto(destino: Path, categoria: str, nome: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (800, 800), CORES.get(categoria, "#FFFFFF"))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((120, 160, 680, 560), radius=60, fill="#22184A")
    try:
        fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        menor = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError:
        fonte = menor = ImageFont.load_default()
    d.text((400, 360), ROTULO.get(categoria, "OFERTA"), fill="#FFD12E", font=fonte, anchor="mm")
    d.text((400, 650), nome[:34], fill="#22184A", font=menor, anchor="mm")
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "JPEG", quality=85)


def busca(loja: str, nome: str) -> str:
    """Link da busca do produto na loja (os exemplos não são produtos reais)."""
    from urllib.parse import quote
    termo = " ".join(nome.replace('"', " ").split()[:6])
    return {
        "Mercado Livre": "https://lista.mercadolivre.com.br/" + quote(slug(termo)),
        "Amazon": "https://www.amazon.com.br/s?k=" + quote(termo),
        "Shopee": "https://shopee.com.br/search?keyword=" + quote(termo),
        "AliExpress": "https://pt.aliexpress.com/w/wholesale-" + quote(slug(termo)) + ".html",
    }.get(loja, "https://www.google.com/search?q=" + quote(termo))


def ofertas_demo(config: dict, pasta_img: Path) -> list[Oferta]:
    cats = config.get("categorias", {})
    saida = []
    for i, (loja, nome, preco, antigo, cupom, regra, cat) in enumerate(EXEMPLOS):
        oid = f"demo:{i}"
        _foto(pasta_img / f"{slug(oid.replace(':', '-'), 40)}.jpg", cat, nome)
        saida.append(Oferta(
            id=oid, loja=loja, nome=nome, nome_completo=nome, preco=preco, antigo=antigo,
            desconto=calcular_desconto(preco, antigo), cupom=cupom, cupom_regra=regra,
            link=busca(loja, nome), url_produto=busca(loja, nome),
            afiliado=loja != "Mercado Livre", categoria=cat, emoji=cats.get(cat, {}).get("emoji", "🔥"),
            comissao=[7.0, 9.5, 4.0, None][i % 4], nota=4.8, vendas=1200 + i * 37, termo="demo",
        ))
    return saida
