"""DOM 提取器 — 从页面提取所有可交互元素，生成结构化描述"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from loguru import logger
from playwright.async_api import Page


@dataclass
class PageElement:
    """单个可交互元素的结构化描述"""
    id: str                          # 内部编号 "el_0", "el_1"...
    tag: str                         # "input", "select", "button", "textarea"
    type: Optional[str] = None       # "text", "email", "file", "submit"...
    label: Optional[str] = None      # 关联的 label 文本
    placeholder: Optional[str] = None
    required: bool = False
    options: Optional[list[str]] = None  # select 的选项列表
    value: Optional[str] = None      # 当前值
    selector: str = ""               # CSS selector，用于后续操作
    text: Optional[str] = None       # 按钮/链接的文本内容

    def to_dict(self) -> dict:
        """转为 dict，去掉 None 值减少噪音"""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PageDOM:
    """整个页面的结构化描述"""
    url: str
    title: str
    elements: list[PageElement] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "elements": [el.to_dict() for el in self.elements],
        }


# 提取可交互元素的 JS 脚本，在浏览器里执行
_EXTRACT_JS = """
() => {
    const results = [];

    function getLabel(el) {
        // 1. <label for="id"> 关联
        if (el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) return label.textContent.trim();
        }
        // 2. 父级 <label> 嵌套
        const parent = el.closest('label');
        if (parent) {
            const clone = parent.cloneNode(true);
            // 移除子元素的文本，只保留 label 自身文本
            clone.querySelectorAll('input,select,textarea').forEach(c => c.remove());
            const text = clone.textContent.trim();
            if (text) return text;
        }
        // 3. aria-label
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        // 4. aria-labelledby
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ref = document.getElementById(labelledBy);
            if (ref) return ref.textContent.trim();
        }
        return null;
    }

    function getSelector(el) {
        if (el.id) return '#' + el.id;
        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        // fallback: nth-of-type
        const parent = el.parentElement;
        if (!parent) return el.tagName.toLowerCase();
        const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
        const idx = siblings.indexOf(el) + 1;
        return `${el.tagName.toLowerCase()}:nth-of-type(${idx})`;
    }

    // 提取 input 元素
    document.querySelectorAll('input:not([type="hidden"])').forEach(el => {
        if (!el.offsetParent && el.type !== 'file') return; // 跳过不可见元素（file 除外）
        results.push({
            tag: 'input',
            type: el.type || 'text',
            label: getLabel(el) || el.placeholder || null,
            placeholder: el.placeholder || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            value: el.value || null,
            selector: getSelector(el),
        });
    });

    // 提取 textarea
    document.querySelectorAll('textarea').forEach(el => {
        if (!el.offsetParent) return;
        results.push({
            tag: 'textarea',
            type: 'textarea',
            label: getLabel(el) || el.placeholder || null,
            placeholder: el.placeholder || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            value: el.value || null,
            selector: getSelector(el),
        });
    });

    // 提取 select
    document.querySelectorAll('select').forEach(el => {
        if (!el.offsetParent) return;
        const options = Array.from(el.options).map(o => o.text.trim()).filter(t => t);
        results.push({
            tag: 'select',
            type: 'select',
            label: getLabel(el),
            required: el.required || el.getAttribute('aria-required') === 'true',
            options: options,
            value: el.value || null,
            selector: getSelector(el),
        });
    });

    // 提取 button 和 input[type=submit]
    document.querySelectorAll('button, input[type="submit"]').forEach(el => {
        if (!el.offsetParent) return;
        results.push({
            tag: el.tagName.toLowerCase() === 'button' ? 'button' : 'input',
            type: 'submit',
            text: el.textContent?.trim() || el.value || null,
            selector: getSelector(el),
        });
    });

    return results;
}
"""


class DOMExtractor:
    """从页面提取可交互元素"""

    async def extract(self, page: Page) -> PageDOM:
        """提取当前页面的所有可交互元素"""
        # 等待页面基本加载完成
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            logger.warning("等待页面加载超时，继续提取")

        url = page.url
        title = await page.title()

        # 在浏览器里执行 JS 提取元素
        raw_elements = await page.evaluate(_EXTRACT_JS)

        elements = []
        for i, raw in enumerate(raw_elements):
            el = PageElement(
                id=f"el_{i}",
                tag=raw.get("tag", ""),
                type=raw.get("type"),
                label=raw.get("label"),
                placeholder=raw.get("placeholder"),
                required=raw.get("required", False),
                options=raw.get("options"),
                value=raw.get("value"),
                selector=raw.get("selector", ""),
                text=raw.get("text"),
            )
            elements.append(el)

        logger.info(f"提取到 {len(elements)} 个可交互元素 ({url})")
        return PageDOM(url=url, title=title, elements=elements)
