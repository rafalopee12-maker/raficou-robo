#!/usr/bin/env bash
# Não deixa o robô rodar se o ramo "dados" existe mas não foi baixado (evita apagar o histórico).
resultado="$1"
if [ "$resultado" != "success" ] && git ls-remote --exit-code --heads origin dados >/dev/null; then
  echo "::error::O ramo dados existe mas não foi baixado. Parando para não apagar o histórico."
  exit 1
fi
rm -rf estado/.git
mkdir -p estado
