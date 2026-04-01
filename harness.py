"""
하네스 메인 스크립트 (harness.py)

이 파일의 역할:
    이 스크립트가 전체 프로젝트의 "오케스트레이터"이다.
    사람이 직접 Claude에게 명령하는 대신, 이 Python 스크립트가
    프로그래밍 방식으로 에이전트를 호출하고 제어한다.

    이것이 바로 "하네스(Harness) 패턴"의 핵심이다:
    - 사람 → CLI → Claude   (일반적인 사용)
    - 사람 → harness.py → Claude Agent SDK → Claude   (하네스 패턴)

동작 흐름 (Generator-Evaluator 패턴):
    1. feature_list.json이 없으면 → 초기화 에이전트 실행
    2. feature_list.json이 있으면 → 코딩 에이전트(Generator) 실행
    3. Evaluator 에이전트가 구현 결과를 검증
    4. 통과 → 다음 기능 / 미달 → 피드백 전달 후 재시도 (최대 3회)
    5. 모든 기능이 done이면 → 완료

    ┌──────────────────────────────────────────────────┐
    │               harness.py 실행                     │
    │                     │                            │
    │          feature_list.json 있나?                  │
    │            ↙ 없다        ↘ 있다                   │
    │    초기화 에이전트      코딩 에이전트(Generator)    │
    │    (1회 실행)          (기능 구현)                 │
    │         │                   │                    │
    │         ↓                   ↓                    │
    │    뼈대 파일 생성     Evaluator 에이전트           │
    │         │             (구현 검증, 채점)            │
    │         │                   │                    │
    │         │            통과? ──┤                    │
    │         │          ↙        ↘                    │
    │         │    No: 피드백 전달   Yes: 다음 기능       │
    │         │    (최대 3회 재시도)       │              │
    │         │          ↓               │              │
    │         │    코딩 에이전트 재실행    │              │
    │         │                          │              │
    │         └──→ pending 남았나? ←──────┘              │
    │               ↙ 예     ↘ 아니오                    │
    │          코딩 에이전트    완료!                     │
    └──────────────────────────────────────────────────┘

세션 간 공유:
    에이전트는 매 세션마다 새로 시작된다 (컨텍스트 윈도우 초기화).
    세션 간에 공유되는 것은 오직 파일 시스템뿐이다:
    - feature_list.json: 기능 목록과 진행 상태
    - progress.txt: 작업 이력 로그
    - evaluation_result.json: Evaluator의 평가 결과 (피드백 전달용)
    - output/: 실제 웹사이트 파일들
    - git: 커밋 히스토리

실행 방법:
    ANTHROPIC_API_KEY=sk-... python3 harness.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================
# Claude Agent SDK 임포트
# ============================================================
# claude_code_sdk는 Claude Code를 프로그래밍 방식으로 호출하는 공식 SDK이다.
# - query(): 프롬프트를 보내고 결과를 스트리밍으로 받는 함수
# - ClaudeCodeOptions: 에이전트의 동작을 설정하는 옵션 객체
from claude_code_sdk import query, ClaudeCodeOptions

# ============================================================
# 보안 훅 임포트
# ============================================================
# security.py에서 만든 보안 훅을 연결한다.
# 이 훅이 에이전트의 모든 Bash/Write/Edit 호출을 검사한다.
from security import create_security_hooks


# ============================================================
# 프로젝트 경로 설정
# ============================================================
# 모든 경로를 이 스크립트의 위치 기준으로 절대 경로로 설정한다.
# 이렇게 하면 어디서 실행하든 동일하게 동작한다.
PROJECT_ROOT: Path = Path(__file__).parent.resolve()
PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"
FEATURE_LIST_PATH: Path = PROJECT_ROOT / "feature_list.json"
PROGRESS_PATH: Path = PROJECT_ROOT / "progress.txt"
EVALUATION_RESULT_PATH: Path = PROJECT_ROOT / "evaluation_result.json"
OUTPUT_DIR: Path = PROJECT_ROOT / "output"

# ============================================================
# Generator-Evaluator 패턴 설정
# ============================================================
# Evaluator가 미달 판정을 내리면 같은 기능을 재시도한다.
# 무한 루프를 방지하기 위해 최대 재시도 횟수를 제한한다.
MAX_RETRIES: int = 3


# ============================================================
# 로그 유틸리티
# ============================================================
def log(message: str, level: str = "INFO") -> None:
    """
    타임스탬프가 포함된 로그를 출력한다.

    하네스의 실행 흐름을 추적하기 위해 모든 주요 이벤트를 로그로 남긴다.
    에이전트의 출력과 구분하기 위해 [하네스] 접두사를 붙인다.

    Args:
        message: 출력할 메시지.
        level: 로그 레벨 (INFO, WARN, ERROR, DONE).
    """
    timestamp: str = datetime.now().strftime("%H:%M:%S")
    prefix: dict[str, str] = {
        "INFO": "📋",
        "WARN": "⚠️",
        "ERROR": "❌",
        "DONE": "✅",
        "START": "🚀",
    }
    icon: str = prefix.get(level, "📋")
    print(f"[하네스 {timestamp}] {icon} {message}")


# ============================================================
# feature_list.json 관리 함수들
# ============================================================
def load_feature_list() -> dict[str, Any] | None:
    """
    feature_list.json을 읽어서 파싱한다.

    이 파일은 초기화 에이전트가 생성하고, 코딩 에이전트가 매 세션마다
    업데이트한다. 하네스는 이 파일을 읽어서 다음 세션을 실행할지 결정한다.

    Returns:
        파싱된 JSON 딕셔너리. 파일이 없으면 None.
    """
    if not FEATURE_LIST_PATH.exists():
        return None

    with open(FEATURE_LIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def count_pending_features(feature_data: dict[str, Any]) -> int:
    """
    feature_list.json에서 아직 구현되지 않은 기능의 수를 센다.

    Args:
        feature_data: feature_list.json의 파싱된 데이터.

    Returns:
        "status"가 "pending"인 기능의 수.
    """
    features: list[dict[str, Any]] = feature_data.get("features", [])
    return sum(1 for f in features if f.get("status") == "pending")


def get_feature_summary(feature_data: dict[str, Any]) -> str:
    """
    기능 목록의 현재 상태를 요약 문자열로 반환한다.

    Args:
        feature_data: feature_list.json의 파싱된 데이터.

    Returns:
        "전체 7개 / 완료 3개 / 남은 4개" 형태의 요약 문자열.
    """
    features: list[dict[str, Any]] = feature_data.get("features", [])
    total: int = len(features)
    done: int = sum(1 for f in features if f.get("status") == "done")
    pending: int = sum(1 for f in features if f.get("status") == "pending")
    return f"전체 {total}개 / 완료 {done}개 / 남은 {pending}개"


# ============================================================
# evaluation_result.json 관리 함수들
# ============================================================
def load_evaluation_result() -> dict[str, Any] | None:
    """
    evaluation_result.json을 읽어서 파싱한다.

    Evaluator 에이전트가 생성하는 파일이다.
    하네스는 이 파일을 읽어서 통과 여부를 판단하고,
    미달 시 피드백을 코딩 에이전트에게 전달한다.

    Returns:
        파싱된 JSON 딕셔너리. 파일이 없으면 None.
    """
    if not EVALUATION_RESULT_PATH.exists():
        return None

    with open(EVALUATION_RESULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_feedback(evaluation: dict[str, Any]) -> str:
    """
    Evaluator의 평가 결과를 코딩 에이전트에게 전달할 피드백 문자열로 변환한다.

    이 피드백은 코딩 에이전트의 프롬프트에 추가되어,
    에이전트가 지적된 문제를 우선적으로 수정하도록 유도한다.

    Args:
        evaluation: evaluation_result.json의 파싱된 데이터.

    Returns:
        코딩 에이전트에게 전달할 피드백 문자열.
    """
    lines: list[str] = []
    lines.append(f"## Evaluator 피드백 (기능 #{evaluation.get('feature_id', '?')}: {evaluation.get('feature_name', '?')})")
    lines.append("")

    # 점수 요약
    scores: dict[str, int] = evaluation.get("scores", {})
    avg: float = evaluation.get("average", 0.0)
    lines.append(f"점수: 완성도 {scores.get('completeness', 0)} / "
                 f"품질 {scores.get('code_quality', 0)} / "
                 f"UI {scores.get('ui_ux', 0)} / "
                 f"호환성 {scores.get('compatibility', 0)} = 평균 {avg}")
    lines.append("")

    # 문제점
    issues: list[str] = evaluation.get("issues", [])
    if issues:
        lines.append("### 문제점 (반드시 수정할 것)")
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")
        lines.append("")

    # 개선사항
    improvements: list[str] = evaluation.get("improvements", [])
    if improvements:
        lines.append("### 개선사항 (이렇게 수정하라)")
        for i, imp in enumerate(improvements, 1):
            lines.append(f"{i}. {imp}")
        lines.append("")

    return "\n".join(lines)


def revert_feature_to_pending(feature_id: int) -> None:
    """
    feature_list.json에서 특정 기능의 상태를 다시 pending으로 되돌린다.

    Evaluator가 미달 판정을 내리면, 해당 기능을 pending으로 되돌려서
    코딩 에이전트가 다시 선택하여 수정하도록 한다.

    Args:
        feature_id: 되돌릴 기능의 id.
    """
    feature_data: dict[str, Any] | None = load_feature_list()
    if feature_data is None:
        return

    for feature in feature_data.get("features", []):
        if feature.get("id") == feature_id:
            feature["status"] = "pending"
            break

    with open(FEATURE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(feature_data, f, ensure_ascii=False, indent=2)


def get_latest_done_feature_id(feature_data: dict[str, Any]) -> int | None:
    """
    feature_list.json에서 가장 최근 done된 기능의 id를 반환한다.

    Args:
        feature_data: feature_list.json의 파싱된 데이터.

    Returns:
        가장 큰 id를 가진 done 기능의 id. 없으면 None.
    """
    done_features: list[dict[str, Any]] = [
        f for f in feature_data.get("features", [])
        if f.get("status") == "done"
    ]
    if not done_features:
        return None
    return max(f.get("id", 0) for f in done_features)


# ============================================================
# 프롬프트 로딩 함수
# ============================================================
def load_prompt(filename: str) -> str:
    """
    prompts/ 폴더에서 프롬프트 파일을 읽어온다.

    초기화 에이전트와 코딩 에이전트는 서로 다른 프롬프트를 받는다.
    같은 Claude 모델이지만, 프롬프트에 따라 다른 역할을 수행한다.
    이것이 하네스 패턴의 핵심: "같은 모델, 다른 역할".

    Args:
        filename: 프롬프트 파일명 (예: "initializer_task.md").

    Returns:
        프롬프트 파일의 전체 내용.

    Raises:
        FileNotFoundError: 프롬프트 파일이 없을 때.
    """
    prompt_path: Path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# 에이전트 세션 실행 함수
# ============================================================
async def run_agent_session(
    prompt: str,
    session_name: str,
    max_turns: int = 30,
) -> dict[str, Any]:
    """
    Claude 에이전트 세션 하나를 실행한다.

    이 함수가 하네스의 핵심이다. Claude Agent SDK의 query()를 호출하여
    에이전트를 실행하고, 스트리밍으로 결과를 수집한다.

    하네스 패턴에서 각 세션은 독립적이다:
    - 세션마다 새로운 컨텍스트 윈도우가 시작된다
    - 이전 세션의 대화 내용은 전달되지 않는다
    - 세션 간 연속성은 오직 파일 시스템(feature_list.json, progress.txt)으로 유지된다

    Args:
        prompt: 에이전트에게 전달할 프롬프트 (initializer 또는 continuation).
        session_name: 로그에 표시할 세션 이름 (예: "초기화", "코딩 #3").
        max_turns: 에이전트가 사용할 수 있는 최대 도구 호출 횟수.
                   너무 적으면 작업을 완료하지 못하고, 너무 많으면 비용이 늘어난다.


    Returns:
        세션 결과를 담은 딕셔너리:
        {
            "session_name": str,      # 세션 이름
            "result": str | None,     # 에이전트 출력 (성공 시)
            "status": str,            # "success", "error_max_turns" 등
            "cost_usd": float,        # 이 세션에서 사용한 비용
            "num_turns": int,         # 실제 사용한 도구 호출 횟수
        }
    """
    log(f"[{session_name}] 세션 시작", "START")
    log(f"[{session_name}] 최대 턴: {max_turns}")

    # ---------------------------------------------------------
    # 에이전트 옵션 구성
    # ---------------------------------------------------------
    # ClaudeCodeOptions는 에이전트의 동작을 제어하는 모든 설정을 담는다.
    # 이 옵션은 세션마다 새로 만든다 (세션 간 상태 공유 방지).
    options: ClaudeCodeOptions = ClaudeCodeOptions(
        # 에이전트가 사용할 수 있는 도구 목록
        # 이 도구들은 보안 훅(security.py)의 검사를 거친 뒤에만 실행된다.
        allowed_tools=[
            "Read",       # 파일 읽기 (안전 - 훅 검사 불필요)
            "Write",      # 파일 쓰기 (훅이 경로 검사)
            "Edit",       # 파일 수정 (훅이 경로 검사)
            "Bash",       # 셸 명령어 (훅이 명령어 검사)
            "Glob",       # 파일 패턴 검색 (안전)
            "Grep",       # 파일 내용 검색 (안전)
        ],

        # 권한 모드: "acceptEdits"는 파일 편집을 자동 승인한다.
        # 하네스 패턴에서는 사람이 매번 승인하지 않으므로 이 모드를 사용한다.
        # 대신 security.py의 훅이 보안 검사를 수행한다.
        permission_mode="acceptEdits",

        # 작업 디렉토리를 프로젝트 루트로 설정한다.
        # 이렇게 하면 CLAUDE.md가 자동으로 로드되어 에이전트에게 프로젝트 규칙이 전달된다.
        cwd=str(PROJECT_ROOT),

        # 에이전트의 리소스 제한
        max_turns=max_turns,

        # 보안 훅 연결
        # security.py의 create_security_hooks()가 반환하는 훅 딕셔너리를
        # 그대로 전달한다. 이 훅이 모든 도구 호출을 가로채서 검사한다.
        hooks=create_security_hooks(project_root=str(PROJECT_ROOT)),
    )

    # ---------------------------------------------------------
    # 에이전트 실행 및 결과 수집
    # ---------------------------------------------------------
    # query()는 비동기 제너레이터로, 에이전트의 메시지를 하나씩 스트리밍한다.
    # 에이전트가 도구를 호출하고, 결과를 받고, 다음 도구를 호출하는
    # 전체 루프가 이 query() 안에서 자동으로 실행된다.
    result: dict[str, Any] = {
        "session_name": session_name,
        "result": None,
        "status": "unknown",
        "cost_usd": 0.0,
        "num_turns": 0,
    }

    try:
        async for message in query(
            prompt=prompt,
            options=options,
        ):
            # -------------------------------------------------
            # 메시지 타입별 처리
            # -------------------------------------------------
            # SDK는 여러 타입�� 메시지를 스트리밍한다:
            # - AssistantMessage: ��이전트의 응답 (텍스트 + 도구 호출)
            # - UserMessage: 도구 실행 결과
            # - ResultMessage: 세션 종료 시 최종 결과
            # - SystemMessage: 시스템 ���벤트 (rate_limit_event 등)
            #
            # 알 �� 없는 메시지 타입이 올 수 있���므로, 각 타입을 안전하게 처리한다.

            try:
                # 최종 결과 메시지인지 확인한다.
                # ResultMessage는 session_id, subtype, total_cost_usd 등을 가진다.
                if hasattr(message, "subtype") and hasattr(message, "total_cost_usd"):
                    result["status"] = message.subtype
                    result["cost_usd"] = message.total_cost_usd
                    result["num_turns"] = getattr(message, "num_turns", 0)
                    result["result"] = getattr(message, "result", None)

                    log(f"[{session_name}] 세션 종료: {message.subtype}")
                    log(f"[{session_name}] 비용: ${message.total_cost_usd:.4f}, 턴: {result['num_turns']}")

                # 에이전��의 응답 메시지 (도구 호출 포함)
                elif hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            log(f"[{session_name}] 도구 호출: {block.name}")

                # 그 외 메시지 (rate_limit_event, system 등)는 무시한다.
                # SDK가 내부적으로 처리하므로 하네스에서 별도 처리할 필요 없다.

            except Exception as msg_err:
                # 개별 메시지 처리 중 에러는 무시하고 다음 메시지로 넘어간다.
                # 세션 전체를 중단하지 않기 위함이다.
                log(f"[{session_name}] 메시지 처리 중 경고: {msg_err}", "WARN")

    except Exception as e:
        log(f"[{session_name}] 에러 발생: {e}", "ERROR")
        result["status"] = "error"
        result["result"] = str(e)

    return result


# ============================================================
# 초기화 단계
# ============================================================
async def run_initializer() -> dict[str, Any]:
    """
    초기화 에이전트를 실행한다 (1단계).

    프로젝트의 뼈대를 만드는 1회성 작업이다.
    feature_list.json이 없을 때만 실행된다.

    초기화 에이전트가 하는 일:
    - output/ 디렉토리 생성
    - feature_list.json 생성 (기능 목록)
    - progress.txt 생성 (빈 로그)
    - output/index.html, style.css, app.js 뼈대 생성
    - git init + 첫 커밋

    Returns:
        세션 결과 딕셔너리.
    """
    log("초기화가 필요합니다 (feature_list.json 없음)", "WARN")

    prompt: str = load_prompt("initializer_task.md")
    return await run_agent_session(
        prompt=prompt,
        session_name="초기화",
        max_turns=20,       # 초기화는 단순 작업이므로 턴을 적게 잡는다
    )


# ============================================================
# 코딩 단계
# ============================================================
async def run_coding_session(session_number: int) -> dict[str, Any]:
    """
    코딩 에이전트를 실행한다 (2단계, 반복).

    매 세션마다 pending 기능 하나를 구현한다.
    세션 간에 공유되는 것은 파일 시스템뿐이다.

    Args:
        session_number: 현재 코딩 세션 번호 (로그용).

    Returns:
        세션 결과 딕셔너리.
    """
    # 현재 진행 상황을 로그에 출력한다
    feature_data: dict[str, Any] | None = load_feature_list()
    if feature_data:
        log(f"진행 상황: {get_feature_summary(feature_data)}")

    prompt: str = load_prompt("continuation_task.md")
    return await run_agent_session(
        prompt=prompt,
        session_name=f"코딩 #{session_number}",
        max_turns=30,       # 코딩은 더 복잡하므로 턴을 넉넉하게 잡는다
    )


# ============================================================
# Evaluator 단계
# ============================================================
async def run_evaluator(feature_id: int) -> dict[str, Any]:
    """
    Evaluator 에이전트를 실행한다.

    Generator-Evaluator 패턴에서 "검증하는 놈" 역할이다.
    코딩 에이전트가 구현한 기능을 별도 에이전트가 객관적으로 평가한다.

    Evaluator는 읽기 전용이다:
    - Read, Glob, Grep만 사용 (Write, Edit, Bash 미허용)
    - evaluation_result.json만 쓸 수 있다 (Write는 이 파일에만 허용)

    Args:
        feature_id: 평가할 기능의 id (로그용).

    Returns:
        세션 결과 딕셔너리.
    """
    log(f"[Evaluator] 기능 #{feature_id} 평가 시작", "START")

    prompt: str = load_prompt("evaluator_task.md")
    return await run_agent_session(
        prompt=prompt,
        session_name=f"Evaluator #{feature_id}",
        max_turns=15,       # 평가는 읽기 위주이므로 턴을 적게 잡는다
    )


# ============================================================
# 피드백 포함 코딩 세션
# ============================================================
async def run_coding_with_feedback(
    session_number: int,
    feedback: str,
) -> dict[str, Any]:
    """
    Evaluator의 피드백을 포함하여 코딩 에이전트를 재실행한다.

    Generator-Evaluator 패턴에서 "재시도" 부분이다.
    Evaluator가 미달 판정을 내리면, 피드백(문제점 + 개선사항)을
    코딩 에이전트의 프롬프트에 추가하여 재실행한다.

    이렇게 하면 코딩 에이전트는:
    1. evaluation_result.json에서 피드백을 읽고
    2. 지적된 문제를 우선적으로 수정한다

    Args:
        session_number: 현재 코딩 세션 번호 (로그용).
        feedback: Evaluator가 작성한 피드백 문자열.

    Returns:
        세션 결과 딕셔너리.
    """
    log(f"[Generator] 피드백 반영 재시도 (세션 #{session_number})", "WARN")

    # 기본 프롬프트에 Evaluator 피드백을 추가한다
    base_prompt: str = load_prompt("continuation_task.md")
    prompt_with_feedback: str = (
        f"{base_prompt}\n\n"
        f"---\n\n"
        f"# ⚠️ 이전 Evaluator 평가에서 미달 판정을 받았다. 아래 피드백을 최우선으로 반영하라.\n\n"
        f"{feedback}"
    )

    return await run_agent_session(
        prompt=prompt_with_feedback,
        session_name=f"코딩 #{session_number} (재시도)",
        max_turns=30,
    )


# ============================================================
# 메인 오케스트레이션 루프
# ============================================================
async def main() -> None:
    """
    하네스의 메인 실행 함수.

    이 함수가 전체 흐름을 제어하는 오케스트레이터이다:
    1. 초기화 여부 판단
    2. Generator(코딩 에이전트) 실행
    3. Evaluator(평가 에이전트) 실행
    4. 통과 → 다음 기능 / 미달 → 피드백 전달 후 재시도 (최대 3회)

    세션 결과를 모아서 최종 요약을 출력한다.
    """
    log("=" * 50)
    log("네덜란드 미술관 웹사이트 - 하네스 시작", "START")
    log("=" * 50)

    # 프롬프트 파일 존재 확인
    for filename in ["initializer_task.md", "continuation_task.md", "evaluator_task.md"]:
        if not (PROMPTS_DIR / filename).exists():
            log(f"프롬프트 파일 누락: prompts/{filename}", "ERROR")
            sys.exit(1)

    # ---------------------------------------------------------
    # 세션 결과를 모으는 리스트
    # ---------------------------------------------------------
    # 모든 세션이 끝난 후 최종 요약을 출력하기 위해 결과를 모은다.
    all_results: list[dict[str, Any]] = []

    # ---------------------------------------------------------
    # 1단계: 초기화 (필요한 경우에만)
    # ---------------------------------------------------------
    # feature_list.json이 없으면 초기화 에이전트를 실행한다.
    # 이미 있으면 초기화를 건너뛴다 (이전에 이미 실행됨).
    if not FEATURE_LIST_PATH.exists():
        init_result: dict[str, Any] = await run_initializer()
        all_results.append(init_result)

        # 초기화 실패 시 즉시 중단한다.
        # 환경이 올바르게 갖춰지지 않으면 코딩 에이전트가 실패하기 때문이다.
        if init_result["status"] != "success":
            log(f"초기화 실패: {init_result['status']}", "ERROR")
            log("코딩 단계로 넘어갈 수 없습니다. 문제를 확인해주세요.", "ERROR")
            _print_summary(all_results)
            sys.exit(1)

        # 초기화 후 feature_list.json이 생성되었는지 확인한다
        if not FEATURE_LIST_PATH.exists():
            log("초기화 에이전트가 feature_list.json을 생성하지 않았습니다", "ERROR")
            _print_summary(all_results)
            sys.exit(1)

        log("초기화 완료, 코딩 단계로 진입합니다", "DONE")
    else:
        log("feature_list.json 발견 - 초기화 건너뜀")

    # ---------------------------------------------------------
    # 2단계: Generator-Evaluator 루프
    # ---------------------------------------------------------
    # 매 반복마다:
    #   1. feature_list.json을 읽는다
    #   2. pending 기능이 있으면 Generator(코딩 에이전트)를 실행한다
    #   3. Evaluator(평가 에이전트)가 구현 결과를 검증한다
    #   4. 통과 → 다음 기능 / 미달 → 피드백 전달 후 재시도 (최대 3회)
    #
    # 이것이 Generator-Evaluator 패턴의 핵심이다:
    # - Generator는 기능을 만든다
    # - Evaluator는 만들어진 기능을 검증한다
    # - 미달이면 Evaluator의 피드백을 Generator에게 전달하여 재시도한다
    # - "만드는 놈과 검증하는 놈은 반드시 분리한다"
    session_number: int = 1
    retry_count: int = 0        # 현재 기능의 재시도 횟수
    feedback: str | None = None  # Evaluator의 피드백 (재시도 시 전달)
    max_sessions: int = 50       # 무한 루프 방지용 안전장치 (재시도 포함)

    while session_number <= max_sessions:
        # feature_list.json을 매번 새로 읽는다
        # (이전 세션의 에이전트가 업데이트했을 수 있으므로)
        feature_data: dict[str, Any] | None = load_feature_list()

        if feature_data is None:
            log("feature_list.json이 사라졌습니다", "ERROR")
            break

        pending: int = count_pending_features(feature_data)

        if pending == 0:
            log("모든 기능이 구현되었습니다!", "DONE")
            break

        log(f"남은 기능: {pending}개")
        log("-" * 40)

        # ==========================================================
        # Generator 실행 (코딩 에이전트)
        # ==========================================================
        # 피드백이 있으면 피드백을 포함한 프롬프트로 재실행한다.
        # 피드백이 없으면 기본 프롬프트로 실행한다.
        if feedback:
            coding_result: dict[str, Any] = await run_coding_with_feedback(
                session_number, feedback
            )
        else:
            coding_result: dict[str, Any] = await run_coding_session(session_number)

        all_results.append(coding_result)

        # Generator 세션 실패 시 중단
        if coding_result["status"] != "success":
            log(f"코딩 세션 #{session_number} 실패: {coding_result['status']}", "ERROR")
            log("남은 기능은 다음 harness.py 실행 시 이어서 작업합니다.", "WARN")
            break

        # ==========================================================
        # Evaluator 실행 (평가 에이전트)
        # ==========================================================
        # 코딩 에이전트가 완료한 기능을 별도 에이전트가 검증한다.
        # feature_list.json에서 가장 최근 done된 기능의 id를 찾는다.
        feature_data = load_feature_list()
        if feature_data is None:
            log("feature_list.json이 사라졌습니다", "ERROR")
            break

        current_feature_id: int | None = get_latest_done_feature_id(feature_data)

        if current_feature_id is None:
            # 코딩 에이전트가 done으로 바꾸지 않았을 수 있다 → 다음으로 넘어감
            log("[Evaluator] done 기능을 찾을 수 없음, 다음으로 진행", "WARN")
            feedback = None
            retry_count = 0
            session_number += 1
            continue

        eval_result: dict[str, Any] = await run_evaluator(current_feature_id)
        all_results.append(eval_result)

        # Evaluator 세션 실패 시 → 평가 건너뛰고 다음 기능으로
        if eval_result["status"] != "success":
            log(f"[Evaluator] 세션 실패: {eval_result['status']}, 평가 건너뜀", "WARN")
            feedback = None
            retry_count = 0
            session_number += 1
            continue

        # ==========================================================
        # 평가 결과 판정
        # ==========================================================
        evaluation: dict[str, Any] | None = load_evaluation_result()

        if evaluation is None:
            log("[Evaluator] evaluation_result.json을 찾을 수 없음, 통과 처리", "WARN")
            feedback = None
            retry_count = 0
            session_number += 1
            continue

        # 평가 점수 로그 출력
        scores: dict[str, int] = evaluation.get("scores", {})
        avg: float = evaluation.get("average", 0.0)
        log(f"[Evaluator] 점수: "
            f"완성도 {scores.get('completeness', 0)} / "
            f"품질 {scores.get('code_quality', 0)} / "
            f"UI {scores.get('ui_ux', 0)} / "
            f"호환성 {scores.get('compatibility', 0)} = 평균 {avg}")

        if evaluation.get("passed", False):
            # ----- 통과 -----
            log(f"[Evaluator] 기능 #{current_feature_id} 통과!", "DONE")
            feedback = None
            retry_count = 0
        else:
            # ----- 미달 -----
            retry_count += 1
            issues: list[str] = evaluation.get("issues", [])
            log(f"[Evaluator] 기능 #{current_feature_id} 미달 "
                f"(재시도 {retry_count}/{MAX_RETRIES})", "WARN")
            for i, issue in enumerate(issues, 1):
                log(f"[Evaluator]   {i}. {issue}")

            if retry_count >= MAX_RETRIES:
                # 최대 재시도 초과 → 포기하고 다음 기능으로
                log(f"[Evaluator] 최대 재시도 횟수({MAX_RETRIES}) 초과, 다음 기능으로 넘어감", "WARN")
                feedback = None
                retry_count = 0
            else:
                # 재시도 → 기능을 pending으로 되돌리고 피드백 전달
                revert_feature_to_pending(current_feature_id)
                feedback = format_feedback(evaluation)
                log(f"[Evaluator] 기능 #{current_feature_id}를 pending으로 되돌림, 피드백 전달")

        session_number += 1

    else:
        # max_sessions에 도달한 경우 (while-else)
        log(f"최대 세션 수({max_sessions})에 도달했습니다", "WARN")
        log("남은 기능은 다음 harness.py 실행 시 이어서 작업합니다.", "WARN")

    # ---------------------------------------------------------
    # 최종 요약 출력
    # ---------------------------------------------------------
    _print_summary(all_results)


# ============================================================
# 최종 요약 출력 함수
# ============================================================
def _print_summary(results: list[dict[str, Any]]) -> None:
    """
    모든 세션의 결과를 요약하여 출력한다.

    Args:
        results: 각 세션의 결과 딕셔너리 리스트.
    """
    log("=" * 50)
    log("실행 요약")
    log("=" * 50)

    total_cost: float = 0.0
    total_turns: int = 0

    for r in results:
        status_icon: str = "✅" if r["status"] == "success" else "❌"
        cost: float = r.get("cost_usd", 0.0)
        turns: int = r.get("num_turns", 0)
        total_cost += cost
        total_turns += turns

        log(f"  {status_icon} {r['session_name']}: {r['status']} "
            f"(${cost:.4f}, {turns}턴)")

    log("-" * 50)
    log(f"  총 세션: {len(results)}개")
    log(f"  총 비용: ${total_cost:.4f}")
    log(f"  총 턴: {total_turns}")

    # 최종 feature_list 상태 출력
    feature_data: dict[str, Any] | None = load_feature_list()
    if feature_data:
        log(f"  기능 상태: {get_feature_summary(feature_data)}")

    log("=" * 50)


# ============================================================
# 엔트리포인트
# ============================================================
# python3 harness.py 로 실행하면 main()이 호출된다.
if __name__ == "__main__":
    asyncio.run(main())
