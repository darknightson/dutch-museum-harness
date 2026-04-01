---
name: pr-skill
description: "PR", "피알", "풀리퀘", "pr-skill"이라고 말하면 활성화.
  현재 브랜치의 변경사항을 push하고 PR을 자동 생성한다.
disable-model-invocation: true
---

# PR 스킬 (Push + Pull Request)

## 트리거
사용자가 "PR", "피알", "풀리퀘", "pr-skill" 이라고 말하면 이 스킬을 실행한다.

## 수행 절차

### 1단계: 커밋되지 않은 변경사항 확인
```bash
git status
```

커밋되지 않은 변경사항이 있으면:
- "커밋되지 않은 변경사항이 있습니다. 먼저 /ke-commit을 실행해주세요." 안내
- 스킬 종료

### 2단계: 현재 브랜치 확인
```bash
git branch --show-current
```

- main 또는 develop 브랜치면: "PR은 feature 브랜치에서 생성해야 합니다." 안내 후 종료
- feature 브랜치면: 계속 진행

### 3단계: 타겟 브랜치 결정
```bash
git merge-base --is-ancestor develop HEAD && echo "develop" || echo "main"
```

- develop에서 파생된 브랜치면: 타겟 = **develop**
- main에서 파생된 브랜치면: 타겟 = **main**

### 4단계: 변경사항 분석
```bash
git log <타겟브랜치>..HEAD --oneline
git diff <타겟브랜치>..HEAD --stat
```

커밋 목록과 변경된 파일을 분석하여 PR 본문을 자동 생성한다.

### 5단계: PR 본문 생성

아래 형식을 **정확히** 따른다:
```
## 제목
<브랜치명과 커밋 내용에서 추출한 작업 제목>

## 내용
- 어떤것 때문에 작업을 진행하게 되었는지
- 변경/추가된 부분이 어떤 것들이 있는지
- 주요 작업 내용이 어떤것들이 있는지

## link
- 지라 티켓이나 링크 (커밋 메시지에서 추출, 없으면 "N/A")
- 관련 아지트나 문서 링크 (없으면 "N/A")

## 추가 설명
- 참고할 이슈나 리뷰어가 알아야 할 내용
- 기술적 결정사항이나 트레이드오프

## 테스트 방법
- 테스트 TC정보나 테스트 URL 정보
- 로컬 테스트 방법 (해당되는 경우)

---
AI-Use: yes
AI-Model: <사용된 모델명>
AI-Contribution: <기여도>%
```

### AI-Contribution 기준
| 비율 | 기준 |
|------|------|
| 90~100% | AI가 설계~구현을 자율 수행, 사용자는 지시/승인만 |
| 70~80% | 사용자가 방향/설계를 잡고 AI가 대부분 구현 |
| 40~60% | 사용자와 AI가 공동 작업 |
| 10~30% | 사용자가 직접 작성, AI는 보조 역할 |

### 6단계: 사용자 확인
생성된 PR 본문을 보여주고 확인을 요청한다:
- "이대로 Push + PR 생성할까요?"
- 타겟 브랜치 확인: "PR 타겟: <자동 감지된 브랜치> (변경하시겠습니까?)"
- 수정 요청이 있으면 반영 후 다시 확인

### 7단계: Push
```bash
git push origin <현재브랜치>
```

push 실패 시 에러 메시지를 보여주고 종료한다.

### 8단계: PR 생성
```bash
gh pr create --base <타겟브랜치> --title "<제목>" --body "<본문>"
```

`gh` CLI가 없으면:
- "gh CLI가 설치되어 있지 않습니다. brew install gh로 설치해주세요." 안내

### 9단계: 결과 보고
- PR URL 출력
- "PR이 생성되었습니다: <URL>"

## 금지 사항
- 사용자 확인 없이 push하지 않는다
- main/develop 브랜치에서 직접 PR을 만들지 않는다
- PR 본문의 형식을 임의로 변경하지 않는다
- force push를 하지 않는다