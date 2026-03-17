import os

CONFIG = {
    "url": "https://glzx.yonghui.cn/login",
    "username": "15810698941",
    "password": "SyDt2024666888",
    "download_dir": r"C:\Users\Administrator\Desktop",
    # headless=False 表示显示浏览器窗口，方便观察和调试
    "headless": False,
    # 滑块自动识别失败后等待手动处理的超时时间（秒）
    "manual_slider_timeout": 60,
    # 操作超时时间（毫秒）
    "timeout": 30000,
    # 最大重试次数
    "max_retries": 3,
}
