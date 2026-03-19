import os

CONFIG = {
    "url": os.environ.get("YH_URL", "https://glzx.yonghui.cn/login"),
    "username": os.environ.get("YH_USERNAME", "15810698941"),
    "password": os.environ.get("YH_PASSWORD", "SyDt2024666888"),
    "download_dir": os.environ.get(
        "YH_DOWNLOAD_DIR",
        os.path.join(os.path.expanduser("~"), "Desktop"),
    ),
    # headless=False 表示显示浏览器窗口，方便观察和调试
    "headless": os.environ.get("YH_HEADLESS", "false").lower() == "true",
    # 滑块自动识别失败后等待手动处理的超时时间（秒）
    "manual_slider_timeout": int(os.environ.get("YH_SLIDER_TIMEOUT", "60")),
    # 操作超时时间（毫秒）
    "timeout": int(os.environ.get("YH_TIMEOUT", "30000")),
    # 最大重试次数
    "max_retries": int(os.environ.get("YH_MAX_RETRIES", "3")),
}
