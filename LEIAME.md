# Robô de ofertas do RAFICOU!

O robô procura promoções gamer no AliExpress, na Shopee, na Amazon e no Mercado Livre a cada 30 minutos. Ele já pega o seu link de afiliado e, quando a loja informa, o cupom do produto. As ofertas aparecem na aba **Ofertas** do app RAFICOU!. Você escolhe uma, toca em **Montar post**, confere a imagem e compartilha no Telegram ou no WhatsApp.

```
GitHub (grátis, a cada 30 min)                         seu celular
┌──────────────────────────────┐   ofertas.json   ┌──────────────────────────┐
│ robô → APIs de afiliado      │ ───────────────▶ │ RAFICOU! → aba Ofertas   │
│ filtro gamer + histórico     │   + fotos        │ Montar post → Compartilhar│
└──────────────────────────────┘                  └──────────────────────────┘
```

Tudo roda na sua conta do GitHub, sem servidor pago.

---

## 1. Instalar o app novo (RAFICOU-1.2.apk)

A versão 1.2 traz a aba Ofertas e a permissão de internet, que a 1.1 não tinha.

1. **Desinstale a 1.1 primeiro.** A 1.2 foi assinada com uma chave nova, então o Android não instala uma por cima da outra. Os links dos grupos e os QR codes voltam ao padrão. Se você tinha trocado algum, troque de novo em *Grupos e rodapé da imagem*.
2. Abra o `RAFICOU-1.2.apk` no celular e permita instalar de fonte desconhecida, se o Android pedir.
3. Guarde os arquivos `raficou-chave.p12` e `senha-da-chave.txt` num lugar seguro, fora do celular. As próximas versões precisam ser assinadas com essa mesma chave pra atualizar sem desinstalar.

O app já abre na aba Ofertas, com **exemplos**. As ofertas reais aparecem depois do passo 5.

> Sem instalar nada: o mesmo app também funciona no navegador, no endereço do seu robô (passo 5). Lá o botão **Compartilhar** abre o Telegram e o WhatsApp com a imagem e o texto.

---

## 2. Colocar o robô no GitHub (dá pra fazer tudo pelo celular)

1. Crie uma conta em github.com e um repositório **público** vazio chamado `raficou-robo`. Precisa ser público pro site ser grátis. As chaves das lojas **não** ficam visíveis: elas vão em *Secrets*.
2. **Envie o zip:** abra `github.com/SEU-USUARIO/raficou-robo/upload/main`, toque em *choose your files*, escolha o `raficou-robo.zip` e toque em **Commit changes**. Não precisa descompactar.
3. **Ligue o site:** em **Settings → Pages**, em *Source*, escolha **GitHub Actions**.
4. **Crie o arquivo do robô:** abra `github.com/SEU-USUARIO/raficou-robo/new/main`. No nome do arquivo, escreva `.github/workflows/robo.yml`. No conteúdo, cole o texto do arquivo `.github/workflows/robo.yml` que veio no zip. Depois toque em **Commit changes**.
5. Pronto: o robô roda sozinho, desempacota o zip na primeira vez e publica o site. Dá pra acompanhar em **Actions**.

> Dica: no Chrome do celular, use **⋮ → Site para computador** nas telas de configuração do GitHub.

---

## 3. Cadastrar as chaves de cada loja

Em **Settings → Secrets and variables → Actions → New repository secret**, crie os segredos das lojas que você já tem. Loja sem chave é pulada, e o resto funciona normalmente.

| Loja | Segredos | Onde conseguir |
|---|---|---|
| **AliExpress** | `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET`, `ALIEXPRESS_TRACKING_ID` | Cadastro de afiliado em portals.aliexpress.com. Depois, crie um app do tipo *Affiliate* em openservice.aliexpress.com (é ali que ficam a App Key e o App Secret). O Tracking ID fica no Portals, em *Account → Tracking ID*. |
| **Shopee** | `SHOPEE_APP_ID`, `SHOPEE_SECRET` | affiliate.shopee.com.br. Depois de aprovado, entre em *Open API* e copie o App ID e o Secret. A aprovação é manual e pode levar alguns dias. |
| **Amazon** | `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, `AMAZON_PARTNER_TAG` | Associados Amazon → *Ferramentas → Creators API* → criar aplicativo e credencial. A Amazon só libera com **10 vendas qualificadas nos últimos 30 dias**. A Partner Tag é a sua tag, tipo `raficou-20`. |
| **Mercado Livre** | `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `CHAVE_ESTADO` e a variável `ML_REDIRECT_URI` | Veja o passo 4. |

Se o AliExpress der erro de assinatura (`IncompleteSignature`), crie em **Variables** (aba ao lado de Secrets) a variável `ALIEXPRESS_SIGN_METHOD` com o valor `md5`.

---

## 4. Mercado Livre (lista de acompanhamento)

O Mercado Livre não deixa apps de terceiros usarem a busca da API. Então, aqui, o robô **acompanha os produtos que você escolher** e avisa quando eles entram em promoção ou chegam no menor preço dos últimos 30 dias.

1. Em developers.mercadolivre.com.br, abra o **DevCenter** e crie um aplicativo:
   - *URI de redirect*: o endereço do seu site, por exemplo `https://SEU-USUARIO.github.io/raficou-robo/`
   - *Permissões funcionais*: leitura de **Itens** e **Produtos**
2. No GitHub, crie os segredos `ML_CLIENT_ID` (o ID do app) e `ML_CLIENT_SECRET` (a chave secreta). Crie também `CHAVE_ESTADO`, com qualquer frase longa que só você saiba: ela protege o token que o robô guarda.
3. Em **Variables**, crie `ML_REDIRECT_URI` com o mesmo endereço do item 1.
4. Abra no navegador do celular (trocando o ID e o endereço pelos seus):
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_ID&redirect_uri=https://SEU-USUARIO.github.io/raficou-robo/`
5. Autorize. Você volta pro seu site, que mostra o **Código do Mercado Livre** com um botão Copiar.
6. No GitHub, abra **Actions → Robô de ofertas → Run workflow**, cole o código no campo *Só para conectar o Mercado Livre* e toque em **Run workflow**. O código vale só alguns minutos.
7. Edite o arquivo `mercadolivre.txt` com os links dos produtos, um por linha. Se quiser, coloque o seu link de afiliado `meli.la` ao lado de cada um. Sem ele, o app avisa *Sem link de afiliado* e você gera o link no app do Mercado Livre.

---

## 5. Ligar o robô e conectar o app

1. Abra **Actions → Robô de ofertas → Run workflow**. Na primeira vez, o GitHub pode pedir pra você confirmar que quer ativar os workflows.
2. No fim, o resumo da execução mostra uma tabela: ✅ (ofertas encontradas), ⏸️ (sem chaves) ou ❌ (erro, com o motivo).
3. O endereço do seu robô é `https://SEU-USUARIO.github.io/raficou-robo/`.
4. No app: **Ofertas → Ajustes do robô** (lá embaixo) → cole o endereço → **Salvar e buscar**.

A partir daí, o robô roda sozinho a cada 30 minutos.

---

## 6. Usar no dia a dia

- **Filtros**: loja, categoria, desconto mínimo, *Com cupom*, *Menor preço 30 dias* e *Esconder postadas*.
- **🔥 Menor preço em 30 dias**: o preço de hoje é o menor que o robô viu no período.
- **⚠️ alertas**: *"O preço 'de' nunca apareceu"* quer dizer que o desconto pode estar inflado. *"Já esteve mais barato"* mostra quando foi.
- **Montar post** preenche foto, nome, preços, cupom, observação e link na aba *Post de oferta*. Confira e toque em **Compartilhar**. A oferta fica marcada como ✓ Postada.
- O contador vermelho na aba mostra quantas ofertas você ainda não postou.

---

## 7. Ajustar o que o robô procura (`config.json`)

- `termos`: o que buscar. O campo `en` é o termo em inglês, que o AliExpress entende melhor. O campo `lojas` limita a busca a algumas lojas.
- `filtros`: `desconto_minimo` (15%), `preco_minimo` (R$ 30), `nota_minima` (4,5), `vendas_minimas` (30) e por quantas horas uma oferta continua no app depois de sumir da busca (12 h).
- `palavras_bloqueadas`: corta capinhas, películas, adesivos e outros acessórios que não interessam.

Quando você salva uma mudança no GitHub, o robô roda de novo na hora.

---

## Limites que vale saber

- **Cupons**: o AliExpress informa o cupom do produto pela API. Shopee, Amazon e Mercado Livre não informam. Nessas lojas o robô mostra o desconto e as ofertas relâmpago, e você digita o cupom na mão, se tiver um.
- **Shopee**: a API não traz o preço "de". O robô calcula esse valor a partir do percentual de desconto que a Shopee mostra.
- **Amazon**: se as vendas caírem abaixo de 10 em 30 dias, a Amazon pausa o acesso, e a Amazon aparece com ⏸️/❌ até voltar.
- **GitHub**: o horário pode atrasar alguns minutos em momentos de pico. Se o repositório ficar 60 dias sem nenhuma atividade, o GitHub pode pausar o agendamento. Se isso acontecer, entre em *Actions* e clique em **Enable workflow**.
- As fotos ficam guardadas só enquanto a oferta está no app.

---

## Para quem mexe com código

```bash
pip install -r requirements.txt
python -m robo --demo                        # gera saida/ com ofertas de exemplo, sem chaves
python -m unittest discover -s tests -t .    # testes com respostas simuladas das lojas
```

Gerar uma versão nova do APK (mesma chave = atualiza sem desinstalar):

```bash
cd apk
python gerar_apk.py --base RAFICOU-1.2.apk --html ../site/index.html --saida RAFICOU-1.3.apk \
    --chave raficou-chave.p12 --senha "SENHA" --versao 1.3 --codigo 4 \
    --feed https://SEU-USUARIO.github.io/raficou-robo/
```

O `--feed` grava o endereço do robô dentro do app, e aí não é preciso colar o endereço em Ajustes.
