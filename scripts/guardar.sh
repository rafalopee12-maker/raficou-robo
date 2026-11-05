#!/usr/bin/env bash
# Guarda estado/ (histórico de preços e token do Mercado Livre) no ramo "dados", sempre com um commit só.
set -e
mkdir -p estado && cd estado
rm -rf .git
git init -q -b dados
git config user.name "robo-raficou"
git config user.email "robo-raficou@users.noreply.github.com"
git add -A
git commit -qm "estado $(date -u +%FT%TZ)" --allow-empty
git push -qf "https://x-access-token:${TOKEN}@github.com/${GITHUB_REPOSITORY}.git" dados
