# VisiPick — 실시간 영상 분석 제품 자동 정렬·분류 시스템 (VisiPick)
> 비전 기반 불량 검사부터 로봇 Pick & Place, AGV 운송까지 검사→분류→이송 전 과정을 단일 상태머신으로 통합 제어하는 스마트 물류 자동화 시스템

![CI](https://github.com/jaeni01/VisiPick/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-00FFFF?style=flat-square&logo=yolo&logoColor=black)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white)
![C#](https://img.shields.io/badge/C%23-239120?style=flat-square&logo=csharp&logoColor=white)
![.NET WPF](https://img.shields.io/badge/.NET%20WPF-512BD4?style=flat-square&logo=dotnet&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-660066?style=flat-square&logo=mqtt&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)

<p align="center"><img src="docs/demo.gif" width="640" alt="Demo"></p>
<p align="center"><em>트레이 로봇 적재 → AGV 자동 운반 구간</em> · <a href="https://youtu.be/rDrZn_7qteQ">▶ 전체 영상</a></p>

## 📌 프로젝트 정보
| 항목 | 내용 |
|------|------|
| 개발 기간 | 2026.05.12 ~ 2026.06.19 (스쿱 인턴십 · 2026 충청남도 PILOT Program, 인턴 기간 2026.05~08) |
| 팀 구성 | 5인 팀 프로젝트 |
| 담당 역할 | 시스템 설계 · 비전 검사 · 중앙 제어 상태머신 · 통신 아키텍처 · 로봇 제어 |
| 시연 영상 | [YouTube](https://youtu.be/rDrZn_7qteQ) |

> **팀 역할 경계** — YOLOv8n 모델 학습·데이터셋은 팀원 담당(본인은 실시간 추론 통합·후처리·판정 설계), FastAPI 백엔드·WPF HMI·AGV ESP32 펌웨어는 각 팀원 담당.

## 🎯 프로젝트 개요
VisiPick는 멈추지 않고 흐르는(Non-stop) 컨베이어 위의 전자부품 4종을 두 대의 카메라로 실시간 검사하고, 레시피(특정 기판에 필요한 부품 조합)에 맞춰 자동으로 골라 모은 뒤, 로봇이 완성 트레이를 통째로 AGV에 실어 창고까지 운반하는 미니 스마트팩토리 셀입니다. 단순 양·불 분류를 넘어 "필요한 것만 골라 키팅" + "흐르는 채로(인라인) 검사"를 목표로 했습니다.

핵심은 검사부터 이송까지 흩어지기 쉬운 공정 단계를 Python 기반 단일 상태머신으로 묶어 일관되게 제어한 점이며, 이를 통해 다중 장비·다중 프로토콜 환경에서도 상태 충돌 없이 안정적으로 동작하도록 설계했습니다.

## ✨ 주요 기능 / 담당 업무
- **비전 검사 파이프라인**: YOLOv8n 추론과 OpenCV 측면 핀 검사를 결합해 부품을 분류하고 불량을 판정. 핀 개수, 핀 간격 변동계수(gap_cv), 정렬 편차(tip_y), 리드 휨(lean)을 기준으로 핀휨을 계측하고 DefectCode(`BENT_PIN`/`BROKEN`) 체계를 설계해 판정 결과를 코드화.
- **중앙 제어 상태머신**: Python 프로세스를 시스템 단일 상태 관리 주체(ISA-95 Level 1 Cell Controller, Single Source of Truth)로 두고 `IDLE → RUNNING → TRAY_TRANSFER → COMPLETE` 전 과정을 하나의 상태머신으로 통합 제어. 센서 트리거 기반 멀티프레임 검사, 게이트 지연 큐, 비상정지 일시정지화를 구현.
- **다중 프로토콜 통신 아키텍처**: HMI는 FastAPI(WebSocket/REST), AGV는 MQTT, ESP32 게이트·컨베이어는 USB Serial, myCobot은 Ethernet TCP/IP로 연동해 이기종 장비를 하나의 제어 흐름으로 통합. 데이터 성격별로 채널을 분리(제어 명령=REST, 상태 이벤트=MQTT, 영상=MJPEG).
- **로봇 제어 통합**: myCobot 280을 pymycobot `MyCobot280Socket`으로 제어하며, 트레이 자세 유지를 위한 교시 경로 재생, 0.05초 단위 보간 스트리밍, 2단 속도 제어, 소프트웨어 E-stop 경로를 구현해 안전성 확보.
- **백엔드 비전 엔진 이식**: 독립 동작하던 비전 엔진(상부 분류기 + 측면 핀검사 + 4분류 판정)을 어댑터 패턴으로 FastAPI 백엔드에 접합해 단일 서비스로 통합.

## 📊 성능 지표
- 통합 YOLOv8n 모델 기준 **mAP50 98% · mAP50-95 94%** (7클래스 · 학습: 팀원 / 추론 통합: 본인)
- 1초 10프레임 다수결 판정 + 신뢰도 게이트 0.40 — 불량은 3프레임 이상 검출 시에만 확정 (`config/config.json` `inspect_frames`/`defect_min_frames`)

## 🛠 기술 스택
### Software
- Python (YOLOv8n, OpenCV, PyTorch/TorchVision, pymycobot)
- C# WPF (.NET, MVVM, MahApps.Metro, LiveCharts2, EF Core, MQTTnet)
- FastAPI (REST + WebSocket)
- Mosquitto MQTT
- TCP/IP Socket
- SQLite (WAL)

### Hardware
- myCobot 280 Pi 로봇 팔
- Arduino / ESP32 (게이트·컨베이어)
- AGV (ESP32-CAM)
- 검사 카메라 2대 (상부·측면)

## 🔀 시스템 아키텍처
```mermaid
flowchart LR
  CAM_T["상부 카메라"] --> VISION_T["YOLOv8n 분류·불량"]
  CAM_S["측면 카메라"] --> VISION_S["OpenCV 핀검사"]
  VISION_T --> DEC["4분류 판정<br/>NEEDED/DUPLICATE/UNCERTAIN/DEFECT"]
  VISION_S --> DEC
  DEC --> FSM["Python 중앙 상태머신"]
  FSM --> HMI["FastAPI / HMI"]
  FSM --> AGV["MQTT / AGV"]
  FSM --> ESP["Serial / ESP32 게이트·컨베이어"]
  FSM --> COBOT["TCP / myCobot"]
  COBOT --> PICK["트레이 Pick & Place"]
  AGV --> MOVE["AGV 이송"]
  FSM --> DB["SQLite 영속화"]
```
카메라 영상이 비전 엔진을 거쳐 판정되면 중앙 상태머신이 결과를 받아 HMI·AGV·게이트·로봇으로 제어 명령을 분배하고, 로봇 트레이 이재와 AGV 이송을 수행하며 모든 이력을 SQLite에 영속화합니다.

## 📁 폴더 구조
```
VisiPick/
├── src/
│   ├── core/          # state_machine(중앙 FSM·SSOT)·db·agv_mqtt·frame_bus·vision_service·spc_analysis
│   ├── vision/        # camera_top/side·camera_util·classifier(YOLO 추론)·pin_inspector(핀 계측)·defect_detector
│   ├── orchestrator/  # decision(4분류 판정)·recipe_mgr(레시피 매칭)·tray_mgr(트레이 카운트)
│   ├── devices/       # robot(myCobot 경로 재생·보간 스트리밍)·serial_ctrl(ESP32 시리얼)
│   ├── api/           # api_server — FastAPI REST/WebSocket/MJPEG (:8000)
│   └── utils/         # logger·config_loader·db_init·heartbeat·part_map
├── config/            # config.json — 커미셔닝 상수(벨트 속도·게이트 오프셋·임계값)
├── mock/              # MockBroker·MockESP32·MockMyCobot·MockAGV — 하드웨어 없이 실행
├── tests/             # auto_test(풀 사이클 스모크)·testsets(판정 로직)·게이트 루프·비전 통합
├── tools/             # robot_teach(경유점 티칭)·live_yolo·live_pin·camtest 등 현장 도구
├── jetson/            # Jetson 배포용 비전 서브셋
├── models/            # best.pt — YOLOv8n 가중치 (학습: 팀원)
└── docs/              # 설계 문서·ADR·트러블슈팅
```

## 🚀 Quick Start
하드웨어 0대로 전체 파이프라인을 돌려볼 수 있습니다 — `auto_test` 가 dummy 모드를 강제하고 mock 브로커·ESP32·로봇·AGV 를 자동 기동하므로 설정 수정이 필요 없습니다.
```bash
pip install -r requirements-ci.txt   # 최소 의존성 (mock 실행용)
python -m tests.auto_test 5          # 검사→판정→게이트→트레이→로봇→AGV 5사이클 스모크
python -m tests.testsets             # 판정 로직(4분류) 테스트
```
실제 장비 구동 (`config/config.json` 의 각 `dummy_mode` 가 `false` 인 상태):
```bash
pip install -r requirements.txt     # 실장비·YOLO 추론용 (torch/ultralytics 포함)
python -m src.core.state_machine    # 중앙 제어 FSM
python -m src.api.api_server        # FastAPI 백엔드 (:8000) — 별도 프로세스
```

## 💻 핵심 코드 (담당 역할)

### 1. 4분류 판정 로직 — `src/orchestrator/decision.py`
"불확실 ≠ 불량"을 코드로 구현한 부분입니다. 신뢰도가 낮거나 미검출인 부품을 폐기(REJECT)하지 않고 `UNCERTAIN`(반환 → 재투입)으로 분리해, 정상품을 한 번의 저신뢰 판정으로 버리지 않고 수율을 보호합니다.
```python
def evaluate(self, top: dict, side: dict) -> DecisionResult:
    part = top.get("part")
    conf = float(top.get("confidence", 0.0))
    hint = (top.get("verdict_hint") or "UNKNOWN").upper()
    pin_verdict = (side.get("verdict") or "UNKNOWN").upper()

    # 1) 저신뢰/미검출 -> UNCERTAIN (Gate1 반환 → 재투입)
    #    불량(폐기)이 아니라 '판단 보류'. 정상품을 저신뢰 한 번으로 버리지 않는다.
    if part is None or conf < self.min_conf:
        return DecisionResult(Verdict.UNCERTAIN, part, ...)

    # 2) 분류기가 reject 힌트 -> REJECT
    if hint == "REJECT":
        return DecisionResult(Verdict.REJECT, part, ...)

    # 3) 측면 핀 휨 -> REJECT
    if pin_verdict == "BENT":
        return DecisionResult(Verdict.REJECT, part, ...)

    # 4) 이미 수집한 부품 -> DUPLICATE
    if self.is_duplicate(part):
        return DecisionResult(Verdict.DUPLICATE, part, ...)

    # 5) 기본 -> PASS (양품 → 트레이 낙하)
    return DecisionResult(Verdict.PASS, part, ...)
```

### 2. 측면 핀 휨 정밀 계측 — `src/vision/pin_inspector.py`
핀 있는 부품(IC·터미널블록)의 핀 위치를 OpenCV로 추출해 휨을 판정합니다. 핀 개수, 간격 변동계수(gap_cv), 정렬 편차(polyfit 잔차)를 종합해 `NORMAL`/`BENT`/`UNKNOWN`을 가립니다. 전체 기울기는 무시하고 polyfit 잔차로 "혼자 어긋난 핀"만 잡아내는 점이 핵심입니다.
```python
def _verdict(self, xs, ys, part) -> PinResult:
    pin_count = len(xs)
    expected  = self.expected.get(part or "", 0)
    count_tol = self.pin_count_tolerance.get(part or "", 1)
    gap_mean = gap_cv = 0.0
    if pin_count >= 2:
        gaps    = np.diff(xs).astype(np.float32)
        gap_mean = float(gaps.mean())
        gap_cv  = float(gaps.std() / max(gap_mean, 1e-3))   # 간격 변동계수
    # y 정렬 편차: polyfit 잔차(전체 기울기는 무시, 혼자 어긋난 핀만 잡힘)
    if pin_count >= 3:
        a, b = np.polyfit(np.asarray(xs, np.float32), np.asarray(ys, np.float32), 1)
        tip_y_range = int(np.abs(ys - (a * xs + b)).max())
    verdict = "NORMAL"
    if expected and abs(pin_count - expected) > count_tol:
        verdict = "BENT"          # 핀 수 불일치
    if pin_count >= 2 and gap_cv > self.gap_tol:
        verdict = "BENT"          # 간격 불균일
    if tip_y_range > self.tip_y_tol:
        verdict = "BENT"          # 정렬 이탈
    return PinResult(verdict=verdict, pin_count=pin_count, gap_cv=gap_cv, ...)
```

### 3. 로봇 트레이 이재 — 보간 스트리밍 + 2단 속도 — `src/devices/robot.py`
끝점만 주면 이동 중 트레이가 기울어 부품이 쏟아지므로, 교시한 경유점 사이를 0.05초 단위 미세 설정점으로 잘게 나눠 연속 전송(보간 스트리밍)해 등속·부드럽게 움직입니다. 트레이를 쥔 구간은 속도를 낮춰 쏟김을 방지합니다.
```python
def _stream_to(self, start, target, deg_s, dt=0.05):
    """관절 보간 스트리밍 — start→target 미세 설정점을 dt 주기로 연속 전송(등속)."""
    cmd = min(100, max(10, int(deg_s * 1.5)))
    d = max(abs(a - b) for a, b in zip(start, target))
    n = max(1, int(d / (max(deg_s, 1.0) * dt)) + 1)
    # 스텝별 페이싱: 전송에 걸린 시간만 dt 에서 차감. 누적 시계 방식은 전송이 dt보다
    # 느릴 때 밀린 설정점을 한꺼번에 쏟아 로봇이 중간점을 건너뛰고 돌진 → 빚을 안 넘긴다.
    for k in range(1, n + 1):
        t0 = time.time()
        pt = [round(a + (b - a) * k / n, 2) for a, b in zip(start, target)]
        self._mc.send_angles(pt, cmd)
        remain = dt - (time.time() - t0)
        if remain > 0:
            time.sleep(remain)
```

## 🔧 기술적 도전과 해결 (Technical Challenges)
> 대표 3건만 요약 — 전체 6건(검사 지연·게이트 타이밍·로봇 지연 스파이크 포함)은 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) 참고.

### Q1. 한 프레임만으로 판정하니 오검출이 잦았다
> **Challenge:** 흐르는 컨베이어 위 부품을 한 장의 프레임으로만 판정하면 그 순간의 각도·빛 반사·블러로 인해 오검출이 발생했습니다.
> **Solution:** 부품이 카메라 구간을 지나는 1초 동안 10프레임을 추론해 다수결로 판정하도록 변경했습니다. 불량은 단발성 오검출을 무시하기 위해 최소 프레임 수(`defect_min_frames`, 기본 3) 이상에서 잡혔을 때만 확정하고, 1~2개만 불량인 경우는 각도/노이즈 오검출로 보고 무시했습니다. 여러 관찰을 평균해 노이즈에 강건한 판정을 얻었습니다.

### Q2. 로봇이 트레이를 옮기다 부품을 쏟았다
> **Challenge:** 집기·놓기 두 점만 주고 이동시키면 경로 중간에 트레이가 기울어 부품이 쏟아졌습니다. 또 TCP가 미세 설정점을 모았다 일괄 방출해 "멈췄다 훅" 튀는 떨림이 생겼습니다.
> **Solution:** 경유점을 직접 티칭해 경로 전체를 재생하도록 하고(자세 유지), 점 사이를 0.05초 단위 미세 설정점으로 보간 스트리밍해 등속으로 움직이게 했습니다. 떨림의 원인이던 Nagle 알고리즘은 `TCP_NODELAY`로 비활성화했고, 트레이를 쥔 구간은 속도를 낮추는 2단 속도로 쏟김을 막았습니다.

### Q3. 로봇 비상정지를 어떻게 안전하게 구현할 것인가
> **Challenge:** 일반적인 비상정지는 전원을 끊지만, myCobot은 12V 전원을 차단하면 중력으로 팔이 무너지고 SD 카드가 손상될 위험이 있었습니다.
> **Solution:** 전원 차단 대신 소프트웨어 레벨 정지 경로를 설계했습니다. 비전 시스템이 이상을 감지하면 중앙 서버가 소프트웨어 E-stop을 발동하고, 비상정지를 프로그램 종료가 아닌 "일시정지"로 처리해 진행 중이던 레시피·트레이 상태를 유지한 채 재개할 수 있게 했습니다.

## 📚 문서
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 코드맵 · 데이터 흐름 · 시스템 불변식 · 채널 분리
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 기술적 도전과 해결 전체 6건
- [docs/adr/](docs/adr/) — 아키텍처 결정 기록(ADR) 5건
- 그 외 설계 문서: [docs/](docs/) (SYSTEM_OVERVIEW · API_SPEC · DB_SCHEMA · MESSAGE_SPEC · MQTT_Schema · VISION_INTEGRATION)

## 📸 프로젝트 흐름 및 이미지 기록
> 전체 구성 → 운영 화면 → 검사 샘플 → 컨베이어 입력 순서로 보면, 이 프로젝트가 단순 검출 데모가 아니라 비전·로봇·AGV·통신을 하나의 상태 흐름으로 묶은 자동 분류 시스템임을 빠르게 확인할 수 있습니다.

### System / Operation

| 화면 | 설명 |
|------|------|
| ![전체 공정 플로우차트](images/01.png) | 전체 공정 플로우차트 — 초기화·MQTT 연결부터 IR 센서 감지, 상부 YOLO 검사, 측면 OpenCV 핀 검사, 불량 Gate 분류, 트레이 적재, 로봇 AGV 상차, AGV 운반·충전 스테이션 복귀, EMERGENCY_STOP 분기까지의 상태 흐름 |
| ![시스템 구성도](images/02_system-overview.png) | 시스템 구성도 — 중앙 서버를 기준으로 myCobot, AGV, 카메라, 임베디드 노드, 관제 UI가 어떤 방향으로 연결되는지 정리한 전체 구조 |
| ![운영 대시보드](images/03_operator-dashboard.png) | 운영 대시보드 — 실시간 카메라 피드, 검사 통계, AGV 맵, 작업 로그, AGV/로봇 제어를 한 화면에 배치해 설비 상태를 관제하도록 구성 |
| ![프로젝트 발표 개요](images/04_project-overview-slide.png) | 발표용 전체 시스템 이미지 — 카메라 검사, 제품 분류, 트레이 적재, 로봇 이재, AGV 운반까지의 물리 흐름을 한 장으로 설명 |

### Vision Evidence

| 샘플 | 설명 |
|------|------|
| ![IC pin bent samples](images/05_ic-pinbent-samples.jpg) | IC Pinbent 샘플 — 측면 핀 휨/위치 이상을 검출해야 하는 대표 난이도 케이스 |
| ![CAP normal samples](images/06_cap-normal-samples.jpg) | CAP Normal 샘플 — 정상 부품을 안정적으로 통과시키기 위한 기준 클래스 |
| ![IC flipped samples](images/07_ic-flipped-samples.jpg) | IC Flipped 샘플 — 부품 방향 불량을 분류해 Gate 분기와 트레이 적재 결과로 연결 |
| ![Conveyor frame](images/08_conveyor-frame.jpg) | 컨베이어 입력 프레임 — 검사 전 원본 프레임으로, 조명·각도·벨트 위치 변화가 있는 실제 입력 조건 |

## 🎬 시연 영상
[![시연 영상](https://img.youtube.com/vi/rDrZn_7qteQ/0.jpg)](https://youtu.be/rDrZn_7qteQ)

## 📄 라이선스 · 공개 범위
5인 팀 프로젝트 산출물을 포트폴리오 목적으로 공개한 저장소입니다. 모델 가중치(`models/best.pt`)는 팀원이 학습한 산출물입니다. 별도 라이선스는 부여하지 않았습니다 — 코드 참고는 자유이며, 재사용·재배포는 문의해 주세요.
