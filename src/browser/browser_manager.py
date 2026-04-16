"""浏览器实例管理 — 启动、关闭、Session 持久化

使用 persistent context + 系统 Chrome，避免被 Google OAuth 检测为自动化浏览器。
用户数据保存在 data/chrome_profile/ 目录，登录状态自动持久化。
启动时注入 stealth 脚本，隐藏 Playwright 指纹特征。
"""

from pathlib import Path

from loguru import logger
from playwright.async_api import BrowserContext, Page, async_playwright

from src.browser.human_like import STEALTH_INIT_SCRIPT

# Chrome 用户数据目录（登录状态、cookie 等自动保存在这里）
DEFAULT_USER_DATA_DIR = Path("data/chrome_profile")


class BrowserManager:
    """管理 Playwright 浏览器生命周期和登录状态持久化"""

    def __init__(
        self,
        headless: bool = False,
        slow_mo: int = 0,
        user_data_dir: Path = DEFAULT_USER_DATA_DIR,
    ):
        self._headless = headless
        self._slow_mo = slow_mo
        self._user_data_dir = user_data_dir
        self._playwright = None
        self._context: BrowserContext | None = None

    async def launch(self) -> None:
        """启动浏览器（persistent context，登录状态自动持久化 + stealth 注入）"""
        self._playwright = await async_playwright().start()

        # 确保用户数据目录存在
        self._user_data_dir.mkdir(parents=True, exist_ok=True)

        # persistent context = 真实 Chrome profile
        # 登录状态、cookie、localStorage 自动保存和恢复
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._user_data_dir),
            headless=self._headless,
            slow_mo=self._slow_mo,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",  # 去掉自动化标记
            ],
            ignore_default_args=["--enable-automation"],  # 移除 Playwright 默认的自动化标志
        )

        # 注入 stealth 脚本 — 隐藏 Playwright 指纹
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        logger.info(f"浏览器已启动 + stealth 已注入 (profile: {self._user_data_dir})")

    async def new_page(self) -> Page:
        """创建新页面"""
        if not self._context:
            raise RuntimeError("浏览器未启动，请先调用 launch()")
        page = await self._context.new_page()
        logger.debug("新页面已创建")
        return page

    async def close(self) -> None:
        """关闭浏览器（persistent context 自动保存状态）"""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("浏览器已关闭")

    @property
    def context(self) -> BrowserContext | None:
        return self._context

    @property
    def has_session(self) -> bool:
        """是否有已保存的用户数据"""
        return self._user_data_dir.exists() and any(self._user_data_dir.iterdir())

    def clear_session(self) -> None:
        """清除用户数据目录"""
        import shutil
        if self._user_data_dir.exists():
            shutil.rmtree(self._user_data_dir)
            logger.info(f"已清除用户数据: {self._user_data_dir}")
