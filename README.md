# NoIMG

Ferramenta local com dois modos:

1. **Melhorar qualidade**: aumenta a imagem 2x ou 4x com IA (Real-ESRGAN). Se a imagem tiver fundo transparente, o resultado continua transparente.
2. **Remover fundo**: recorta o objeto na **mesma resolução** da original e salva em PNG sem perdas. Os pixels do objeto continuam idênticos aos da original, e só as bordas semitransparentes recebem correção de cor.

Tudo roda no seu PC. Nenhuma imagem é enviada para a internet.

### Padronizar tamanho (dentro de "Melhorar qualidade")
Serve para um lote de personagens ou produtos com tamanhos e nitidez diferentes. Você pode mandar até 30 imagens de uma vez.

1. O NoIMG corta as sobras transparentes de cada imagem, para cada objeto ocupar o mesmo espaço.
2. Encaixa todas no tamanho escolhido (512, 1024, 2048, 1080×1350 ou personalizado), com margem ajustável. Dá para alinhar pela base, que deixa os personagens no mesmo "chão", ou no centro. Também dá para preencher a tela toda.
3. Com "Nitidez igual em todas" ligado, cada imagem é levada a 1/2 ou 1/4 do tamanho final e ampliada pelo Real-ESRGAN. Assim as borradas e as nítidas terminam com a mesma textura. Desligue essa opção para preservar o detalhe original das imagens que já são grandes.
4. No fim, você baixa as imagens uma a uma ou todas num ZIP.

## Como instalar

Você precisa de Python 3.12 ou mais novo e de Node.js 20 ou mais novo.

1. Clone o repositório.
2. Dê dois cliques em `instalar.bat`. Ele cria o ambiente Python, baixa os modelos de IA (cerca de 540 MB, conferidos por SHA-256) e gera o site.

Os modelos e o site gerado (`models/` e `web/dist/`) ficam fora do git. Dois modelos passam do limite de 100 MB por arquivo do GitHub.

## Como usar

Dê dois cliques em `iniciar.bat`. O navegador abre em http://127.0.0.1:7860.

## Frontend

Fica em `frontend/` e usa React, Vite e Tailwind v4 com o design system Ice Blue (`src/index.css`). Componentes do VengeanceUI (MIT) adaptados para Vite estão em `src/components/ui/`: spotlight-navbar, border-beam, stagger-text, stats-counter e faq-accordion.

- Para desenvolver, rode `npm run dev` em `frontend/` com o `app.py` aberto. O Vite repassa `/api` para a porta 7860.
- Para publicar, rode `npm run build`. O resultado vai para `web/dist`, que o `app.py` serve.
- Para regenerar as demos de antes/depois, rode `python gerar_demos.py`. Elas são feitas pelo próprio NoIMG.
- As fotos vêm do Unsplash (via Lorem Picsum, licença Unsplash). Os créditos ficam em `frontend/public/img/creditos.json` e aparecem no rodapé.

## O que a engenharia reversa (REA) mostrou

### iLoveIMG: upscale
- O navegador **não processa nada**. O site envia o arquivo (plupload) para um servidor de trabalho e chama `POST {workerServer}/{apiVersion}/upscale` com `task`, `server_filename` e `scale` (2 ou 4). A resposta é a imagem pronta (`blob`).
- Opções da página: "Size multiplier" com `data-value="2"` e `data-value="4"`. Limites: 6 MB e `pxsize: 33177600` (≈33 MP na saída). Aceita só JPG e PNG.
- O modelo de IA fica no servidor e não aparece no código do site. Aqui usamos o **Real-ESRGAN** (o padrão aberto mais usado para isso).

### remove.bg: remoção de fundo
- O servidor devolve um **ZIP** (`ZipCanvas.fromBinary` no bundle) com:
  - `color.jpg`: a cor do objeto, já com a cor do fundo removida das bordas
  - `alpha.png`: a máscara de transparência, suave e em resolução total
  - opcionais: `shadow_color.jpg`, `shadow_alpha.png`, `semi_transparency…`
- O navegador junta as duas imagens pixel a pixel (`Jt.data[i+3] = alpha.data[i]`) para montar o PNG final.
- **Por isso a qualidade é boa:** a máscara é calculada à parte, aplicada na resolução original, e a cor das bordas é "descontaminada".

### Como o NoIMG reproduz isso
| Etapa | remove.bg / iLoveIMG | NoIMG |
|---|---|---|
| Segmentação | modelo próprio no servidor | ISNet (ou BiRefNet em PCs com ≥ 8 GB de RAM), 1024 px |
| Máscara em alta resolução | `alpha.png` em resolução total | *fast guided filter* usando a foto original como guia |
| Cor das bordas | `color.jpg` descontaminado | *blur-fusion foreground estimation* (Forte & Pitié) |
| Junção | canvas no navegador | `numpy`, salvo em PNG sem perdas |
| Upscale | servidor, 2x/4x | Real-ESRGAN (x4v3 rápido, x4plus/x2plus máximo) |
| Upscale com transparência | não suportado (só JPG/PNG sem alfa) | RGB e alfa ampliados separadamente, com a cor "vazada" para as áreas transparentes (evita halo escuro) |

## Modelos (`models/`)
- `realesr-general-x4v3.pth`, `RealESRGAN_x4plus.pth`, `RealESRGAN_x2plus.pth`: releases oficiais do xinntao/Real-ESRGAN (BSD-3)
- `isnet-general-use.onnx`, `birefnet-lite.onnx`: releases do danielgatis/rembg

## Desempenho neste PC (i3-3110M, 4 GB)
- Remover fundo: cerca de 15 a 40 s por foto
- Upscale 2x "Rápido" de 400×400 com transparência: cerca de 30 s. "Máxima qualidade" é cerca de 10x mais lento.
- Limites de entrada: 4 MP para 2x, 1 MP para 4x, 40 MP para remover fundo
