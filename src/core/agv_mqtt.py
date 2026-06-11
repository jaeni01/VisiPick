import json, threading
import paho.mqtt.client as mqtt
from datetime import datetime
from src.utils.logger import setup_logger
from src.utils.config_loader import config
from src.core.db import save_agv_mission, save_system_event

logger = setup_logger("agv_mqtt")

BROKER    = config["mqtt"]["broker"]
PORT      = config["mqtt"]["port"]
START     = config["agv"]["nodes"]["start"]       # 기본 대기/출발 노드 (N1)
WAREHOUSE = config["agv"]["nodes"]["warehouse"]   # "WAREHOUSE"

# 진행 중인 미션: {agv_id(int): {"source","destination","recipe_session_id","phase"}}
#   phase: "outbound"(→창고) | "returning"(창고→홈 복귀)
_pending: dict[int, dict] = {}
# 현재 AGV 상태 캐시: {agv_id(int): {status, next_action, node, ...}}
_status: dict[int, dict] = {}
# 홈 도킹 슬롯 점유 현황(마스터 권위): {home_id(1/2/3): agv_id 점유 or None=비어있음}
_home_occupancy: dict[int, int | None] = {1: None, 2: None, 3: None}
_lock = threading.Lock()

# 전체 AGV ID 목록(브로드캐스트 대상)
ALL_AGV_IDS = list(range(1, config["agv"]["count"] + 1))


def _parse_agv_id(raw) -> int:
    """ESP32가 보내는 "AGV_1" 형식을 int 1로 변환."""
    try:
        if isinstance(raw, int):
            return raw
        # "AGV_1" → 1
        return int(str(raw).replace("AGV_", "").strip())
    except Exception:
        return 0


class AGVMqttManager:
    """
    AGV MQTT pub/sub 매니저.
    - 구독: visipick/agv/+/status
    - 발행: visipick/agv/{id}/command

    ESP32 펌웨어 동작 방식:
      1. GO_WAREHOUSE_1 or GO_WAREHOUSE_2 → 목적지 설정 (아직 출발 안 함)
      2. TRAY_LOADED                      → 이동 시작 (트레이가 올려졌음을 알림)
      3. 창고 도착 → 5초 대기 → 자동 회전 → 자동 복귀 홈 (UNLOAD/GO_N1 불필요)
      4. 상태 JSON: {"agv_id":"AGV_1","status":"...","next_action":"...","node":"..."}
         arrived 감지: next_action == "ARRIVED_WAREHOUSE_1" / "ARRIVED_WAREHOUSE_2"
         홈 복귀 완료: next_action == "ARRIVED_HOME"
    """

    def __init__(self):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(BROKER, PORT)
        self._client.loop_start()
        logger.info(f"AGV MQTT 매니저 시작: {BROKER}:{PORT}")

    # ── MQTT 콜백 ──────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("visipick/agv/+/status")
        logger.info("AGV 상태 구독: visipick/agv/+/status")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except Exception:
            return

        agv_id      = _parse_agv_id(data.get("agv_id"))
        status      = data.get("status")        # ESP32: "status" 키
        next_action = data.get("next_action")
        node        = data.get("node")

        with _lock:
            _status[agv_id] = {
                "status":      status,
                "next_action": next_action,
                "node":        node,
                "timestamp":   data.get("timestamp", datetime.now().isoformat()),
                "raw":         data,
            }

        logger.debug(f"AGV {agv_id} 상태: {status} / next_action={next_action} @ {node}")

        # 창고 도착 감지
        if next_action in ("ARRIVED_WAREHOUSE_1", "ARRIVED_WAREHOUSE_2"):
            warehouse_num = 1 if next_action == "ARRIVED_WAREHOUSE_1" else 2
            self._on_warehouse_arrived(agv_id, warehouse_num)

        # 홈 복귀 완료 감지
        elif next_action == "ARRIVED_HOME":
            self._on_home_arrived(agv_id)

    def _on_warehouse_arrived(self, agv_id: int, warehouse_num: int):
        """창고 도착 처리. ESP32가 5초 후 자동 복귀하므로 UNLOAD/GO 명령 불필요."""
        with _lock:
            mission = _pending.get(agv_id)

        destination = f"WAREHOUSE_{warehouse_num}"

        if not mission:
            save_system_event("AGV", "INFO", f"AGV {agv_id} 창고{warehouse_num} 도착 (미등록 미션)")
            logger.info(f"AGV {agv_id} 창고{warehouse_num} 도착 (미등록 미션)")
            return

        # 미션 DB 기록
        save_agv_mission(agv_id, mission["source"], destination,
                         mission.get("recipe_session_id"))
        save_system_event("AGV", "INFO",
                          f"AGV {agv_id} 창고{warehouse_num} 도착 — 자동 복귀 대기 중")
        logger.info(f"AGV {agv_id} 창고{warehouse_num} 도착 — ESP32 자동 복귀(5초 대기 후)")

        with _lock:
            if agv_id in _pending:
                _pending[agv_id]["phase"] = "returning"

    def _on_home_arrived(self, agv_id: int):
        """홈 복귀 완료 처리.

        AGV가 점유한 홈(status.selected_home)을 마스터 점유표에 BUSY로 기록하고
        전체 AGV에 HOME{n}_BUSY 브로드캐스트(다른 AGV의 동일 홈 선택 차단).
        """
        with _lock:
            _pending.pop(agv_id, None)
            home_id = _status.get(agv_id, {}).get("raw", {}).get("selected_home", 0)

        if home_id in (1, 2, 3):
            self._mark_home_busy(home_id, agv_id)
            save_system_event("AGV", "INFO",
                              f"AGV {agv_id} 홈{home_id} 도킹 — 슬롯 BUSY")
            logger.info(f"AGV {agv_id} 홈{home_id} 복귀 완료 — 슬롯 점유")
        else:
            save_system_event("AGV", "INFO", f"AGV {agv_id} 홈 복귀 완료 — 대기")
            logger.info(f"AGV {agv_id} 홈 복귀 완료 (홈 번호 미보고) — 다음 미션 대기")

    # ── 홈 슬롯 점유표(마스터 권위) ───────────────────────────────────────
    def _mark_home_busy(self, home_id: int, agv_id: int):
        """홈 슬롯을 점유 처리하고 전체 AGV에 BUSY 브로드캐스트."""
        with _lock:
            _home_occupancy[home_id] = agv_id
        for aid in ALL_AGV_IDS:
            self._command(aid, f"HOME{home_id}_BUSY")
        logger.info(f"홈{home_id} BUSY (점유: AGV {agv_id}) — 전체 브로드캐스트")

    def _mark_home_free(self, home_id: int):
        """홈 슬롯을 비움 처리하고 전체 AGV에 FREE 브로드캐스트.
        대기 중(RETURN_NO_FREE_HOME_WAIT)인 AGV가 있으면 그 홈으로 자동 출발한다."""
        with _lock:
            _home_occupancy[home_id] = None
        for aid in ALL_AGV_IDS:
            self._command(aid, f"HOME{home_id}_FREE")
        logger.info(f"홈{home_id} FREE — 전체 브로드캐스트")

    # ── 공개 API ────────────────────────────────────────────────────────────

    def _command(self, agv_id: int, payload: str):
        """AGV 명령 1건 발행 (visipick/agv/{id}/command). payload는 plain string."""
        self._client.publish(f"visipick/agv/{agv_id}/command", payload)
        logger.info(f"AGV {agv_id} 명령 발행: {payload}")

    def dispatch(self, agv_id: int, source: str = None,
                 recipe_session_id: int = None):
        """완성 트레이 운반 명령.
        1) GO_WAREHOUSE_1 or GO_WAREHOUSE_2 → 목적지 설정
        2) TRAY_LOADED                      → 이동 시작
        ESP32가 창고 도착 후 5초 대기 → 자동 복귀하므로 추가 명령 불필요.
        """
        source = source or START
        # AGV 1 → WAREHOUSE_1, AGV 2 → WAREHOUSE_2
        destination = f"{WAREHOUSE}_{agv_id}"

        # 이 AGV가 점유 중이던 홈 슬롯을 비움 → 대기 중인 다른 AGV가 그 홈으로 출발 가능
        with _lock:
            freed_home = next((h for h, owner in _home_occupancy.items()
                               if owner == agv_id), None)
        if freed_home is not None:
            self._mark_home_free(freed_home)

        with _lock:
            _pending[agv_id] = {
                "source":            source,
                "destination":       destination,
                "recipe_session_id": recipe_session_id,
                "phase":             "outbound",
            }

        self._command(agv_id, f"GO_{destination}")   # 목적지 설정
        self._command(agv_id, "TRAY_LOADED")          # 이동 시작
        logger.info(f"AGV {agv_id} 출고 명령: {source} → {destination}")

    def emergency_stop(self, agv_id: int = None):
        """비상정지. agv_id=None 이면 전체(1·2) 발행."""
        ids = [agv_id] if agv_id else [1, 2]
        for aid in ids:
            self._command(aid, "EMERGENCY_STOP")

    def emergency_clear(self, agv_id: int = None):
        """비상정지 해제."""
        ids = [agv_id] if agv_id else [1, 2]
        for aid in ids:
            self._command(aid, "EMERGENCY_CLEAR")

    # ── 홈(도킹) 슬롯 관리 ─────────────────────────────────────────────────
    def go_home(self, agv_id: int, home_id: int):
        """특정 홈(1/2/3)으로 복귀 명령. 펌웨어: GO_HOME_1/2/3."""
        self._command(agv_id, f"GO_HOME_{home_id}")

    def set_home_free(self, home_id: int, free: bool = True, agv_id: int = None):
        """홈 슬롯 비움/점유를 마스터 점유표에 반영 + 전체 AGV 브로드캐스트.
        free=True  → 마스터에서 비움 처리, 전체에 HOME{n}_FREE (대기 AGV 자동 출발).
        free=False → agv_id 점유로 기록, 전체에 HOME{n}_BUSY.
        주로 로봇이 홈의 트레이를 비웠을 때 set_home_free(n, True) 로 호출한다.
        """
        if free:
            self._mark_home_free(home_id)
        else:
            self._mark_home_busy(home_id, agv_id or 0)

    def get_home_occupancy(self) -> dict:
        """마스터 권위 홈 점유표 반환 {home_id: agv_id or None}."""
        with _lock:
            return dict(_home_occupancy)

    def clear_mission(self, agv_id: int):
        """AGV 미션/상태 초기화. 펌웨어: CLEAR_MISSION."""
        self._command(agv_id, "CLEAR_MISSION")

    def request_status(self, agv_id: int):
        """AGV 상태 즉시 publish 요청. 펌웨어: STATUS."""
        self._command(agv_id, "STATUS")

    def get_status(self, agv_id: int = None) -> dict:
        """현재 AGV 상태 반환. agv_id=None 이면 전체 딕셔너리."""
        with _lock:
            if agv_id is None:
                return dict(_status)
            return dict(_status.get(agv_id, {}))

    def get_home_free(self, agv_id: int) -> dict:
        """AGV가 보고한 홈 슬롯 점유 현황 반환 {1:bool,2:bool,3:bool}.
        펌웨어 status JSON 의 home1_free/home2_free/home3_free 에서 읽는다.
        """
        with _lock:
            raw = _status.get(agv_id, {}).get("raw", {})
        return {
            1: bool(raw.get("home1_free", False)),
            2: bool(raw.get("home2_free", False)),
            3: bool(raw.get("home3_free", False)),
        }

    def stop(self):
        self._client.loop_stop()
        logger.info("AGV MQTT 매니저 종료")


# ── 모듈 레벨 싱글톤 ──────────────────────────────────────────────────────────

_manager: AGVMqttManager | None = None


def get_manager() -> AGVMqttManager:
    """모듈 전체에서 공유하는 AGVMqttManager 인스턴스 반환."""
    global _manager
    if _manager is None:
        _manager = AGVMqttManager()
    return _manager
