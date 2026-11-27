"""
Chart to SVG converter - WillChart.jsConvert data to vector SVG graphics

Supported chart types:
- line: Line chart
- bar: bar chart
- pie: pie chart
- doughnut: donut chart
- radar: radar chart
- polarArea: polar regions map
- scatter: Scatter plot
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.font_manager as fm
    from matplotlib.patches import Wedge, Rectangle
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("MatplotlibIf not installed, the PDF chart vector rendering function will not be available")


try:
    from scipy.interpolate import make_interp_spline
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.info("ScipyIf not installed, the line chart will not support the curve smoothing function (does not affect basic rendering）")


class ChartToSVGConverter:
    """
    WillChart.jsConvert chart data to SVG vector graphics
    """


    DEFAULT_COLORS = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'
    ]


    CSS_VAR_COLOR_MAP = {
        'var(--color-accent)': '#3b82f6',
        'var(--re-accent-color)': '#3b82f6',
        'var(--re-accent-color-translucent)': (0.29, 0.565, 0.886, 0.08),
        'var(--color-kpi-down)': '#ef4444',
        'var(--re-danger-color)': '#ef4444',
        'var(--re-danger-color-translucent)': (0.91, 0.365, 0.459, 0.08),
        'var(--color-warning)': '#f59e0b',
        'var(--re-warning-color)': '#f59e0b',
        'var(--re-warning-color-translucent)': (1.0, 0.702, 0.278, 0.08),
        'var(--color-success)': '#10b981',
        'var(--re-success-color)': '#10b981',
        'var(--re-success-color-translucent)': (0.314, 0.784, 0.471, 0.08),
        'var(--color-accent-positive)': '#50C878',
        'var(--color-accent-negative)': '#E85D75',
        'var(--color-text-secondary)': '#6B7280',
        'var(--accentPositive)': '#50C878',
        'var(--accentNegative)': '#E85D75',
        'var(--sentiment-positive, #28A745)': '#28A745',
        'var(--sentiment-negative, #E53E3E)': '#E53E3E',
        'var(--sentiment-neutral, #FFC107)': '#FFC107',
        'var(--sentiment-positive)': '#28A745',
        'var(--sentiment-negative)': '#E53E3E',
        'var(--sentiment-neutral)': '#FFC107',
        'var(--color-primary)': '#3b82f6',
        'var(--color-secondary)': '#10b981'
    }


    CSS_VAR_RGB_MAP = {
        'color-primary-rgb': (52, 152, 219),
        'color-tone-up-rgb': (80, 200, 120),
        'color-tone-down-rgb': (232, 93, 117),
        'color-accent-positive-rgb': (80, 200, 120),
        'color-accent-neutral-rgb': (149, 165, 166),
    }

    def __init__(self, font_path: Optional[str] = None):
        """
        Initialize converter

        parameters:
            font_path: Chinese fontpath (optional）
        """
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("MatplotlibNot installed, please run: pip install matplotlib")

        self.font_path = font_path
        self._setup_chinese_font()

    def _setup_chinese_font(self):
        """ConfigurationChinese font"""
        if self.font_path:
            try:

                fm.fontManager.addfont(self.font_path)

                font_prop = fm.FontProperties(fname=self.font_path)
                plt.rcParams['font.family'] = font_prop.get_name()
                plt.rcParams['axes.unicode_minus'] = False
                logger.info(f"LoadedChinese font: {self.font_path}")
            except Exception as e:
                logger.warning(f"loadChinese fontFailed: {e}，System default font will be used")
        else:

            try:
                plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
            except Exception as e:
                logger.warning(f"ConfigurationChinese fontFailed: {e}")

    def convert_widget_to_svg(
        self,
        widget_data: Dict[str, Any],
        width: int = 800,
        height: int = 500,
        dpi: int = 100
    ) -> Optional[str]:
        """
        Convert widget data to SVG string

        parameters:
            widget_data: widgetblock data (includingwidgetType、data、props）
            width: Chart width (pixels）
            height: Chart height (pixels）
            dpi: DPIsettings

        Return:
            str: SVGString, Failed returnsNone
        """
        try:

            widget_type = widget_data.get('widgetType', '')
            if not widget_type or not widget_type.startswith('chart.js'):
                logger.warning(f"Unsupported widget type: {widget_type}")
                return None


            chart_type = widget_type.split('/')[-1] if '/' in widget_type else 'bar'


            props = widget_data.get('props', {})
            if props.get('type'):
                chart_type = props['type']


            horizontal_bar = False
            if chart_type and str(chart_type).lower() == 'horizontalbar':
                chart_type = 'bar'
                horizontal_bar = True


            if isinstance(props, dict):
                options = props.get('options') or {}
                index_axis = (options.get('indexAxis') or props.get('indexAxis') or '').lower()
                if index_axis == 'y':
                    horizontal_bar = True


            data = widget_data.get('data', {})
            if not data:
                logger.warning("Chart data is empty")
                return None


            if 'wordcloud' in str(chart_type).lower():

                logger.debug("Word cloud chart detected, skipping chart_to_svg conversion")
                return None


            if chart_type == 'bar':
                return self._render_bar(data, props, width, height, dpi, horizontal=horizontal_bar)
            elif chart_type == 'bubble':
                return self._render_bubble(data, props, width, height, dpi)
            else:
                render_method = getattr(self, f'_render_{chart_type}', None)
                if not render_method:
                    logger.warning(f"Unsupported chart type: {chart_type}")
                    return None


            return render_method(data, props, width, height, dpi)

        except Exception as e:
            logger.error(f"Convert chart toSVGFailed: {e}", exc_info=True)
            return None

    def _create_figure(
        self,
        width: int,
        height: int,
        dpi: int,
        title: Optional[str] = None
    ) -> Tuple[Any, Any]:
        """
        Create matplotlib charts

        Return:
            tuple: (fig, ax)
        """
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)

        if title:
            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        return fig, ax

    def _parse_color(self, color: Any) -> Any:
        """
        Parse color values and convert CSS format to format supported by matplotlib

        parameters:
            color: Color value (maybe in CSS format likergba()or hex or css variables)

        Return:
            matplotlibSupported color formats (hex string orRGB(A)tuple）
        """
        if color is None:
            return None


        _np = globals().get("np")
        if _np is not None and hasattr(_np, "ndarray") and isinstance(color, _np.ndarray):
            color = color.tolist()


        if isinstance(color, (list, tuple)):
            if len(color) in (3, 4) and all(isinstance(c, (int, float)) for c in color):
                normalized = []
                for idx, channel in enumerate(color):

                    value = float(channel)
                    if value > 1:
                        value = value / 255.0

                    if idx < 3:
                        value = max(0.0, min(value, 1.0))
                    else:
                        value = max(0.0, min(value, 1.0))
                    normalized.append(value)
                return tuple(normalized)

            try:
                return tuple(color)
            except Exception:
                return color


        if not isinstance(color, str):
            return str(color)

        color = color.strip()


        var_rgba_pattern = r'rgba?\(var\(--([\w-]+)\)\s*(?:,\s*([\d.]+))?\)'
        match = re.match(var_rgba_pattern, color)
        if match:
            var_name, alpha_str = match.groups()
            rgb_tuple = self.CSS_VAR_RGB_MAP.get(var_name)


            if not rgb_tuple:
                if var_name.endswith('-rgb'):
                    rgb_tuple = self.CSS_VAR_RGB_MAP.get(var_name[:-4])
                else:
                    rgb_tuple = self.CSS_VAR_RGB_MAP.get(f"{var_name}-rgb")

            if rgb_tuple:
                r, g, b = rgb_tuple
                alpha = float(alpha_str) if alpha_str is not None else 1.0
                return (r / 255, g / 255, b / 255, alpha)



        if color.startswith('var('):

            fb_match = re.match(r'^var\(\s*--[^,)+]+,\s*([^)]+)\)', color)
            if fb_match:
                fb_raw = fb_match.group(1).strip()
                fb_color = self._parse_color(fb_raw)
                if fb_color:
                    return fb_color

            mapped_color = self.CSS_VAR_COLOR_MAP.get(color)
            if mapped_color:
                return mapped_color

            if 'accent' in color or 'primary' in color:
                return '#3b82f6'
            elif 'danger' in color or 'down' in color or 'error' in color:
                return '#ef4444'
            elif 'warning' in color:
                return '#f59e0b'
            elif 'success' in color or 'up' in color:
                return '#10b981'

            return '#36A2EB'


        rgba_pattern = r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)'
        match = re.match(rgba_pattern, color)
        if match:
            r, g, b, a = match.groups()

            return (int(r)/255, int(g)/255, int(b)/255, float(a))


        rgb_pattern = r'rgb\((\d+),\s*(\d+),\s*(\d+)\)'
        match = re.match(rgb_pattern, color)
        if match:
            r, g, b = match.groups()

            return (int(r)/255, int(g)/255, int(b)/255)


        return color

    def _ensure_visible_color(self, color: Any, default_color: str, min_alpha: float = 0.6) -> Any:
        """
        Make sure colors are visible when rendering: avoid transparency values ​​and raise opacity that is too low
        """
        base_color = default_color if color in (None, "", "transparent") else color
        parsed = self._parse_color(base_color)
        default_parsed = self._parse_color(default_color)

        if isinstance(parsed, tuple):
            if len(parsed) == 4:
                r, g, b, a = parsed
                return (r, g, b, max(a, min_alpha))
            return parsed

        if isinstance(parsed, str) and parsed.lower() == "transparent":
            return default_parsed

        return parsed if parsed is not None else default_parsed

    def _get_colors(self, datasets: List[Dict[str, Any]]) -> List[str]:
        """
        Get chart color

        The colors defined in the dataset are used first, otherwise the default palette is used.
        """
        colors = []
        for i, dataset in enumerate(datasets):

            color = (
                dataset.get('backgroundColor') or
                dataset.get('borderColor') or
                dataset.get('color') or
                self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
            )


            if isinstance(color, list):
                color = color[0] if color else self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]


            color = self._parse_color(color)

            colors.append(color)

        return colors

    def _align_labels_and_data(
        self,
        labels: Any,
        dataset_data: Any,
        chart_type: str,
        require_positive_sum: bool = False
    ) -> Tuple[List[str], List[float]]:
        """
        Align labels and data lengths for categorical charts, and clean non-numeric values.

        Matplotlib pie chart/The donut chart requires labels to be consistent with the length of the data, otherwise it will throwErrors。
        """
        original_label_len = len(labels) if isinstance(labels, list) else 0
        original_data_len = len(dataset_data) if isinstance(dataset_data, list) else 0

        aligned_labels = [str(label) for label in labels] if isinstance(labels, list) else []
        raw_data = dataset_data if isinstance(dataset_data, list) else []

        cleaned_data: List[float] = []
        for value in raw_data:
            try:
                numeric = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                numeric = 0.0
            if numeric < 0:
                numeric = 0.0
            cleaned_data.append(numeric)

        target_len = max(len(aligned_labels), len(cleaned_data))
        if target_len == 0:
            return [], []

        if len(aligned_labels) < target_len:
            start = len(aligned_labels)
            aligned_labels.extend([f"Unnamed{start + idx + 1}" for idx in range(target_len - start)])

        if len(cleaned_data) < target_len:
            cleaned_data.extend([0.0] * (target_len - len(cleaned_data)))

        if original_label_len != original_data_len:
            logger.warning(
                f"{chart_type}Figure labels length({original_label_len})and data length({original_data_len})inconsistent，"
                f"Aligned to{target_len}"
            )

        if require_positive_sum and not any(value > 0 for value in cleaned_data):
            logger.warning(f"{chart_type}The graph data is empty and rendering is skipped.")
            return [], []

        return aligned_labels[:target_len], cleaned_data[:target_len]

    def _figure_to_svg(self, fig: Any) -> str:
        """
        Convert matplotlib chart to SVG string
        """
        svg_buffer = io.BytesIO()
        fig.savefig(svg_buffer, format='svg', bbox_inches='tight', transparent=False, facecolor='white')
        plt.close(fig)

        svg_buffer.seek(0)
        svg_string = svg_buffer.getvalue().decode('utf-8')

        return svg_string

    def _render_line(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """
        Render a line chart (enhanced version)

        Support features：
        - Multiple y-axes（yAxisID: 'y', 'y1', 'y2', 'y3'...）
        - fill area（fill: true）
        - Transparency (alpha channel in backgroundColor）
        - Line style (tension curve smoothing）
        """
        try:
            labels = data.get('labels') or []
            datasets = data.get('datasets') or []

            has_object_points = any(
                isinstance(ds, dict)
                and isinstance(ds.get('data'), list)
                and any(isinstance(pt, dict) and ('x' in pt or 'y' in pt) for pt in ds.get('data'))
                for ds in datasets
            )

            if (not datasets) or ((not labels) and not has_object_points):
                return None


            y_axis_ids = []
            for dataset in datasets:
                y_axis_id = dataset.get('yAxisID', 'y')
                if y_axis_id not in y_axis_ids:
                    y_axis_ids.append(y_axis_id)


            if 'y' in y_axis_ids:
                y_axis_ids.remove('y')
                y_axis_ids.insert(0, 'y')


            has_multiple_axes = len(y_axis_ids) > 1

            title = props.get('title')
            options = props.get('options', {})
            scales = options.get('scales', {})
            x_tick_labels = list(labels) if isinstance(labels, list) else []


            fig, ax1 = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)

            if title:
                ax1.set_title(title, fontsize=14, fontweight='bold', pad=20)


            axes = {'y': ax1}

            if has_multiple_axes:

                left_axes_count = 0
                right_axes_count = 0


                for y_axis_id in y_axis_ids[1:]:
                    if y_axis_id == 'y':
                        continue


                    new_ax = ax1.twinx()
                    axes[y_axis_id] = new_ax


                    y_config = scales.get(y_axis_id, {})
                    position = y_config.get('position', 'right')

                    if position == 'left':

                        if left_axes_count > 0:
                            new_ax.spines['left'].set_position(('outward', 60 * left_axes_count))
                        new_ax.yaxis.set_label_position('left')
                        new_ax.yaxis.set_ticks_position('left')
                        left_axes_count += 1
                    else:

                        if right_axes_count > 0:
                            new_ax.spines['right'].set_position(('outward', 60 * right_axes_count))
                        right_axes_count += 1

            colors = self._get_colors(datasets)


            axis_lines = {axis_id: [] for axis_id in y_axis_ids}
            legend_handles = []
            legend_labels = []


            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'series{i+1}')
                color = colors[i]


                y_axis_id = dataset.get('yAxisID', 'y')
                fill = True
                tension = dataset.get('tension', 0)
                border_color = self._parse_color(dataset.get('borderColor', color))
                background_color = self._parse_color(dataset.get('backgroundColor', color))


                ax = axes.get(y_axis_id, ax1)

                is_object_data = isinstance(dataset_data, list) and any(
                    isinstance(point, dict) and ('x' in point or 'y' in point)
                    for point in dataset_data
                )

                if is_object_data:
                    x_data = []
                    y_data = []
                    annotations = []

                    for idx, point in enumerate(dataset_data):
                        if not isinstance(point, dict):
                            continue

                        label_text = str(point.get('x', f"point{idx + 1}"))
                        if len(x_tick_labels) < len(dataset_data):
                            x_tick_labels.append(label_text)

                        x_data.append(len(x_data))

                        y_val = point.get('y', 0)
                        try:
                            y_val = float(y_val)
                        except (TypeError, ValueError):
                            y_val = 0
                        y_data.append(y_val)
                        annotations.append(point.get('event'))

                    if not x_data:
                        continue

                    line, = ax.plot(x_data, y_data, marker='o', label=label,
                                    color=border_color, linewidth=2, markersize=6)

                    if fill:
                        ax.fill_between(x_data, y_data, alpha=0.2, color=background_color)

                    for pos, y_val, text in zip(x_data, y_data, annotations):
                        if text:
                            ax.annotate(
                                text,
                                (pos, y_val),
                                textcoords='offset points',
                                xytext=(0, 8),
                                ha='center',
                                fontsize=8,
                                rotation=20
                            )
                else:

                    x_data = range(len(labels))


                    if tension > 0 and SCIPY_AVAILABLE:

                        if len(dataset_data) >= 4:
                            try:
                                x_smooth = np.linspace(0, len(labels)-1, len(labels)*3)
                                spl = make_interp_spline(x_data, dataset_data, k=min(3, len(dataset_data)-1))
                                y_smooth = spl(x_smooth)
                                line, = ax.plot(x_smooth, y_smooth, label=label, color=border_color, linewidth=2)


                                if fill:
                                    ax.fill_between(x_smooth, y_smooth, alpha=0.2, color=background_color)
                            except:

                                line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                              color=border_color, linewidth=2, markersize=6)
                                if fill:
                                    ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)
                        else:
                            line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                          color=border_color, linewidth=2, markersize=6)
                            if fill:
                                ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)
                    else:

                        line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                      color=border_color, linewidth=2, markersize=6)


                        if fill:
                            ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)


                axis_lines[y_axis_id].append(line)


                if fill:

                    fill_patch = Rectangle((0, 0), 1, 1,
                                          facecolor=background_color,
                                          edgecolor='none',
                                          alpha=0.15)

                    legend_handles.append((line, fill_patch))
                    legend_labels.append(label)
                else:
                    legend_handles.append(line)
                    legend_labels.append(label)


            if x_tick_labels:
                ax1.set_xticks(range(len(x_tick_labels)))
                ax1.set_xticklabels(x_tick_labels, rotation=45, ha='right')


            for y_axis_id, ax in axes.items():
                y_config = scales.get(y_axis_id, {})
                y_title = y_config.get('title', {}).get('text', '')

                if y_title:
                    ax.set_ylabel(y_title, fontsize=11)


                if len(axis_lines[y_axis_id]) == 1:
                    line_color = axis_lines[y_axis_id][0].get_color()
                    ax.tick_params(axis='y', labelcolor=line_color)
                    ax.yaxis.label.set_color(line_color)


            ax1.grid(True, alpha=0.3, linestyle='--')
            for y_axis_id in y_axis_ids[1:]:
                if y_axis_id in axes:
                    axes[y_axis_id].grid(False)


            if has_multiple_axes or len(datasets) > 1:

                from matplotlib.legend_handler import HandlerTuple

                ax1.legend(legend_handles, legend_labels,
                          loc='best',
                          framealpha=0.9,
                          handler_map={tuple: HandlerTuple(ndivide=None)})

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Rendering a line chartFailed: {e}", exc_info=True)
            return None

    def _render_bar(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int,
        horizontal: bool = False
    ) -> Optional[str]:
        """Render histogram (horizontal supported)barh）"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            colors = self._get_colors(datasets)


            positions = np.arange(len(labels))
            width_bar = 0.8 / len(datasets) if len(datasets) > 1 else 0.6


            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'series{i+1}')
                color = colors[i]

                offset = (i - len(datasets)/2 + 0.5) * width_bar

                if horizontal:
                    ax.barh(
                        positions + offset,
                        dataset_data,
                        height=width_bar,
                        label=label,
                        color=color,
                        alpha=0.8,
                        edgecolor='white',
                        linewidth=0.5
                    )
                else:
                    ax.bar(
                        positions + offset,
                        dataset_data,
                        width_bar,
                        label=label,
                        color=color,
                        alpha=0.8,
                        edgecolor='white',
                        linewidth=0.5
                    )


            if horizontal:
                ax.set_yticks(positions)
                ax.set_yticklabels(labels)
                ax.invert_yaxis()
                ax.grid(True, alpha=0.3, linestyle='--', axis='x')
            else:
                ax.set_xticks(positions)
                ax.set_xticklabels(labels, rotation=45, ha='right')
                ax.grid(True, alpha=0.3, linestyle='--', axis='y')


            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Render a histogramFailed: {e}")
            return None

    def _render_bubble(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render bubble chart"""
        try:
            datasets = data.get('datasets', [])
            if not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)
            colors = self._get_colors(datasets)

            def _safe_radius(raw) -> float:
                """Safely convert the input radius to floating point and set a minimum threshold to avoid bubbles disappearing completely"""
                try:
                    val = float(raw)
                    return max(val, 0.5)
                except Exception:
                    return 1.0

            all_x: list[float] = []
            all_y: list[float] = []
            max_r: float = 0.0

            for i, dataset in enumerate(datasets):
                points = dataset.get('data', [])
                label = dataset.get('label', f'series{i+1}')
                color = colors[i]

                if points and isinstance(points[0], dict):
                    xs = [p.get('x', 0) for p in points]
                    ys = [p.get('y', 0) for p in points]
                    rs = [_safe_radius(p.get('r', 1)) for p in points]
                else:
                    xs = list(range(len(points)))
                    ys = points
                    rs = [1.0 for _ in points]

                all_x.extend(xs)
                all_y.extend(ys)
                if rs:
                    max_r = max(max_r, max(rs))


                size_scale = 8.0 if max_r <= 20 else 6.5
                sizes = [(r * size_scale) ** 2 for r in rs]

                ax.scatter(
                    xs,
                    ys,
                    s=sizes,
                    label=label,
                    color=color,
                    alpha=0.45,
                    edgecolors='white',
                    linewidth=0.6
                )

            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)


            if all_x and all_y:
                x_min, x_max = min(all_x), max(all_x)
                y_min, y_max = min(all_y), max(all_y)
                x_span = max(x_max - x_min, 1e-6)
                y_span = max(y_max - y_min, 1e-6)
                pad_x = max(x_span * 0.12, max_r * 1.2)
                pad_y = max(y_span * 0.12, max_r * 1.2)
                ax.set_xlim(x_min - pad_x, x_max + pad_x)
                ax.set_ylim(y_min - pad_y, y_max + pad_y)

                ax.margins(x=0.05, y=0.05)

            ax.grid(True, alpha=0.3, linestyle='--')
            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Render bubble chartFailed: {e}", exc_info=True)
            return None

    def _render_pie(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Rendering a pie chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None


            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="cake",
                require_positive_sum=True
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)


            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]


            wedges, texts, autotexts = ax.pie(
                dataset_data,
                labels=labels,
                colors=colors,
                autopct='%1.1f%%',
                startangle=90,
                textprops={'fontsize': 10}
            )


            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            ax.axis('equal')

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Rendering a pie chartFailed: {e}")
            return None

    def _render_doughnut(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render a donut chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None


            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="ring",
                require_positive_sum=True
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)


            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]


            wedges, texts, autotexts = ax.pie(
                dataset_data,
                labels=labels,
                colors=colors,
                autopct='%1.1f%%',
                startangle=90,
                wedgeprops=dict(width=0.5, edgecolor='white'),
                textprops={'fontsize': 10}
            )


            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            ax.axis('equal')

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Render a donut chartFailed: {e}")
            return None

    def _render_radar(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render radar chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            title = props.get('title')
            fig = plt.figure(figsize=(width/dpi, height/dpi), dpi=dpi)


            ax = fig.add_subplot(111, projection='polar')

            if title:
                ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            colors = self._get_colors(datasets)


            angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
            angles += angles[:1]


            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'series{i+1}')
                color = colors[i]


                values = dataset_data + dataset_data[:1]


                ax.plot(angles, values, 'o-', linewidth=2, label=label, color=color)
                ax.fill(angles, values, alpha=0.25, color=color)


            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(labels)


            if len(datasets) > 1:
                ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Render radar chartFailed: {e}")
            return None

    def _render_scatter(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Rendering a scatter plot"""
        try:
            datasets = data.get('datasets', [])

            if not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            colors = self._get_colors(datasets)


            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'series{i+1}')
                color = colors[i]


                if dataset_data and isinstance(dataset_data[0], dict):
                    x_values = [point.get('x', 0) for point in dataset_data]
                    y_values = [point.get('y', 0) for point in dataset_data]
                else:

                    x_values = range(len(dataset_data))
                    y_values = dataset_data

                ax.scatter(
                    x_values,
                    y_values,
                    label=label,
                    color=color,
                    s=50,
                    alpha=0.6,
                    edgecolors='white',
                    linewidth=0.5
                )


            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)


            ax.grid(True, alpha=0.3, linestyle='--')

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Rendering a scatter plotFailed: {e}")
            return None

    def _render_polarArea(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Rendering a map of the polar regions"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None


            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="polar regions",
                require_positive_sum=False
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig = plt.figure(figsize=(width/dpi, height/dpi), dpi=dpi)
            ax = fig.add_subplot(111, projection='polar')

            if title:
                ax.set_title(title, fontsize=14, fontweight='bold', pad=20)


            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]


            theta = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
            width_bar = 2 * np.pi / len(labels)


            bars = ax.bar(
                theta,
                dataset_data,
                width=width_bar,
                bottom=0.0,
                color=colors,
                alpha=0.7,
                edgecolor='white',
                linewidth=1
            )


            ax.set_xticks(theta)
            ax.set_xticklabels(labels)

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Rendering a map of the polar regionsFailed: {e}")
            return None


def create_chart_converter(font_path: Optional[str] = None) -> ChartToSVGConverter:
    """
    Create a chart converter instance

    parameters:
        font_path: Chinese fontpath (optional)

    Return:
        ChartToSVGConverter: Converter example
    """
    return ChartToSVGConverter(font_path=font_path)


__all__ = ["ChartToSVGConverter", "create_chart_converter"]
