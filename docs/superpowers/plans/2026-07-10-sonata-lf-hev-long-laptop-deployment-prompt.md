# Sonata LF Hybrid Laptop Deployment Prompt

`/Users/mark.yeon/Documents/work/oss/sunny_opendbc`에서 Sonata LF Hybrid 개인 fork 작업을 이어서 진행해줘.

먼저 다음을 수행해:

1. 현재 worktree와 remote를 확인하고 사용자 변경을 보존해.
2. 개인 저장소 `ku524/opendbc`의 `sonata-lf-hev-long-sp`를 fetch/checkout해.
3. 기대 HEAD는 이 문서를 포함한 현재 remote branch HEAD다. checkout 후 `git status --short --branch`와 `git log -1`로 기록해.
4. `AGENTS.md`를 가장 먼저 읽고 반드시 준수해.
5. 다음 문서를 읽어:
   - `.claude/handoff.md`
   - `docs/superpowers/plans/PORT-STATUS.md`
   - `docs/superpowers/plans/2026-07-10-sonata-lf-hev-long-sunnypilot-port.md`
6. 개인 draft PR은 `https://github.com/ku524/opendbc/pull/1`이다.
7. 업스트림 sunnypilot/commaai PR은 만들거나 수정하지 마.

목표는 Task 7의 실제 기기 배포 및 차량 검증이다. 업스트림 merge 품질을 위한 추가 test hardening, 범용 refactor, 리뷰 문서 갱신은 하지 마. 실제 차량 runtime, panda safety, 배포에 직접 필요한 작업만 수행해.

## A. 배포 전 기록

- comma 기기에 SSH 가능한지 확인해.
- 현재 openpilot/sunnypilot branch와 commit을 기록해.
- `opendbc_repo`의 현재 branch/commit과 dirty 상태를 기록해.
- `openpilot/opendbc` symlink가 어디를 가리키는지 확인해.
- 현재 panda firmware hash와 관련 pandad 로그를 기록해.
- 현재 상태로 되돌릴 정확한 rollback 절차를 먼저 작성해.
- 사용자 변경이나 dirty worktree를 덮어쓰지 마.

## B. steerRatio 데이터

- 현재 기본값은 `15.2605`다.
- comma opendbc PR #2926의 `16.445`는 검증된 learner 값이 아니다.
- 가능하면 alpha longitudinal을 켜기 전에 기존 안전한 설정으로 30~60분 full rlog를 수집하도록 안내해.
- 법정 속도 내 40~100 km/h 분포와 완만한 좌우 곡선이 포함되어야 한다.
- `carParams`, `liveParameters`, `livePose`, `liveCalibration`, `carState`, `can` 존재를 확인해.
- route가 제공되면 steerRatio 시간별 수렴, 마지막 10~20분 median, 분산, `steerRatioStd`, `stiffnessFactor`, angle offset을 분석해.
- 충분한 근거가 없으면 `CarSpecs.steerRatio`를 바꾸지 마.

## C. 기기 배포

- 기기의 `opendbc_repo`에 개인 branch를 fetch하고 정확한 commit을 checkout해.
- 이 기기와 sunnypilot revision의 실제 build 경로를 소스에서 확인해. build/flash 명령을 추측하지 마.
- panda safety C 변경이 실제 panda firmware binary에 포함되는지 확인해.
- build 결과와 firmware hash를 기록해.

## D. 수동 승인 Gate

다음 작업 직전에는 멈추고 사용자에게 상태와 rollback 절차를 보고해:

1. 기기 reboot
2. panda firmware flash/auto-reflash
3. Alpha Longitudinal 활성화
4. 실제 차량 actuation 시험

## E. 정차 상태 검증

- 새 panda firmware hash가 적용됐는지 확인해.
- 정확한 차량 fingerprint와 Hyundai safetyParam을 확인해.
- `canValid=True`, `canTimeout=False`를 확인해.
- radar ECU `0x7D0` disable 응답을 확인해.
- stock SCC 송신 중단과 dual-SCC 부재를 확인해.
- brake disengage와 gas override를 정차 상태에서 검증해.
- ECU fault, CAN fault, 의도하지 않은 actuation 여부를 확인해.

다음 중 하나라도 발생하면 즉시 중단하고 rollback해:

- panda firmware hash 불일치
- 잘못된 fingerprint 또는 safetyParam
- CAN invalid/timeout
- radar disable 실패
- stock SCC 지속 또는 dual-SCC
- brake/gas override 오동작
- 의도하지 않은 가속·제동
- EPS/LKAS/HUD fault
- ignition cycle 후 stock radar/ACC 복구 실패

실제 주행은 에이전트가 수행하지 않는다. 사용자가 운전하고, 에이전트는 단계별 체크리스트와 로그 분석만 제공해. 첫 시험은 폐쇄된 안전 공간, 최저 속도, 브레이크 즉시 조작 자세로 제한해. openpilot longitudinal 중 factory AEB가 비활성일 수 있음을 매 gate에서 명시해.

각 단계마다 실행 명령, 관측 결과, 확인된 사실, 미확인 항목, 다음 수동 승인 gate를 짧게 보고해. 작업을 source 수정이나 추가 테스트로 전환하기 전에 그것이 이 차량의 실제 blocker인지 먼저 입증해.

## F. Live diagnostics 금지

- 실차 runtime 검증 중 임시 Python `SubMaster`/`SubSocket`, 반복 실행하는 live monitor, health monitor를 만들지 마.
- comma msgq는 service당 reader slot이 15개다. subscriber 생성은 slot count를 증가시키지만 subscriber 종료는 mmap만 닫고 count를 감소시키지 않는다. 16번째 subscriber는 해당 service의 모든 subscriber를 reset/evict한다.
- 짧은 monitor라도 반복 재실행하면 `selfdrived`, `radard` 등 정상 process의 구독을 끊어 `communication issue between processes`, service invalid, process 재연결을 유발할 수 있다. 이것은 관측 노이즈가 아니라 관측자가 시스템을 망가뜨리는 measurement contamination이다.
- 실시간 검증은 기존 process log, Params 직접 읽기, panda 상태, 저장된 qlog/rlog를 우선한다. CAN·controls·service-validity 분석은 route 종료 후 qlog/rlog로 수행한다.
- live subscriber가 꼭 필요하면 사용자 승인 후 하나의 장기 실행 process만 사용하고 재실행하지 마. 구독 service, PID, 시작·종료 시각을 기록해. 그 세션은 최종 safety/validity 증거로 사용하지 마.
- 임시 subscriber를 한 번이라도 반복 실행했거나 eviction이 의심되면 monitor를 모두 종료하고 full vehicle OFF/ON 후 새 route에서 다시 검증해. 오염된 세션에서 production source를 수정하거나 root cause를 판정하지 마.
- 2026-07-11 실패 기록과 소스 근거는 `2026-07-11-sonata-lf-hev-long-device-handoff.md`의 `Diagnostic Monitoring Hazard`를 먼저 읽어.
