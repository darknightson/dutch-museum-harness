# 네덜란드 미술관 웹사이트 - 하네스 패턴 학습 프로젝트

## 1. 하네스(Harness) 패턴이란?

하네스는 AI 에이전트를 **사람 대신 코드가 제어**하는 패턴이다.

일반적인 사용에서는 사람이 터미널에서 직접 Claude에게 명령한다.
하네스 패턴에서는 Python 스크립트가 Claude Agent SDK를 통해 에이전트를 호출한다.

```
일반적인 사용:   사람 → CLI → Claude
하네스 패턴:    사람 → harness.py → Claude Agent SDK → Claude
```

### 왜 하네스를 쓰는가?

| 일반 사용 | 하네스 패턴 |
|-----------|------------|
| 사람이 매번 명령어를 입력 | 스크립트가 자동으로 반복 실행 |
| 한 세션에서 모든 작업 수행 | 작업을 단계별로 분리하여 세션마다 하나씩 처리 |
| 보안은 사람의 판단에 의존 | 보안 훅이 모든 도구 호출을 자동 검사 |
| 실패 시 사람이 직접 대응 | 실패 시 자동 중단, 다음 실행 시 이어서 작업 |
| 만든 사람이 직접 검증 | 별도 Evaluator 에이전트가 객관적으로 검증 |

### 핵심 개념 4가지

**1) 오케스트레이터 (harness.py)**
전체 흐름을 제어하는 Python 스크립트다. 어떤 에이전트를 언제 실행할지, 반복할지 중단할지를 결정한다.

**2) 프롬프트 분리 (prompts/)**
같은 Claude 모델에 다른 프롬프트를 주면 다른 역할을 수행한다. 초기화, 코딩, 평가 에이전트는 같은 모델이지만 프롬프트가 다르다.

**3) 파일 시스템 기반 상태 공유**
에이전트는 매 세션마다 새로 시작된다 (이전 대화를 기억하지 못한다). 세션 간 연속성은 오직 파일 시스템(`feature_list.json`, `progress.txt`, `evaluation_result.json`, `git`)으로 유지된다.

**4) Generator-Evaluator 패턴**
코딩 에이전트(Generator)가 기능을 만들고, 평가 에이전트(Evaluator)가 검증한다. "만드는 놈과 검증하는 놈은 반드시 분리한다" — GAN에서 영감을 받은 구조로, Anthropic이 발표한 에이전트 설계 패턴이다.

---

## 2. 프로젝트 하네스 흐름

### 전체 흐름도

```
python3 harness.py 실행
        │
        ▼
┌─ feature_list.json 있나? ──────────────────────────────────┐
│                                                             │
│  없다 (첫 실행)                있다 (이어서 작업)              │
│       │                              │                      │
│       ▼                              │                      │
│  ┌────────────────┐                  │                      │
│  │ Planner         │                  │                      │
│  │ (초기화 에이전트) │                  │                      │
│  │                 │                  │                      │
│  │ 하는 일:        │                  │                      │
│  │ - output/ 생성  │                  │                      │
│  │ - 뼈대 파일     │                  │                      │
│  │ - feature_      │                  │                      │
│  │   list.json     │                  │                      │
│  │ - git init      │                  │                      │
│  └───────┬────────┘                  │                      │
│          │                           │                      │
│          ▼                           ▼                      │
│      ┌──────────────────────────────────┐                   │
│      │    pending 기능이 남아있나?        │                   │
│      └───────────┬──────────────────────┘                   │
│            예    │          아니오                            │
│                  ▼             ▼                             │
│  ┌───────────────────┐    완료! 요약 출력                    │
│  │ Generator          │                                     │
│  │ (코딩 에이전트)     │    ┌───────────────────────┐        │
│  │                    │    │ 세션별 비용, 턴 수,     │        │
│  │ 하는 일:           │    │ 평가 점수, 재시도 현황  │        │
│  │ 1. 피드백 확인     │    └───────────────────────┘        │
│  │ 2. pending 선택    │◄──── security.py                    │
│  │ 3. 기능 구현       │     모든 도구 호출을                  │
│  │ 4. 상태 갱신       │     실시간으로 검사                   │
│  │ 5. git commit      │                                     │
│  └────────┬──────────┘                                     │
│           │                                                 │
│           ▼                                                 │
│  ┌───────────────────┐                                     │
│  │ Evaluator          │                                     │
│  │ (평가 에이전트)     │                                     │
│  │                    │                                     │
│  │ 하는 일:           │                                     │
│  │ 1. 구현 코드 읽기  │                                     │
│  │ 2. 4가지 기준 채점 │                                     │
│  │ 3. 통과/미달 판정  │                                     │
│  │ 4. 결과 JSON 저장  │                                     │
│  └────────┬──────────┘                                     │
│           │                                                 │
│      통과? ──┐                                              │
│     ↙        ↘                                              │
│  미달 ❌    통과 ✅ ──→ 다시 pending 체크로 ─────────────────┘
│    │                                                        
│    ▼                                                        
│  재시도 횟수 < 3?                                            
│   ↙          ↘                                              
│ Yes           No                                            
│  │             │                                            
│  ▼             ▼                                            
│ 피드백 전달   포기, 다음                                      
│ pending으로   기능으로 ──→ 다시 pending 체크로 ───────────────┘
│ 되돌림                                                      
│  │                                                          
│  └── Generator 재실행 (피드백 포함) ─────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

### Generator-Evaluator 루프 상세

이 프로젝트의 핵심 패턴이다. 하나의 기능이 완성되기까지의 과정:

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Generator   │────▶│  Evaluator   │────▶│ 하네스 판정   │
│  (코딩)      │     │  (검증)      │     │              │
│              │     │              │     │  passed?     │
│ continuation │     │ evaluator    │     │  ├─ true  ──▶ 다음 기능
│ _task.md     │     │ _task.md     │     │  └─ false ──▶ 재시도
└─────────────┘     └─────────────┘     └──────────────┘
       ▲                                        │
       │            피드백 전달                    │
       └──────────────────────────────────────────┘
              evaluation_result.json의
              issues + improvements를
              프롬프트에 추가하여 재실행
```

**평가 기준 4가지 (각 0~10점):**

| 기준 | 검사 내용 |
|------|----------|
| 기능 완성도 | feature_list.json의 description 요구사항이 모두 구현됐는가? |
| 코드 품질 | CLAUDE.md 규칙(BEM, ES6+, 시맨틱 태그 등) 준수 여부 |
| UI/UX | 반응형, 접근성, 시각적 일관성 |
| 기존 기능 호환성 | 이전 기능이 깨지지 않았는가? |

- 평균 **7점 이상**: 통과 → 다음 기능으로
- 평균 **7점 미만**: 미달 → 피드백과 함께 재시도 (최대 3회)

### 세션 간 데이터 흐름

에이전트는 매 세션마다 컨텍스트가 초기화된다. 이전 대화를 기억하지 못한다.
대신 아래 파일들이 세션 간 "메모리" 역할을 한다:

```
세션 #1          세션 #2          세션 #3          세션 #4          세션 #5
(초기화)         (코딩)           (평가)           (코딩-재시도)     (평가)
   │                │                │                │                │
   ▼                ▼                ▼                ▼                ▼
feature_list    feature_list    evaluation_     feature_list    evaluation_
  .json           .json         result.json       .json         result.json
 7개 pending     #1 → done      점수: 6.0       #1 → done       점수: 8.0
                                passed: false   (피드백 반영)    passed: true
                                issues: [...]                       │
                                      │                             ▼
                                      ▼                       다음 기능으로!
                                 피드백 전달
                                 #1 → pending
```

---

## 3. 파일 설명

```
website/
├── README.md                   ← 지금 읽고 있는 파일
├── CLAUDE.md                   ← 에이전트 규칙서
├── harness.py                  ← 하네스 오케스트레이터
├── security.py                 ← 보안 훅
├── prompts/
│   ├── initializer_task.md     ← 초기화 에이전트 (Planner)
│   ├── continuation_task.md    ← 코딩 에이전트 (Generator)
│   └── evaluator_task.md       ← 평가 에이전트 (Evaluator)
└── output/                     ← 에이전트가 생성하는 결과물
    ├── index.html
    ├── style.css
    └── app.js
```

### `harness.py` - 오케스트레이터

전체 흐름을 제어하는 메인 스크립트다. Claude Agent SDK의 `query()` 함수로 에이전트를 호출한다.

**핵심 역할:**
- `feature_list.json` 유무로 초기화/코딩 단계를 판단한다
- Generator → Evaluator → 통과/재시도 루프를 실행한다
- `evaluation_result.json`을 읽어서 통과 여부를 판정한다
- 미달 시 피드백을 Generator 프롬프트에 추가하여 재실행한다
- 같은 기능에 대해 최대 3회 재시도, 초과 시 다음 기능으로
- 매 세션의 비용, 턴 수, 성공 여부를 추적하고 요약한다
- `security.py`의 보안 훅을 에이전트 옵션에 연결한다

**SDK 사용 방식:**
```python
from claude_code_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    permission_mode="acceptEdits",
    hooks=create_security_hooks(project_root=str(PROJECT_ROOT)),
)

async for message in query(prompt=prompt, options=options):
    # 에이전트의 응답을 스트리밍으로 수신
```

### `security.py` - 보안 훅

에이전트가 도구를 호출할 때마다 자동으로 검사하는 보안 게이트다.

**검사 대상:**
| 도구 | 검사 내용 | 예시 |
|------|----------|------|
| Bash | 명령어 화이트리스트 + 차단 패턴 | `git add` 허용, `rm -rf` 차단 |
| Write/Edit | 파일 경로가 output/ 안인지 | `output/style.css` 허용, `/etc/passwd` 차단 |
| Read, Glob, Grep | 검사 안 함 (읽기 전용이라 안전) | - |

**허용 명령어:** git, mkdir, touch, cat, ls, echo, cd, pwd
**차단 패턴:** rm, sudo, chmod, curl, wget, npm, yarn, pip

**동작 원리:**
```
에이전트가 Bash("rm -rf /") 호출
       │
       ▼
security.py의 PreToolUse 훅이 가로챔
       │
       ▼
check_command("rm -rf /") → (False, "재귀/강제 삭제는 금지됩니다")
       │
       ▼
deny 응답 반환 → 에이전트는 명령을 실행하지 못함
       │
       ▼
[보안 16:30:00] 차단됨: [Bash] rm -rf /
         사유: 재귀/강제 삭제는 금지됩니다
```

### `prompts/initializer_task.md` - Planner (초기화 에이전트)

하네스가 **1단계**에서 에이전트에게 전달하는 지시서다.
이 에이전트는 코드를 짜지 않는다. 환경만 세팅한다.

**수행 절차:**
1. `output/` 디렉토리 생성
2. `feature_list.json` 생성 (7개 기능, 모두 `"status": "pending"`)
3. `progress.txt` 생성 (빈 로그)
4. `output/index.html` - 빈 HTML5 뼈대
5. `output/style.css` - CSS 변수 + 리셋만
6. `output/app.js` - `'use strict'` + 빈 함수 선언만
7. `git init` + 첫 커밋
8. 모든 파일 존재 확인

### `prompts/continuation_task.md` - Generator (코딩 에이전트)

하네스가 **2단계부터 반복**으로 에이전트에게 전달하는 지시서다.
매 세션마다 기능 하나를 구현한다.

**수행 절차:**
1. `progress.txt` 읽기 (이전 작업 확인)
2. `evaluation_result.json` 확인 (Evaluator 피드백이 있으면 우선 반영)
3. `feature_list.json`에서 pending 기능 중 id가 가장 작은 것 선택
4. 현재 코드 파악 (index.html, style.css, app.js 읽기)
5. 기능 구현 (output/ 안의 파일만 수정)
6. 기본 검증 (HTML 닫힘 태그, JS 런타임 에러만 — 상세 검증은 Evaluator가 수행)
7. `feature_list.json` 상태를 `"done"`으로 갱신
8. `progress.txt`에 작업 내용 기록
9. `git commit`

### `prompts/evaluator_task.md` - Evaluator (평가 에이전트)

Generator가 기능을 구현한 직후, 하네스가 호출하는 **검증 전용 에이전트**다.
코드를 수정하지 않는다. 읽고 평가만 한다.

**수행 절차:**
1. `feature_list.json`에서 가장 최근 `"done"` 기능 확인
2. `output/` 파일들을 읽고 해당 기능 검증
3. 4가지 기준으로 채점 (각 0~10점): 완성도, 코드 품질, UI/UX, 호환성
4. 평균 7점 이상이면 통과, 미만이면 미달
5. 미달 시 구체적 문제점(issues)과 개선사항(improvements) 작성
6. `evaluation_result.json` 저장

**결과 파일 예시:**
```json
{
  "feature_id": 3,
  "feature_name": "미술관 소개 섹션",
  "scores": {
    "completeness": 8,
    "code_quality": 7,
    "ui_ux": 6,
    "compatibility": 9
  },
  "average": 7.5,
  "passed": true,
  "issues": [],
  "improvements": []
}
```

### `CLAUDE.md` - 에이전트 규칙서

Claude Agent SDK가 자동으로 읽어서 에이전트에게 전달하는 프로젝트 규칙이다.
`ClaudeAgentOptions(setting_sources=["project"])`로 로드된다.

**포함 내용:**
- 기술 스택 제한 (HTML/CSS/JS만, 프레임워크 금지)
- 커밋 컨벤션 (`type: 제목` + 왜/무엇/결과)
- 코딩 스타일 (Python 타입힌트, JS ES6+, CSS BEM)
- 행동 제한 (output/ 밖 쓰기 금지, 외부 리소스 금지)

### 상태 파일 (에이전트가 생성/관리)

| 파일 | 생성 | 갱신 | 역할 |
|------|------|------|------|
| `feature_list.json` | Planner | Generator | 기능 목록과 진행 상태 (pending/done) |
| `progress.txt` | Planner | Generator | 작업 이력 로그 |
| `evaluation_result.json` | - | Evaluator | 평가 점수, 통과 여부, 피드백 |

---

## 실행 방법

```bash
# 1. Claude Agent SDK 설치
pip install claude-code-sdk

# 2. API 키 설정
export ANTHROPIC_API_KEY=sk-ant-...

# 3. 하네스 실행
python3 harness.py
```

첫 실행 시 초기화 → 코딩 → 평가 순서로 자동 진행된다.
중간에 중단해도 다음 실행 시 `feature_list.json`을 읽고 이어서 작업한다.

### 실행 로그 예시

```
[하네스 10:00:00] 🚀 네덜란드 미술관 웹사이트 - 하네스 시작
[하네스 10:00:01] 📋 feature_list.json 발견 - 초기화 건너뜀
[하네스 10:00:01] 📋 남은 기능: 6개
[하네스 10:00:01] 🚀 [코딩 #1] 세션 시작
[하네스 10:01:30] 📋 [코딩 #1] 세션 종료: success
[하네스 10:01:31] 🚀 [Evaluator #2] 기능 #2 평가 시작
[하네스 10:02:00] 📋 [Evaluator] 점수: 완성도 8 / 품질 7 / UI 6 / 호환성 9 = 평균 7.5
[하네스 10:02:00] ✅ [Evaluator] 기능 #2 통과!
[하네스 10:02:00] 📋 남은 기능: 5개
...
[하네스 10:05:00] 📋 [Evaluator] 점수: 완성도 6 / 품질 5 / UI 4 / 호환성 8 = 평균 5.75
[하네스 10:05:00] ⚠️ [Evaluator] 기능 #4 미달 (재시도 1/3)
[하네스 10:05:00] ⚠️ [Generator] 피드백 반영 재시도 (세션 #5)
```