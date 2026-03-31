# 네덜란드 미술관 웹사이트

## 프로젝트 개요

네덜란드의 유명 미술관과 작품을 소개하는 단일 페이지 웹사이트(SPA)를 구축한다.
이 프로젝트는 **하네스(Harness) 패턴**을 학습하기 위한 교육용 프로젝트이다.

### 하네스 패턴이란

하네스는 AI 에이전트를 **프로그래밍 방식으로 제어**하는 구조이다.
사람이 CLI에서 직접 명령하는 대신, Python 스크립트(`harness.py`)가 에이전트를 호출한다.

```
harness.py (오케스트레이터)
  ├── 1단계: 초기화 에이전트 실행 (prompts/initializer_task.md)
  │     → output/ 디렉토리와 뼈대 파일 생성
  ├── 2단계: 코딩 에이전트 실행 (prompts/continuation_task.md)
  │     → 실제 콘텐츠와 기능 구현
  └── security.py (보안 훅)
        → 모든 도구 호출을 검사하고 위험한 명령을 차단
```

이렇게 나누는 이유:
- 각 단계의 책임을 분리하여 디버깅이 쉬워진다
- 초기화 실패 시 코딩 단계로 넘어가지 않아 비용을 절약한다
- 각 단계에 서로 다른 보안 정책을 적용할 수 있다

## 기술 스택

| 영역 | 기술 | 용도 |
|------|------|------|
| 하네스 | Python 3.11+ | 에이전트 오케스트레이션 (`harness.py`, `security.py`) |
| 프론트엔드 | HTML5 | 시맨틱 마크업 (header, nav, main, section, footer) |
| 스타일 | CSS3 | 순수 CSS (변수, Grid, Flexbox) |
| 인터랙션 | JavaScript ES6+ | 바닐라 JS (프레임워크 금지) |

## 파일 구조

```
website/
├── CLAUDE.md                      # 이 파일 - 프로젝트 규칙서
├── harness.py                     # 하네스 메인 스크립트 (Claude Agent SDK)
├── security.py                    # 보안 훅 모듈
├── prompts/
│   ├── initializer_task.md        # 초기화 에이전트 프롬프트
│   └── continuation_task.md       # 코딩 에이전트 프롬프트
└── output/                        # 에이전트가 생성하는 웹사이트 결과물
    ├── index.html
    ├── style.css
    └── app.js
```

## 커밋 컨벤션

### 형식

```
type: 제목 (50자 이내)

왜: 이 변경이 필요한 이유
무엇: 구체적으로 변경한 내용
결과: 이 커밋 이후 달라지는 동작
```

### type 종류

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `refactor`: 동작 변경 없는 코드 개선
- `docs`: 문서 변경 (CLAUDE.md, 프롬프트 등)
- `style`: 코드 포맷팅, CSS 변경
- `test`: 테스트 추가 또는 수정
- `chore`: 빌드, 설정 등 기타 변경

### 예시

```
feat: 갤러리 섹션에 라이트박스 기능 추가

왜: 작품 이미지를 클릭했을 때 확대해서 볼 수 있어야 한다
무엇: app.js에 LightBox 클래스 추가, style.css에 모달 스타일 추가
결과: 갤러리 이미지 클릭 시 오버레이로 확대 표시됨
```

## 코딩 스타일

### Python (하네스 스크립트)

- **타입 힌트 필수**: 모든 함수의 매개변수와 반환값에 타입 힌트를 명시한다.
- `async/await` 패턴을 사용한다 (Claude Agent SDK가 비동기 기반).
- f-string을 사용한다.
- 독스트링은 한국어로 작성한다.

```python
# 좋은 예
async def run_agent(prompt: str, max_turns: int = 20) -> dict[str, Any]:
    """에이전트를 실행하고 결과를 반환한다."""
    ...

# 나쁜 예
async def run_agent(prompt, max_turns=20):
    ...
```

### JavaScript (웹사이트)

- ES6+ 문법을 사용한다 (const/let, 화살표 함수, 템플릿 리터럴).
- `var` 사용 금지.
- `'use strict'` 선언 필수.
- DOM 조작은 `querySelector` / `querySelectorAll`을 사용한다.
- 이벤트 위임(Event Delegation)을 적극 활용한다.

```javascript
// 좋은 예
const initGallery = () => {
  const gallery = document.querySelector('.gallery');
  gallery.addEventListener('click', (e) => {
    if (e.target.matches('.gallery__item')) { ... }
  });
};

// 나쁜 예
var items = document.getElementsByClassName('gallery-item');
for (var i = 0; i < items.length; i++) { ... }
```

### CSS

- CSS 변수(Custom Properties)로 테마 색상을 관리한다.
- 클래스 이름은 BEM 방법론을 따른다 (예: `.gallery__item--active`).
- 반응형: 모바일(~768px), 태블릿(~1024px), 데스크톱(1025px~).

### HTML

- UTF-8 인코딩, `lang="ko"` 설정.
- 접근성: `alt`, `aria-label` 등을 반드시 포함한다.

## 중요 규칙

### 한 번에 하나의 기능만 작업한다
- 여러 기능을 동시에 수정하지 않는다.
- 하나의 기능을 완료하고 검증한 후 다음으로 넘어간다.
- 커밋도 기능 단위로 나눈다.

### 테스트 삭제 금지
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 테스트가 실패하면 테스트를 고치는 것이 아니라 코드를 고친다.
- 새로운 기능에는 대응하는 검증 로직을 추가한다.

### 에이전트 행동 제한
- 모든 웹사이트 파일은 반드시 `output/` 디렉토리 안에 생성한다.
- `output/` 바깥의 파일을 수정하거나 삭제하지 않는다.
- 외부 CDN, API, 패키지 매니저(npm, yarn)를 사용하지 않는다.
- 이미지는 CSS gradient나 유니코드 문자로 대체한다.
- `rm -rf`, `sudo`, 시스템 파일 접근은 보안 훅이 차단한다.
