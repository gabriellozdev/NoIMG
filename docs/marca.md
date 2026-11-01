# Marca NoIMG

**Ideia:** um fantasma cuja barra se desfaz em pixels do xadrez de transparência. É o que sobra quando o fundo some. O fantasma (invisível, "sem imagem") é o nome; os pixels soltos são o recorte e a ampliação.

## Arquivos (`frontend/public/brand/`)

| Arquivo | Uso |
|---|---|
| `noimg-horizontal.svg` | padrão: cabeçalho, README, documentos |
| `noimg-stacked.svg` | espaços quadrados (capa, post) |
| `noimg-symbol.svg` | símbolo sozinho, a partir de 48 px |
| `noimg-symbol-small.svg` | símbolo abaixo de 48 px (olhos mais grossos, um pixel só) |
| `noimg-wordmark.svg` | só o nome, quando o símbolo já aparece por perto |
| `noimg-symbol-white.svg` | sobre fundo escuro |
| `noimg-symbol-mono-2e4bff.svg` | uma cor, em cobalto |

Ícones: `frontend/public/favicon.svg`, `favicon.ico` (16/32/48) e `apple-touch-icon.png` usam o corte pequeno sobre o bloco rosa. O ícone do `NoIMG.exe` é `launcher/noimg.ico` (16 a 256 px).

## Cores

| | HEX | Uso |
|---|---|---|
| Tinta | `#141418` | o símbolo e o nome, sempre que possível |
| Rosa | `#FFB3C7` | bloco do ícone do app e do favicon |
| Cobalto | `#2E4BFF` | versão de uma cor; no site, só nas ações |
| Branco | `#FFFFFF` | versão invertida, sobre tinta ou fotos escuras |

Os olhos são furos de verdade: o fundo aparece neles. Não preencha os olhos com outra cor.

## Regras

- **Respiro:** deixe em volta do logo, no mínimo, ¼ da altura do símbolo.
- **Tamanho mínimo:**
  - símbolo completo: 48 px;
  - abaixo disso: `noimg-symbol-small.svg`;
  - horizontal: 32 px de altura.
- **Fundos aprovados:**
  - branco, rosa e amarelo `#FFE27A` com a tinta;
  - tinta e fotos escuras com o branco.
- **Não fazer:**
  - esticar ou girar;
  - trocar a fonte do nome;
  - separar os pixels do fantasma;
  - pôr sombra ou degradê;
  - usar o cobalto sobre o rosa;
  - pôr o símbolo completo em 16 px.

## Pendências

- O nome "noimg" é desenhado com traços de ponta redonda (`stroke`), não contornados. Ele aparece igual em navegadores e no tamanho do SVG. Para gráfica, recorte em vinil ou bordado, um editor vetorial precisa aplicar *Outline Stroke* e *Unite*.
- Não foi feita busca de marca registrada. Fantasmas de pixel lembram, de longe, Pac-Man e Snapchat.
