"""
PostgreSQL 클라이언트
시스템 설정 및 모델 설정 관리
"""
import os
import logging
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
import json

logger = logging.getLogger(__name__)


class PostgresClient:
    """PostgreSQL 클라이언트"""

    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        """데이터베이스 연결"""
        try:
            self.conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', 'postgres'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                user=os.getenv('POSTGRES_USER', 'admin'),
                password=os.getenv('POSTGRES_PASSWORD', 'admin123'),
                database=os.getenv('POSTGRES_DB', 'telemetry_db'),
                cursor_factory=RealDictCursor
            )
            logger.info("PostgreSQL connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def get_system_config(self, config_key: str) -> Optional[str]:
        """시스템 설정 조회"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT config_value FROM system_config WHERE config_key = %s",
                    (config_key,)
                )
                result = cur.fetchone()
                return result['config_value'] if result else None
        except Exception as e:
            logger.error(f"Error getting system config: {e}")
            return None

    def get_all_system_configs(self) -> List[Dict[str, Any]]:
        """모든 시스템 설정 조회"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT * FROM system_config ORDER BY config_key")
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting all system configs: {e}")
            return []

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """모델 설정 조회"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM model_config WHERE model_name = %s",
                    (model_name,)
                )
                return cur.fetchone()
        except Exception as e:
            logger.error(f"Error getting model config: {e}")
            return None

    def get_satellite_config(self, satellite_id: str) -> Optional[Dict[str, Any]]:
        """위성 설정 조회"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM satellite_config WHERE satellite_id = %s",
                    (satellite_id,)
                )
                return cur.fetchone()
        except Exception as e:
            logger.error(f"Error getting satellite config: {e}")
            return None

    def get_all_satellites(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """모든 위성 조회"""
        try:
            with self.conn.cursor() as cur:
                if enabled_only:
                    cur.execute(
                        "SELECT * FROM satellite_config WHERE monitoring_enabled = true ORDER BY satellite_id"
                    )
                else:
                    cur.execute("SELECT * FROM satellite_config ORDER BY satellite_id")
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting satellites: {e}")
            return []

    def get_all_subsystems(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """모든 서브시스템 조회"""
        try:
            with self.conn.cursor() as cur:
                if enabled_only:
                    cur.execute(
                        "SELECT * FROM subsystem_config WHERE monitoring_enabled = true ORDER BY subsystem_name"
                    )
                else:
                    cur.execute("SELECT * FROM subsystem_config ORDER BY subsystem_name")
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting subsystems: {e}")
            return []

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")


# 싱글톤 인스턴스
postgres_client = PostgresClient()
