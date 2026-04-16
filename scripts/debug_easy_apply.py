"""调试 Easy Apply 流程 — 自动搜索职位并尝试 Easy Apply (DRY RUN)

用法：
    .venv/bin/python scripts/debug_easy_apply.py
"""

import asyncio
import sys
from pathlib import Path

import yaml
from loguru import logger

# 配置 loguru — DEBUG 级别，输出到 stderr 和文件
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="{time:HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}")
logger.add("data/debug_easy_apply.log", level="DEBUG", rotation="1 MB",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}")

from src.browser.browser_manager import BrowserManager
from src.linkedin.navigator import LinkedInNavigator
from src.linkedin.easy_apply import EasyApplyHandler


def load_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.warning(f"配置文件不存在: {path}")
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def run():
    settings = load_yaml("config/settings.yaml")

    # 强制 dry_run
    dry_run = True
    logger.info(f"=== DEBUG EASY APPLY (dry_run={dry_run}) ===")

    # 浏览器配置
    browser_cfg = settings.get("browser", {})
    bm = BrowserManager(
        headless=browser_cfg.get("headless", False),
        slow_mo=browser_cfg.get("slow_mo", 100),
    )
    await bm.launch()
    logger.debug(f"BrowserManager 已启动, headless={browser_cfg.get('headless', False)}")

    pages = bm.context.pages
    page = pages[0] if pages else await bm.new_page()
    logger.debug(f"使用页面: {page.url}")

    nav = LinkedInNavigator(page)

    # 1. 检查登录
    logged_in = await nav.is_logged_in()
    if not logged_in:
        logger.info("未登录，请在浏览器中手动登录 LinkedIn（最多等待 120 秒）")
        await page.goto("https://www.linkedin.com/login")
        try:
            await page.wait_for_url("**/feed/**", timeout=120000)
            logged_in = True
            logger.info("登录成功")
        except Exception:
            logger.error("登录超时，退出")
            await bm.close()
            return

    # 2. 搜索职位
    search_cfg = settings.get("linkedin", {}).get("search", {})
    keywords = search_cfg.get("keywords", "Software Engineer")
    location = search_cfg.get("location", "Seattle")
    easy_apply_only = search_cfg.get("easy_apply_only", False)

    logger.info(f"搜索: keywords={keywords}, location={location}, easy_apply_only={easy_apply_only}")
    await nav.search_jobs(keywords, location, easy_apply_only)
    await page.wait_for_timeout(3000)

    # 3. 解析职位列表
    listings = await nav.get_job_listings()
    logger.info(f"找到 {len(listings)} 个职位")
    for i, job in enumerate(listings):
        tag = "[Easy Apply]" if job.is_easy_apply else "[External]"
        logger.debug(f"  {i+1}. {tag} {job.title} @ {job.company} | {job.location} | url={job.url}")

    easy_apply_jobs = [j for j in listings if j.is_easy_apply]
    logger.info(f"其中 Easy Apply: {len(easy_apply_jobs)} 个")

    if not easy_apply_jobs:
        logger.warning("没有找到 Easy Apply 职位，退出")
        await bm.close()
        return

    # 4. 只尝试第一个 Easy Apply 职位（调试用）
    job = easy_apply_jobs[0]
    logger.info(f"=== 尝试投递: {job.title} @ {job.company} ===")
    logger.debug(f"职位 URL: {job.url}")

    await nav.click_job(job)
    await page.wait_for_timeout(3000)

    logger.debug(f"当前页面 URL: {page.url}")
    logger.debug(f"当前页面 title: {await page.title()}")

    # 截图保存
    screenshot_path = "data/debug_before_apply.png"
    await page.screenshot(path=screenshot_path)
    logger.debug(f"截图已保存: {screenshot_path}")

    # 打印页面上所有按钮（调试）
    buttons = await page.query_selector_all("button")
    logger.debug(f"页面上共有 {len(buttons)} 个 button 元素:")
    for btn in buttons:
        text = (await btn.text_content() or "").strip()
        visible = await btn.is_visible()
        if text and visible:
            class_name = await btn.get_attribute("class") or ""
            aria = await btn.get_attribute("aria-label") or ""
            logger.debug(f"  [BUTTON] text='{text[:80]}' visible={visible} class='{class_name[:60]}' aria='{aria}'")

    # 执行 Easy Apply
    handler = EasyApplyHandler(page, dry_run=True)
    result = await handler.apply(job.title, job.company)

    if result.success:
        logger.info(f"✓ DRY RUN 成功: {job.title} @ {job.company} (完成 {result.steps_completed} 步)")
    else:
        logger.error(f"✗ 投递失败: {job.title} @ {job.company} — {result.error} (完成 {result.steps_completed} 步)")

    # 截图保存结果
    await page.screenshot(path="data/debug_after_apply.png")
    logger.debug("结果截图已保存: data/debug_after_apply.png")

    logger.info("=== 调试完成 ===")
    await bm.close()


if __name__ == "__main__":
    asyncio.run(run())
