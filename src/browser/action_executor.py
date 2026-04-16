"""动作执行器 — 在页面上执行填写、点击、选择、上传等操作

所有操作都通过 HumanLike 模块加入随机延迟，模拟人类行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from src.browser.human_like import HumanLike


@dataclass
class Action:
    """单个操作指令"""
    type: str           # "fill", "click", "select", "upload", "check"
    selector: str       # CSS selector
    value: Optional[str] = None  # 填写的值 / 选择的选项 / 文件路径


@dataclass
class ActionResult:
    """操作执行结果"""
    success: bool
    action: Action
    error: Optional[str] = None


class ActionExecutor:
    """根据指令在页面上执行操作（带人类行为模拟）"""

    def __init__(self, timeout: int = 5000, human: HumanLike | None = None):
        self._timeout = timeout
        self._human = human or HumanLike()

    async def execute(self, page: Page, action: Action) -> ActionResult:
        """执行单个操作，返回结果（操作前后加随机延迟）"""
        try:
            handler = self._get_handler(action.type)
            await handler(page, action)
            logger.debug(f"✓ {action.type} {action.selector} = {action.value!r}")
            # 操作后随机延迟
            await self._human.action_delay()
            return ActionResult(success=True, action=action)
        except Exception as e:
            logger.warning(f"✗ {action.type} {action.selector}: {e}")
            return ActionResult(success=False, action=action, error=str(e))

    def _get_handler(self, action_type: str):
        """根据操作类型返回对应的处理函数"""
        handlers = {
            "fill": self._fill,
            "click": self._click,
            "select": self._select,
            "upload": self._upload,
            "check": self._check,
        }
        handler = handlers.get(action_type)
        if not handler:
            raise ValueError(f"未知操作类型: {action_type}")
        return handler

    async def _fill(self, page: Page, action: Action) -> None:
        """填写文本输入框（模拟人类逐字打字）"""
        el = page.locator(action.selector).first
        await self._human.human_type_element(el, page, action.value or "")

    async def _click(self, page: Page, action: Action) -> None:
        """点击元素"""
        await page.locator(action.selector).first.click(timeout=self._timeout)

    async def _select(self, page: Page, action: Action) -> None:
        """选择下拉框选项"""
        el = page.locator(action.selector).first
        try:
            # 先尝试原生 <select>
            await el.select_option(action.value or "", timeout=self._timeout)
        except Exception:
            # fallback: 自定义下拉框 — 点击展开，再点击匹配的选项
            await el.click(timeout=self._timeout)
            option = page.locator(f"text={action.value}").first
            await option.click(timeout=self._timeout)

    async def _upload(self, page: Page, action: Action) -> None:
        """上传文件"""
        if not action.value:
            raise ValueError("upload 操作需要提供文件路径")
        await page.locator(action.selector).first.set_input_files(
            action.value, timeout=self._timeout
        )

    async def _check(self, page: Page, action: Action) -> None:
        """勾选/取消勾选 checkbox"""
        el = page.locator(action.selector).first
        if action.value == "false":
            await el.uncheck(timeout=self._timeout)
        else:
            await el.check(timeout=self._timeout)

    async def execute_batch(self, page: Page, actions: list[Action]) -> list[ActionResult]:
        """批量执行操作，返回所有结果"""
        results = []
        for action in actions:
            result = await self.execute(page, action)
            results.append(result)
        return results
