"""Troca o código de autorização do Mercado Livre por um refresh_token e guarda criptografado.

python -m robo.ml_login TG-xxxxxxxx      (o workflow Robô de ofertas faz isso quando você cola o código)
"""
from __future__ import annotations

import sys
from pathlib import Path

from .base import env, sessao
from .mercadolivre import API, MercadoLivre


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    codigo = (args[0] if args else env("ML_CODIGO")).strip()
    if not codigo:
        print("Passe o código TG-... que aparece no endereço depois de autorizar o app.")
        return 2
    for v in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REDIRECT_URI", "CHAVE_ESTADO"):
        if not env(v):
            print(f"Falta o segredo {v}.")
            return 2
    r = sessao().post(f"{API}/oauth/token", timeout=30, headers={"Accept": "application/json"}, data={
        "grant_type": "authorization_code",
        "client_id": env("ML_CLIENT_ID"),
        "client_secret": env("ML_CLIENT_SECRET"),
        "code": codigo,
        "redirect_uri": env("ML_REDIRECT_URI"),
    })
    j = r.json() if r.content else {}
    if r.status_code != 200 or not j.get("refresh_token"):
        print(f"O Mercado Livre recusou (HTTP {r.status_code}): {j.get('message') or j.get('error') or r.text[:200]}")
        print("O código vale só alguns minutos e só uma vez. Gere outro e rode de novo.")
        return 1
    MercadoLivre({}, pasta_estado=Path("estado"))._guardar_refresh(j["refresh_token"])
    print("Pronto! Mercado Livre conectado. O token ficou guardado criptografado em estado/ml_token.enc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
