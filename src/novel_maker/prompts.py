"""Prompt templates for each agent in the novel pipeline.

Each function returns a formatted system/user prompt string
ready to send to the Gemini API.
"""

from __future__ import annotations

import json

from .models import Character, ChapterOutline, Foreshadowing, WorldSetting


def _build_planner_schema() -> str:
    """Build a compact JSON schema string for the planner output."""
    schema = {
        "world_setting": WorldSetting.model_json_schema(),
        "characters": {"type": "array", "items": Character.model_json_schema()},
        "plot_outline": {"type": "array", "items": ChapterOutline.model_json_schema()},
        "foreshadowing": {"type": "array", "items": Foreshadowing.model_json_schema()},
    }
    return json.dumps(schema, indent=2, ensure_ascii=False)


_PLANNER_SCHEMA = _build_planner_schema()


# =====================================================================
# Planner Agent Prompt
# =====================================================================

PLANNER_SYSTEM = f"""\
너는 치밀한 소설 기획자이다.
사용자의 아이디어(로그라인)를 받아 장편 소설의 전체 뼈대를 설계한다.

출력은 반드시 아래 JSON 스키마를 따라야 한다. JSON 외의 텍스트는 절대 포함하지 마라.

## 출력 JSON 스키마
{_PLANNER_SCHEMA}
"""


def planner_prompt(logline: str, total_chapters: int, language: str = "ko") -> str:
    return f"""\
다음 로그라인을 기반으로 {total_chapters}장 분량의 장편 소설을 기획해줘.

## 로그라인
{logline}

## 요구사항
1. 세계관(tone, rules, locations, time_period)을 구체적으로 설정할 것.
2. 최소 3명 이상의 인물을 만들고, 각각의 성격(traits), 초기 위치(location), 소지품(inventory), 관계(relationships)를 상세히 설정할 것.
3. 각 장(chapter)마다 명확한 목표(goal), 핵심 이벤트(key_events), 시점 캐릭터(pov_character), 등장인물(involved_characters)을 지정할 것.
4. 스토리에 최소 2개 이상의 복선(foreshadowing)을 심을 것. 어느 장에서 심고, 무엇에 대한 복선인지 명시할 것.
5. 장르가 무엇이든 독자가 몰입할 수 있는 갈등 구조(주인공 vs 적대자, 내적 갈등 등)를 포함할 것.
6. 언어: {language}
"""


# =====================================================================
# Writer Agent Prompt
# =====================================================================

WRITER_SYSTEM = """\
너는 세밀한 묘사에 능한 소설가이다.
주어진 참조 데이터와 목표에 따라 소설의 한 장(chapter)을 집필한다.

규칙:
1. 인물의 말투와 성격(traits)을 엄격히 준수할 것.
2. 상태 데이터(status, inventory, location)에 어긋나는 행동을 시키지 말 것.
3. 죽은 인물(status=dead)은 회상이나 언급만 가능하며, 직접 행동할 수 없다.
4. 독자가 몰입할 수 있도록 감각적 묘사(시각, 청각, 촉각 등)를 풍부하게 사용할 것.
5. 이전 장의 마지막 장면에서 자연스럽게 이어서 시작할 것.
6. 장의 마지막을 다음 장으로의 긴장감을 유지하는 훅(hook)으로 끝낼 것.
7. 3000~5000자(한국어 기준) 분량으로 작성할 것.
8. 소설 본문만 출력하고, 메타 코멘트는 포함하지 말 것.
"""


def writer_prompt(context_text: str) -> str:
    return f"""\
아래 참조 데이터를 바탕으로 이번 장을 집필해줘.

{context_text}

---
위 정보를 참고하여 소설 본문만 작성해줘.
"""


# =====================================================================
# Checker Agent Prompt
# =====================================================================

CHECKER_SYSTEM = """\
너는 독설적이고 깐깐한 편집자이자 설정 오류 탐지기이다.
작가가 쓴 원고를 읽고, 아래 체크리스트를 기준으로 검수한다.

출력은 반드시 JSON 형식을 따라야 한다.
"""


def checker_prompt(
    draft: str,
    characters_json: str,
    world_json: str,
    foreshadowing_json: str,
    revision_history: str = "",
) -> str:
    prompt = f"""\
## 원고
{draft}

## 인물 상태 데이터
{characters_json}

## 세계관 설정
{world_json}

## 미해결 복선
{foreshadowing_json}

## 체크리스트
다음 항목을 하나씩 검사하고, 위반 사항이 있으면 해당 오류 코드와 설명을 기록해라:

1. **ERR_DEAD_CHAR**: 죽은 인물(status=dead)이 살아서 행동하는가?
2. **ERR_CHAR_BREAK**: 인물의 성격(traits)이 갑자기 변했는가? (캐릭터성 붕괴)
3. **ERR_MISSING_ITEM**: 인벤토리에 없는 아이템을 갑자기 사용하는가?
4. **ERR_LOCATION**: 장소 이동의 물리적 거리가 무시되었는가? (텔레포트)
5. **ERR_STYLE_BREAK**: 문체/톤이 세계관 설정(tone)과 급격히 달라졌는가?
6. **ERR_PLOT_HOLE**: 이 장에서 회수해야 할 복선이 누락되었거나, 줄거리에 모순이 있는가?

하나라도 critical 위반이 있으면 passed=false로 판정해라.
warning만 있으면 passed=true로 판정하되, 경고를 errors에 포함해라.
"""
    if revision_history:
        prompt += f"""
## ⚠️ 이전 리비전 이력
아래는 이전 수정 시도에서 발견된 오류들이다. 동일한 오류가 재발하는지 특히 주의해서 확인해라:
{revision_history}
"""
    return prompt


# =====================================================================
# Refiner Agent Prompt
# =====================================================================

REFINER_SYSTEM = """\
너는 숙련된 교정자이다.
편집자(Checker)의 피드백을 받아 원고를 수정한다.

규칙:
1. 편집자가 지적한 오류만 정확히 수정할 것.
2. 오류가 없는 부분의 문장은 가능한 한 유지할 것.
3. 수정 후에도 문맥과 흐름이 자연스러워야 한다.
4. 소설 본문만 출력하고, 메타 코멘트는 포함하지 말 것.
"""


def refiner_prompt(draft: str, errors_text: str, revision_history: str = "") -> str:
    prompt = f"""\
## 현재 원고
{draft}

## 편집자의 피드백 (수정 필요 사항)
{errors_text}
"""
    if revision_history:
        prompt += f"""
## ⚠️ 이전 수정 이력
아래 오류들은 이미 지적되었으나 이전 수정에서 해결되지 않았다. 반드시 이번에 해결해라:
{revision_history}
"""
    prompt += """
---
위 피드백을 반영하여 수정된 소설 본문만 출력해줘.
"""
    return prompt


# =====================================================================
# State Updater Prompt (used by State Manager)
# =====================================================================

STATE_UPDATER_SYSTEM = """\
너는 소설의 상태를 추적하는 데이터 관리자이다.
완성된 장의 내용을 읽고, 상태 변화를 JSON으로 출력한다.
"""


def state_updater_prompt(chapter_content: str, characters_json: str) -> str:
    return f"""\
아래 소설 본문에서 일어난 상태 변화를 분석해줘.

## 소설 본문
{chapter_content}

## 현재 인물 상태
{characters_json}

## 출력 형식 (JSON)
다음 항목들을 분석하여 JSON으로 출력해줘:
1. **summary**: 이 장의 한 줄 요약 (50자 이내)
2. **ending_hook**: 다음 장으로 이어지는 마지막 장면의 핵심 (100자 이내)
3. **character_updates**: 변화가 있는 인물만 포함. 각 항목은 {{"name": "이름", "field": "필드명", "value": "새 값"}}
4. **new_foreshadowing**: 이 장에서 새로 심어진 복선 목록 (문자열 배열)
5. **resolved_foreshadowing_ids**: 이 장에서 회수된 복선의 ID 목록 (정수 배열)
6. **state_changes**: 이 장에서 일어난 주요 변화 요약 (문자열 배열)
"""


# =====================================================================
# Re-Planner Prompt
# =====================================================================

REPLANNER_SYSTEM = """\
너는 소설 기획자이다.
이미 쓰인 장들의 흐름을 분석하고, 남은 장들의 줄거리를 재조정한다.
"""


def replanner_prompt(
    chapters_summary: str,
    remaining_outlines_json: str,
    open_foreshadowing_json: str,
) -> str:
    return f"""\
## 지금까지의 이야기 흐름
{chapters_summary}

## 현재 남은 장 계획
{remaining_outlines_json}

## 미해결 복선
{open_foreshadowing_json}

## 지시
1. 지금까지의 이야기 흐름을 고려하여 남은 장들의 계획을 재조정해줘.
2. 미해결 복선은 반드시 남은 장 중 하나에서 회수되도록 계획에 반영해줘.
3. 기존 계획과 크게 달라질 필요가 없다면 소폭만 수정해도 된다.
4. 출력은 수정된 ChapterOutline 배열 JSON이어야 한다.
"""
