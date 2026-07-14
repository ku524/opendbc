# Sonata LF Hybrid Follow-Up Laptop Deployment Prompt

이 문서는 최초 Alpha Longitudinal 배포가 아니라, 2026-07-11 실차 주행과 route 분석 뒤 만들어진 후속 수정본을 다시 배포하고 검증하기 위한 실행 프롬프트다.

다른 랩탑의 Codex/Claude 세션에 아래 지시 전체를 제공해.

---

`ku524/opendbc`의 Sonata LF Hybrid 후속 수정본을 기존 comma 3X에 재배포하고 단계별 차량 검증을 진행해줘.

## 1. 시작 조건

1. 저장소의 `AGENTS.md`를 가장 먼저 읽고 반드시 준수해.
2. 사용자 변경과 dirty worktree를 보존해. 읽지 않은 파일은 수정하지 마.
3. 개인 fork `ku524/opendbc`에서 remote branch `sonata-lf-hev-long-sp`를 fetch해.
4. remote branch의 현재 HEAD를 기록하고 detached checkout 또는 별도 worktree로 작업해.
5. `bc54535e`가 checkout한 HEAD의 ancestor인지 확인해. 아니면 배포하지 말고 보고해.
6. 개인 draft PR은 `https://github.com/ku524/opendbc/pull/1`이다. 업스트림 commaai 또는 sunnypilot PR은 만들거나 수정하지 마.

필수 확인 명령:

```bash
git fetch origin sonata-lf-hev-long-sp
git switch --detach origin/sonata-lf-hev-long-sp
git status --short --branch
git log -1 --oneline
git merge-base --is-ancestor bc54535e HEAD
```

## 2. 먼저 읽을 문서

- `.claude/handoff.md`
- `docs/superpowers/plans/PORT-STATUS.md`
- `docs/superpowers/plans/2026-07-11-sonata-lf-hev-long-device-handoff.md`
- `docs/superpowers/plans/2026-07-11-sonata-lf-hev-on-car-validation-checklist.md`
- `docs/superpowers/plans/2026-07-10-sonata-lf-hev-longitudinal.md`

실차 순서, 중단 조건, 수집할 증거와 rollback은 on-car validation checklist를 source of truth로 사용해.

## 3. 이번 후속 수정의 배경

최초 배포와 주행은 성공했다.

- 의도하지 않은 가속·제동 없음
- comma와 차량 fault/warning 없음
- 정차 유지와 재출발 성공
- brake/gas override 즉시 동작
- stock SCC 송신 중단, openpilot SCC11/SCC12 약 50 Hz, dual SCC 없음
- panda RX invalid/fault와 CAN invalid/timeout 없음

하지만 출발 가속과 최종 정차 감속이 너무 강해 승차감 기준은 실패했다.

백업된 Alpha Long route `000000e4--5ae02c8c77`의 full-rlog 분석 결과:

- 11회 lead-following 출발에서 planner target median은 `0.444 m/s²`였지만 `LongControl`은 모두 고정 `1.0 m/s²`를 요청했다.
- 9회 lead-following 정차에서 planner target median은 `-0.036 m/s²`였지만 요청값 median은 `-1.753 m/s²`, 약 `-2.0 m/s²`까지 도달했다.
- Hyundai controller는 이 요청을 증폭하지 않았고 panda/CAN은 정상 상태였다.

따라서 planner-only 문제가 아니라 generic `LongControl`의 고정 start/stop 경로가 주된 trigger로 확인됐다.

## 4. 이번에 배포할 후속 변경

- `681f9aaa`: 배포 당시 검증된 LKAS HUD field 처리 복원
- `9c3031f0`: Sonata LF Hybrid에만 `startingState=False`, `stoppingDecelRate=0.45` 적용
- `bc54535e`: `MANDO_RADAR` 활성화, static `steerRatio=16.4` 적용

`stopAccel=-2.0`, panda safety 정책, CAN message format, pedal override 정책은 변경하지 않았다.

Radar 근거는 반드시 route별로 구분해.

- 백업 Alpha Long route는 `openpilotLongitudinalControl=true`이며, SCC ECU normal communication disable 뒤에도 bus 1 `0x500-0x51f` 32개 track address가 약 20 Hz로 유지됐다.
- 이 route의 31개 rlog replay에서 RadarInterface는 37,167개 output과 637,807개 finite point를 만들었고 모든 segment parser가 valid로 끝났다.
- 사용자가 URL로 제공한 116분 highway route는 `openpilotLongitudinalControl=false`다. 이 route는 Mando 활성화 증거가 아니라 `steerRatio=16.4` 근거다.
- highway route의 qualified steerRatio median은 `16.402`, 좌/우 `16.405/16.372`, 마지막 20분 `16.404`다.

Offline parser 검증은 physical lead selection, adjacent-lane rejection, cut-in, stopped-object, phantom-braking 안전성을 증명하지 않는다. 이것들은 실차 gate다.

## 5. 현재 기기 상태를 추측하지 마

이 문서 작성 시 마지막으로 알려진 기기 상태는 다음과 같지만, 접속 후 반드시 다시 확인해.

- sunnypilot `staging@3781e253`, 파일 배포 때문에 intentionally dirty
- 활성 opendbc는 이전 device-tested revision `f62fb8fe` 기반
- Alpha Long은 최초 시험에서 활성화됨
- main sunnypilot의 실험용 poll-all `radard.py`가 활성 상태로 보존됨

새 후속 branch는 아직 차량에 배포되거나 실차 검증되지 않았다.

기기 변경 전에 현재 sunnypilot/opendbc revision, symlink, dirty state, panda firmware hash, Params, `radard.py` hash와 rollback archive를 기록해. 백업이 없거나 읽히지 않으면 중단해.

## 6. 배포 격리 조건

이번 검증은 opendbc PR-only 동작을 확인해야 한다.

1. 검증된 백업에서 original `radard.py`를 복구해.
2. full vehicle OFF/ON cycle을 수행해. ignition이 켜진 상태의 comma-only reboot로 대체하지 마.
3. checkout한 current remote branch를 실제 sunnypilot source에서 확인한 build/deployment 경로로 배포해. 명령을 추측하지 마.
4. panda firmware가 rebuild 또는 auto-reflash되면 변경 전후 hash와 `pandad` 결과를 기록해.
5. reboot, firmware flash/auto-reflash, Alpha Long 활성화, 실제 actuation 직전에는 각각 멈추고 사용자 승인을 받아.

## 7. sunnypilot 설정 비교

설정은 offroad에서 `Hyundai/Kia/Genesis -> Custom Longitudinal Tuning`으로 선택해.

- `Off=0`: Hyundai custom jerk controller 비활성. stock SCC가 아니라 기본 sunnypilot longitudinal이다.
- `Dynamic=1`: 속도 기반 jerk 제한과 jerk-limited acceleration을 사용한다.
- `Predictive=2`: 목표 가속과 직전 출력 차이의 lookahead jerk를 사용한다. 신호등이나 브레이크등을 예측하는 기능이 아니다.

첫 검증은 다른 longitudinal modifier를 끄고 다음 순서로 진행해.

1. original `radard.py` + current PR source + tuning `Off`
2. 동일 source와 유사 조건 + tuning `Dynamic`

두 route 사이에 source, `radard.py`, Driving Personality, Experimental Mode, map/vision/speed-limit modifier를 바꾸지 마. 각 route 시작 전에 실제 Params와 UI 설정을 기록해. `Predictive`는 Dynamic 결과가 안전하지만 반응이 지나치게 느릴 때 별도 승인 후 시험해.

## 8. 정차 상태 gate

저장된 Params, 기존 process log와 route 종료 후 rlog로 다음을 확인해.

- fingerprint `HYUNDAI_SONATA_LF_HYBRID`
- `openpilotLongitudinalControl=true`, `pcmCruise=false`, `radarUnavailable=false`
- Hyundai safetyParam에 LONG, HYBRID, ALT_STANDSTILL 유지
- `steerRatio=16.4`, `MANDO_RADAR` 적용
- CAN valid, timeout 없음, panda RX invalid/fault 없음
- radar ECU `0x7D0` normal communication disable 성공
- stock SCC source 0 중단, openpilot SCC11/SCC12 약 50 Hz, tester-present 약 1 Hz, dual SCC 없음
- bus 1 Mando `0x500-0x51f` track 유지
- EPS/LKAS/HUD/cruise/radar/communication warning 없음

빈 route, CarParams 누락, fingerprint/safetyParam 불일치, radar unavailable, CAN invalid/timeout, stock SCC 지속, dual SCC, radar disable 실패, warning 중 하나라도 있으면 actuation하지 말고 rollback해.

## 9. 실차 검증

운전은 사용자가 수행한다. 첫 시험은 폐쇄되거나 위험이 낮은 공간, 최저 속도, 즉시 브레이크 가능한 상태로 제한해. Alpha Long 중 factory AEB가 비활성일 수 있음을 매 gate에서 명시해.

순서:

1. 저속 engage/cancel/brake disengage/gas override
2. 여러 번의 lead-following 정차, hold, resume
3. 출발 force, 저속 surge, final-stop jerk, following-distance 안정성
4. same-lane lead, adjacent-lane 차량, curve, cut-in/out, stopped traffic, roadside object
5. 합법 속도 내 좌우 완만한 곡선에서 `steerRatio=16.4` 대칭성, oscillation, saturation

의도하지 않은 가속·제동, override 지연, phantom braking, 명백한 lead 미검출, 지속적인 옆 차선 lead 선택, 불안정한 lead switching, steering oscillation 또는 fault가 발생하면 즉시 중단하고 rollback해.

## 10. 진단 오염 금지

- 임시 Python `SubMaster`/`SubSocket`, 반복 live monitor를 만들거나 재실행하지 마.
- msgq service당 reader slot은 15개이며 종료된 subscriber가 slot count를 되돌리지 않아 반복 실행이 production subscriber를 evict할 수 있다.
- 기존 process log, Params 직접 읽기, panda 상태, route 종료 후 qlog/rlog 분석을 우선해.
- 외부 subscriber 반복 실행이나 eviction이 의심되면 해당 route를 증거로 쓰지 마. monitor를 종료하고 full vehicle OFF/ON 후 새 route를 수집해.

## 11. 결과물

각 route마다 다음을 보존해.

- source commit, panda firmware hash, original `radard.py` hash
- 모든 longitudinal/UI 설정
- route ID, segment, 시간, 도로·교통 조건
- engage, override, standstill, resume, harsh launch/stop, cut-in, false lead, steering anomaly timestamp
- 완전한 rlog
- warning screenshot과 timestamp

새 route가 확보되기 전에는 추가 승차감 상수, radar polling, lateral torque limit을 수정하지 마. 먼저 기존 candidate를 검증하고, 결과 route를 원래 분석 세션으로 가져와 Off/Dynamic 가속·jerk, radar lead selection과 steering 결과를 비교해.

각 단계에서 실행 명령, 관측값, 확인된 사실, 미확인 항목, 다음 수동 승인 gate를 짧게 보고해.

---
