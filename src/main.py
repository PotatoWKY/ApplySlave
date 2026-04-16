"""ApplySlave — 简历自动投递机器人

用法：
    .venv/bin/python -m src.main          # 正常运行（投递）
    .venv/bin/python -m src.main logout    # 登出（清除 session，切换账号）
"""

import asyncio
import sys
from pathlib import Path

import yaml
from loguru import logger

from src.browser.browser_manager import BrowserManager
from src.browser.human_like import HumanLike
from src.linkedin.navigator import LinkedInNavigator
from src.linkedin.easy_apply import EasyApplyHandler
from src.ai.llm_client import LLMClient
from src.ai.form_filler import FormFiller


def load_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.warning(f"配置文件不存在: {path}")
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def setup_logging(settings: dict) -> None:
    """根据配置文件设置 loguru"""
    log_cfg = settings.get("logging", {})
    level = log_cfg.get("level", "INFO")
    log_file = log_cfg.get("file", "data/apply-slave.log")

    logger.remove()  # 移除默认 handler
    logger.add(
        sys.stderr,
        level=level,
        format="{time:HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}",
    )
    logger.add(
        log_file,
        level="DEBUG",  # 文件始终记录 DEBUG
        rotation="5 MB",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}",
    )
    logger.info(f"日志级别: stderr={level}, file=DEBUG -> {log_file}")


async def run():
    settings = load_yaml("config/settings.yaml")
    setup_logging(settings)

    # 初始化反检测模块
    anti_cfg = settings.get("anti_detection", {})
    human = HumanLike(config=anti_cfg)

    # 检查时间窗口
    if not human.is_active_hours():
        logger.warning("当前不在活跃时间窗口内，退出（避免凌晨操作被检测）")
        logger.info(f"允许运行时间: {anti_cfg.get('active_hours_start', 8)}:00 - {anti_cfg.get('active_hours_end', 22)}:00")
        return

    # 浏览器配置
    browser_cfg = settings.get("browser", {})
    bm = BrowserManager(
        headless=browser_cfg.get("headless", False),
        slow_mo=browser_cfg.get("slow_mo", 0),
    )
    await bm.launch()

    # persistent context 启动时会自带一个空白页，用它而不是新建
    pages = bm.context.pages
    page = pages[0] if pages else await bm.new_page()

    nav = LinkedInNavigator(page)

    # 1. 检查登录状态
    logged_in = await nav.is_logged_in()
    if not logged_in:
        # 让用户在浏览器中自己登录（支持任何登录方式）
        # persistent context 会自动保存 cookie，下次启动自动恢复
        logger.info("请在浏览器中登录 LinkedIn（支持 Google/Apple/邮箱等任何方式）")
        logger.info("登录成功后程序会自动继续（最多等待 120 秒）")
        await page.goto("https://www.linkedin.com/login")
        try:
            await page.wait_for_url("**/feed/**", timeout=120000)
            logged_in = True
            logger.info("登录成功，cookie 已自动保存")
        except Exception:
            logged_in = False

    if not logged_in:
        logger.error("登录失败，退出")
        await bm.close()
        return

    # 2. 搜索职位
    search_cfg = settings.get("linkedin", {}).get("search", {})
    keywords = search_cfg.get("keywords", "Software Engineer")
    location = search_cfg.get("location", "Shanghai")
    easy_apply_only = search_cfg.get("easy_apply_only", False)

    await nav.search_jobs(keywords, location, easy_apply_only)
    await human.page_delay()

    # 3. 解析职位列表
    listings = await nav.get_job_listings()

    logger.info(f"找到 {len(listings)} 个职位")
    for i, job in enumerate(listings):
        tag = "[Easy Apply]" if job.is_easy_apply else "[External]"
        logger.info(f"  {i+1}. {tag} {job.title} @ {job.company} | {job.location}")

    # 4. 遍历 Easy Apply 职位并投递
    apply_cfg = settings.get("apply", {})
    dry_run = apply_cfg.get("dry_run", True)
    base_max = apply_cfg.get("max_applications", 25)
    effective_max = human.get_effective_max_applications(base_max)
    logger.info(f"今日最大投递数: {effective_max}（基准 {base_max}，随机浮动）")

    easy_apply_jobs = [j for j in listings if j.is_easy_apply]
    logger.info(f"开始投递 {len(easy_apply_jobs)} 个 Easy Apply 职位 (dry_run={dry_run})")

    # 初始化 LLM + FormFiller
    llm_cfg = settings.get("llm", {})
    profile = load_yaml("config/profile.yaml")
    llm = LLMClient(
        model=llm_cfg.get("model", "qwen2.5:7b"),
        base_url=llm_cfg.get("base_url", "http://localhost:11434"),
        timeout=llm_cfg.get("timeout", 60),
        max_retries=llm_cfg.get("max_retries", 3),
    )
    form_filler = FormFiller(llm=llm, profile=profile)
    logger.info(f"FormFiller 已初始化 (model={llm_cfg.get('model', 'qwen2.5:7b')})")

    handler = EasyApplyHandler(page, dry_run=dry_run, form_filler=form_filler, human=human)
    applied = 0
    skipped_browse = 0

    for job in easy_apply_jobs:
        # 再次检查时间窗口（长时间运行可能跨过边界）
        if not human.is_active_hours():
            logger.warning("已超出活跃时间窗口，停止投递")
            break

        if applied >= effective_max:
            logger.info(f"已达到今日最大投递数 {effective_max}，停止")
            break

        # 模拟人类挑选行为 — 有一定概率只浏览不投递
        if human.should_skip_job():
            skipped_browse += 1
            logger.info(f"[模拟浏览] 跳过 {job.title} @ {job.company}（模拟人类挑选，不投递）")
            await nav.click_job(job)
            await human.simulate_reading(page)
            await human.between_jobs_delay()
            continue

        # 打开职位详情
        await nav.click_job(job)
        await human.simulate_reading(page)

        # 执行 Easy Apply
        result = await handler.apply(job.title, job.company)
        if result.success:
            status = "DRY RUN 成功" if result.dry_run else "投递成功"
            logger.info(f"✓ {status}: {job.title} @ {job.company} (完成 {result.steps_completed} 步)")
            applied += 1
        else:
            logger.warning(f"✗ 投递失败: {job.title} @ {job.company} — {result.error} (完成 {result.steps_completed} 步)")

        # 两个职位之间的随机延迟
        await human.between_jobs_delay()

    logger.info(f"完成，共投递 {applied} 个职位，模拟浏览跳过 {skipped_browse} 个")
    await bm.close()


def logout():
    """登出 — 清除浏览器 session，下次运行时需要重新登录"""
    bm = BrowserManager()
    if bm.has_session:
        bm.clear_session()
        print("✓ 已清除登录状态，下次运行时请用新账号登录")
    else:
        print("当前没有已保存的登录状态")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "logout":
        logout()
    else:
        asyncio.run(run())
