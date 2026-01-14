# Kitsu Exporter

Kitsu API(Gazu)를 사용하여 프로젝트의 샷 리스트, 상태, 태스크 정보 및 썸네일을 엑셀 파일로 추출하는 도구입니다.

## 주요 기능
- Kitsu API 연동을 통한 최신 데이터 조회
- 터미널 GUI(TUI) 기반의 직관적인 인터페이스
- 엑셀 파일 생성 시 샷 썸네일 이미지 자동 삽입
- `uv`를 사용한 간편한 설치 및 실행

## 설치 및 실행 방법

### 1. 전제 조건
- Python 3.12 이상
- [uv](https://github.com/astral-sh/uv) 설치 권장

### 2. 설치 및 실행 방법

프로젝트 디렉토리에서 다음 명령어를 입력하여 환경을 구축하고 앱을 실행합니다:

```bash
# 의존성 설치 및 환경 구축
uv sync

# 앱 실행 (두 명령어 모두 가능)
uv run kitsu-exporter
# 또는
uv run kitsu_exporter
```

또는 패키지를 설치한 후 직접 실행할 수도 있습니다:

```bash
uv pip install .
kitsu-exporter # 또는 kitsu_exporter
```

> [!TIP]
> 엔트리 포인트 설치 없이 바로 실행하려면 다음 명령을 사용하세요:
> `uv run python -m kitsu_exporter.app`

## 사용법
1. 앱 실행 후 Kitsu 서버 주소, 이메일, 비밀번호를 입력하여 로그인합니다.
   - **서버 주소**: `kitsu.yourstudio.com` 처럼 주소만 입력해도 시스템이 자동으로 `https://.../api` 형태로 보정합니다.
2. 데이터를 추출할 프로젝트를 목록에서 선택합니다.
3. 'Start Export' 버튼을 클릭하여 추출을 시작합니다.
4. 완료 후 해당 디렉토리에 `{프로젝트명}_shots.xlsx` 파일이 생성됩니다.
