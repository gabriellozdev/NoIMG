"""Testes do pipeline de remoção de fundo. Rode com: python -m unittest tests.test_remocao

Os que precisam do modelo ISNet (models/isnet-general-use.onnx) são pulados se ele faltar.
"""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from noimg import core  # noqa: E402

HAS_ISNET = (core.MODELS / "isnet-general-use.onnx").exists()


def _scene(w, h):
    """Fundo verde com um disco vermelho; alfa de referência suave na borda."""
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    r = min(w, h) * 0.3
    d = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2)
    alpha = np.clip(r - d + 0.5, 0, 1)
    fg = np.array([0.9, 0.1, 0.1], np.float32)
    bg = np.array([0.1, 0.6, 0.2], np.float32)
    img = fg * alpha[..., None] + bg * (1 - alpha[..., None])
    return img.astype(np.float32), alpha.astype(np.float32), fg, bg


class LetterboxTest(unittest.TestCase):
    def test_janela_util_preserva_proporcao(self):
        for w, h in ((1600, 900), (700, 1300), (1024, 1024), (333, 2000)):
            img = np.random.default_rng(0).random((h, w, 3), dtype=np.float32)
            canvas, (top, left, nh, nw) = core._model_input(img, True, "replicate", (0.5, 0.5, 0.5))
            self.assertEqual(canvas.shape, (core.SEG_SIZE, core.SEG_SIZE, 3))
            self.assertEqual(max(nh, nw), core.SEG_SIZE)
            self.assertAlmostEqual(nw / nh, w / h, delta=0.01 * w / h + 2 / min(nh, nw))
            self.assertTrue(0 <= top and top + nh <= core.SEG_SIZE and 0 <= left and left + nw <= core.SEG_SIZE)

    def test_padding_media_usa_media_do_modelo(self):
        img = np.zeros((500, 1000, 3), np.float32)
        canvas, (top, _, nh, _) = core._model_input(img, True, "mean", (0.485, 0.456, 0.406))
        self.assertTrue(np.allclose(canvas[0, 0], (0.485, 0.456, 0.406), atol=1e-6))
        self.assertTrue(np.allclose(canvas[top + nh // 2, 500], 0))

    def test_auto_so_usa_padding_em_proporcao_extrema(self):
        cfg = core.DEFAULT_MATTING
        self.assertFalse(core.use_letterbox(cfg, 1067, 1600))  # 3:2 → achata, como no treino
        self.assertFalse(core.use_letterbox(cfg, 1600, 1600))
        self.assertTrue(core.use_letterbox(cfg, 600, 1600))  # 2,7:1 → padding
        self.assertTrue(core.use_letterbox(cfg, 1600, 700))
        self.assertFalse(core.use_letterbox(core.LEGACY_MATTING, 600, 1600))

    def test_sem_letterbox_achata_como_antes(self):
        img = np.zeros((300, 900, 3), np.float32)
        canvas, win = core._model_input(img, False, "replicate", (0.5, 0.5, 0.5))
        self.assertEqual(canvas.shape[:2], (core.SEG_SIZE, core.SEG_SIZE))
        self.assertEqual(win, (0, 0, core.SEG_SIZE, core.SEG_SIZE))


class RefinoTest(unittest.TestCase):
    def test_alfa_final_tem_tamanho_exato_da_original(self):
        for w, h in ((1601, 899), (700, 1301)):
            img, alpha, _, _ = _scene(w, h)
            m = cv2.resize(alpha, (core.SEG_SIZE, round(core.SEG_SIZE * h / w)) if w > h else (round(core.SEG_SIZE * w / h), core.SEG_SIZE))
            out = core.alpha_from_raw(img, m, core.DEFAULT_MATTING)
            self.assertEqual(out.shape, (h, w))

    def test_guided_rgb_recupera_borda_que_o_cinza_nao_ve(self):
        # vermelho e verde com o MESMO cinza: só o guia RGB enxerga a borda
        h, w = 200, 200
        img = np.zeros((h, w, 3), np.float32)
        img[:, :100] = (0.6, 0.2, 0.2)
        gray_r = cv2.cvtColor(img[:1, :1], cv2.COLOR_RGB2GRAY)[0, 0]
        g = (gray_r - 0.299 * 0.1 - 0.114 * 0.1) / 0.587
        img[:, 100:] = (0.1, g, 0.1)
        truth = np.zeros((h, w), np.float32)
        truth[:, :100] = 1
        blurry = cv2.GaussianBlur(truth, (0, 0), 2)  # borda borrada dentro do alcance do filtro (r = 6)
        rgb = core._guided_filter_rgb(img, blurry, 6, 1e-4)
        gray = core._guided_filter(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), blurry, 6, 1e-4)
        edge = slice(90, 110)
        self.assertLess(np.abs(rgb - truth)[:, edge].mean(), np.abs(gray - truth)[:, edge].mean() * 0.5)

    def test_area_fora_da_faixa_nao_muda(self):
        img, alpha, _, _ = _scene(400, 400)
        band = np.zeros_like(alpha, bool)
        band[190:210, 100:120] = True
        out = core._refine_band(img, alpha, band, core.DEFAULT_MATTING, 2)
        self.assertTrue(np.array_equal(out[~band], alpha[~band]))


class NormalizacaoTest(unittest.TestCase):
    def test_guarded_nao_infla_previsao_fraca(self):
        m = np.full((10, 10), 0.05, np.float32)
        m[3:6, 3:6] = 0.3  # o modelo não tem certeza de nada
        self.assertAlmostEqual(float(core._normalize(m, "minmax").max()), 1.0, places=5)
        self.assertLess(float(core._normalize(m, "guarded").max()), 0.4)

    def test_guarded_igual_minmax_quando_confiante(self):
        m = np.linspace(0, 1, 100, dtype=np.float32).reshape(10, 10)
        self.assertTrue(np.allclose(core._normalize(m, "guarded"), core._normalize(m, "minmax")))


class PerfilObjetosTest(unittest.TestCase):
    def test_solidify_tira_mancha_fecha_furo_e_encurta_borda(self):
        a = np.zeros((200, 200), np.float32)
        a[40:160, 40:160] = 1.0
        a[90:93, 90:93] = 0.0  # furinho dentro do objeto
        a[5:8, 5:8] = 0.9  # mancha solta no fundo
        a[40:160, 160] = 0.7  # borda "apagada"
        out = core._solidify(a, core.OBJECTS_MATTING)
        self.assertTrue(np.all(out[90:93, 90:93] == 1.0))
        self.assertTrue(np.all(out[5:8, 5:8] == 0.0))
        self.assertGreater(float(out[100, 160]), 0.95)

    def test_solidify_preserva_furo_grande_e_objeto_na_borda(self):
        a = np.zeros((200, 200), np.float32)
        a[:, :120] = 1.0  # objeto encostado na borda da imagem
        a[60:140, 30:90] = 0.0  # furo grande (alça de caneca, por ex.)
        out = core._solidify(a, core.OBJECTS_MATTING)
        self.assertTrue(np.array_equal(out, a))

    def test_perfis_do_app(self):
        self.assertEqual(set(core.MATTING_PROFILES), {"objetos", "detalhado"})
        self.assertIs(core.MATTING_PROFILES["detalhado"], core.DEFAULT_MATTING)
        self.assertEqual(core.OBJECTS_MATTING.fg, "blur")


class PrimeiroPlanoTest(unittest.TestCase):
    def test_ml_recupera_cor_e_preserva_pixels_confiaveis(self):
        img, alpha, fg, _ = _scene(300, 200)
        for method in ("ml", "blur"):
            F = core.estimate_foreground(img, alpha, method)
            solid = alpha >= 0.999
            self.assertTrue(np.array_equal(F[solid], img[solid]))
        F = core.estimate_foreground(img, alpha, "ml")
        edge = (alpha > 0.1) & (alpha < 0.9)
        err_ml = np.abs(F[edge] - fg).mean()
        err_raw = np.abs(img[edge] - fg).mean()
        self.assertLess(err_ml, err_raw * 0.5)


@unittest.skipUnless(HAS_ISNET, "modelo ISNet ausente")
class PipelineTest(unittest.TestCase):
    def test_remove_background_mantem_tamanho_e_upscale_intacto(self):
        img, _, _, _ = _scene(640, 360)
        out = core.remove_background(img, model="isnet")
        self.assertEqual(out.shape, (360, 640, 4))
        legacy = core.remove_background(img, model="isnet", cfg=core.LEGACY_MATTING)
        self.assertEqual(legacy.shape, (360, 640, 4))
        up = core.upscale(np.dstack([img[:40, :40], np.ones((40, 40), np.float32)]), 2, "rapido")
        self.assertEqual(up.shape, (80, 80, 4))


if __name__ == "__main__":
    unittest.main()
