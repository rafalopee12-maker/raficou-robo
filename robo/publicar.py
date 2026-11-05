"""Monta a pasta do site: index.html (app), ofertas.json e as fotos reduzidas em img/."""
from __future__ import annotations

import io
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import log, sessao
from .modelo import Oferta, agora_iso, slug

LADO_MAX = 900


def baixar_foto(http, url: str, destino: Path) -> bool:
    if not url:
        return False
    try:
        r = http.get(url, timeout=20)
        if r.status_code != 200 or not r.headers.get("Content-Type", "image").startswith("image"):
            return False
        from PIL import Image
        img = Image.open(io.BytesIO(r.content))
        img = img.convert("RGBA") if img.mode in ("P", "LA") else img
        if img.mode == "RGBA":
            fundo = Image.new("RGB", img.size, "white")
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        img = img.convert("RGB")
        img.thumbnail((LADO_MAX, LADO_MAX))
        destino.parent.mkdir(parents=True, exist_ok=True)
        img.save(destino, "JPEG", quality=85, optimize=True)
        return True
    except Exception as e:
        log.info("foto não baixou (%s): %s", url[:80], e)
        return False


def feed_anterior(caminho: Path) -> list[dict]:
    try:
        return json.loads(caminho.read_text(encoding="utf-8")).get("ofertas", [])
    except (FileNotFoundError, ValueError):
        return []


def mesclar(novas: list[Oferta], anteriores: list[dict], horas: int, maximo: int) -> list[dict]:
    """Ofertas desta rodada + as da rodada anterior que ainda não venceram (some se a loja tirar)."""
    corte = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    vistas = {o.id for o in novas}
    lista = [o.para_json() for o in novas]
    for a in anteriores:
        if a.get("id") not in vistas and a.get("visto_em", "") >= corte:
            a["novo"] = False
            lista.append(a)
    lista.sort(key=lambda d: d.get("pontos", 0), reverse=True)
    return lista[:maximo]


def publicar(ofertas: list[Oferta], saida: Path, site: Path, config: dict, resumo: dict,
             anterior: Path | None = None, http=None) -> dict:
    """anterior: cópia do feed da rodada passada (fica em estado/, que é guardado entre execuções)."""
    http = http or sessao()
    f = config.get("filtros", {})
    pasta_img = saida / "img"
    anteriores = feed_anterior(anterior or (saida / "ofertas.json"))
    lista = mesclar(ofertas, anteriores, f.get("manter_oferta_por_horas", 12), f.get("maximo_no_feed", 200))

    for d in lista:
        nome = f"{slug(d['id'].replace(':', '-'), 40)}.jpg"
        if (pasta_img / nome).exists() or baixar_foto(http, d.get("imagem_original", ""), pasta_img / nome):
            d["imagem"] = f"img/{nome}"
        else:
            d.pop("imagem", None)
    feed = {"versao": 1, "gerado_em": agora_iso(), "total": len(lista), "lojas": resumo, "ofertas": lista}

    saida.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(feed, ensure_ascii=False, indent=1)
    (saida / "ofertas.json").write_text(texto, encoding="utf-8")
    if anterior:
        anterior.parent.mkdir(parents=True, exist_ok=True)
        anterior.write_text(texto, encoding="utf-8")

    usadas = {Path(d["imagem"]).name for d in lista if d.get("imagem")}
    for p in pasta_img.glob("*.jpg") if pasta_img.exists() else []:
        if p.name not in usadas:
            p.unlink()

    if site.exists():
        for arq in site.iterdir():
            if arq.is_file():
                shutil.copy2(arq, saida / arq.name)
    (saida / ".nojekyll").write_text("")
    return feed
