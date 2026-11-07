# Git 읽기 전용 환경에서 pull 대응과 재발 방지

- 작업일: 2026-11-03
- PC: laptop (이 PC에서 만들어진 파일이다. 작성 세션의 PC 대조 기록은 파일에 없다)
- 갱신: 이 기록이 언급하는 검토표 파일은 이후 커밋 `a4306e8`(데스크탑)에서 저장소에서 제거되었다. 아래의 "검토표가 존재한다"는 서술은 작성 당시 상태다.

## 한 일

- 데스크탑 검토표 `docs/작업이력/2026-11-03-6단계-검토표-desktop.md`가 없다는 보고를 받고, 원격 브랜치와 현재 작업 트리의 차이를 확인했다.
- 당시 원격 추적 브랜치에는 검토표를 추가한 커밋 `5a27f0a`가 있었고, 작업 트리는 그 커밋보다 한 개 뒤처져 있었다. 변경 경로는 로컬 변경·미추적 파일과 겹치지 않아 fast-forward 가능한 상태로 판단했다.
- `git pull --ff-only origin feat/file-pipeline-extraction-integrate`를 실행했으나 `.git/FETCH_HEAD`가 읽기 전용이라는 오류로 실패했다. 이 환경에서는 `.git`에 기록할 수 없어서 pull이 완료되지 않았다.
- 이후 현재 확인한 작업 트리는 `5a27f0a`이며 검토표 파일이 존재하고, 브랜치가 `origin/feat/file-pipeline-extraction-integrate`와 동기화되어 있다. 이 전환은 현재 세션에서 실행한 pull 결과로 확인되지 않으므로, 별도 터미널·업데이트된 작업공간에서 반영됐을 가능성은 추측으로 남긴다.
- 현재 미커밋 변경은 추출 코드, 테스트, README 및 미추적 이력 파일 등에 남아 있다. 이번 이력 추가 외에는 수정하지 않는다.

## 재발 방지 절차

1. 먼저 `git status --short --branch`, `git branch -vv`, `git log -1 --oneline`으로 브랜치, upstream, 작업 트리를 기록한다.
2. `git fetch origin` 뒤 `git log --oneline HEAD..@{u}`와 `git diff --name-only HEAD..@{u}`로 원격 커밋과 변경 경로를 확인한다. fetch는 원격 추적 참조만 갱신하며 현재 작업 파일을 바꾸지 않는다.
3. pull 전 변경 경로가 로컬 수정·미추적 파일과 겹치는지 확인한다. 겹치거나 pull이 작업 파일을 덮어쓸 우려가 있으면 중단하고, 변경을 보존할 방법을 먼저 정한다.
4. 겹침이 없고 현재 브랜치의 fast-forward만 허용할 때 `git pull --ff-only <remote> <branch>`를 실행한다. `.git/FETCH_HEAD` 등 Git 메타데이터가 읽기 전용이라는 오류가 나면 반복 실행하지 않는다.
5. 읽기 전용 오류가 나면 Git 명령 문제가 아니라 해당 작업공간의 `.git` 쓰기 권한·마운트 문제로 기록한다. 같은 저장소의 사용자가 쓰기 가능한 터미널에서 상태를 다시 확인한 뒤 pull하고, `git status --short --branch`, `git log -1 --oneline`, `git ls-files --error-unmatch <기대 파일>`로 반영을 확인한다.
6. 에이전트 작업공간, 노트북, 데스크탑은 파일시스템이 다를 수 있으므로 한쪽의 `/tmp`나 Git 상태를 다른 환경의 사실로 간주하지 않는다. 결과를 보고할 때 확인한 환경과 명령 출력을 구분한다.

## 검증

- 확인 명령: `git status --short --branch`, `git branch -vv`, `git log -1 --oneline`, `ls docs/작업이력/2026-11-03-6단계-검토표-desktop.md`.
- 현재 확인 결과: `feat/file-pipeline-extraction-integrate`가 `origin/feat/file-pipeline-extraction-integrate`와 동기화되어 있고, HEAD는 `5a27f0a`; 검토표 파일이 있다.
- pull 재실행은 하지 않았다. 앞서 기록된 읽기 전용 `.git` 오류가 이 현재 셸에서 재현되는지 별도로 확인하지 않았으며, 이미 동기화되어 재실행할 필요도 없었다.
- 테스트는 실행하지 않았다. 이번 변경은 작업이력 문서만 추가한다.

## 직접 확인한 사실과 추측

- 직접 확인: 이전 pull 시도는 `.git/FETCH_HEAD` 읽기 전용 오류로 실패했다는 실행 결과가 전달되었다. 현재 checkout에는 커밋 `5a27f0a`와 검토표 파일이 있고, upstream과 동기화되어 있다.
- 추측: 이전 실패 뒤 다른 쓰기 가능한 터미널 또는 checkout 동기화가 해당 커밋을 반영했을 수 있다. 현재 상태만으로 반영 주체나 시점을 특정할 수 없다.

## 다음에 할 일

- pull이 필요할 때 위 절차로 브랜치와 변경 경로부터 확인한다.
- 읽기 전용 오류가 다시 나면 현재 작업공간에서 pull을 반복하지 말고, 쓰기 가능한 로컬 터미널에서 동기화를 수행한다.
- 관련 커밋: `5a27f0a` (검토표 추가 커밋; 본 이력은 아직 미커밋).
