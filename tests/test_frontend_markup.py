import unittest
from pathlib import Path


FRONTEND_HTML = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


class FrontendAccessibilityMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = FRONTEND_HTML.read_text(encoding="utf-8")

    def test_icon_only_controls_have_accessible_names(self):
        required_snippets = [
            ":aria-label=\"isDark ? 'Ativar modo claro' : 'Ativar modo escuro'\"",
            "aria-label=\"Diminuir quantidade\"",
            "aria-label=\"Aumentar quantidade\"",
            ":aria-label=\"'Mover parada ' + (idx + 1) + ' para cima'\"",
            ":aria-label=\"'Mover parada ' + (idx + 1) + ' para baixo'\"",
            ":aria-label=\"'Editar parada ' + (idx + 1)\"",
            ":aria-label=\"'Remover parada ' + (idx + 1)\"",
            "aria-label=\"Abrir rota no Google Maps\"",
            "aria-label=\"Enviar rota pelo WhatsApp\"",
            "aria-label=\"Copiar rota em texto formatado\"",
            "aria-label=\"Exportar rota em CSV\"",
            "aria-label=\"Imprimir cupom da rota\"",
            ":aria-label=\"'Abrir busca manual no Google Maps para ' + node.address\"",
            ":aria-label=\"'Copiar endereço não localizado ' + node.address\"",
        ]

        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.html)

    def test_status_and_error_regions_are_announced(self):
        self.assertIn('role="alert" aria-live="assertive"', self.html)
        self.assertIn('class="toast" role="status" aria-live="polite"', self.html)
        self.assertIn('class="progress-container" aria-live="polite"', self.html)

    def test_segmented_controls_expose_state(self):
        self.assertIn('role="tablist" aria-label="Selecionar motoboy"', self.html)
        self.assertIn('role="tab" :aria-selected="activeBlockIndex === i"', self.html)
        self.assertIn('role="group" aria-label="Retornar ao restaurante"', self.html)
        self.assertIn('role="group" aria-label="Tipo de itinerário"', self.html)


if __name__ == "__main__":
    unittest.main()
