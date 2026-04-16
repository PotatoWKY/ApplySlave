"""人类行为模拟 — 随机延迟、打字模拟、鼠标移动，降低自动化检测风险

核心策略：
1. 随机化所有时间间隔（不要均匀的 slow_mo）
2. 模拟人类打字速度（每个字符之间有随机延迟）
3. 操作之间加入随机等待
4. 偶尔做一些"人类行为"（滚动、停顿）
5. 控制每日投递量和时间窗口
"""

from __future__ import annotations

import random
import asyncio
from datetime import datetime

from loguru import logger
from playwright.async_api import Page


# 默认配置（可被 settings.yaml 覆盖）
DEFAULT_ANTI_DETECTION = {
    "typing_delay_min": 50,       # 打字每个字符最小延迟 ms
    "typing_delay_max": 180,      # 打字每个字符最大延迟 ms
    "action_delay_min": 800,      # 操作之间最小延迟 ms
    "action_delay_max": 2500,     # 操作之间最大延迟 ms
    "page_delay_min": 3000,       # 页面切换最小延迟 ms
    "page_delay_max": 8000,       # 页面切换最大延迟 ms
    "between_jobs_min": 5000,     # 两个职位之间最小延迟 ms
    "between_jobs_max": 15000,    # 两个职位之间最大延迟 ms
    "active_hours_start": 8,      # 允许运行的开始时间（24h）
    "active_hours_end": 22,       # 允许运行的结束时间（24h）
    "daily_max_variance": 8,      # 每日最大投递数的随机浮动范围
    "browse_without_apply_chance": 0.15,  # 浏览但不投递的概率（模拟人类挑选行为）
}


class HumanLike:
    """模拟人类行为的工具类"""

    def __init__(self, config: dict | None = None):
        self._cfg = {**DEFAULT_ANTI_DETECTION, **(config or {})}

    # ── 随机延迟 ──

    async def action_delay(self) -> None:
        """操作之间的随机延迟（点击、填写等）"""
        ms = random.randint(self._cfg["action_delay_min"], self._cfg["action_delay_max"])
        await asyncio.sleep(ms / 1000)

    async def page_delay(self) -> None:
        """页面切换时的随机延迟"""
        ms = random.randint(self._cfg["page_delay_min"], self._cfg["page_delay_max"])
        logger.debug(f"页面延迟: {ms}ms")
        await asyncio.sleep(ms / 1000)

    async def between_jobs_delay(self) -> None:
        """两个职位之间的随机延迟"""
        ms = random.randint(self._cfg["between_jobs_min"], self._cfg["between_jobs_max"])
        logger.debug(f"职位间延迟: {ms}ms")
        await asyncio.sleep(ms / 1000)

    # ── 人类打字 ──

    async def human_type(self, page: Page, selector: str, text: str) -> None:
        """模拟人类打字 — 每个字符之间有随机延迟"""
        el = page.locator(selector).first
        await el.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # 先清空
        await el.fill("")
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # 逐字输入
        for char in text:
            await page.keyboard.type(char)
            delay_ms = random.randint(
                self._cfg["typing_delay_min"],
                self._cfg["typing_delay_max"],
            )
            await asyncio.sleep(delay_ms / 1000)

            # 偶尔打字中间停顿一下（模拟思考）
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    async def human_type_element(self, element, page: Page, text: str) -> None:
        """对已定位的元素模拟人类打字"""
        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await element.fill("")
        await asyncio.sleep(random.uniform(0.05, 0.15))

        for char in text:
            await page.keyboard.type(char)
            delay_ms = random.randint(
                self._cfg["typing_delay_min"],
                self._cfg["typing_delay_max"],
            )
            await asyncio.sleep(delay_ms / 1000)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    # ── 人类行为模拟 ──

    async def random_scroll(self, page: Page) -> None:
        """随机滚动页面（模拟人类浏览）"""
        direction = random.choice(["down", "up", "down", "down"])  # 偏向向下
        distance = random.randint(100, 500)
        if direction == "up":
            distance = -distance
        await page.mouse.wheel(0, distance)
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def simulate_reading(self, page: Page) -> None:
        """模拟阅读页面内容（随机停顿 + 滚动）"""
        # 停顿一会儿"阅读"
        await asyncio.sleep(random.uniform(1.5, 4.0))
        # 可能滚动一下
        if random.random() < 0.6:
            await self.random_scroll(page)
        # 再停顿
        await asyncio.sleep(random.uniform(0.5, 2.0))

    def should_skip_job(self) -> bool:
        """随机决定是否跳过这个职位（模拟人类挑选行为）"""
        return random.random() < self._cfg["browse_without_apply_chance"]

    # ── 时间窗口 ──

    def is_active_hours(self) -> bool:
        """检查当前是否在允许运行的时间窗口内"""
        hour = datetime.now().hour
        start = self._cfg["active_hours_start"]
        end = self._cfg["active_hours_end"]
        return start <= hour < end

    def get_effective_max_applications(self, base_max: int) -> int:
        """给每日最大投递数加随机浮动"""
        variance = self._cfg["daily_max_variance"]
        delta = random.randint(-variance, 0)  # 只减不加，保守一点
        return max(5, base_max + delta)


# ── Stealth 脚本 ──

STEALTH_INIT_SCRIPT = """
() => {
    // 1. 隐藏 webdriver 属性
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. 隐藏 Playwright 注入的全局变量
    delete window.__playwright__binding__;
    delete window.__pwInitScripts;

    // 3. 伪装 plugins（headless Chrome 默认没有 plugins）
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // 4. 伪装 languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // 5. 修复 chrome.runtime（Playwright 缺少这个）
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {};
    }

    // 6. 伪装 permissions API
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    }
}
"""
