"""测试 LinkedIn 导航器 — 登录、搜索、解析职位列表

用法：
    1. 先在 config/secrets.yaml 填入你的 LinkedIn 账号密码
    2. .venv/bin/python tests/test_linkedin_nav.py

首次运行需要登录（自动或手动），之后 session 会自动恢复。
"""

import asyncio

import yaml

from src.browser.browser_manager import BrowserManager
from src.linkedin.navigator import LinkedInNavigator


def load_secrets() -> dict:
    """读取 secrets.yaml"""
    try:
        with open("config/secrets.yaml", "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


async def main():
    bm = BrowserManager()
    await bm.launch()
    page = await bm.new_page()

    nav = LinkedInNavigator(page)

    # 检查登录状态
    logged_in = await nav.is_logged_in()
    if not logged_in:
        secrets = load_secrets()
        email = secrets.get("linkedin", {}).get("email", "")
        password = secrets.get("linkedin", {}).get("password", "")

        if email and password:
            print("从 config/secrets.yaml 读取凭证，自动登录...")
            logged_in = await nav.login(email, password)
        else:
            print("\nconfig/secrets.yaml 中未配置账号密码")
            print("请在浏览器中手动登录 LinkedIn...")
            await page.goto("https://www.linkedin.com/login")
            try:
                await page.wait_for_url("**/feed/**", timeout=120000)
                logged_in = True
                print("登录成功！")
            except Exception:
                print("登录超时")

    if not logged_in:
        print("登录失败，退出")
        await bm.close()
        return

    # 搜索职位
    await nav.search_jobs("Software Engineer", "Shanghai")

    # 等一下让页面完全加载
    await page.wait_for_timeout(3000)

    # 解析职位列表
    listings = await nav.get_job_listings()

    print(f"\n{'=' * 60}")
    print(f"找到 {len(listings)} 个职位:")
    print("=" * 60)
    for i, job in enumerate(listings):
        tag = "[Easy Apply]" if job.is_easy_apply else "[External]"
        print(f"  {i+1}. {tag} {job.title}")
        print(f"     {job.company} | {job.location}")
        print(f"     {job.url[:80]}...")
        print()

    await bm.close()


if __name__ == "__main__":
    asyncio.run(main())
