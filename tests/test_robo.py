"""Testes do robô com respostas simuladas das lojas (rodar: python -m unittest -v)."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from robo import aliexpress, amazon, mercadolivre, shopee
from robo.__main__ import processar
from robo.historico import Historico, pontuar
from robo.modelo import Oferta, nome_curto, numero, porcentagem
from robo.publicar import publicar

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))


class Resposta:
    def __init__(self, dados, status=200):
        self.dados, self.status_code = dados, status
        self.content = json.dumps(dados).encode()
        self.text = self.content.decode()
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self.dados


class HttpFalso:
    """Guarda as chamadas e devolve respostas na ordem em que foram registradas."""
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def _proxima(self, metodo, url, **kw):
        self.chamadas.append((metodo, url, kw))
        r = self.respostas.pop(0) if self.respostas else Resposta({})
        return r(url, kw) if callable(r) else r

    def post(self, url, **kw):
        return self._proxima("POST", url, **kw)

    def get(self, url, **kw):
        return self._proxima("GET", url, **kw)


def config_um_termo(loja, **extra):
    c = json.loads(json.dumps(CONFIG))
    c["termos"] = [{"termo": "headset gamer", "en": "gaming headset", "categoria": "audio", "lojas": [loja]}]
    c.update(extra)
    return c


class TestModelo(unittest.TestCase):
    def test_numero(self):
        self.assertEqual(numero("R$ 1.299,90"), 1299.90)
        self.assertEqual(numero("1299.90"), 1299.90)
        self.assertEqual(numero("1.299"), 1299.0)
        self.assertIsNone(numero(""))

    def test_porcentagem(self):
        self.assertEqual(porcentagem("35%"), 35)
        self.assertEqual(porcentagem("0.38"), 38)
        self.assertEqual(porcentagem(7), 7)

    def test_nome_curto(self):
        t = "【Frete Grátis】2024 New Headset Gamer Sem Fio Bluetooth 5.3 com Microfone Removível RGB Para PS5 PC Xbox Switch Celular"
        n = nome_curto(t)
        self.assertLessEqual(len(n), 73)
        self.assertNotIn("Frete", n)
        self.assertTrue(n.startswith("Headset Gamer"))


class TestAliExpress(unittest.TestCase):
    def test_assinatura_sha256_igual_ao_sdk(self):
        p = {"app_key": "123", "method": "aliexpress.affiliate.product.query", "timestamp": "1700000000000", "keywords": "mouse"}
        texto = "app_key123keywordsmousemethodaliexpress.affiliate.product.querytimestamp1700000000000"
        esperado = hmac.new(b"seg", texto.encode(), hashlib.sha256).hexdigest().upper()
        self.assertEqual(aliexpress.assinar(p, "seg"), esperado)

    def test_assinatura_md5(self):
        p = {"b": "2", "a": "1"}
        self.assertEqual(aliexpress.assinar(p, "S", "md5"), hashlib.md5(b"Sa1b2S").hexdigest().upper())

    @mock.patch.dict(os.environ, {"ALIEXPRESS_APP_KEY": "k", "ALIEXPRESS_APP_SECRET": "s", "ALIEXPRESS_TRACKING_ID": "raficou"})
    def test_coleta_com_cupom(self):
        produto = {
            "product_id": 1005004757833857, "product_title": "Gaming Headset Wireless 7.1 RGB",
            "target_sale_price": "189.90", "target_original_price": "329.90",
            "promotion_link": "https://s.click.aliexpress.com/e/_abc", "product_detail_url": "https://pt.aliexpress.com/item/1.html",
            "product_main_image_url": "https://ae01.alicdn.com/kf/x.jpg", "evaluate_rate": "97.2%",
            "lastest_volume": 812, "commission_rate": "7.0%",
            "promo_code_info": {"promo_code": "brgamer20", "code_value": "R$20 off em compras acima de R$150",
                                "code_availabletime_end": "2026-11-30 23:59:59"},
        }
        lixo = dict(produto, product_id=2, product_title="Case for headset cover")
        sem_desconto = dict(produto, product_id=3, target_original_price="190.00", promo_code_info={})
        http = HttpFalso(Resposta({"aliexpress_affiliate_product_query_response": {"resp_result": {
            "resp_code": 200, "result": {"products": {"product": [produto, lixo, sem_desconto]}}}}}))
        ofs = aliexpress.AliExpress(config_um_termo("aliexpress"), http).coletar()
        self.assertEqual(len(ofs), 1)
        o = ofs[0]
        self.assertEqual((o.preco, o.antigo, o.desconto), (189.90, 329.90, 42))
        self.assertEqual(o.cupom, "BRGAMER20")
        self.assertEqual(o.link, "https://s.click.aliexpress.com/e/_abc")
        self.assertEqual(o.emoji, "🎧")
        self.assertEqual(o.nota, 4.9)
        enviado = http.chamadas[0][2]["data"]
        self.assertEqual(enviado["keywords"], "gaming headset")
        self.assertEqual(enviado["ship_to_country"], "BR")
        self.assertIn("sign", enviado)

    @mock.patch.dict(os.environ, {"ALIEXPRESS_APP_KEY": "k", "ALIEXPRESS_APP_SECRET": "s", "ALIEXPRESS_TRACKING_ID": "t"})
    def test_erro_de_assinatura_vira_mensagem_clara(self):
        http = HttpFalso(Resposta({"error_response": {"code": "IncompleteSignature", "msg": "bad sign"}}))
        with self.assertRaises(Exception) as cm:
            aliexpress.AliExpress(config_um_termo("aliexpress"), http).coletar()
        self.assertIn("md5", str(cm.exception))


class TestShopee(unittest.TestCase):
    def test_cabecalho(self):
        h = shopee.cabecalho("111", "abc", '{"q":1}', ts=1700000000)
        assinatura = hashlib.sha256(b'1111700000000{"q":1}abc').hexdigest()
        self.assertEqual(h, f"SHA256 Credential=111, Timestamp=1700000000, Signature={assinatura}")

    @mock.patch.dict(os.environ, {"SHOPEE_APP_ID": "111", "SHOPEE_SECRET": "abc"})
    def test_coleta(self):
        node = {"itemId": 99, "shopId": 7, "productName": "Headset Gamer HyperX Cloud Stinger 2",
                "priceMin": "199.90", "priceMax": "199.90", "priceDiscountRate": 33, "imageUrl": "https://cf.shopee.com.br/file/x",
                "productLink": "https://shopee.com.br/product/7/99", "offerLink": "https://s.shopee.com.br/abc",
                "commissionRate": "0.08", "sales": 1520, "ratingStar": "4.9", "shopName": "Loja Oficial"}
        http = HttpFalso(Resposta({"data": {"productOfferV2": {"nodes": [node], "pageInfo": {}}}}))
        o = shopee.Shopee(config_um_termo("shopee"), http).coletar()[0]
        self.assertEqual(o.id, "shp:7_99")
        self.assertEqual(o.antigo, 298.36)
        self.assertEqual(o.desconto, 33)
        self.assertEqual(o.comissao, 8)
        corpo = http.chamadas[0][2]["data"].decode()
        assinatura = http.chamadas[0][2]["headers"]["Authorization"].split("Signature=")[1]
        ts = http.chamadas[0][2]["headers"]["Authorization"].split("Timestamp=")[1].split(",")[0]
        self.assertEqual(assinatura, hashlib.sha256(f"111{ts}{corpo}abc".encode()).hexdigest())


class TestAmazon(unittest.TestCase):
    @mock.patch.dict(os.environ, {"AMAZON_CREDENTIAL_ID": "id", "AMAZON_CREDENTIAL_SECRET": "sec", "AMAZON_PARTNER_TAG": "raficou-20"})
    def test_coleta(self):
        item = {"asin": "B0CQKLS4RP", "detailPageURL": "https://www.amazon.com.br/dp/B0CQKLS4RP?tag=raficou-20",
                "itemInfo": {"title": {"displayValue": "Controle DualSense Branco PS5"}},
                "images": {"primary": {"large": {"url": "https://m.media-amazon.com/images/I/x.jpg"}}},
                "offersV2": {"listings": [{"isBuyBoxWinner": True,
                    "price": {"money": {"amount": 349.0}, "savingBasis": {"money": {"amount": 469.0}}, "savings": {"percentage": 26}},
                    "dealDetails": {"badge": "Oferta por tempo limitado", "percentClaimed": 38}}]}}
        http = HttpFalso(Resposta({"access_token": "tok", "expires_in": 3600}),
                         Resposta({"searchResult": {"items": [item]}}))
        o = amazon.Amazon(config_um_termo("amazon"), http).coletar()[0]
        self.assertEqual((o.preco, o.antigo, o.desconto), (349.0, 469.0, 26))
        self.assertIn("38% vendido", o.obs)
        _, url, kw = http.chamadas[1]
        self.assertTrue(url.endswith("/catalog/v1/searchItems"))
        self.assertEqual(kw["headers"]["x-marketplace"], "www.amazon.com.br")
        self.assertEqual(kw["json"]["partnerTag"], "raficou-20")
        self.assertEqual(http.chamadas[0][2]["json"]["scope"], "creatorsapi::default")


class TestMercadoLivre(unittest.TestCase):
    def test_ler_lista(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ml.txt"
            p.write_text("# comentario\nhttps://www.mercadolivre.com.br/controle/p/MLB18617473  https://meli.la/abc\n"
                         "https://produto.mercadolivre.com.br/MLB-1234567890-headset-_JM\nlixo\n", encoding="utf-8")
            itens = mercadolivre.ler_lista(p)
        self.assertEqual([i["id"] for i in itens], ["MLB18617473", "MLB1234567890"])
        self.assertEqual(itens[0]["afiliado"], "https://meli.la/abc")

    @mock.patch.dict(os.environ, {"ML_CLIENT_ID": "1", "ML_CLIENT_SECRET": "2", "ML_REFRESH_TOKEN": "TG-old", "CHAVE_ESTADO": "segredo"})
    def test_coleta_e_token_rotativo(self):
        with tempfile.TemporaryDirectory() as d:
            lista = Path(d) / "ml.txt"
            lista.write_text("https://produto.mercadolivre.com.br/MLB-1234567890-ssd-_JM https://meli.la/xyz\n", encoding="utf-8")
            http = HttpFalso(
                Resposta({"access_token": "APP", "refresh_token": "TG-new"}),
                Resposta([{"code": 200, "body": {"id": "MLB1234567890", "title": "SSD NVMe 1TB", "price": 519.9,
                                                  "pictures": [{"secure_url": "https://http2.mlstatic.com/D_1-I.jpg"}],
                                                  "permalink": "https://produto.mercadolivre.com.br/MLB-1234567890", "status": "active"}}]),
                Resposta({"amount": 379.99, "regular_amount": 519.9}),
            )
            col = mercadolivre.MercadoLivre(config_um_termo("mercadolivre"), http, pasta_estado=Path(d), lista=lista)
            o = col.coletar()[0]
            self.assertEqual((o.preco, o.antigo, o.desconto), (379.99, 519.9, 27))
            self.assertEqual(o.link, "https://meli.la/xyz")
            self.assertTrue(o.imagem_original.endswith("-O.jpg"))
            guardado = (Path(d) / "ml_token.enc").read_bytes()
            self.assertNotIn(b"TG-new", guardado)
            col2 = mercadolivre.MercadoLivre(config_um_termo("mercadolivre"), HttpFalso(), pasta_estado=Path(d), lista=lista)
            self.assertEqual(col2._refresh_guardado(), "TG-new")


class TestHistorico(unittest.TestCase):
    def oferta(self, preco, antigo=None):
        return Oferta(id="x:1", loja="Shopee", nome="Mouse", preco=preco, antigo=antigo, link="l")

    def test_menor_preco_e_desconto_inflado(self):
        with tempfile.TemporaryDirectory() as d:
            h = Historico(Path(d) / "h.json")
            hoje = date(2026, 11, 5)
            for i, p in enumerate([200, 210, 205, 199]):
                h.registrar(self.oferta(p), hoje - timedelta(days=10 - i))
            o = self.oferta(180, antigo=400)
            h.registrar(o, hoje)
            self.assertTrue(o.menor_preco_30d)
            self.assertIn("nunca apareceu", o.alerta)
            o2 = self.oferta(230)
            h.registrar(o2, hoje + timedelta(days=1))
            self.assertIn("Já esteve mais barato", o2.alerta)
            self.assertLess(pontuar(o2), pontuar(o))
            h.salvar()
            self.assertIn("x:1", json.loads((Path(d) / "h.json").read_text()))

    def test_lista_ml_so_entra_em_promocao(self):
        with tempfile.TemporaryDirectory() as d:
            h = Historico(Path(d) / "h.json")
            sem = Oferta(id="ml:1", loja="Mercado Livre", nome="A", preco=100, link="l", termo="lista")
            com = Oferta(id="ml:2", loja="Mercado Livre", nome="B", preco=80, antigo=100, desconto=20, link="l", termo="lista")
            self.assertEqual([o.id for o in processar([sem, com], h, CONFIG)], ["ml:2"])


class TestPublicar(unittest.TestCase):
    def test_feed_e_mescla(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            site = d / "site"; site.mkdir()
            (site / "index.html").write_text("<html></html>")
            a = Oferta(id="ali:1", loja="AliExpress", nome="A", preco=10, link="l", desconto=30, pontos=30)
            b = Oferta(id="ali:2", loja="AliExpress", nome="B", preco=10, link="l", desconto=50, pontos=50)
            semfoto = HttpFalso()
            publicar([a, b], d / "out", site, CONFIG, {}, anterior=d / "estado" / "ult.json", http=semfoto)
            feed = publicar([a], d / "out2", site, CONFIG, {}, anterior=d / "estado" / "ult.json", http=semfoto)
            self.assertEqual([o["id"] for o in feed["ofertas"]], ["ali:2", "ali:1"])  # b continua (dentro de 12 h)
            self.assertFalse(feed["ofertas"][0]["novo"] if "novo" in feed["ofertas"][0] else False)
            self.assertTrue((d / "out2" / "index.html").exists())
            self.assertTrue((d / "out2" / ".nojekyll").exists())


if __name__ == "__main__":
    unittest.main()


class TestSegredos(unittest.TestCase):
    def test_json_do_actions_vira_variavel(self):
        from robo import base
        with mock.patch.dict(os.environ, {"SEGREDOS": json.dumps({"SHOPEE_APP_ID": "123", "github_token": "x"}),
                                          "VARIAVEIS": json.dumps({"ML_REDIRECT_URI": "https://a.github.io/r/"})}, clear=False):
            os.environ.pop("SHOPEE_APP_ID", None)
            base.carregar_segredos()
            self.assertEqual(os.environ["SHOPEE_APP_ID"], "123")
            self.assertEqual(os.environ["ML_REDIRECT_URI"], "https://a.github.io/r/")
            os.environ.pop("SHOPEE_APP_ID"); os.environ.pop("ML_REDIRECT_URI")
