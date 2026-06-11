import threading
import time

from src.utils.logger import setup_logger
from src.utils.config_loader import config
from src.vision.camera_util import open_camera

logger = setup_logger("camera_side")

DUMMY_MODE = config["vision"]["dummy_mode"]
CAM_SIDE   = config["cameras"]["side"]
CAM_INDEX  = CAM_SIDE["index"]


class CameraSide:
    """Camera2 — 측면 카메라 (핀 휘어짐/들뜸 정밀 검사).

    상부 카메라(camera_top)와 동일하게 백그라운드 그래버 스레드로 '최신 프레임'만
    유지한다 → 5프레임 검사 루프에서 동기 read() 로 오래된 버퍼가 누적돼 검사 결과가
    밀리는 문제를 방지. DSHOW 백엔드 + config.cameras.side.controls(노출/게인) 적용.
    """

    def __init__(self):
        self._cap = None
        self._latest = None              # 그래버가 갱신하는 최신 프레임
        self._lock = threading.Lock()
        self._running = False
        if DUMMY_MODE:
            logger.info("Camera2(측면) 더미 모드")
            return
        self._cap = open_camera(CAM_SIDE)
        if not self._cap.isOpened():
            raise RuntimeError(f"Camera2(측면) 열기 실패: index={CAM_INDEX}")
        self._running = True
        threading.Thread(target=self._grab_loop, daemon=True).start()
        logger.info(f"Camera2(측면) 초기화 완료: index={CAM_INDEX} — 그래버 스레드 ON")

    def _grab_loop(self):
        """카메라에서 끊임없이 읽어 최신 프레임만 보관."""
        while self._running and self._cap is not None:
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest = frame
            else:
                time.sleep(0.005)

    def capture(self):
        """검사용 최신 프레임 반환. 더미/미수신: None."""
        if DUMMY_MODE or self._cap is None:
            return None
        with self._lock:
            frame = None if self._latest is None else self._latest.copy()
        if frame is None:
            logger.warning("Camera2 최신 프레임 없음")
            return None
        return frame

    def release(self):
        self._running = False
        if self._cap:
            time.sleep(0.05)             # 그래버 루프 종료 대기
            self._cap.release()
            logger.info("Camera2(측면) 해제")
