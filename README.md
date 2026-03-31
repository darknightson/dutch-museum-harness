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

### 핵심 개념 3가지

**1) 오케스트레이터 (harness.py)**
전체 흐름을 제어하는 Python 스크립트다. 어떤 에이전트를 언제 실행할지, 반복할지 중단할지를 결정한다.

**2) 프롬프트 분리 (prompts/)**
같은 Claude 모델에 다른 프롬프트를 주면 다른 역할을 수행한다. 초기화 에이전트와 코딩 에이전트는 같은 모델이지만 프롬프트가 다르다.

**3) 파일 시스템 기반 상태 공유**
에이전트는 매 세션마다 새로 시작된다 (이전 대화를 기억하지 못한다). 세션 간 연속성은 오직 파일 시스템(`feature_list.json`, `progress.txt`, `git`)으로 유지된다.

---

## 2. 프로젝트 하네스 흐름

```
python3 harness.py 실행
        │
        ▼
┌─ feature_list.json 있나? ─────────────────────────┐
│                                                    │
│  없다 (첫 실행)              있다 (이어서 작업)      │
│       │                          │                 │
│       ▼                          │                 │
│  ┌──────────────┐                │                 │
│  │ 초기화 에이전트 │               │                 │
│  │              │                │                 │
│  │ 프롬프트:     │                │                 │
│  │ initializer  │                │                 │
│  │ _task.md     │                │                 │
│  │              │                │                 │
│  │ 하는 일:     │                │                 │
│  │ - output/ 생성│                │                 │
│  │ - 뼈대 파일   │                │                 │
│  │ - feature_   │                │                 │
│  │   list.json  │                │                 │
│  │ - git init   │                │                 │
│  └──────┬───────┘                │                 │
│         │                        │                 │
│         ▼                        ▼                 │
│     ┌──────────────────────────────┐               │
│     │  pending 기능이 남아있나?      │               │
│     └──────────┬───────────────────┘               │
│           예   │         아니오                      │
│                ▼            ▼                       │
│     ┌──────────────┐   완료! 요약 출력              │
│     │ 코딩 에이전트  │                               │
│     │              │   ┌─────────────────────┐     │
│     │ 프롬프트:     │   │ 세션별 비용, 턴 수,   │     │
│     │ continuation │   │ 기능 완료 현황 출력   │     │
│     │ _task.md     │   └─────────────────────┘     │
│     │              │                               │
│     │ 하는 일:     │                               │
│     │ 1. progress  │                               │
│     │    .txt 읽기 │                               │
│     │ 2. pending   │◄──── security.py              │
│     │    기능 선택  │     모든 도구 호출을            │
│     │ 3. 기능 구현  │     실시간으로 검사             │
│     │ 4. 상태 갱신  │     (Bash 명령어, 파일 경로)    │
│     │ 5. git commit│                               │
│     └──────┬───────┘                               │
│            │                                       │
│            └── 다시 pending 체크로 ──────────────────┘
│
└────────────────────────────────────────────────────┘
```

### 세션 간 데이터 흐름

에이전트는 매 세션마다 컨텍스트가 초기화된다. 이전 대화를 기억하지 못한다.
대신 아래 파일들이 세션 간 "메모리" 역할을 한다:

```
세션 #1 (초기화)          세션 #2 (코딩)           세션 #3 (코딩)
     │                       │                       │
     ▼                       ▼                       ▼
feature_list.json ──────► feature_list.json ──────► feature_list.json
  7개 pending               6개 pending               5개 pending
                             1개 done                  2개 done
     │                       │                       │
     ▼                       ▼                       ▼
progress.txt ────────────► progress.txt ────────────► progress.txt
  (비어있음)                  +1줄 기록                 +1줄 기록
     │                       │                       │
     ▼                       ▼                       ▼
git log ─────────────────► git log ─────────────────► git log
  "chore: 초기화"            +"feat: 헤더 구현"         +"feat: 히어로 구현"
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
│   ├── initializer_task.md     ← 초기화 에이전트 프롬프트
│   └── continuation_task.md    ← 코딩 에이전트 프롬프트
└── output/                     ← 에이전트가 생성하는 결과물
    ├── index.html
    ├── style.css
    └── app.js
```

### `harness.py` - 오케스트레이터

전체 흐름을 제어하는 메인 스크립트다. Claude Agent SDK의 `query()` 함수로 에이전트를 호출한다.

**핵심 역할:**
- `feature_list.json` 유무로 초기화/코딩 단계를 판단한다
- 코딩 에이전트를 pending 기능이 없을 때까지 반복 실행한다
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

### `prompts/initializer_task.md` - 초기화 에이전트 프롬프트

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

### `prompts/continuation_task.md` - 코딩 에이전트 프롬프트

하네스가 **2단계부터 반복**으로 에이전트에게 전달하는 지시서다.
매 세션마다 기능 하나를 구현한다.

**수행 절차:**
1. `progress.txt` 읽기 (이전 작업 확인)
2. `feature_list.json`에서 pending 기능 중 id가 가장 작은 것 선택
3. 현재 코드 파악 (index.html, style.css, app.js 읽기)
4. 기능 구현 (output/ 안의 파일만 수정)
5. 셀프 검증 (HTML 구조, CSS 참조, JS 선택자 등)
6. `feature_list.json` 상태를 `"done"`으로 갱신
7. `progress.txt`에 작업 내용 기록
8. `git commit`

### `CLAUDE.md` - 에이전트 규칙서

Claude Agent SDK가 자동으로 읽어서 에이전트에게 전달하는 프로젝트 규칙이다.
`ClaudeAgentOptions(setting_sources=["project"])`로 로드된다.

**포함 내용:**
- 기술 스택 제한 (HTML/CSS/JS만, 프레임워크 금지)
- 커밋 컨벤션 (`type: 제목` + 왜/무엇/결과)
- 코딩 스타일 (Python 타입힌트, JS ES6+, CSS BEM)
- 행동 제한 (output/ 밖 쓰기 금지, 외부 리소스 금지)

### `feature_list.json` - 기능 목록 (에이전트가 생성)

초기화 에이전트가 생성하고, 코딩 에이전트가 매 세션마다 갱신한다.
하네스는 이 파일의 pending 수를 보고 반복/종료를 결정한다.

```json
{
  "features": [
    { "id": 1, "name": "헤더와 네비게이션", "status": "done" },
    { "id": 2, "name": "히어로 섹션", "status": "pending" },
    ...
  ]
}
```

### `progress.txt` - 작업 로그 (에이전트가 생성)

코딩 에이전트가 매 세션 끝에 한 줄씩 기록한다.
다음 세션의 에이전트가 이 파일을 읽고 이전 작업을 파악한다.

```
[2026-03-31] 헤더와 네비게이션 | 반응형 햄버거 메뉴 구현 | done
[2026-03-31] 히어로 섹션 | CTA 버튼, 배경 그라디언트 | done
```

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

첫 실행 시 초기화 → 코딩 순서로 자동 진행된다.
중간에 중단해도 다음 실행 시 `feature_list.json`을 읽고 이어서 작업한다.
