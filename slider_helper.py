"""
滑块验证码处理模块
策略：
  1. 自动截图 → OpenCV 边缘检测找缺口位置 → 模拟人工拖动
  2. 自动失败时，提示用户手动完成，脚本继续等待
"""
import asyncio
import base64
import io
import random
import time

import cv2
import numpy as np
from PIL import Image


def _pil_to_cv2(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _detect_gap_x(bg_bytes: bytes, piece_bytes: bytes) -> int:
    """
    用模板匹配找滑块缺口的 x 坐标。
    bg_bytes   : 带缺口的背景图（二进制）
    piece_bytes: 滑块小图（二进制）
    返回缺口左边缘的 x 坐标（像素）
    """
    bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
    piece_img = Image.open(io.BytesIO(piece_bytes)).convert("RGB")

    bg = _pil_to_cv2(bg_img)
    piece = _pil_to_cv2(piece_img)

    # 转灰度 + Canny 边缘
    bg_gray = cv2.Canny(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), 100, 200)
    piece_gray = cv2.Canny(cv2.cvtColor(piece, cv2.COLOR_BGR2GRAY), 100, 200)

    # 模板匹配
    result = cv2.matchTemplate(bg_gray, piece_gray, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(result)
    return max_loc[0]  # x 坐标


async def _drag_slider(page, slider_handle, distance: int):
    """
    模拟人工拖动滑块：加速 → 减速 → 微调，带随机抖动
    """
    box = await slider_handle.bounding_box()
    if not box:
        raise RuntimeError("找不到滑块元素边界")

    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    await asyncio.sleep(0.3)

    # 分段移动，模拟加速再减速
    steps = 30
    moved = 0
    for i in range(steps):
        # 缓动函数：先快后慢
        ratio = i / steps
        eased = distance * (1 - (1 - ratio) ** 2)
        step_x = eased - moved
        moved = eased

        jitter_y = random.uniform(-1.5, 1.5)
        await page.mouse.move(start_x + moved, start_y + jitter_y)
        await asyncio.sleep(random.uniform(0.01, 0.03))

    # 轻微回拉再推进，模仿人手抖动
    await page.mouse.move(start_x + distance - 3, start_y)
    await asyncio.sleep(0.1)
    await page.mouse.move(start_x + distance, start_y)
    await asyncio.sleep(0.2)

    await page.mouse.up()


async def handle_slider(page, config: dict) -> bool:
    """
    尝试自动处理滑块验证码。
    返回 True 表示已处理（自动或手动），False 表示超时放弃。

    调用方式：在登录按钮点击后调用此函数。
    函数会自动判断滑块是否出现，未出现则直接返回 True（无需验证）。
    """
    # 常见滑块容器选择器（覆盖极验、自研等主流样式）
    slider_selectors = [
        ".slider-container",
        ".slide-verify",
        ".geetest_holder",
        "[class*='slider']",
        "[class*='captcha']",
        "[class*='verify']",
    ]
    slider_btn_selectors = [
        ".slider-btn",
        ".slide-verify-slider-mask-item",
        ".geetest_slider_button",
        "[class*='slider-btn']",
        "[class*='drag-btn']",
        "[class*='handler']",
    ]
    bg_img_selectors = [
        ".slide-verify-block",
        ".geetest_canvas_bg",
        "[class*='bg-img']",
        "canvas",
    ]
    piece_img_selectors = [
        ".slide-verify-slider-mask",
        ".geetest_canvas_slice",
        "[class*='piece']",
        "[class*='puzzle']",
    ]

    # 等待滑块出现（最多 5 秒）
    slider_visible = False
    for sel in slider_selectors:
        try:
            await page.wait_for_selector(sel, timeout=5000, state="visible")
            slider_visible = True
            break
        except Exception:
            continue

    if not slider_visible:
        print("[滑块] 未检测到滑块验证码，跳过")
        return True

    print("[滑块] 检测到滑块验证码，尝试自动处理...")

    # 尝试自动处理（最多 3 次）
    for attempt in range(1, 4):
        print(f"[滑块] 第 {attempt} 次尝试自动识别...")
        try:
            # 找滑块按钮
            slider_handle = None
            for sel in slider_btn_selectors:
                try:
                    slider_handle = page.locator(sel).first
                    await slider_handle.wait_for(timeout=3000, state="visible")
                    break
                except Exception:
                    slider_handle = None

            if slider_handle is None:
                raise RuntimeError("找不到滑块按钮元素")

            # 获取背景图和滑块图的像素数据（截图方式）
            # 先截整个验证码区域，再分别截背景和缺口
            bg_el = None
            piece_el = None
            for sel in bg_img_selectors:
                try:
                    bg_el = page.locator(sel).first
                    await bg_el.wait_for(timeout=2000, state="visible")
                    break
                except Exception:
                    bg_el = None
            for sel in piece_img_selectors:
                try:
                    piece_el = page.locator(sel).first
                    await piece_el.wait_for(timeout=2000, state="visible")
                    break
                except Exception:
                    piece_el = None

            if bg_el is None or piece_el is None:
                raise RuntimeError("找不到背景图或滑块拼图元素")

            bg_bytes = await bg_el.screenshot()
            piece_bytes = await piece_el.screenshot()

            gap_x = _detect_gap_x(bg_bytes, piece_bytes)
            # 获取滑块按钮当前位置以换算实际拖动距离
            slider_box = await slider_handle.bounding_box()
            # 减去滑块按钮自身起始 x（通常已在左侧）
            drag_distance = gap_x - (slider_box["x"] if slider_box else 0)
            drag_distance = max(10, drag_distance)  # 防止负值

            await _drag_slider(page, slider_handle, drag_distance)
            await asyncio.sleep(1.5)

            # 判断是否通过（验证码消失或出现成功提示）
            still_visible = False
            for sel in slider_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible():
                        still_visible = True
                        break
                except Exception:
                    pass

            if not still_visible:
                print("[滑块] 自动处理成功！")
                return True
            else:
                print(f"[滑块] 第 {attempt} 次未通过，刷新重试...")
                # 尝试点击刷新按钮
                for refresh_sel in ["[class*='refresh']", "[class*='reload']", ".slide-verify-refresh"]:
                    try:
                        await page.click(refresh_sel, timeout=2000)
                        await asyncio.sleep(1)
                        break
                    except Exception:
                        pass

        except Exception as e:
            print(f"[滑块] 自动处理异常：{e}")

    # 自动处理失败，等待手动
    print(f"\n{'='*50}")
    print("[滑块] 自动识别失败，请在浏览器窗口中手动拖动滑块完成验证")
    print(f"[滑块] 等待最多 {config['manual_slider_timeout']} 秒...")
    print(f"{'='*50}\n")

    deadline = time.time() + config["manual_slider_timeout"]
    while time.time() < deadline:
        still_visible = False
        for sel in slider_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible():
                    still_visible = True
                    break
            except Exception:
                pass
        if not still_visible:
            print("[滑块] 检测到验证已完成，继续执行...")
            return True
        await asyncio.sleep(2)

    print("[滑块] 等待超时，验证未完成")
    return False
