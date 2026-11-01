# Remoção de fundo: melhorias e benchmark

Este documento registra o que mudou em `noimg/core.py`, por que mudou e como foi medido.
Todas as decisões foram tomadas com o benchmark abaixo, não por inspeção visual.

## Como reproduzir

Os dados não ficam no repositório (licenças de pesquisa). Baixe-os numa pasta `DADOS`:

- **AIM-500** (Li et al., 2021): 500 fotos naturais com alfa anotado à mão, em 7 categorias e 3 tipos.
  Espelho em parquet: <https://huggingface.co/datasets/nobg/AIM-500> (`aim500.parquet`).
- **PPM-100** (Ke et al., 2020, MODNet): 100 retratos com cabelo e alfa anotado.
  <https://huggingface.co/datasets/realdream-ai/ppm-matting> (descompacte `PPM-100.zip`).

```bash
python tests/bench_remocao.py prepare --data DADOS --set CONJUNTO   # 6 por categoria + 8 retratos (semente 7)
python tests/bench_remocao.py raw  --set CONJUNTO                   # roda o modelo, com cache
python tests/bench_remocao.py eval --set CONJUNTO --out eval.json --configs legado,padrao-novo
python tests/resumo_bench.py eval.json --por category
python tests/bench_remocao.py fg   --set CONJUNTO --out fg.json
python tests/bench_remocao.py perf --out perf.json
python -m unittest tests.test_remocao
```

O pipeline anterior continua disponível como `core.LEGACY_MATTING`, para comparação.

**Conjunto usado:** 54 imagens, todas com no máximo 1600 px:
- 42 do AIM-500, 6 por categoria: animal, fruta, móvel, planta, retrato, brinquedo e transparente;
- 8 retratos com cabelo do PPM-100;
- 4 recortes quadrados.

Por orientação, são 25 verticais, 24 horizontais e 5 quadradas.

Há também um conjunto com **24 recortes em proporção extrema** (2,4:1 e 1:2,4), tirados das mesmas fotos.

**Métricas:** SAD/1000, MSE×1000, Grad/1000 e Conn/1000, como no Composition-1k, com o alfa em 0–1. As variantes com sufixo "trans" são restritas à região de transição da referência (0 < α < 1, dilatada), que é onde ficam cabelos, pelos e bordas. Para todas, menor é melhor.

**Modelo:** só o ISNet foi medido. O BiRefNet-lite não roda neste PC de 4 GB: falta memória a 1024 px, e por isso o NoIMG já cai para o ISNet em máquinas com menos de 8 GB.

## 1. Proporção na entrada do modelo

Antes, a imagem era sempre achatada para 1024×1024. Agora há três modos, definidos em `MattingConfig.letterbox`:
- **achatado:** o comportamento anterior;
- **letterbox:** o lado maior vira 1024, o resto é preenchido com padding, e o padding é retirado da máscara depois;
- **automático:** escolhe um dos dois pela proporção da imagem.

| Conjunto | Entrada | SAD | MSE | Conn | MSE trans |
|---|---|---|---|---|---|
| normal (54) | achatado | **152,5** | **86,7** | **152,6** | 60,8 |
| normal (54) | letterbox, padding cor média | 162,9 | 91,9 | 163,5 | 61,2 |
| normal (54) | letterbox, padding borda repetida | 160,9 | 90,7 | 161,9 | 60,8 |
| extremo (24) | achatado | 125,9 | 122,0 | 130,3 | 191,4 |
| extremo (24) | **letterbox, padding cor média** | **72,8** | **68,1** | **74,0** | **126,2** |
| extremo (24) | letterbox, padding borda repetida | 92,0 | 92,5 | 94,4 | 144,4 |

(todas com o refino novo; ver seção 2)

**O que os números mostram:**
- Em proporção comum (~3:2), achatar é melhor. É o pré-processamento com que o ISNet (DIS) e o BiRefNet foram treinados: os dois redimensionam para 1024×1024 sem manter a proporção.
- O letterbox não erra por falta de resolução, e sim por interpretação. Com outro enquadramento, o modelo muda o que considera objeto: no banco do AIM-500, por exemplo, o assento some.
- Em proporção extrema, o achatamento distorce 2,4x, e o letterbox reduz o erro em ~42%.
- O padding na **cor média** do modelo é melhor que repetir a borda. Repetir a borda estende o fundo da foto (rua, chão) e confunde o modelo.
- Combinar as duas visões (média das probabilidades) melhora a transição (MSE trans 57,3), mas piora SAD e Conn e dobra o tempo de inferência. Não foi adotado.

**Padrão:** `letterbox="auto"`. A imagem é achatada até a proporção 2:1, e acima disso usa letterbox com padding na cor média. Foram testados os pontos 1,5:1 e 2,4:1; o limite de 2:1 fica entre eles e **não foi ajustado fino**.

## 2. Refino das bordas

Antes, o refino era um guided filter com guia cinza (r = 2 px de modelo), seguido de um "contraste ×1,6" na borda. Agora é um guided filter com guia **RGB** (covariância 3×3 da cor; He et al., eq. 19), r = 6 px de modelo, eps 1e-4, **sem** o contraste. O filtro só é aplicado na faixa incerta da borda: miolo e fundo seguros não mudam.

Para limitar a memória, o processamento é feito em tiras de 384 linhas dentro da caixa que contém a borda.

| Config (achatado) | MSE trans | Grad | Grad trans | Vence legado (MSE trans) | Refino (1600 px) |
|---|---|---|---|---|---|
| legado: cinza r2 + contraste 1,6 | 70,8 | 4,91 | 2,99 | — | 0,3 s |
| cinza r2, sem contraste | 63,4 | 3,84 | 2,37 | 44/54 | 0,2 s |
| cinza r6 | 65,1 | 3,85 | 2,45 | 37/54 | 0,4 s |
| RGB r4 | 61,6 | 3,67 | 2,23 | 47/54 | 0,7 s |
| **RGB r6 (novo)** | **60,8** | **3,57** | **2,16** | **46/54** | 0,9–1,3 s |
| RGB r8 | 60,4 | 3,54 | 2,14 | 41/54 | 1,4 s |

**O que os números mostram:**
- O "contraste ×1,6" piorava a borda (MSE trans 71 contra 63). Era um filtro que disfarçava o borrado, e foi removido.
- Com o mesmo raio, o guia RGB é melhor que o cinza. Um teste unitário mostra o caso extremo: vermelho e verde com o mesmo tom de cinza, borda que só o RGB enxerga.
- Na transição, o RGB r6 vence o legado em **todas** as 8 categorias. No cabelo, o MSE trans vai de 44,0 para 36,0.
- O SAD em cabelo e em móveis subiu um pouco (9,6 → 12,2 e 14,8 → 19,6). Isso vem de valores fracos fora da borda real que o contraste antigo zerava à força. MSE e Grad melhoraram nessas mesmas categorias.

## 3. Normalização do alfa

Antes, toda saída do modelo era esticada por min-max para 0–1. Foram comparadas três opções:
- **min-max:** o comportamento anterior;
- **guarded:** estica no máximo até 0,8 → 1;
- **none:** usa a saída do modelo como está.

| Caso | min-max | guarded | none |
|---|---|---|---|
| 54 imagens com objeto (SAD / MSE trans) | 152,46 / 60,79 | 152,46 / 60,79 | 152,46 / 60,77 |
| 12 recortes só de fundo (alfa médio; ideal 0) | 0,0186 | **0,0054** | 0,0054 |
| pior recorte só de fundo | 0,092 | **0,064** | 0,064 |

- Quando há objeto, a saída do ISNet já vai de ~0 a ~1, e as três opções empatam.
- Quando não há objeto, o modelo prevê no máximo ~0,01, e o min-max estica isso até 1, inventando objeto (3,4x mais alfa espúrio).
- O min-max também é frágil a qualquer desvio no piso. Ao combinar visões ampliadas antes de normalizar, valores cúbicos abaixo de 0 deslocaram o fundo inteiro para ~0,07, acima do corte de 0,02. Isso foi medido durante este trabalho.

**Padrão:** `norm="guarded"`. Ele empata quando o modelo tem certeza e não infla quando não tem.

## 4. Cor do primeiro plano

Antes, a cor era estimada por "blur fusion" (Forte & Pitié). Agora é a estimativa multinível de Germer et al. (2020), em numpy vetorizado, sem dependências novas. Ela resolve I = αF + (1 − α)B do nível de 1 px até a resolução original. Pixels com α ≥ 0,999 continuam idênticos ao original. O upscale continua usando o método antigo, sem mudança de comportamento.

A medida usa composições sintéticas com cor conhecida: a foto do conjunto, com o alfa de referência, sobre o fundo de outra foto. O estimador recebe só a composição e o alfa.

| Método | Erro de cor (ponderado por α, na borda) | MSE da composição | Melhor que blur | Tempo |
|---|---|---|---|---|
| sem correção | 38,96 | 3,06 | — | — |
| blur fusion (anterior) | 33,33 | 2,26 | — | 1,6 s |
| **multinível (novo)** | **29,30** | **1,72** | **42/49** | 5,3 s |

O multinível é melhor em todas as 8 categorias. Sobre um fundo novo, o erro da composição é (F − F_real)·α, então ele é o mesmo para fundo claro, escuro ou colorido. As pranchas visuais mostram os três fundos.

## 5. ViTMatte (experimental, fora do padrão)

`noimg/experimental_vitmatte.py` usa o ViTMatte-S (`hustvl/vitmatte-small-composition-1k`) para refinar a máscara do ISNet. O trimap vem da máscara do ISNet: miolo e fundo certos por erosão, e 10 px de dúvida de cada lado da borda. O alfa do ViTMatte só é usado dentro da faixa de dúvida.

Avaliação feita nas 16 imagens mais difíceis do conjunto: 8 retratos com cabelo, 6 transparentes e 2 animais. Resolução de 768 px.

| Métrica | padrão novo | + ViTMatte | ViTMatte melhor em |
|---|---|---|---|
| SAD | 214,8 | 203,5 (−5%) | 12/16 |
| MSE | 119,4 | 114,5 (−4%) | 12/16 |
| Grad | 5,91 | 4,57 (−23%) | 9/16 |
| MSE trans | 94,2 | 83,2 (−12%) | 10/16 |
| MSE trans, cabelo (8) | 36,0 | 30,5 | — |
| MSE trans, transparente (6) | 199,1 | 175,7 | — |
| MSE trans, animal (2) | 12,0 | 16,1 (pior) | — |

Visualmente é o melhor resultado em cabelo. Ele remove a névoa que o ISNet deixa em volta de fios soltos e recupera mechas: veja `cabelo_vitmatte.png` nas pranchas.

**Custo medido** (processo separado, retrato de 1067×1600, memória comprometida):

| Lado no ViTMatte | Tempo do refino | Pico de memória |
|---|---|---|
| 512 px | 5–8 s | 1,05 GB |
| 768 px | 10–20 s | 1,34 GB |
| 1024 px | 22–44 s | 1,72 GB |

Numa das execuções a 1024 px, com outros programas abertos, o processo foi encerrado por falta de memória neste PC de 4 GB.

**Por que não é o padrão:**
- **inconsistência:** ganha em 10 de 16 imagens difíceis e piora em animais;
- **custo:** dobra ou triplica o tempo por imagem, e o pico de memória sobe 0,3–0,7 GB;
- **dependência:** exige `transformers` (com `huggingface_hub`, `safetensors` e `tokenizers`) e ~100 MB de pesos;
- **licença:** os pesos são Apache-2.0, mas o modelo foi treinado no Composition-1k da Adobe, de uso restrito a pesquisa. Isso precisa ser avaliado antes de qualquer uso comercial.

**Como testar:** `pip install -r requirements-experimental.txt` e depois `python tests/bench_remocao.py vitmatte --set CONJUNTO --out vitmatte.json --max-side 768`.

## 6. Tempo e memória ponta a ponta

`python tests/bench_remocao.py perf`, um processo por medida, com a memória comprometida (`PeakPagefileUsage`). O *working set* não é confiável aqui, porque o Windows o reduz quando falta RAM.

| Imagem | Legado | Novo | Pico de memória (legado → novo) |
|---|---|---|---|
| 1600×1067 | 21,7 s | 16,5 s | 998 → 999 MB |
| 1067×1600 | 13,1 s | 19,2 s | 1003 → 1002 MB |
| 1400×1400 | 12,9 s | 15,7 s | 1002 → 966 MB |
| 2400×1600 | 14,0 s | 20,8 s | 1023 → 1171 MB |

O tempo ponta a ponta oscila bastante neste PC: a inferência do modelo domina e varia entre execuções. Por etapa, a 1600 px:
- refino RGB: 0,2–0,4 s → 0,7–1,3 s;
- cor multinível: ~1,6 s → ~5 s.

A resolução de inferência não mudou (1024 px).

## Padrão final (`core.DEFAULT_MATTING`)

`letterbox="auto"` (2:1), `pad="mean"`, `norm="guarded"`, `guide="rgb"`, `gf_radius=6`, `gf_eps=1e-4`, `contrast=1.0`, `fg="ml"`.

| Conjunto | SAD | MSE | Grad | Conn | MSE trans | Vence o legado |
|---|---|---|---|---|---|---|
| normal (54): legado → novo | 152,5 → 152,5 | 89,1 → 86,7 | 4,91 → 3,57 | 152,8 → 152,6 | 70,8 → 60,8 | 46/54 |
| extremo (24): legado → novo | 125,1 → 72,8 | 128,7 → 68,1 | 5,39 → 2,97 | 128,6 → 74,0 | 210,7 → 126,2 | 20/24 |

## Limitações que continuam

- **Névoa em cabelo solto:** a previsão do ISNet em cabelo solto é grosseira e deixa uma névoa clara em volta dos fios. O contraste antigo escondia a névoa, mas piorava a borda. O ViTMatte resolve, a um custo alto (seção 5).
- **Objetos transparentes** (vidro, plástico) continuam sendo a pior categoria (MSE trans ~200). O ISNet trata vidro como opaco ou como fundo, e o refino de borda não muda isso.
- **Fotos sem objeto principal claro** (tipo NS do AIM-500): o modelo escolhe um objeto, e a escolha pode não ser a do usuário.
- **Limite de 2:1 da regra automática:** foi escolhido entre os pontos medidos (1,5:1 e 2,4:1), sem varredura fina.
- **BiRefNet não medido:** não roda em 4 GB. O pré-processamento dele foi mantido (ImageNet, 1024×1024, achatado), mas os parâmetros novos não foram validados com ele.
- **Amostra pequena:** 54 + 24 imagens, poucas por categoria. Diferenças pequenas (±2%) não são conclusivas.
- **Métrica da cor do primeiro plano:** usa composições sintéticas. Não há referência de F real em fotos naturais.
