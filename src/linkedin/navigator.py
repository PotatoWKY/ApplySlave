"""LinkedIn 导航器 — 登录、搜索职位、解析职位列表（硬编码）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger
from playwright.async_api import Page

# LinkedIn URL 常量
LOGIN_URL = "https://www.linkedin.com/login"
JOBS_SEARCH_URL = "https://www.linkedin.com/jobs/search/"
FEED_URL = "https://www.linkedin.com/feed/"


@dataclass
class JobListing:
    """职位列表项"""
    title: str
    company: str
    location: str
    url: str
    is_easy_apply: bool


class LinkedInNavigator:
    """LinkedIn 页面导航和操作（硬编码）"""

    def __init__(self, page: Page):
        self._page = page

    async def is_logged_in(self) -> bool:
        """检查是否已登录（尝试访问 feed 页，看是否被重定向）"""
        try:
            await self._page.goto(FEED_URL, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            logger.warning(f"访问 feed 页失败: {e}")
            return False

        await self._page.wait_for_timeout(2000)

        current = self._page.url
        logged_in = "feed" in current and "login" not in current
        logger.info(f"登录状态: {'已登录' if logged_in else '未登录'} ({current})")
        return logged_in

    async def login(self, email: str, password: str) -> bool:
        """登录 LinkedIn，遇到二次验证会暂停等用户手动处理"""
        logger.info(f"使用凭证登录: {email}")
        await self._page.goto(LOGIN_URL, wait_until="domcontentloaded")

        await self._page.fill("#username", email)
        await self._page.fill("#password", password)
        await self._page.click('button[type="submit"]')

        await self._page.wait_for_load_state("domcontentloaded")

        current = self._page.url
        if "checkpoint" in current or "challenge" in current:
            logger.warning("检测到二次验证，请在浏览器中手动完成（最多等待 120 秒）")
            try:
                await self._page.wait_for_url("**/feed/**", timeout=120000)
            except Exception:
                logger.error("等待二次验证超时")
                return False

        is_in = "feed" in self._page.url
        if is_in:
            logger.info("登录成功")
        else:
            logger.error(f"登录失败，当前页面: {self._page.url}")
        return is_in

    async def search_jobs(
        self,
        keywords: str,
        location: str,
        easy_apply_only: bool = False,
    ) -> None:
        """搜索职位"""
        logger.info(f"搜索职位: keywords='{keywords}', location='{location}', easy_apply_only={easy_apply_only}")

        # URL encode 参数，防止空格等特殊字符导致请求失败
        params = f"?keywords={quote_plus(keywords)}&location={quote_plus(location)}"
        if easy_apply_only:
            params += "&f_AL=true"
        url = JOBS_SEARCH_URL + params

        logger.debug(f"搜索 URL: {url}")
        await self._page.goto(url, wait_until="domcontentloaded")

        # 等待职位卡片出现 — 多个 selector 兼容不同版本
        selectors = [
            ".jobs-search-results-list",           # 搜索结果容器
            ".jobs-search-results__list-item",      # 单个职位卡片
            ".job-card-container",                  # 备用卡片容器
            "li.ember-view.occludable-update",      # 另一种卡片容器
            "[data-job-id]",                        # 带 job-id 属性的元素
        ]
        selector_str = ", ".join(selectors)
        try:
            await self._page.wait_for_selector(selector_str, timeout=15000)
            logger.info("职位列表已加载")
        except Exception:
            logger.warning("职位列表加载超时，可能没有搜索结果")
            # 打印页面内容帮助调试
            title = await self._page.title()
            logger.debug(f"当前页面 title: {title}, url: {self._page.url}")

    async def get_job_listings(self, max_jobs: int = 25) -> list[JobListing]:
        """解析当前搜索结果页的职位列表，通过滚动加载更多"""
        listings = []
        seen_urls = set()

        # 找到职位列表的滚动容器
        scroll_container = await self._find_scroll_container()

        # 用于检测的 card selector
        card_selectors = [
            ".jobs-search-results__list-item",
            ".job-card-container",
            "li[data-occludable-job-id]",
            ".jobs-search-results-list li.ember-view",
        ]

        max_scroll_attempts = 15
        no_new_count = 0

        for scroll_round in range(max_scroll_attempts):
            # 找卡片
            cards = []
            winning_sel = ""
            for sel in card_selectors:
                cards = await self._page.query_selector_all(sel)
                if cards:
                    winning_sel = sel
                    break

            if not cards:
                if scroll_round == 0:
                    logger.warning("未找到任何职位卡片")
                break

            # 解析新卡片
            new_count = 0
            for card in cards:
                try:
                    listing = await self._parse_job_card(card)
                    if listing and listing.url not in seen_urls:
                        seen_urls.add(listing.url)
                        listings.append(listing)
                        new_count += 1
                except Exception as e:
                    logger.warning(f"解析职位卡片失败: {e}")
                    continue

            logger.debug(f"滚动第 {scroll_round+1} 轮: DOM 中 {len(cards)} 个卡片, 新增 {new_count} 个, 总计 {len(listings)} 个")

            # 够了就停
            if len(listings) >= max_jobs:
                logger.info(f"已达到目标数量 {max_jobs}，停止滚动")
                break

            # 没有新卡片 = 到底了
            if new_count == 0:
                no_new_count += 1
                if no_new_count >= 2:
                    logger.info("连续 2 轮无新卡片，列表已到底")
                    break
            else:
                no_new_count = 0

            # 滚动加载更多
            await self._scroll_job_list(scroll_container)
            await self._page.wait_for_timeout(2000)

        easy_count = sum(1 for j in listings if j.is_easy_apply)
        logger.info(f"解析完成: {len(listings)} 个职位, 其中 Easy Apply {easy_count} 个")
        return listings

    async def _find_scroll_container(self):
        """找到职位列表的滚动容器"""
        # LinkedIn 的职位列表在一个可滚动的 div 里
        container_selectors = [
            '.jobs-search-results-list',
            '.jobs-search-two-pane__results',
            '[class*="jobs-search-results"]',
        ]
        for sel in container_selectors:
            el = await self._page.query_selector(sel)
            if el:
                logger.debug(f"找到滚动容器: {sel}")
                return el
        logger.debug("未找到专用滚动容器，将使用页面滚动")
        return None

    async def _scroll_job_list(self, container) -> None:
        """滚动职位列表加载更多（逐步滚动触发懒加载）"""
        try:
            # 找到 job card 的可滚动祖先容器并 scrollBy
            await self._page.evaluate("""() => {
                const card = document.querySelector('.job-card-container');
                if (!card) { window.scrollBy(0, 800); return; }
                let el = card.parentElement;
                while (el) {
                    if (el.scrollHeight > el.clientHeight + 10) {
                        el.scrollBy(0, 800);
                        return;
                    }
                    el = el.parentElement;
                }
                window.scrollBy(0, 800);
            }""")
        except Exception as e:
            logger.debug(f"滚动失败: {e}")

    async def _parse_job_card(self, card) -> Optional[JobListing]:
        """解析单个职位卡片"""
        # 职位名 — 多种 selector 兼容
        title_selectors = [
            ".job-card-list__title--link strong",
            "a.job-card-container__link strong",
            ".job-card-list__title strong",
            "a[data-control-name='job_card_title'] strong",
            ".artdeco-entity-lockup__title strong",
            "a strong",  # 最宽泛的 fallback
        ]
        title = await self._try_get_text(card, title_selectors, "Unknown")

        # 公司名
        company_selectors = [
            ".artdeco-entity-lockup__subtitle span",
            ".job-card-container__primary-description",
            ".job-card-container__company-name",
            "a.job-card-container__company-name",
        ]
        company = await self._try_get_text(card, company_selectors, "Unknown")

        # 地点
        location_selectors = [
            ".artdeco-entity-lockup__caption span",
            ".job-card-container__metadata-wrapper li",
            ".job-card-container__metadata-item",
        ]
        location = await self._try_get_text(card, location_selectors, "Unknown")

        # 链接
        link_el = await card.query_selector("a[href*='/jobs/view/']")
        if not link_el:
            link_el = await card.query_selector("a[href*='/jobs/']")
        url = ""
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                url = f"https://www.linkedin.com{href}" if href.startswith("/") else href

        # 是否 Easy Apply — 检查多种标识
        is_easy_apply = False
        card_text = (await card.text_content() or "").lower()
        if "easy apply" in card_text:
            is_easy_apply = True
        else:
            # 检查是否有 Easy Apply 图标/标签
            easy_badge = await card.query_selector(
                '[class*="easy-apply"], [aria-label*="Easy Apply"], .job-card-container__apply-method'
            )
            if easy_badge:
                is_easy_apply = True

        logger.debug(
            f"  解析: title='{title}', company='{company}', "
            f"location='{location}', easy_apply={is_easy_apply}, url='{url[:80]}'"
        )

        return JobListing(
            title=title,
            company=company,
            location=location,
            url=url,
            is_easy_apply=is_easy_apply,
        )

    async def _try_get_text(self, parent, selectors: list[str], default: str) -> str:
        """依次尝试多个 selector，返回第一个匹配到的文本"""
        for sel in selectors:
            el = await parent.query_selector(sel)
            if el:
                text = (await el.text_content() or "").strip()
                if text:
                    return text
        return default

    async def next_page(self) -> bool:
        """翻到下一页，返回是否成功"""
        next_btn = await self._page.query_selector(
            'button[aria-label="View next page"]'
        )
        if not next_btn:
            logger.info("没有下一页了")
            return False

        is_disabled = await next_btn.get_attribute("disabled")
        if is_disabled:
            logger.info("下一页按钮已禁用")
            return False

        await next_btn.click()
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        logger.info("已翻到下一页")
        return True

    async def click_job(self, listing: JobListing) -> None:
        """点击一个职位，打开详情面板"""
        # 清理 URL — 去掉 tracking 参数，只保留 job ID
        clean_url = listing.url
        if clean_url and "/jobs/view/" in clean_url:
            # 提取 /jobs/view/12345/ 部分
            import re
            match = re.search(r'(/jobs/view/\d+/)', clean_url)
            if match:
                clean_url = f"https://www.linkedin.com{match.group(1)}"

        logger.debug(f"打开职位: {listing.title} @ {listing.company}, url={clean_url}")

        if not clean_url:
            logger.warning(f"职位 URL 为空: {listing.title}")
            return

        await self._page.goto(clean_url, wait_until="domcontentloaded")

        # 等待职位详情面板或 Apply 按钮加载
        try:
            await self._page.wait_for_selector(
                '.jobs-unified-top-card, .job-details-jobs-unified-top-card__container, '
                '.jobs-details, .jobs-search__job-details, '
                'button.jobs-apply-button, button:has-text("Apply")',
                timeout=15000,
            )
            logger.debug("职位详情面板已加载")
        except Exception:
            logger.warning("职位详情面板加载超时")

        # 额外等待让动态内容渲染完成
        await self._page.wait_for_timeout(2000)
        logger.info(f"已打开职位: {listing.title} @ {listing.company}")

    async def detect_apply_type(self) -> str:
        """检测当前职位详情页的申请类型"""
        # 查找所有 apply 相关按钮
        buttons = await self._page.query_selector_all('button')
        for btn in buttons:
            text = (await btn.text_content() or "").strip().lower()
            visible = await btn.is_visible()
            if not visible:
                continue
            if "easy apply" in text:
                logger.debug(f"检测到 Easy Apply 按钮: '{text}'")
                return "easy_apply"
            if "apply" in text and "easy" not in text:
                logger.debug(f"检测到外部 Apply 按钮: '{text}'")
                return "external"

        logger.debug("未检测到 Apply 按钮")
        return "unknown"
