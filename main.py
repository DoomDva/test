"""
永辉供链平台 - 订货通知单自动导出脚本
替代影刀 RPA，使用 Python + Playwright 实现

使用方法：
    pip install -r requirements.txt
    playwright install chromium
    python main.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from config import CONFIG
from slider_helper import handle_slider


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def ask_date(prompt: str, default: str) -> str:
    """交互式输入日期，回车使用默认值"""
    val = input(f"{prompt} [默认 {default}]: ").strip()
    return val if val else default


def get_date_range() -> tuple[str, str]:
    """交互式获取订货日期范围"""
    today = datetime.today()
    default_start = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    default_end = today.strftime("%Y-%m-%d")

    print("\n请输入订货日期范围（格式 YYYY-MM-DD，直接回车使用默认值）：")
    date_start = ask_date("  开始日期", default_start)
    date_end = ask_date("  结束日期", default_end)
    return date_start, date_end


async def close_dialogs(page):
    """关闭页面上可能出现的弹窗"""
    for selector in [
        "button:has-text('关闭')",
        "button:has-text('取消')",
        "button:has-text('我知道了')",
        ".el-dialog__headerbtn",   # Element UI 关闭按钮
        ".ant-modal-close",        # Ant Design 关闭按钮
        "[class*='close-btn']",
        "[class*='modal-close']",
    ]:
        try:
            el = page.locator(selector).first
            if await el.is_visible():
                await el.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass


# ──────────────────────────────────────────────
# 核心步骤
# ──────────────────────────────────────────────

async def step_login(page):
    """步骤1-3：打开页面、填写账号密码、处理滑块验证"""
    print("\n[1/5] 打开登录页面...")
    await page.goto(CONFIG["url"], wait_until="networkidle")
    await close_dialogs(page)

    print("[2/5] 填写账号密码...")
    # 尝试常见的输入框选择器
    username_selectors = [
        'input[placeholder*="手机号"]',
        'input[placeholder*="账号"]',
        'input[name="username"]',
        'input[name="phone"]',
        'input[type="text"]:first-of-type',
    ]
    password_selectors = [
        'input[placeholder*="密码"]',
        'input[name="password"]',
        'input[type="password"]',
    ]

    username_filled = False
    for sel in username_selectors:
        try:
            await page.fill(sel, CONFIG["username"], timeout=3000)
            username_filled = True
            break
        except Exception:
            pass
    if not username_filled:
        raise RuntimeError("找不到账号输入框，请检查选择器")

    for sel in password_selectors:
        try:
            await page.fill(sel, CONFIG["password"], timeout=3000)
            break
        except Exception:
            pass

    # 点击登录按钮
    login_btn_selectors = [
        'button:has-text("登录")',
        'button[type="submit"]',
        'input[type="submit"]',
        '[class*="login-btn"]',
    ]
    for sel in login_btn_selectors:
        try:
            await page.click(sel, timeout=3000)
            break
        except Exception:
            pass

    await asyncio.sleep(1)

    print("[3/5] 处理滑块验证码...")
    success = await handle_slider(page, CONFIG)
    if not success:
        raise RuntimeError("滑块验证码处理失败，脚本终止")

    # 等待登录完成（URL 变化或首页元素出现）
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=15000)
        print("      登录成功！")
    except PlaywrightTimeoutError:
        # 有些系统登录后 URL 不变，改为等待导航菜单出现
        try:
            await page.wait_for_selector(
                "[class*='menu'], [class*='nav'], [class*='sidebar']",
                timeout=10000
            )
            print("      登录成功！")
        except PlaywrightTimeoutError:
            raise RuntimeError("登录超时，可能账号密码错误或验证未通过")


async def step_navigate(page):
    """步骤4：导航到 采购管理 → 订货通知单"""
    print("\n[4/5] 导航到订货通知单...")
    await close_dialogs(page)

    # 点击"采购管理"菜单
    procurement_selectors = [
        'text=采购管理',
        '[class*="menu-item"]:has-text("采购管理")',
        'li:has-text("采购管理")',
    ]
    for sel in procurement_selectors:
        try:
            await page.click(sel, timeout=5000)
            await asyncio.sleep(0.8)
            break
        except Exception:
            pass

    # 点击"订货通知单"子菜单
    order_notice_selectors = [
        'text=订货通知单',
        '[class*="menu-item"]:has-text("订货通知单")',
        'li:has-text("订货通知单")',
    ]
    for sel in order_notice_selectors:
        try:
            await page.click(sel, timeout=5000)
            await asyncio.sleep(1)
            break
        except Exception:
            pass

    # 等待页面内容加载
    await page.wait_for_load_state("networkidle", timeout=15000)
    print("      已进入订货通知单页面")


async def step_query(page, date_start: str, date_end: str):
    """步骤5：筛选日期并查询"""
    print(f"\n[5/5] 筛选日期 {date_start} ~ {date_end} 并查询...")
    await close_dialogs(page)

    # 填写开始日期
    date_start_selectors = [
        'input[placeholder*="开始日期"]',
        'input[placeholder*="起始日期"]',
        '[class*="date-start"] input',
        '[class*="start-date"] input',
    ]
    for sel in date_start_selectors:
        try:
            await page.fill(sel, date_start, timeout=3000)
            await page.keyboard.press("Tab")
            break
        except Exception:
            pass

    # 填写结束日期
    date_end_selectors = [
        'input[placeholder*="结束日期"]',
        'input[placeholder*="截止日期"]',
        '[class*="date-end"] input',
        '[class*="end-date"] input',
    ]
    for sel in date_end_selectors:
        try:
            await page.fill(sel, date_end, timeout=3000)
            await page.keyboard.press("Tab")
            break
        except Exception:
            pass

    await asyncio.sleep(0.5)

    # 点击查询按钮
    query_selectors = [
        'button:has-text("查询")',
        'button:has-text("搜索")',
        '[class*="search-btn"]',
        '[class*="query-btn"]',
    ]
    for sel in query_selectors:
        try:
            await page.click(sel, timeout=5000)
            break
        except Exception:
            pass

    # 等待查询结果加载
    await page.wait_for_load_state("networkidle", timeout=20000)
    # 等待表格行出现
    for table_sel in ["tr.el-table__row", ".ant-table-row", "[class*='table-row']", "tbody tr"]:
        try:
            await page.wait_for_selector(table_sel, timeout=10000, state="visible")
            break
        except Exception:
            pass
    print("      查询完成")


async def step_export(page, download_dir: str):
    """步骤6：全选并导出 Excel"""
    print("\n[导出] 全选数据并导出 Excel...")
    await close_dialogs(page)

    # 全选（通常是表头的 checkbox）
    select_all_selectors = [
        'th input[type="checkbox"]',
        '.el-table__header input[type="checkbox"]',
        '.ant-table-thead input[type="checkbox"]',
        'button:has-text("全选")',
        '[class*="select-all"]',
    ]
    for sel in select_all_selectors:
        try:
            await page.click(sel, timeout=3000)
            await asyncio.sleep(0.5)
            break
        except Exception:
            pass

    # 点击导出按钮
    export_selectors = [
        'button:has-text("导出")',
        'button:has-text("导出Excel")',
        'button:has-text("下载")',
        '[class*="export-btn"]',
        '[class*="download-btn"]',
    ]
    export_clicked = False
    for sel in export_selectors:
        try:
            await page.click(sel, timeout=5000)
            export_clicked = True
            await asyncio.sleep(0.5)
            break
        except Exception:
            pass

    if not export_clicked:
        raise RuntimeError("找不到导出按钮，请检查页面元素")

    # 可能出现二次确认弹窗
    for confirm_sel in [
        'button:has-text("确认")',
        'button:has-text("确定")',
        'button:has-text("确认导出")',
        '.el-button--primary:has-text("确定")',
    ]:
        try:
            el = page.locator(confirm_sel).first
            if await el.is_visible():
                await el.click()
                break
        except Exception:
            pass

    # 监听下载事件，保存文件
    print(f"      等待文件下载到：{download_dir}")
    try:
        async with page.expect_download(timeout=60000) as dl_info:
            # 若导出按钮点击后未触发下载，再尝试一次确认按钮
            pass
        download = await dl_info.value
        filename = download.suggested_filename or f"订货通知单_{datetime.today().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path = os.path.join(download_dir, filename)
        await download.save_as(save_path)
        print(f"\n✓ 导出成功！文件已保存至：{save_path}")
        return save_path
    except PlaywrightTimeoutError:
        raise RuntimeError("下载超时，请检查导出按钮是否正确触发")


# ──────────────────────────────────────────────
# 主流程（含重试）
# ──────────────────────────────────────────────

async def run():
    date_start, date_end = get_date_range()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=CONFIG["headless"],
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            viewport=None,           # 使用最大化窗口
            accept_downloads=True,
            locale="zh-CN",
        )
        # 自动关闭意外弹出的 alert/confirm/prompt
        context.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))

        page = await context.new_page()
        page.set_default_timeout(CONFIG["timeout"])

        for attempt in range(1, CONFIG["max_retries"] + 1):
            try:
                await step_login(page)
                await step_navigate(page)
                await step_query(page, date_start, date_end)
                await step_export(page, CONFIG["download_dir"])
                break  # 成功，退出重试循环

            except PlaywrightTimeoutError as e:
                print(f"\n[警告] 操作超时（第 {attempt} 次）：{e}")
                if attempt < CONFIG["max_retries"]:
                    print(f"       {attempt * 2} 秒后重试...")
                    await asyncio.sleep(attempt * 2)
                    await page.reload(wait_until="networkidle")
                else:
                    print("[错误] 已达最大重试次数，脚本退出")
                    sys.exit(1)

            except RuntimeError as e:
                print(f"\n[错误] {e}")
                sys.exit(1)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
