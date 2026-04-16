"""测试 DOMExtractor — 在真实 LinkedIn 页面上提取表单元素

用法：
    .venv/bin/python tests/test_extractor.py

流程：
    1. 打开浏览器（如果有已保存的 session 会自动恢复登录）
    2. 导航到 LinkedIn 职位搜索页
    3. 暂停 60 秒，让你手动操作（登录、打开一个职位的申请页面等）
    4. 提取当前页面的所有可交互元素并打印
    5. 保存 session 后关闭
"""

import asyncio
import json

from src.browser.browser_manager import BrowserManager
from src.browser.dom_extractor import DOMExtractor


async def main():
    bm = BrowserManager()  # headed 模式，能看到浏览器
    await bm.launch()
    page = await bm.new_page()

    # 打开 LinkedIn 职位页
    await page.goto("https://www.linkedin.com/jobs/")

    print("\n" + "=" * 60)
    print("浏览器已打开 LinkedIn Jobs 页面")
    print("请在浏览器中操作：")
    print("  1. 如果未登录，请手动登录")
    print("  2. 搜索一个职位，点击 Easy Apply 或 Apply")
    print("  3. 停留在你想测试的页面上")
    print("=" * 60)
    print("等待 60 秒后自动提取当前页面元素...")
    print("（或者你可以按 Ctrl+C 提前结束等待）\n")

    try:
        await page.wait_for_timeout(60000)
    except KeyboardInterrupt:
        print("\n手动结束等待，开始提取...")

    # 提取当前页面
    extractor = DOMExtractor()
    dom = await extractor.extract(page)

    print(f"\n{'=' * 60}")
    print(f"页面: {dom.title}")
    print(f"URL:  {dom.url}")
    print(f"提取到 {len(dom.elements)} 个可交互元素:")
    print("=" * 60)

    for el in dom.elements:
        print(json.dumps(el.to_dict(), ensure_ascii=False, indent=2))
        print("---")

    # 保存完整结果到文件，方便后续分析
    output_path = "data/test_dom_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dom.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到: {output_path}")

    await bm.close()


if __name__ == "__main__":
    asyncio.run(main())
