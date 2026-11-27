"""
LaTeX Math formula to SVG renderer
Render LaTeX equations to SVG format for PDF export using matplotlib
"""

import io
import re
from typing import Optional
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import mathtext
from loguru import logger


matplotlib.use('Agg')


class MathToSVG:
    """Converter for LaTeX math formulas to SVG"""

    def __init__(self, font_size: int = 14, color: str = 'black'):
        """
        Initialize formula converter

        Args:
            font_size: Font size (points）
            color: text color
        """
        self.font_size = font_size
        self.color = color

    def convert_to_svg(self, latex: str, display_mode: bool = True) -> Optional[str]:
        """
        Convert LaTeX formula to SVG string

        Args:
            latex: LaTeX formula string (excluding $$ or $ symbol）
            display_mode: True is display mode (block-level formula), False is inline mode

        Returns:
            SVG String, returned if conversion fails None
        """
        try:

            latex = (latex or "").strip()
            patterns = [
                r'^\$\$(.*)\$\$$',
                r'^\$(.*)\$$',
                r'^\\\[(.*)\\\]$',
                r'^\\\((.*)\\\)$',
            ]
            for pat in patterns:
                m = re.match(pat, latex, re.DOTALL)
                if m:
                    latex = m.group(1).strip()
                    break

            latex = re.sub(r'[\x00-\x1f\x7f]', '', latex)
            latex = latex.replace(r'\\tfrac', r'\\frac').replace(r'\\dfrac', r'\\frac')
            if not latex:
                logger.warning("Empty LaTeX formula")
                return None


            fig = plt.figure(figsize=(10, 2) if display_mode else (6, 1))
            fig.patch.set_alpha(0)



            if display_mode:

                text = fig.text(
                    0.5, 0.5,
                    f'${latex}$',
                    fontsize=self.font_size * 1.2,
                    color=self.color,
                    ha='center',
                    va='center',
                    usetex=False
                )
            else:

                text = fig.text(
                    0.1, 0.5,
                    f'${latex}$',
                    fontsize=self.font_size,
                    color=self.color,
                    ha='left',
                    va='center',
                    usetex=False
                )


            fig.canvas.draw()
            bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())


            bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())


            margin = 0.1
            fig.set_size_inches(
                bbox_inches.width + 2 * margin,
                bbox_inches.height + 2 * margin
            )


            text.set_position((0.5, 0.5))


            svg_buffer = io.StringIO()
            plt.savefig(
                svg_buffer,
                format='svg',
                bbox_inches='tight',
                pad_inches=0.1,
                transparent=True,
                dpi=300
            )
            plt.close(fig)


            svg_content = svg_buffer.getvalue()
            svg_buffer.close()

            return svg_content

        except Exception as e:
            logger.error(f"LaTeX Formula conversion failed: {latex[:100]}... mistake: {str(e)}")
            return None

    def convert_inline_to_svg(self, latex: str) -> Optional[str]:
        """
        Convert inline LaTeX formula to SVG

        Args:
            latex: LaTeX formula string

        Returns:
            SVG String, returned if conversion fails None
        """
        return self.convert_to_svg(latex, display_mode=False)

    def convert_display_to_svg(self, latex: str) -> Optional[str]:
        """
        Convert display mode LaTeX formula to SVG

        Args:
            latex: LaTeX formula string

        Returns:
            SVG String, returned if conversion fails None
        """
        return self.convert_to_svg(latex, display_mode=True)


def convert_math_block_to_svg(
    latex: str,
    font_size: int = 16,
    color: str = 'black'
) -> Optional[str]:
    """
    Convenience function: Convert a block of math formulas to SVG

    Args:
        latex: LaTeX formula string
        font_size: font size
        color: text color

    Returns:
        SVG String, returned if conversion fails None
    """
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_display_to_svg(latex)


def convert_math_inline_to_svg(
    latex: str,
    font_size: int = 14,
    color: str = 'black'
) -> Optional[str]:
    """
    Convenience functions: Convert inline math formulas to SVG

    Args:
        latex: LaTeX formula string
        font_size: font size
        color: text color

    Returns:
        SVG String, returned if conversion fails None
    """
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_inline_to_svg(latex)


if __name__ == "__main__":

    import sys


    test_formulas = [
        r"E = mc^2",
        r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        r"\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}",
        r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}",
    ]

    converter = MathToSVG(font_size=16)

    for i, formula in enumerate(test_formulas):
        logger.info(f"test formula {i+1}: {formula}")
        svg = converter.convert_display_to_svg(formula)
        if svg:

            filename = f"test_math_{i+1}.svg"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(svg)
            logger.info(f"Successfully saved to {filename}")
        else:
            logger.error(f"formula {i+1} Conversion failed")

    logger.info("Test completed")
