"""
核心逻辑单元测试

覆盖范围：
  - main.ask_date         : 交互式日期输入（含默认值回退）
  - main.get_date_range   : 日期范围格式与逻辑校验
  - slider_helper._pil_to_cv2   : PIL → OpenCV 颜色空间转换
  - slider_helper._detect_gap_x : 滑块缺口 x 坐标检测
  - slider_helper.handle_slider : 无滑块时快速跳过路径
"""

import asyncio
import io
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

# ── 路径修正（从 tests/ 访问项目根） ─────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import ask_date, get_date_range
from slider_helper import _detect_gap_x, _pil_to_cv2, handle_slider


# ════════════════════════════════════════════════
# ask_date
# ════════════════════════════════════════════════

class TestAskDate:
    def test_returns_user_input_when_provided(self):
        with patch("builtins.input", return_value="2024-05-20"):
            result = ask_date("开始日期", "2024-05-01")
        assert result == "2024-05-20"

    def test_returns_default_on_empty_input(self):
        with patch("builtins.input", return_value=""):
            result = ask_date("开始日期", "2024-05-01")
        assert result == "2024-05-01"

    def test_strips_whitespace_from_input(self):
        with patch("builtins.input", return_value="  2024-06-15  "):
            result = ask_date("结束日期", "2024-06-01")
        assert result == "2024-06-15"

    def test_prompt_contains_default_value(self):
        """input 调用时提示文本应包含默认值"""
        captured = []
        def mock_input(prompt):
            captured.append(prompt)
            return ""
        with patch("builtins.input", side_effect=mock_input):
            ask_date("开始日期", "2024-01-01")
        assert "2024-01-01" in captured[0]


# ════════════════════════════════════════════════
# get_date_range
# ════════════════════════════════════════════════

class TestGetDateRange:
    def test_returns_tuple_of_two_strings(self):
        with patch("builtins.input", return_value=""):
            result = get_date_range()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(d, str) for d in result)

    def test_default_start_is_yesterday(self):
        today = datetime.today()
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        with patch("builtins.input", return_value=""):
            start, _ = get_date_range()
        assert start == yesterday

    def test_default_end_is_today(self):
        today = datetime.today().strftime("%Y-%m-%d")
        with patch("builtins.input", return_value=""):
            _, end = get_date_range()
        assert end == today

    def test_custom_dates_are_returned(self):
        inputs = iter(["2024-03-01", "2024-03-31"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            start, end = get_date_range()
        assert start == "2024-03-01"
        assert end == "2024-03-31"

    def test_date_format_is_valid(self):
        with patch("builtins.input", return_value=""):
            start, end = get_date_range()
        fmt = "%Y-%m-%d"
        # 不应抛出 ValueError
        datetime.strptime(start, fmt)
        datetime.strptime(end, fmt)


# ════════════════════════════════════════════════
# slider_helper._pil_to_cv2
# ════════════════════════════════════════════════

class TestPilToCv2:
    def _make_pil(self, color=(255, 0, 0), size=(10, 10)):
        img = Image.new("RGB", size, color)
        return img

    def test_returns_numpy_array(self):
        pil = self._make_pil()
        result = _pil_to_cv2(pil)
        assert isinstance(result, np.ndarray)

    def test_output_shape_matches_input(self):
        pil = self._make_pil(size=(30, 20))
        result = _pil_to_cv2(pil)
        # OpenCV shape: (height, width, channels)
        assert result.shape == (20, 30, 3)

    def test_rgb_to_bgr_conversion(self):
        """纯红色 (255,0,0) 在 BGR 中应为 (0,0,255)"""
        pil = self._make_pil(color=(255, 0, 0))
        result = _pil_to_cv2(pil)
        pixel = result[0, 0]  # (B, G, R)
        assert pixel[0] == 0    # B
        assert pixel[1] == 0    # G
        assert pixel[2] == 255  # R

    def test_pure_green_converts_correctly(self):
        pil = self._make_pil(color=(0, 255, 0))
        result = _pil_to_cv2(pil)
        pixel = result[0, 0]
        assert pixel[0] == 0    # B
        assert pixel[1] == 255  # G
        assert pixel[2] == 0    # R

    def test_dtype_is_uint8(self):
        pil = self._make_pil()
        result = _pil_to_cv2(pil)
        assert result.dtype == np.uint8


# ════════════════════════════════════════════════
# slider_helper._detect_gap_x
# ════════════════════════════════════════════════

def _make_test_pair(width=200, height=100, gap_x=80, gap_size=30):
    """
    生成一对可靠的测试图像：
    - piece: 带十字纹理的滑块图（有 Canny 可识别的边缘）
    - bg   : 在 gap_x 位置嵌入同样纹理，其余区域为暗色背景

    这样 matchTemplate 会在 (gap_x, 20) 找到最强匹配。
    """
    # 绘制带十字的 piece（边缘清晰）
    piece_array = np.zeros((gap_size, gap_size, 3), dtype=np.uint8)
    cx, cy, half = gap_size // 2, gap_size // 2, 2
    piece_array[cy - half: cy + half, :] = 255  # 横线
    piece_array[:, cx - half: cx + half] = 255  # 竖线

    # 背景：暗底 + 在 gap_x 处嵌入 piece 纹理
    bg_array = np.full((height, width, 3), 30, dtype=np.uint8)
    bg_array[20: 20 + gap_size, gap_x: gap_x + gap_size] = piece_array

    bg_img = Image.fromarray(bg_array)
    piece_img = Image.fromarray(piece_array)

    bg_buf, piece_buf = io.BytesIO(), io.BytesIO()
    bg_img.save(bg_buf, format="PNG")
    piece_img.save(piece_buf, format="PNG")
    return bg_buf.getvalue(), piece_buf.getvalue()


def _make_bg_with_gap(width=200, height=100, gap_x=80, gap_size=30) -> bytes:
    return _make_test_pair(width, height, gap_x, gap_size)[0]


def _make_piece(gap_size=30) -> bytes:
    return _make_test_pair(gap_size=gap_size)[1]


class TestDetectGapX:
    def test_returns_integer(self):
        bg = _make_bg_with_gap()
        piece = _make_piece()
        result = _detect_gap_x(bg, piece)
        assert isinstance(result, (int, np.intp))

    def test_result_within_image_width(self):
        width = 200
        bg, piece = _make_test_pair(width=width)
        result = _detect_gap_x(bg, piece)
        assert 0 <= result < width

    def test_detects_approximate_gap_position(self):
        """检测结果应在实际嵌入位置 ±10px 范围内"""
        gap_x = 80
        bg, piece = _make_test_pair(gap_x=gap_x)
        result = _detect_gap_x(bg, piece)
        assert abs(result - gap_x) <= 10, (
            f"期望缺口在 x≈{gap_x}，实际检测为 {result}"
        )

    def test_different_gap_positions(self):
        """不同嵌入位置时，检测结果应单调递增"""
        positions = [40, 80, 120]
        results = []
        for p in positions:
            bg, piece = _make_test_pair(gap_x=p)
            results.append(_detect_gap_x(bg, piece))
        assert results[0] < results[1] < results[2], (
            f"位置递增但检测结果未单调递增: {results}"
        )


# ════════════════════════════════════════════════
# slider_helper.handle_slider（无滑块路径）
# ════════════════════════════════════════════════

class TestHandleSliderNoSlider:
    """当页面上不存在滑块时，handle_slider 应立即返回 True"""

    def _make_mock_page(self):
        page = MagicMock()
        # wait_for_selector 超时（模拟无滑块）
        async def mock_wait(*args, **kwargs):
            raise Exception("Timeout: element not found")
        page.wait_for_selector = mock_wait
        return page

    def test_returns_true_when_no_slider(self):
        page = self._make_mock_page()
        config = {"manual_slider_timeout": 5}
        result = asyncio.get_event_loop().run_until_complete(
            handle_slider(page, config)
        )
        assert result is True
