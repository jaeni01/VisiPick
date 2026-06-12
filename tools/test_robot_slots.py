#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VisiPick — AGV 3슬롯 이재 단독 테스트 (FSM 없이 robot.py 직접 구동)
==========================================================================
트레이 1→2→3 을 각각 robot_path_1/2/3.json 경로로 이재한다.
각 슬롯 사이에 집기 위치에 새 트레이를 놓고 Enter (실운영에선 컨3가 공급).

사전 준비:
  1. Pi: 교시 도구(robot_teach.py) 종료(q) — /dev/ttyAMA0 점유 해제
  2. Pi: 공식 소켓 서버(9000) 실행:  python3 ~/pymycobot/demo/Server_280.py
     (없으면: find ~ -name "Server*.py" 2>/dev/null 로 위치 확인)
  3. PC: config/robot_path_1.json, _2.json, _3.json 배치(scp) 확인
  4. PC: config.robot.dummy_mode = false
  5. PC: pip install pymycobot loguru

실행 (반드시 C:\\VisiPick 루트에서):
  python -m tools.test_robot_slots
"""
from src.devices.robot import Robot, DUMMY_MODE, _load_path, _path_file


def main():
    if DUMMY_MODE:
        print("[!] config.robot.dummy_mode 가 true — 실로봇 테스트가 아닙니다.")
        print("    config/config.json 에서 false 로 바꾼 뒤 다시 실행하세요.")
        return

    # 슬롯 경로 파일 사전 점검 (없으면 단일 경로 폴백이라 미리 알려줌)
    for s in (1, 2, 3):
        p = _load_path(s)
        n = len(p["waypoints"]) if p else 0
        print(f"  슬롯 {s}: {_path_file(s).name} — "
              + (f"{n}점 OK" if p else "없음/무효 (단일 robot_path.json 으로 폴백됨)"))

    r = Robot()
    results = {}
    try:
        for slot in (1, 2, 3):
            input(f"\n[슬롯 {slot}] 집기 위치에 트레이 놓고 Enter (중단: Ctrl+C) > ")
            ok = r.transfer_tray(slot=slot)
            results[slot] = ok
            print(f"  → 슬롯 {slot}: {'✅ 성공' if ok else '❌ 실패 (로그 확인)'}")
    except KeyboardInterrupt:
        print("\n중단됨")
    print("\n결과:", {s: ("OK" if v else "FAIL") for s, v in results.items()})


if __name__ == "__main__":
    main()
