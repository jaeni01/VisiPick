"""
src/devices/robot.py  —  myCobot 280 트레이 이재 제어 (드롭인 교체본)

state_machine.py 인터페이스 100% 보존:
    from src.devices.robot import Robot
    self._robot = Robot()
    self._robot.transfer_tray()   # 레시피 완성 시 호출
    self._robot.home()

동작 방식 (visipick-server RobotCtrl 로직 이식):
    dummy_mode=True  → MockMyCobot TCP(localhost:9002) — 기존 헤드리스 테스트 그대로
    dummy_mode=False → pymycobot MyCobot280Socket 으로 myCobot Pi 공식 소켓 서버 직결.
                       커스텀 RPi4 서버(9002) 불필요. Pi에서 공식 소켓 서버만 실행하면 됨.

config.json 의 robot 섹션에 아래 키가 있어야 함 (없으면 기본값 사용):
    "robot": {
      "host": "192.168.0.8",       # myCobot Pi IP (RealVNC 로 hostname -I 확인, 2026-06-11)
      "port": 9000,                # 공식 소켓 서버 포트 (커스텀 9002 아님!)
      "speed": 80,
      "dummy_mode": false,
      "gripper_open": 100, "gripper_close": 30,
      "pickup_angles": [..6..],    # ← 티칭으로 채울 것 (현재 0)
      "lift_angles":   [..6..],
      "place_angles":  [..6..],
      "home_angles":   [..6..],
      "joint_limits": { "j2_min_deg": -120, "j3_min_deg": -120 }
    }

Pi 쪽 준비(1회): myCobot 280 Pi 에서 공식 소켓 서버 실행 → MyCobot280Socket 이 접속.
티칭: tools/robot_teach.py (Pi 에서 실행) 로 경유점 교시 → path.json 저장 →
      scp 로 config/robot_path.json 배치. 경로 파일이 있으면 4자세는 무시된다.
"""
import socket, json, time
from datetime import datetime
from pathlib import Path
from src.utils.logger import setup_logger
from src.utils.config_loader import config

logger = setup_logger("robot")

_R = config["robot"]
DUMMY_MODE = _R["dummy_mode"]

# ── 실로봇 파라미터 (dummy 면 사용 안 함) ──────────────────────────────
HOST  = _R.get("host", "192.168.0.8")
PORT  = int(_R.get("port", 9000))
SPEED = int(_R.get("speed", 80))
GRIPPER_OPEN  = int(_R.get("gripper_open", 100))
GRIPPER_CLOSE = int(_R.get("gripper_close", 30))
PICKUP = list(_R.get("pickup_angles", [0, 0, 0, 0, 0, 0]))
LIFT   = list(_R.get("lift_angles",   [0, 0, 0, 0, 0, 0]))
PLACE  = list(_R.get("place_angles",  [0, 0, 0, 0, 0, 0]))
HOME   = list(_R.get("home_angles",   [0, 0, 0, 0, 0, 0]))
_JL    = _R.get("joint_limits", {})
J2_MIN = float(_JL.get("j2_min_deg", -120.0))
J3_MIN = float(_JL.get("j3_min_deg", -120.0))
ARRIVE_TOL_DEG  = 3.0     # 웨이포인트 도달 허용 오차
ARRIVE_WAIT_SEC = 8.0     # 웨이포인트당 최대 대기

# ── 촘촘한 경로 교시 파일 ─────────────────────────────────────────────
# 4자세(home/pickup/lift/place)만 쓰면 이동 중 트레이가 뒤집힌다.
# tools/robot_teach.py 로 다관절 경유점을 촘촘히(10~15점) 찍어 path.json 저장 →
# scp 로 config/robot_path.json 에 두면 robot.py 가 그대로 재생한다(부하·뒤집힘 최소화).
# 형식: {"speed":25, "waypoints":[{"angles":[6], "grip":null|"close"|"open"}, ...]}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # C:\VisiPick — config_loader 와 동일 기준
PATH_FILE = _R.get("path_file", "config/robot_path.json")


def _path_file() -> Path:
    p = Path(PATH_FILE)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _load_path():
    """경로 교시 파일 로드 + 전체 검증. 유효하면 dict, 아니면 None(4자세 폴백).
    scp 도중 잘린 파일(JSONDecodeError)·waypoint 형식 오류면 파일 전체를 무시한다 —
    일부만 재생하면 트레이를 쥔 채 엉뚱한 곳에서 멈출 수 있기 때문."""
    fp = _path_file()
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"경로 파일 손상/읽기 실패({fp}): {e}")
        return None
    wps = data.get("waypoints") if isinstance(data, dict) else None
    if not isinstance(wps, list) or not wps:
        logger.error(f"경로 파일에 waypoints 없음({fp})")
        return None
    for i, wp in enumerate(wps):
        ang = wp.get("angles") if isinstance(wp, dict) else None
        if not (isinstance(ang, list) and len(ang) == 6
                and all(isinstance(v, (int, float)) for v in ang)):
            logger.error(f"경로 점 {i+1} angles 형식 오류 — 파일 전체 무시: {wp}")
            return None
    return data

# ── mock 파라미터 (dummy 경로) ────────────────────────────────────────
MOCK_HOST = config["mock"]["robot"]["host"]
MOCK_PORT = config["mock"]["robot"]["port"]


class Robot:
    def __init__(self):
        self._mc = None       # 지연 연결 (부팅 시 Pi 미기동이어도 서버 부팅 OK)

    # ── 공개 인터페이스 (FSM 호출) ───────────────────────────────────
    def transfer_tray(self) -> bool:
        """완성 트레이를 AGV 적재 위치로 이재."""
        if DUMMY_MODE:
            return self._mock_cmd("tray_transfer")
        if not self._ensure():
            return False
        return self._transfer_cycle()

    def home(self) -> bool:
        if DUMMY_MODE:
            return self._mock_cmd("home")
        if not self._ensure():
            return False
        path = _load_path()                    # 경로 첫 점을 홈으로(파일 우선), 없으면 config HOME
        home_ang = path["waypoints"][0]["angles"] if path else HOME
        try:
            return self._send_angles(home_ang)
        except Exception as e:
            logger.error(f"홈 복귀 예외: {e}")
            self._mc = None
            return False

    # ── 실로봇 연결 (지연) ────────────────────────────────────────────
    def _ensure(self) -> bool:
        if self._mc is not None:
            return True
        try:
            try:
                from pymycobot import MyCobot280Socket as _Sock   # pymycobot 4.x 권장
            except Exception:
                from pymycobot.mycobot import MyCobotSocket as _Sock  # 구버전 폴백
            mc = _Sock(HOST, PORT)
            if hasattr(mc, "connect"):
                try:
                    mc.connect()
                except Exception:
                    pass
            self._mc = mc
            logger.info(f"myCobot 연결: {HOST}:{PORT}")
            return True
        except Exception as e:
            logger.error(f"myCobot 연결 실패: {e}")
            self._mc = None
            return False

    # ── 이재 시퀀스 ──────────────────────────────────────────────────
    def _transfer_cycle(self) -> bool:
        """경로 파일이 있으면 촘촘한 경로 재생, 없으면 구버전 4자세 폴백."""
        path = _load_path()
        if path:
            logger.info(f"경로 재생 모드: {_path_file()} ({len(path['waypoints'])}점)")
            return self._run_path(path)
        logger.warning("경로 파일 없음/무효 — 4자세 폴백 모드")
        return self._run_4pose()

    def _run_path(self, path) -> bool:
        """다관절 경로 재생: 각 경유점 send_angles+도착확인, grip 태그에서 그리퍼 동작.
        트레이 수평 유지를 위해 교시한 경유점을 그대로 따라간다(4자세 뒤집힘 회피).

        실패 정책 — 트레이를 쥔 채 공중에 멈추는 게 최악이므로:
          · 일반 경유점 미도달: 경고 후 계속 (촘촘한 경로라 다음 점이 끌어감)
          · 집기/놓기 점 미도달, 3연속 미도달(걸림 의심), 그리퍼 실패: 중단
        도달 기준은 교시 도구 replay 와 동일(5°/12s) — path.json 키로 덮어쓰기 가능."""
        speed = int(path.get("speed", SPEED))
        tol   = float(path.get("arrive_tol_deg", 5.0))
        wait  = float(path.get("arrive_wait_sec", 12.0))
        wps   = path["waypoints"]
        try:
            if not self._grip(GRIPPER_OPEN):         # 시작: 그리퍼 열기
                return False
            misses = 0
            for i, wp in enumerate(wps):
                ang  = wp["angles"]
                grip = (wp.get("grip") or "").lower()
                w = wait * 2 if i == 0 else wait     # 첫 점은 임의 현재 자세 → 장거리 가능
                if self._send_angles(ang, wait=w, speed=speed, tol=tol):
                    misses = 0
                else:
                    misses += 1
                    if grip in ("close", "open"):
                        logger.error(f"집기/놓기 점 {i+1}/{len(wps)} 미도달 — 이재 중단")
                        return False
                    if misses >= 3:
                        logger.error(f"경로 {i+1}/{len(wps)} 3연속 미도달 — 이재 중단(걸림 의심)")
                        return False
                    logger.warning(f"경로 {i+1}/{len(wps)} 미도달({misses}연속) — 다음 점으로 계속")
                if grip == "close":
                    if not self._grip(GRIPPER_CLOSE):    # 집기 지점
                        return False
                elif grip == "open":
                    if not self._grip(GRIPPER_OPEN):     # 놓기 지점
                        return False
            logger.info(f"트레이 이재 완료 (경로 {len(wps)}점, speed {speed})")
            return True
        except Exception as e:
            logger.error(f"트레이 이재 예외(경로): {e}")
            self._mc = None
            return False

    def _run_4pose(self) -> bool:
        """구버전 호환: home→pickup→그립닫기→lift→place→그립열기→home (트레이 뒤집힘 주의)."""
        if all(v == 0 for pose in (HOME, PICKUP, LIFT, PLACE) for v in pose):
            logger.error("경로 파일 없음 + 4자세 미티칭(전부 0) — 이재 거부. "
                         "tools/robot_teach.py 교시 후 config/robot_path.json 배치 필요")
            return False
        try:
            ok = (self._send_angles(HOME)
                  and self._send_angles(PICKUP)
                  and self._grip(GRIPPER_CLOSE)
                  and self._send_angles(LIFT)
                  and self._send_angles(PLACE)
                  and self._grip(GRIPPER_OPEN)
                  and self._send_angles(HOME))
            logger.info("트레이 이재 완료" if ok else "트레이 이재 실패(웨이포인트 미도달)")
            return ok
        except Exception as e:
            logger.error(f"트레이 이재 예외: {e}")
            self._mc = None      # 다음 호출 시 재연결
            return False

    def _send_angles(self, angles, wait: float = ARRIVE_WAIT_SEC, speed: int = SPEED,
                     tol: float = ARRIVE_TOL_DEG) -> bool:
        """관절각 전송 후 도달까지 폴링. send_coords 는 홈 특이점에서 실패하므로 사용 안 함."""
        a = self._clip(angles)
        self._mc.send_angles(a, speed)
        deadline = time.time() + wait
        while time.time() < deadline:
            cur = self._mc.get_angles()           # int 반환 가능 → isinstance 가드
            if isinstance(cur, list) and len(cur) == 6 \
               and all(abs(c - t) < tol for c, t in zip(cur, a)):
                return True
            time.sleep(0.1)
        logger.warning(f"도달 타임아웃: target={a}")
        return False

    def _grip(self, value: int) -> bool:
        try:
            self._mc.set_gripper_value(int(value), 50)
            time.sleep(0.8)
            return True
        except Exception as e:
            logger.error(f"그리퍼 오류: {e}")
            return False

    @staticmethod
    def _clip(angles):
        a = list(angles)
        if len(a) >= 3:
            a[1] = max(a[1], J2_MIN)   # j2 하한
            a[2] = max(a[2], J3_MIN)   # j3 하한
        return a

    # ── mock (dummy_mode) — 기존 MockMyCobot 그대로 사용 ──────────────
    def _mock_cmd(self, action: str) -> bool:
        msg = {"type": "robot_cmd", "action": action,
               "speed": SPEED, "timestamp": datetime.now().isoformat()}
        try:
            with socket.socket() as s:
                s.settimeout(10)
                s.connect((MOCK_HOST, MOCK_PORT))
                s.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode())
                resp = json.loads(s.recv(4096).decode().strip())
            return resp.get("status") == "ok"
        except Exception as e:
            logger.error(f"Mock robot 오류: {e}")
            return False
