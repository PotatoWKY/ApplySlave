"""调试滚动加载"""
import asyncio
from playwright.async_api import async_playwright

async def debug():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir="data/chrome_profile", headless=False, slow_mo=100,
        channel="chrome", args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(
        "https://www.linkedin.com/jobs/search/?keywords=Software+Engineer&location=Seattle&f_AL=true"
    )
    await page.wait_for_timeout(5000)

    cards_before = len(await page.query_selector_all(".job-card-container"))
    print(f"Cards before scroll: {cards_before}")

    # 找 card 的可滚动祖先
    scrollable_info = await page.evaluate("""() => {
        const card = document.querySelector('.job-card-container');
        if (!card) return 'no card';
        let el = card.parentElement;
        const chain = [];
        while (el) {
            chain.push({
                tag: el.tagName,
                cls: (el.className || '').substring(0, 80),
                sh: el.scrollHeight,
                ch: el.clientHeight,
                scrollable: el.scrollHeight > el.clientHeight + 10,
            });
            el = el.parentElement;
        }
        return chain;
    }""")
    print("Parent chain:")
    for item in scrollable_info:
        mark = ">>>" if item.get("scrollable") else "   "
        print(f"  {mark} <{item['tag']}> cls='{item['cls'][:50]}' scrollH={item['sh']} clientH={item['ch']}")

    # 尝试在可滚动祖先里 scrollBy
    for i in range(5):
        await page.evaluate("""() => {
            const card = document.querySelector('.job-card-container');
            if (!card) return;
            let el = card.parentElement;
            while (el) {
                if (el.scrollHeight > el.clientHeight + 10) {
                    el.scrollBy(0, 800);
                    return 'scrolled ' + el.tagName + ' ' + el.className.substring(0,40);
                }
                el = el.parentElement;
            }
            window.scrollBy(0, 800);
            return 'scrolled window';
        }""")
        await page.wait_for_timeout(2000)
        cards_now = len(await page.query_selector_all(".job-card-container"))
        print(f"Scroll {i+1}: {cards_now} cards")

    await ctx.close()
    await p.stop()

asyncio.run(debug())
