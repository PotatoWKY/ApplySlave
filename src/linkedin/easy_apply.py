"""LinkedIn Easy Apply 流程处理 — 多步表单填写和提交（硬编码）"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


from src.ai.form_filler import FormFiller, FieldToFill
from src.browser.human_like import HumanLike


@dataclass
class ApplyResult:
    """投递结果"""
    success: bool
    job_title: str
    company: str
    error: Optional[str] = None
    dry_run: bool = False
    steps_completed: int = 0


class EasyApplyHandler:
    """处理 LinkedIn Easy Apply 多步表单"""

    def __init__(self, page: Page, dry_run: bool = True, form_filler: Optional[FormFiller] = None, human: Optional[HumanLike] = None):
        self._page = page
        self._dry_run = dry_run
        self._form_filler = form_filler
        self._human = human or HumanLike()
        self._current_job_title = ""
        self._current_company = ""

    async def apply(self, job_title: str, company: str) -> ApplyResult:
        """执行 Easy Apply 流程（dry_run 模式下不会真正提交）"""
        logger.info(f"开始 Easy Apply: {job_title} @ {company} (dry_run={self._dry_run})")
        self._current_job_title = job_title
        self._current_company = company

        try:
            # 1. 点击 Easy Apply 按钮
            clicked = await self._click_easy_apply_button()
            if not clicked:
                return ApplyResult(False, job_title, company, "找不到 Easy Apply 按钮")

            # 2. 循环处理多步表单
            max_steps = 10
            last_progress = None
            stuck_count = 0
            for step in range(max_steps):
                logger.info(f"--- 第 {step + 1} 步 ---")

                # 等待弹窗内容稳定
                await self._page.wait_for_timeout(1000)

                # 截图当前步骤（调试用）
                try:
                    await self._page.screenshot(path=f"data/debug_step_{step+1}.png")
                    logger.debug(f"步骤截图已保存: data/debug_step_{step+1}.png")
                except Exception:
                    pass

                # 打印当前弹窗内的所有可见按钮（调试）
                await self._debug_modal_buttons()

                # 检查进度是否变化（防止死循环）
                current_progress = await self._get_progress()
                if current_progress == last_progress:
                    stuck_count += 1
                    if stuck_count >= 2:
                        logger.warning(f"进度卡住 ({current_progress})，连续 {stuck_count} 步无变化，跳过此职位")
                        await self._close_modal()
                        return ApplyResult(False, job_title, company, f"表单卡住在进度 {current_progress}，可能有必填字段未填写", steps_completed=step+1)
                else:
                    stuck_count = 0
                last_progress = current_progress

                # 检查是否有错误提示（必填字段未填等）
                has_errors = await self._check_form_errors()
                if has_errors:
                    logger.warning("表单有错误提示，可能有必填字段未填写")

                # 检查是否到了最终提交步骤
                if await self._is_submit_step():
                    if self._dry_run:
                        logger.info("[DRY RUN] 到达 Submit 步骤，跳过提交，关闭弹窗")
                        await self._close_modal()
                        return ApplyResult(True, job_title, company, dry_run=True, steps_completed=step+1)
                    else:
                        await self._click_submit()
                        return ApplyResult(True, job_title, company, steps_completed=step+1)

                # 检查是否是 Review 步骤
                if await self._is_review_step():
                    if self._dry_run:
                        logger.info("[DRY RUN] 到达 Review 步骤，跳过提交，关闭弹窗")
                        await self._close_modal()
                        return ApplyResult(True, job_title, company, dry_run=True, steps_completed=step+1)
                    else:
                        await self._click_review()
                        continue

                # 填写当前步骤的表单
                await self._fill_current_step()

                # 点击 Next
                moved = await self._click_next()
                if not moved:
                    logger.warning("无法继续下一步，尝试检查是否有未处理的弹窗")
                    # 可能是 safety reminder 或其他中间弹窗
                    handled = await self._handle_intermediate_dialogs()
                    if handled:
                        continue
                    await self._close_modal()
                    return ApplyResult(False, job_title, company, "卡在某一步，Next 按钮不可用", steps_completed=step+1)

            await self._close_modal()
            return ApplyResult(False, job_title, company, "步骤过多，超过上限")

        except Exception as e:
            logger.error(f"Easy Apply 出错: {e}\n{traceback.format_exc()}")
            await self._close_modal()
            return ApplyResult(False, job_title, company, str(e))

    async def _click_easy_apply_button(self) -> bool:
        """点击职位详情页的 Easy Apply 按钮，打开申请弹窗"""
        try:
            # 查找所有包含 "apply" 的可见元素（button 和 a 标签都要查）
            all_clickable = await self._page.query_selector_all('button, a')
            apply_buttons_found = []
            for el in all_clickable:
                text = (await el.text_content() or "").strip()
                visible = await el.is_visible()
                if "apply" in text.lower() and visible:
                    tag = await el.evaluate("el => el.tagName")
                    class_name = await el.get_attribute("class") or ""
                    aria = await el.get_attribute("aria-label") or ""
                    apply_buttons_found.append({
                        "tag": tag, "text": text, "class": class_name[:60], "aria": aria,
                    })
                    logger.debug(f"[APPLY BTN] <{tag}> text='{text}' class='{class_name[:60]}' aria='{aria}'")

            if not apply_buttons_found:
                logger.warning("页面上没有找到任何包含 'apply' 的可见元素")
                logger.debug(f"当前 URL: {self._page.url}")
                return False

            # 策略 1: aria-label 精确匹配（button 或 a）
            btn = await self._page.query_selector('[aria-label*="Easy Apply"]')
            if btn and await btn.is_visible():
                logger.debug("使用 aria-label 匹配到 Easy Apply")
                await btn.click()
            else:
                # 策略 2: 文本匹配（button 和 a 都查）
                logger.debug("aria-label 未匹配，尝试文本匹配")
                locator = self._page.locator('button, a').filter(has_text="Easy Apply").first
                await locator.click(timeout=5000)

            # 等待弹窗出现
            modal_selectors = [
                '.jobs-easy-apply-modal',
                '.jobs-easy-apply-content',
                '.artdeco-modal[role="dialog"]',
                '[data-test-modal]',
                '.artdeco-modal--layer-default',
            ]
            modal_selector = ", ".join(modal_selectors)
            await self._page.wait_for_selector(modal_selector, timeout=8000)
            logger.info("Easy Apply 弹窗已打开")
            return True

        except PlaywrightTimeout:
            logger.warning("等待 Easy Apply 弹窗超时")
            return False
        except Exception as e:
            logger.warning(f"点击 Easy Apply 按钮失败: {e}")
            return False

    async def _is_submit_step(self) -> bool:
        """检查当前步骤是否是最终提交步骤"""
        selectors = [
            'button[aria-label="Submit application"]',
            'button[aria-label="提交申请"]',
            'footer button:has-text("Submit application")',
            'footer button:has-text("Submit")',
        ]
        for sel in selectors:
            btn = await self._page.query_selector(sel)
            if btn and await btn.is_visible():
                logger.debug(f"检测到 Submit 按钮: {sel}")
                return True
        return False

    async def _is_review_step(self) -> bool:
        """检查是否是 Review 步骤"""
        selectors = [
            'button[aria-label="Review your application"]',
            'footer button:has-text("Review")',
        ]
        for sel in selectors:
            btn = await self._page.query_selector(sel)
            if btn and await btn.is_visible():
                logger.debug(f"检测到 Review 按钮: {sel}")
                return True
        return False

    async def _fill_current_step(self) -> None:
        """填写当前步骤的表单字段"""
        modal = await self._find_modal()
        if not modal:
            logger.warning("未找到弹窗，跳过填写")
            return

        await self._debug_form_fields(modal)

        # 收集空字段
        fields_to_fill: list[FieldToFill] = []

        # 文本输入框
        inputs = await modal.locator(
            'input[type="text"], input[type="tel"], input[type="email"], '
            'input[type="number"], input[type="url"]'
        ).all()
        for inp in inputs:
            try:
                if not await inp.is_visible():
                    continue
                value = await inp.input_value()
                label = await self._get_input_label(inp)
                if value.strip():
                    logger.debug(f"  [已填] {label} = '{value}'")
                else:
                    logger.debug(f"  [空] {label}")
                    fields_to_fill.append(FieldToFill(label=label, field_type="input"))
            except Exception as e:
                logger.debug(f"  检查输入框失败: {e}")

        # select 下拉框
        selects = await modal.locator('select').all()
        for sel in selects:
            try:
                if not await sel.is_visible():
                    continue
                value = await sel.input_value()
                label = await self._get_input_label(sel)
                options = await sel.evaluate("""
                    el => Array.from(el.options).map(o => o.text.trim()).filter(t => t && t !== 'Select an option')
                """)
                if value.strip() and value != "Select an option":
                    logger.debug(f"  [已选] {label} = '{value}'")
                else:
                    logger.debug(f"  [空下拉] {label}, options={options}")
                    fields_to_fill.append(FieldToFill(label=label, field_type="select", options=options))
            except Exception as e:
                logger.debug(f"  检查下拉框失败: {e}")

        # textarea
        textareas = await modal.locator('textarea').all()
        for ta in textareas:
            try:
                if not await ta.is_visible():
                    continue
                value = await ta.input_value()
                label = await self._get_input_label(ta)
                if value.strip():
                    logger.debug(f"  [已填] {label} = '{value[:50]}'")
                else:
                    logger.debug(f"  [空文本框] {label}")
                    fields_to_fill.append(FieldToFill(label=label, field_type="textarea"))
            except Exception as e:
                logger.debug(f"  检查文本框失败: {e}")

        # radio groups
        await self._check_radio_groups(modal)

        # 用 FormFiller 填写空字段
        if fields_to_fill and self._form_filler:
            logger.info(f"有 {len(fields_to_fill)} 个空字段，交给 FormFiller 处理")
            answers = await self._form_filler.answer_fields(
                fields_to_fill, self._current_job_title, self._current_company
            )
            await self._apply_answers(modal, answers)
        elif fields_to_fill:
            labels = [f.label for f in fields_to_fill]
            logger.warning(f"有 {len(fields_to_fill)} 个空字段但 FormFiller 不可用: {labels}")

    async def _apply_answers(self, modal, answers) -> None:
        """把 FormFiller 的答案填入表单（使用人类打字模拟）"""
        for answer in answers:
            try:
                filled = False

                # 尝试找到对应的 select
                selects = await modal.locator('select').all()
                for sel in selects:
                    if not await sel.is_visible():
                        continue
                    label = await self._get_input_label(sel)
                    if self._labels_match(label, answer.label):
                        await self._human.action_delay()
                        await sel.select_option(label=answer.value)
                        logger.info(f"  [填写] select '{label}' = '{answer.value}'")
                        filled = True
                        break

                if filled:
                    continue

                # 尝试找到对应的 input（使用人类打字）
                inputs = await modal.locator(
                    'input[type="text"], input[type="tel"], input[type="email"], '
                    'input[type="number"], input[type="url"]'
                ).all()
                for inp in inputs:
                    if not await inp.is_visible():
                        continue
                    label = await self._get_input_label(inp)
                    if self._labels_match(label, answer.label):
                        await self._human.human_type_element(inp, self._page, answer.value)
                        logger.info(f"  [填写] input '{label}' = '{answer.value}'")
                        filled = True
                        break

                if filled:
                    continue

                # 尝试找到对应的 textarea（使用人类打字）
                textareas = await modal.locator('textarea').all()
                for ta in textareas:
                    if not await ta.is_visible():
                        continue
                    label = await self._get_input_label(ta)
                    if self._labels_match(label, answer.label):
                        await self._human.human_type_element(ta, self._page, answer.value)
                        logger.info(f"  [填写] textarea '{label}' = '{answer.value}'")
                        filled = True
                        break

                if not filled:
                    logger.warning(f"  [未找到] 无法定位字段 '{answer.label}'")

            except Exception as e:
                logger.warning(f"  [填写失败] '{answer.label}': {e}")

    def _labels_match(self, field_label: str, answer_label: str) -> bool:
        """模糊匹配 label — 处理 LLM 返回的 label 可能是原始 label 的子串"""
        if field_label == answer_label:
            return True
        fl = field_label.lower().strip()
        al = answer_label.lower().strip()
        if fl == al:
            return True
        # 子串匹配
        if al in fl or fl in al:
            return True
        # 去掉特殊字符后匹配
        import re
        fl_clean = re.sub(r'[^a-z0-9 ]', '', fl)
        al_clean = re.sub(r'[^a-z0-9 ]', '', al)
        if fl_clean == al_clean:
            return True
        if al_clean in fl_clean or fl_clean in al_clean:
            return True
        return False

    async def _check_radio_groups(self, modal) -> list[str]:
        """检查弹窗内未选择的 radio group"""
        unchecked_groups = []
        try:
            # 找到所有 fieldset（LinkedIn 用 fieldset 包裹 radio group）
            fieldsets = await modal.locator('fieldset').all()
            for fs in fieldsets:
                legend = await fs.locator('legend, span.fb-dash-form-element__label').first.text_content()
                legend = (legend or "").strip()
                # 检查是否有已选中的 radio
                checked = await fs.locator('input[type="radio"]:checked').count()
                if checked == 0:
                    logger.debug(f"  [未选] radio group: '{legend}'")
                    unchecked_groups.append(legend)
                else:
                    logger.debug(f"  [已选] radio group: '{legend}'")
        except Exception as e:
            logger.debug(f"检查 radio groups 失败: {e}")
        return unchecked_groups

    async def _check_form_errors(self) -> bool:
        """检查弹窗内是否有表单错误提示"""
        try:
            error_selectors = [
                '.artdeco-inline-feedback--error',
                '.fb-dash-form-element__error-field',
                '[data-test-form-element-error]',
                '.jobs-easy-apply-form-element__error',
            ]
            for sel in error_selectors:
                errors = await self._page.query_selector_all(sel)
                visible_errors = []
                for err in errors:
                    if await err.is_visible():
                        text = (await err.text_content() or "").strip()
                        if text:
                            visible_errors.append(text)
                if visible_errors:
                    for msg in visible_errors:
                        logger.warning(f"  [表单错误] {msg}")
                    return True
        except Exception:
            pass
        return False

    async def _find_modal(self):
        """找到当前打开的 Easy Apply 弹窗"""
        modal_selectors = [
            '.jobs-easy-apply-modal',
            '.jobs-easy-apply-content',
            '.artdeco-modal[role="dialog"]',
            '.artdeco-modal--layer-default',
        ]
        for sel in modal_selectors:
            modal = self._page.locator(sel).first
            try:
                if await modal.is_visible():
                    return modal
            except Exception:
                continue
        return None

    async def _get_input_label(self, element) -> str:
        """获取输入框的 label 文本"""
        try:
            aria = await element.get_attribute("aria-label")
            if aria:
                return self._clean_label(aria)
            el_id = await element.get_attribute("id")
            if el_id:
                label = await self._page.query_selector(f'label[for="{el_id}"]')
                if label:
                    return self._clean_label((await label.text_content()).strip())
            placeholder = await element.get_attribute("placeholder")
            if placeholder:
                return self._clean_label(placeholder)
            parent_label = await element.evaluate("""
                el => {
                    const label = el.closest('label');
                    if (label) {
                        const clone = label.cloneNode(true);
                        clone.querySelectorAll('input,select,textarea').forEach(c => c.remove());
                        return clone.textContent.trim();
                    }
                    const prev = el.previousElementSibling;
                    if (prev && prev.tagName === 'LABEL') return prev.textContent.trim();
                    return null;
                }
            """)
            if parent_label:
                return self._clean_label(parent_label)
        except Exception:
            pass
        return "unknown"

    def _clean_label(self, label: str) -> str:
        """清理 label — 去掉重复文本和多余空白"""
        label = label.strip()
        # 检测重复：如果前半段和后半段一样，只保留一半
        # 例如 "Location (city)Location (city)" -> "Location (city)"
        half = len(label) // 2
        if half > 3 and label[:half] == label[half:]:
            label = label[:half]
        # 去掉尾部的 "Required" 等
        for suffix in ["Required", "required"]:
            if label.endswith(suffix):
                label = label[:-len(suffix)].strip()
        return label

    async def _click_next(self) -> bool:
        """点击 Next 按钮进入下一步"""
        try:
            # 多种 selector 兼容
            next_selectors = [
                'footer button[aria-label="Continue to next step"]',
                'footer button:has-text("Next")',
                'footer button:has-text("Continue")',
                'button[data-easy-apply-next-button]',
            ]
            for sel in next_selectors:
                btn = self._page.locator(sel).first
                try:
                    if await btn.is_visible(timeout=1000):
                        # 检查按钮是否被禁用
                        disabled = await btn.get_attribute("disabled")
                        if disabled:
                            logger.debug(f"Next 按钮被禁用: {sel}")
                            continue
                        await btn.click(timeout=5000)
                        logger.debug(f"点击 Next 成功: {sel}")
                        await self._page.wait_for_timeout(1500)
                        return True
                except Exception:
                    continue

            logger.debug("所有 Next selector 都未匹配")
            return False
        except Exception as e:
            logger.debug(f"点击 Next 失败: {e}")
            return False

    async def _click_submit(self) -> None:
        """点击 Submit 提交申请"""
        if self._dry_run:
            raise RuntimeError("BUG: dry_run 模式下不应调用 _click_submit")
        submit_btn = self._page.locator(
            'footer button:has-text("Submit application"), '
            'button[aria-label="Submit application"]'
        ).first
        await submit_btn.click(timeout=5000)
        await self._page.wait_for_timeout(2000)
        logger.info("已点击 Submit")

    async def _click_review(self) -> None:
        """点击 Review 按钮"""
        review_btn = self._page.locator(
            'footer button:has-text("Review"), '
            'button[aria-label="Review your application"]'
        ).first
        await review_btn.click(timeout=5000)
        await self._page.wait_for_timeout(1000)
        logger.debug("已点击 Review")

    async def _handle_intermediate_dialogs(self) -> bool:
        """处理中间弹窗（safety reminder、phone verification 等）"""
        try:
            # "Safety reminder" 弹窗 — 点击 Continue
            safety_btn = await self._page.query_selector(
                'button:has-text("Continue applying"), '
                'button:has-text("Got it"), '
                'button:has-text("Continue")'
            )
            if safety_btn and await safety_btn.is_visible():
                await safety_btn.click()
                logger.debug("已处理 Safety reminder 弹窗")
                await self._page.wait_for_timeout(1000)
                return True

            # "Save" 弹窗 — 有时 LinkedIn 会弹出保存提示
            save_btn = await self._page.query_selector(
                'button:has-text("Save and continue")'
            )
            if save_btn and await save_btn.is_visible():
                await save_btn.click()
                logger.debug("已处理 Save 弹窗")
                await self._page.wait_for_timeout(1000)
                return True

        except Exception as e:
            logger.debug(f"处理中间弹窗失败: {e}")
        return False

    async def _close_modal(self) -> None:
        """关闭 Easy Apply 弹窗"""
        try:
            # 多种关闭按钮 selector
            close_selectors = [
                'button[aria-label="Dismiss"]',
                'button.artdeco-modal__dismiss',
                '.artdeco-modal button[data-test-modal-close-btn]',
                'button[aria-label="关闭"]',
            ]
            for sel in close_selectors:
                btn = await self._page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    logger.debug(f"点击关闭按钮: {sel}")
                    break

            # 等待 "Discard application?" 确认框
            await self._page.wait_for_timeout(800)

            discard_selectors = [
                'button[data-control-name="discard_application_confirm_btn"]',
                'button[data-test-dialog-primary-btn]',
                'button:has-text("Discard")',
            ]
            for sel in discard_selectors:
                btn = await self._page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    logger.debug(f"已确认丢弃申请: {sel}")
                    break

        except Exception as e:
            logger.debug(f"关闭弹窗时出错（可能已关闭）: {e}")

    async def _debug_modal_buttons(self) -> None:
        """打印弹窗内所有可见按钮（调试用）"""
        try:
            modal = await self._find_modal()
            if not modal:
                logger.debug("[DEBUG] 未找到弹窗")
                return

            buttons = await modal.locator('button').all()
            visible_buttons = []
            for btn in buttons:
                try:
                    if await btn.is_visible():
                        text = (await btn.text_content() or "").strip()
                        aria = await btn.get_attribute("aria-label") or ""
                        disabled = await btn.get_attribute("disabled")
                        if text or aria:
                            status = " [DISABLED]" if disabled else ""
                            visible_buttons.append(f"'{text[:50]}' aria='{aria}'{status}")
                except Exception:
                    continue

            logger.debug(f"[DEBUG] 弹窗内可见按钮 ({len(visible_buttons)}):")
            for b in visible_buttons:
                logger.debug(f"  [BTN] {b}")
        except Exception as e:
            logger.debug(f"[DEBUG] 打印弹窗按钮失败: {e}")

    async def _debug_form_fields(self, modal) -> None:
        """打印弹窗内所有表单字段（调试用）"""
        try:
            # 打印弹窗的标题/进度
            header = modal.locator('h2, h3, .artdeco-modal__header').first
            try:
                header_text = (await header.text_content()).strip()
                logger.debug(f"[DEBUG] 弹窗标题: '{header_text}'")
            except Exception:
                pass

            # 打印进度指示器
            try:
                progress = await self._get_progress()
                logger.debug(f"[DEBUG] 进度: {progress}")
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"[DEBUG] 打印表单字段失败: {e}")

    async def _get_progress(self) -> str:
        """获取当前进度条的值"""
        try:
            modal = await self._find_modal()
            if not modal:
                return "unknown"
            progress_el = modal.locator(
                '[role="progressbar"], '
                '.artdeco-completeness-meter-linear__progress-element'
            ).first
            style = await progress_el.get_attribute("style")
            if style:
                return style.strip()
            value = await progress_el.get_attribute("aria-valuenow")
            if value:
                return f"{value}%"
        except Exception:
            pass
        return "unknown"
