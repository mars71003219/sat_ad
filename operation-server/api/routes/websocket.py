"""
WebSocket 엔드포인트
실시간 데이터 스트리밍
"""
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
from database.victoria_client import victoria_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["websocket"])

# 연결된 클라이언트 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """모든 연결된 클라이언트에게 메시지 전송"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(connection)

        # 연결 끊긴 클라이언트 제거
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()


@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    대시보드 실시간 데이터 스트리밍 (비동기 처리 + Heartbeat)
    """
    await manager.connect(websocket)

    # 필터 상태 유지
    current_filters = {"satellite_id": None, "subsystem": None, "feature_index": None}
    fetch_task = None
    heartbeat_task = None

    async def send_heartbeat():
        """30초마다 heartbeat 전송"""
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
                logger.debug("Heartbeat sent")
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    async def fetch_and_send_data(filters: dict):
        """데이터 조회 및 전송 (별도 태스크)"""
        try:
            import time
            t0 = time.time()

            # httpx async로 직접 호출
            inferences = await victoria_client.get_recent_inference_results(
                limit=10,
                satellite_id=filters['satellite_id'],
                subsystem=filters['subsystem'],
                feature_index=filters['feature_index']
            )
            t1 = time.time()

            await websocket.send_json({
                "type": "inferences",
                "data": inferences,
                "count": len(inferences),
                "filters": filters
            })
            t2 = time.time()

            logger.info(f"[PERF] DB query: {(t1-t0)*1000:.1f}ms, WS send: {(t2-t1)*1000:.1f}ms, TOTAL: {(t2-t0)*1000:.1f}ms")
        except asyncio.CancelledError:
            logger.info("Dashboard fetch task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error fetching inference data: {e}")
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except:
                pass

    try:
        # Heartbeat 태스크 시작
        heartbeat_task = asyncio.create_task(send_heartbeat())

        while True:
            data = await websocket.receive_text()
            filters = json.loads(data)

            # Pong 응답 처리
            if filters.get('type') == 'pong':
                logger.debug("Received pong from client")
                continue

            # 필터 업데이트
            current_filters.update({
                "satellite_id": filters.get('satellite_id'),
                "subsystem": filters.get('subsystem'),
                "feature_index": filters.get('feature_index')
            })

            logger.info(f"[PERF] Filter updated: {current_filters}")

            # 이전 fetch 태스크 취소
            if fetch_task and not fetch_task.done():
                fetch_task.cancel()
                try:
                    await fetch_task
                except asyncio.CancelledError:
                    pass

            # 새로운 fetch 태스크 시작 (비동기)
            fetch_task = asyncio.create_task(fetch_and_send_data(current_filters.copy()))

    except WebSocketDisconnect:
        logger.info("Dashboard WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # 태스크 정리
        if fetch_task and not fetch_task.done():
            fetch_task.cancel()
            try:
                await fetch_task
            except asyncio.CancelledError:
                pass

        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        manager.disconnect(websocket)


@router.websocket("/trends")
async def websocket_trends(websocket: WebSocket):
    """
    트렌드 데이터 실시간 스트리밍 (비동기 처리)
    """
    await manager.connect(websocket)

    # 필터 상태 유지
    current_filters = {
        "satellite_id": None,
        "subsystem": None,
        "feature_index": None,
        "start_time": None,
        "end_time": None
    }
    fetch_task = None

    async def fetch_and_send_trend(filters: dict):
        """트렌드 데이터 조회 및 전송 (별도 태스크)"""
        try:
            from datetime import datetime
            import time
            t0 = time.time()

            start_dt = datetime.fromisoformat(filters['start_time'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(filters['end_time'].replace('Z', '+00:00'))
            t1 = time.time()

            # httpx async로 직접 호출 (asyncio.to_thread 제거)
            data_points = await victoria_client.get_anomaly_score_trend(
                satellite_id=filters['satellite_id'],
                subsystem=filters['subsystem'],
                start_time=start_dt,
                end_time=end_dt,
                feature_index=filters['feature_index']
            )
            t2 = time.time()

            await websocket.send_json({
                "type": "trends",
                "data": {
                    "satellite_id": filters['satellite_id'],
                    "subsystem": filters['subsystem'],
                    "feature_index": filters['feature_index'],
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "data_points": data_points
                }
            })
            t3 = time.time()

            logger.info(f"[PERF TREND] Parse: {(t1-t0)*1000:.1f}ms, DB query: {(t2-t1)*1000:.1f}ms, WS send: {(t3-t2)*1000:.1f}ms, TOTAL: {(t3-t0)*1000:.1f}ms")
        except asyncio.CancelledError:
            logger.info("Trend fetch task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error fetching trend data: {e}")
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except:
                pass

    try:
        while True:
            data = await websocket.receive_text()
            filters = json.loads(data)

            # 필터 업데이트
            current_filters.update({
                "satellite_id": filters.get('satellite_id'),
                "subsystem": filters.get('subsystem'),
                "feature_index": filters.get('feature_index'),
                "start_time": filters.get('start_time'),
                "end_time": filters.get('end_time')
            })

            logger.info(f"[PERF TREND] Filter updated: {current_filters['satellite_id']}/{current_filters['subsystem']}")

            # 필수 필터 체크
            if not all([current_filters['satellite_id'], current_filters['subsystem'],
                       current_filters['start_time'], current_filters['end_time']]):
                continue

            # 이전 fetch 태스크 취소
            if fetch_task and not fetch_task.done():
                fetch_task.cancel()
                try:
                    await fetch_task
                except asyncio.CancelledError:
                    pass

            # 새로운 fetch 태스크 시작 (비동기)
            fetch_task = asyncio.create_task(fetch_and_send_trend(current_filters.copy()))

    except WebSocketDisconnect:
        if fetch_task:
            fetch_task.cancel()
        manager.disconnect(websocket)
        logger.info("Trend client disconnected normally")
    except Exception as e:
        if fetch_task:
            fetch_task.cancel()
        logger.error(f"Trend WebSocket error: {e}")
        manager.disconnect(websocket)
