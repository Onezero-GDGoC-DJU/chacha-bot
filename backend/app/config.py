"""
설정 관리 모듈 (config.py)

명세서 7장(환경변수) 및 I3(설정 분리)에 정의된 시스템 설정을 관리합니다.
Pydantic Settings를 사용하여 환경변수 및 .env 파일의 값을 로드하고 타입을 검증합니다.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    애플리케이션 환경변수 설정 클래스
    
    모든 환경변수는 환경 또는 프로젝트 루트의 .env 파일로부터 읽어옵니다.
    명세서 7장의 규격에 맞춰 기본값 및 필수를 정의합니다.
    """
    
    # --------------------------------------------------------------------------
    # 1. Gemini LLM API 설정 (명세서 7장)
    # --------------------------------------------------------------------------
    # Google AI Studio에서 발급받은 Gemini API 키 (운영 시 필수, 절대 커밋 금지)
    gemini_api_key: Optional[str] = None
    
    # 사용할 Gemini 모델명 (예: gemini-1.5-flash, gemini-1.5-pro)
    gemini_model: str = "gemini-1.5-flash"

    # --------------------------------------------------------------------------
    # 2. 대화 및 맥락(Context) 설정 (명세서 7장)
    # --------------------------------------------------------------------------
    # 맥락에 포함할 최근 대화 턴 수 (기본값: 10턴 = 메시지 20개)
    context_turns: int = 10
    
    # 사용자 메시지 최대 글자 수 (기본값: 4000자, 프론트엔드와 공유)
    max_message_chars: int = 4000

    # --------------------------------------------------------------------------
    # 3. 데이터베이스 설정 (명세서 7장)
    # --------------------------------------------------------------------------
    # SQLite 사용 시 로컬 데이터베이스 파일 경로 (기본값: /data/chacha.db)
    database_path: str = "/data/chacha.db"
    
    # Supabase 사용 시 프로젝트 URL (선택)
    supabase_url: Optional[str] = None
    
    # Supabase Service Role Key (선택, 서버 전용 키)
    supabase_service_role_key: Optional[str] = None

    # --------------------------------------------------------------------------
    # 4. 서버 네트워크 및 시스템 프롬프트 경로
    # --------------------------------------------------------------------------
    # 바인딩할 호스트 및 포트 (I1 명세서: 백엔드는 8000 포트)
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 시스템 프롬프트 파일 경로 (명세서 2.1: backend/prompts/system.md)
    # 현재 파일(backend/app/config.py) 기준으로 backend/prompts/system.md를 탐색
    system_prompt_path: Path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"

    # Pydantic Settings 설정 (대소문자 무시, .env 파일 자동 읽기)
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # 로컬 실행 위치(루트 또는 backend/) 어디서든 .env 로드 가능
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 정의되지 않은 추가 환경변수는 무시
    )


# 전역 설정 싱글톤 인스턴스
settings = Settings()
