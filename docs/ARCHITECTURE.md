# VisiPick 아키텍처

> 중앙 서버(SSOT) 하나가 검사→판정→분류→이재→운반 전 과정을 소유한다.
> 결정 배경은 [docs/adr/](adr/) 참고.

## 코드맵 (폴더 → 역할 → 대표 파일)

| 폴더 | 역할 | 대표 파일 |
|------|------|----------|
| `src/core/` | 중앙 제어·인프라 | `state_machine.py`(공정 FSM·SSOT), `db.py`(SQLite 저장/조회), `agv_mqtt.py`(AGV 매니저), `frame_bus.py`(최신 프레임 공유), `vision_service.py`, `spc_analysis.py` |
| `src/vision/` | 카메라·검사 | `camera_top.py`/`camera_side.py`(그래버 스레드), `camera_util.py`(노출/포맷 공통화), `classifier.py`(YOLOv8n 추론 + classical 폴백), `pin_inspector.py`(핀 휨 계측), `defect_detector.py` |
| `src/orchestrator/` | 판정·레시피 | `decision.py`(4분류 판정 + 라벨/게이트/불량코드 어댑터), `recipe_mgr.py`(레시피 충족), `tray_mgr.py`(트레이 카운트) |
| `src/devices/` | 장치 드라이버 | `robot.py`(myCobot 경로 재생·0.05s 보간 스트리밍·E-stop), `serial_ctrl.py`(ESP32 게이트·컨베이어·IR 센서) |
| `src/api/` | 외부 인터페이스 | `api_server.py`(FastAPI REST/WebSocket/MJPEG :8000) |
| `src/utils/` | 공통 유틸 | `logger.py`, `config_loader.py`(config.json 단일 로드), `db_init.py`, `part_map.py`(부품명 변환 단일 지점), `heartbeat.py` |
| `config/` | 커미셔닝 상수 | `config.json`(벨트 속도·게이트 오프셋·임계값·dummy_mode), `robot_path_*.json`(교시 경로) |
| `mock/` | 하드웨어 대역 | `MockBroker.py`(순수 파이썬 MQTT), `MockESP32.py`(:9001), `MockMyCobot.py`(:9002), `MockAGV.py`(MQTT) |
| `tests/` | 검증 | `auto_test.py`(헤드리스 풀 사이클), `testsets.py`(판정 케이스 테이블), `gate_loop.py`, `test_vision_integration.py` |
| `tools/` | 현장 도구 | `robot_teach.py`(경유점 티칭), `live_yolo.py`/`live_pin.py`(라이브 튜닝), `camtest*.py` |
| `jetson/` | 엣지 배포 | Jetson 용 비전 서브셋 |
| `models/` | 모델 | `best.pt` — YOLOv8n 가중치 (학습: 팀원) |

## 데이터 흐름 (1 사이클)

```
IR 센서(ESP32) ─Serial→ state_machine.on_sensor_triggered
  1. 디바운스(debounce_sec) → 카메라 도달 대기(trigger_to_capture_sec)
  2. 멀티프레임 검사: 1초 / 10프레임
       상부: classifier(YOLOv8n) → 프레임별 4분류, DEFECT 는 3프레임 이상일 때만 확정
       측면: pin_inspector — IC·터미널블록만, 10프레임 투표 (현재 advisory, 판정 미반영)
  3. 판정: orchestrator.decision.evaluate → PASS/REJECT/DUPLICATE/UNCERTAIN
  4. 게이트 예약: 검사 시작 시각 기준 거리÷벨트속도 + 부품별 오프셋
       DEFECT → Gate1(불량 격리) · DUPLICATE/UNCERTAIN → Gate2(반환 컨베이어 → 재투입)
       PASS(NEEDED) → 게이트 없이 컨베이어 끝단에서 트레이 낙하, 레시피 카운트
  5. 기록·송출: DB(InspectionResults) 저장 + MQTT(visipick/inspection) 발행 + 프레임 버스 갱신
  6. 레시피 4종 완성 → 세션 스냅샷 후 즉시 리셋(검사 무정지) → 이재는 백그라운드:
       마지막 부품 낙하 대기 → 컨3 1칸 전진 → 로봇이 트레이를 AGV 슬롯(1~3)에 이재
  7. AGV 에 트레이 3개 적재되면 출발(출발점 RFID 로 대상 AGV 식별, 2대 교대) → 창고 → 홈 복귀
  8. DB: RecipeSessions 완료 처리, AgvMissions·SystemEvents 기록
```

## 시스템 불변식 (Invariants)

1. **공정 상태는 state_machine 만 변경한다.** 상태 전이(`_transition`)는
   `src/core/state_machine.py` 내부에만 존재하며, 다른 컴포넌트는 상태를 구독만 한다.
2. **HMI 는 표시 전용 — 판단 금지.** WPF 는 MQTT/REST 로 받은 것을 그리기만 하고,
   조작은 전부 명령 토픽(`visipick/*/cmd`)으로 중앙 서버에 위임된다.
3. **판정은 decision 단일 경로.** 게이트 동작·DB 분류·HMI 라벨·불량 코드는 모두
   `Decision.evaluate()` 결과에서 파생되며, 다른 곳에서 판정을 덧씌우지 않는다.
4. **부품명 변환은 part_map 단일 지점.** 비전(영문)↔레시피/DB/표시(한글) 변환은
   `src/utils/part_map.py` 에서만 한다 — 매핑 중복 정의 금지.
5. **카메라 프레임은 최신 1장만 유효.** 그래버 스레드가 항상 덮어쓰고(버퍼 없음),
   frame_bus 도 최신 프레임 덮어쓰기 모델이다 — 오래된 프레임 기반 판정 금지.

## 채널 분리 (ADR 0002)

| 채널 | 대상 | 데이터 특성 | 포트 |
|------|------|-------------|------|
| REST / WebSocket | HMI ↔ FastAPI | 제어 명령·조회 (요청-응답 보장) | :8000 |
| MQTT | 검사 결과·이벤트·AGV | 상태 브로드캐스트 (1:N 발행-구독) | :1883 |
| MJPEG (HTTP) | 카메라 영상 → HMI | 대용량 연속 스트림, 최신만 유효 | :8000 |
| Ethernet TCP | myCobot 280 Pi | 0.05s 보간 설정점 (저지연 연속) | :9000 |
| USB Serial | ESP32 게이트·컨베이어·IR | 단순 제어/이벤트 (115200bps) | COM |

## 명명 주의 (알려진 불일치)

`decision.py` 의 게이트 라벨 문자열(`GATE1_PUSH`/`GATE2_PUSH`)은 백엔드 팀원
인프라(HMI/DB 송출)의 명명을 그대로 유지한 것으로, **물리 게이트 번호와 반대다.**
물리 동작 기준은 `state_machine._inspect_one` 의 스케줄링이다:
Gate1 = 불량 격리, Gate2 = 중복·보류 반환. 라벨 문자열은 표시용으로만 쓰인다.

## 테스트 토폴로지

`python -m tests.auto_test N` 은 dummy_mode 4종을 강제하고 MockBroker(:1883)·
MockESP32(:9001)·MockMyCobot(:9002)·MockAGV(MQTT) 를 자동 기동해, 실제
state_machine 코드 경로(검사→판정→게이트→트레이→로봇→AGV→DB)를 하드웨어
없이 N 사이클 검증한다. 판정 로직 단독 검증은 `python -m tests.testsets`.
