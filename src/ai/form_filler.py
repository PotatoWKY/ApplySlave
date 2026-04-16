"""表单填写器 — 用 LLM + profile 数据回答 Easy Apply 附加问题"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from src.ai.llm_client import LLMClient


@dataclass
class FieldToFill:
    """一个需要填写的表单字段"""
    label: str
    field_type: str  # "select", "input", "textarea"
    options: Optional[list[str]] = None  # select 的选项列表
    current_value: str = ""


@dataclass
class FieldAnswer:
    """LLM 给出的答案"""
    label: str
    value: str
    confidence: float = 1.0


class FormFiller:
    """用 LLM 和 profile 数据填写表单"""

    def __init__(self, llm: LLMClient, profile: dict):
        self._llm = llm
        self._profile = profile

    async def answer_fields(self, fields: list[FieldToFill], job_title: str = "", company: str = "") -> list[FieldAnswer]:
        """批量回答表单字段"""
        if not fields:
            return []

        # 先尝试用 profile 中的预设答案直接匹配
        answers = []
        remaining = []
        for field in fields:
            preset = self._match_preset(field)
            if preset:
                logger.debug(f"预设匹配: '{field.label}' -> '{preset}'")
                answers.append(FieldAnswer(label=field.label, value=preset))
            else:
                remaining.append(field)

        # 剩余字段用 LLM 回答
        if remaining:
            llm_answers = await self._ask_llm(remaining, job_title, company)
            answers.extend(llm_answers)

        return answers

    def _match_preset(self, field: FieldToFill) -> Optional[str]:
        """用 profile 中的 easy_apply_answers 预设匹配"""
        presets = self._profile.get("easy_apply_answers", {})
        label_lower = field.label.lower()

        # 关键词匹配
        keyword_map = {
            "visa": "require_visa_sponsorship",
            "sponsorship": "require_visa_sponsorship",
            "authorization": "require_visa_sponsorship",
            "relocate": "willing_to_relocate",
            "relocation": "willing_to_relocate",
            "salary": "salary_expectation",
            "compensation": "salary_expectation",
            "years of experience": "years_of_experience",
            "years experience": "years_of_experience",
            "how many years": "years_of_experience",
        }

        for keyword, preset_key in keyword_map.items():
            if keyword in label_lower and preset_key in presets:
                preset_value = str(presets[preset_key])
                # 如果是 select，找最匹配的选项
                if field.options:
                    matched = self._best_option_match(preset_value, field.options)
                    if matched:
                        return matched
                return preset_value

        return None

    def _best_option_match(self, target: str, options: list[str]) -> Optional[str]:
        """在 select 选项中找最匹配的"""
        target_lower = target.lower().strip()
        for opt in options:
            opt_lower = opt.lower().strip()
            if target_lower == opt_lower:
                return opt
            if target_lower in opt_lower or opt_lower in target_lower:
                return opt
        # "Yes"/"No" 匹配
        if target_lower in ("yes", "no"):
            for opt in options:
                if opt.lower().strip() == target_lower:
                    return opt
        return None

    async def _ask_llm(self, fields: list[FieldToFill], job_title: str, company: str) -> list[FieldAnswer]:
        """用 LLM 回答无法预设匹配的字段"""
        if not await self._llm.is_available():
            logger.warning("LLM 不可用，跳过这些字段")
            return []

        prompt = self._build_prompt(fields, job_title, company)
        logger.debug(f"LLM prompt:\n{prompt[:500]}")

        result = await self._llm.ask_json(prompt)
        if not result:
            logger.warning("LLM 未返回有效 JSON")
            return []

        answers = []
        llm_answers = result.get("answers", [])
        for item in llm_answers:
            label = item.get("label", "")
            value = item.get("value", "")
            if label and value:
                # 如果是 select 字段，确保答案在选项中
                field = next((f for f in fields if f.label == label), None)
                if field and field.options:
                    matched = self._best_option_match(value, field.options)
                    if matched:
                        value = matched
                    else:
                        logger.warning(f"LLM 答案 '{value}' 不在选项中: {field.options}")
                        continue
                answers.append(FieldAnswer(label=label, value=value))
                logger.debug(f"LLM 回答: '{label}' -> '{value}'")

        return answers

    def _build_prompt(self, fields: list[FieldToFill], job_title: str, company: str) -> str:
        """构建发给 LLM 的 prompt"""
        # 简历摘要
        profile_summary = self._profile_summary()

        # 字段描述
        fields_desc = []
        for i, f in enumerate(fields):
            desc = f"  {i+1}. label: \"{f.label}\", type: {f.field_type}"
            if f.options:
                desc += f", options: {f.options}"
            fields_desc.append(desc)
        fields_text = "\n".join(fields_desc)

        return f"""You are filling out a job application form. Answer each field based on the applicant's profile.

Job: {job_title} at {company}

Applicant profile:
{profile_summary}

Fields to fill:
{fields_text}

Rules:
- For select fields, you MUST choose exactly one of the given options
- For yes/no questions, answer based on the profile honestly
- For text/number fields, give a concise answer
- If unsure, give the most reasonable answer for a software engineer applicant

Return JSON:
{{"answers": [{{"label": "field label", "value": "your answer"}}]}}"""

    def _profile_summary(self) -> str:
        """生成简历摘要文本"""
        p = self._profile
        personal = p.get("personal", {})
        lines = [
            f"Name: {personal.get('first_name', '')} {personal.get('last_name', '')}",
            f"Location: {personal.get('location', '')}",
        ]

        for edu in p.get("education", []):
            lines.append(f"Education: {edu.get('degree', '')} in {edu.get('major', '')} from {edu.get('school', '')} ({edu.get('start', '')}-{edu.get('end', '')})")

        for exp in p.get("experience", []):
            lines.append(f"Experience: {exp.get('title', '')} at {exp.get('company', '')} ({exp.get('start', '')}-{exp.get('end', '')})")

        skills = p.get("skills", [])
        if skills:
            lines.append(f"Skills: {', '.join(skills)}")

        presets = p.get("easy_apply_answers", {})
        if presets.get("years_of_experience"):
            lines.append(f"Years of experience: {presets['years_of_experience']}")
        if presets.get("require_visa_sponsorship"):
            lines.append(f"Requires visa sponsorship: {presets['require_visa_sponsorship']}")

        return "\n".join(lines)
