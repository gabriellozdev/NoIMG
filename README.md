# NoIMG

**A local image processing tool powered by AI.**

NoIMG is a desktop-based image processing tool that provides AI-powered upscaling, background removal, and batch image standardization. Everything runs locally on your machine — **your images are never uploaded to external servers.**

## Features

### 1. AI Image Upscaling

Enhance image resolution using [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN).

- Upscale images by **2× or 4×**.
- Supports JPG and PNG formats.
- Preserves transparency in images with alpha channels.
- Multiple AI models available, balancing processing speed and output quality.

### 2. Background Removal

Remove image backgrounds while preserving the original resolution.

- Exports lossless PNG images.
- Preserves the original RGB values of foreground pixels.
- Applies color decontamination to semi-transparent edges.
- Uses AI-based segmentation and high-resolution alpha refinement.

### 3. Batch Image Standardization

Standardize up to **30 images simultaneously**, making it easier to prepare character sprites, product images, and other visual assets with consistent dimensions.

The process includes:

1. **Automatic Cropping:** Removes transparent padding so each object occupies a consistent amount of space.
2. **Canvas Standardization:** Fits images into predefined sizes (512, 1024, 2048, 1080×1350) or custom dimensions.
3. **Flexible Alignment:** Aligns objects by their bottom edge or center, with adjustable margins and an optional full-canvas mode.
4. **Consistent Sharpness:** Optionally resizes images to ½ or ¼ of the target resolution before applying Real-ESRGAN, helping achieve a more consistent texture across images.
5. **Batch Export:** Download individual results or export the entire batch as a ZIP archive.

## Installation

### Requirements

- Python 3.12+
- Node.js 20+

### Setup

1. Clone this repository:

   ```bash
   git clone https://github.com/gabriellozdev/NoIMG.git
   cd NoIMG
   ```

2. Run `instalar.bat`.

The installer automatically:

- Creates the Python virtual environment.
- Downloads the required AI models (approximately 540 MB).
- Verifies downloaded models using SHA-256 checksums.
- Installs frontend dependencies and builds the web interface.

**Note:** AI models and generated frontend files (`models/` and `web/dist/`) are excluded from Git. Some model files exceed GitHub's 100 MB file size limit.

## Usage

Double-click `iniciar.bat` to launch NoIMG.

The application will be available at:

```text
http://127.0.0.1:7860
```

All image processing is performed locally.

### NoIMG Implementation

| Processing Stage | Reference Services | NoIMG |
|---|---|---|
| Segmentation | Proprietary server-side models | ISNet / BiRefNet |
| High-resolution mask | Full-resolution alpha mask | Fast Guided Filter |
| Edge decontamination | Processed foreground colors | Blur-Fusion Foreground Estimation |
| Image composition | Browser Canvas | NumPy |
| Upscaling | Server-side 2× / 4× processing | Real-ESRGAN |
| Transparency during upscaling | Limited support | Separate RGB and alpha upscaling |

**Segmentation models**
- ISNet (default).
- BiRefNet (available on systems with at least 8 GB of RAM).
- 1024 px processing resolution.

**Edge refinement**

NoIMG uses Fast Guided Filtering to refine the alpha mask, using the original image as a guide. For foreground color reconstruction, it implements Blur-Fusion Foreground Estimation based on the work of Forte & Pitié.

**Transparency-aware upscaling**

RGB and alpha channels are upscaled separately. Color information is extended into transparent regions to reduce dark halos and unwanted edge artifacts.

---

## AI Models & Dependencies

Models are downloaded automatically during installation and stored in `models/`.

| Model | Source | License |
|---|---|---|
| `realesr-general-x4v3.pth` | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause |
| `RealESRGAN_x4plus.pth` | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause |
| `RealESRGAN_x2plus.pth` | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause |
| `isnet-general-use.onnx` | [rembg](https://github.com/danielgatis/rembg) | See upstream repository |
| `birefnet-lite.onnx` | [rembg](https://github.com/danielgatis/rembg) | See upstream repository |

## Privacy

NoIMG is designed around local processing.

- Images are processed on your computer.
- No image uploads to external processing servers.
- AI models are downloaded during installation, not during image processing.
- Your processed images remain under your control.

## Open Source & Contributions

NoIMG is an **open-source project**, and its source code is publicly available for everyone to explore, use, and improve.

Contributions are welcome! If you have ideas, find bugs, or want to improve existing features, feel free to contribute.

- **Fork** the repository.
- Create a branch for your changes.
- Submit a **Pull Request** with your improvements.
- Report bugs and suggest new features through GitHub Issues.

All contributions are appreciated. Whether it's fixing bugs, improving performance, refining the interface, or adding new features, your contributions help make NoIMG better.

**The code is open, and everyone is welcome to contribute.**

---

**Built with Python, React, and open-source AI models.**
