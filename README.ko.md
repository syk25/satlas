# Satlas

> [English](README.md) · 🌐 **한국어**

**지금 우리나라 위로 어떤 위성이 지나가고 있을까 — 실시간으로 확인하세요.**

🛰️ 사이트: **[satlas.space](https://satlas.space)**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Live](https://img.shields.io/badge/live-satlas.space-7e14ff.svg)](https://satlas.space)
[![ADRs](https://img.shields.io/badge/architecture%20decisions-25-green.svg)](docs/adr/README.md)

<p align="center">
  <a href="https://youtu.be/F69mwx--Ojc">
    <img src="https://img.youtube.com/vi/F69mwx--Ojc/maxresdefault.jpg" alt="Satlas 데모 — YouTube에서 보기" width="640" />
  </a>
  <br>
  <em>▶ YouTube에서 데모 영상 보기</em>
</p>

---

## 왜 Satlas인가

기존 위성 추적 서비스는 두 가지 질문 중 하나에 답합니다.

| 관점 | 대표 도구 | 답하는 질문 |
|---|---|---|
| 관측자 기준 | Heavens-Above, Stellarium | "내 위치에서 이 위성을 볼 수 있나?" |
| 소유 기준 | UCS Satellite Database | "이 위성은 어느 나라가 만들었나?" |

Satlas는 세 번째 관점을 다룹니다 — **국가 기준**:
*"어떤 위성이 이 나라 위를 지나가는가, 언제 지나가는가?"*

이전에는 이 질문에 답하려면 각 위성의 궤도를 일일이 확인하거나 좌표 기반 도구를 국가 경계에 직접 맞춰야 했습니다. Satlas는 이를 국가 한 번 클릭으로 줄입니다.

이 프로젝트는 공군 복무 중 봤던 항공기 감시 지도에서 영감을 받았습니다. 국가 주변에 떠 있는 항공기들을 실시간으로 보여주는 화면이 인상적이었습니다. *지금 우리 영공에는 뭐가 떠 있을까* 라는 시각이 계속 마음에 남았습니다. 시간이 한참 지나, 밤에 산책하다가 머리 위에서 반짝이는 점들을 봤는데, 대부분 위성이었습니다. 인터넷에 찾아보니 3D 지구본에 위성을 띄운 사이트나 위성 하나하나의 궤도를 보여주는 도구는 있었지만, *지금 우리나라 위에 어떤 위성이 있는지* 알려주는 곳은 없었습니다. 위성 발사가 빠르게 늘고 있는 시기였고, 이 빈자리를 직접 채워보고 싶어 만들게 됐습니다.

---

## 기능

- 🗺️ **지도에서 국가 클릭** → 그 나라 위를 지금 지나가는 위성 전체 표시
- 🏷️ **카테고리 필터** — Starlink, GPS, 기상, 과학, 군용 등
- 📅 **앞으로 24시간 통과 일정** — 1시간 / 6시간 / 24시간 구간별 그룹
- 🛰️ **위성 추적** — 실시간 풋프린트와 95분 지상 궤적을 지도 위에 표시
- 📊 **전체 대시보드** — 활성 위성 총수, 카테고리별 분포, 오늘 가장 자주 통과한 국가, 최근 발사

---

## 스크린샷

<p align="center">
  <img src="https://github.com/user-attachments/assets/3b79930d-ff64-42f8-b4c4-f1b883ffad21" alt="국가 선택 시 상공 위성 표시" width="800" /><br>
  <em>국가를 클릭하면 그 나라 위를 지금 지나가는 위성 전체와 24시간 통과 일정이 표시됩니다.</em>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/35eb2f74-239d-4e34-9a8c-5b1c3c401165" alt="전체 대시보드" width="800" /><br>
  <em>대시보드 — 활성 카탈로그, 카테고리 분포, 오늘 가장 자주 통과한 국가, 최근 발사.</em>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/a367eafa-4f1c-4859-a2e6-290439e61c8b" alt="위성 추적 모드" width="800" /><br>
  <em>위성 추적 — 실시간 위치, 풋프린트, 95분 지상 궤적.</em>
</p>

---

## 기술 스택

| 계층 | 사용 기술 |
|---|---|
| 백엔드 | Python 3.11 · FastAPI · PostgreSQL · Redis · Celery · APScheduler · SGP4 |
| 프론트엔드 | React · Vite · TypeScript · Leaflet · satellite.js |
| 인프라 | Docker Compose · Fly.io · Vercel · Vercel Edge Middleware · GitHub Actions |
| 데이터 | CelesTrak (TLE + SATCAT) · Natural Earth (국가 경계 폴리곤) |

---

## 아키텍처 결정 기록 (ADR)

중요한 기술 결정은 모두 ADR로 남깁니다 — 무엇을 결정했는지, 어떤 대안이 있었고 왜 기각됐는지, 어떤 트레이드오프를 받아들였는지. 전체 목록: **[docs/adr/](docs/adr/README.md)** (25개).

대표 ADR:

- **[ADR-005](docs/adr/ADR-005-data-storage-strategy.md)** — TLE 저장 전략: 하루 두 번 스냅샷 + 단계별 사전계산
- **[ADR-014](docs/adr/ADR-014-deployment-platform.md)** — 배포 플랫폼: Fly.io (백엔드) + Vercel (프론트엔드)
- **[ADR-018](docs/adr/ADR-018-overhead-membership-refresh.md)** — Overhead 갱신: 서버 사이드 윈도우 예측 + 클라이언트 사이드 gating
- **[ADR-024](docs/adr/ADR-024-chunked-visits-recompute.md)** — 청크 단위 recompute + Redis list 스키마 (15k 위성 넘어가면 OOM 절벽 해결)
- **[ADR-025](docs/adr/ADR-025-ip-geo-i18n-and-dynamic-og.md)** — IP 기반 언어 선택 + 국가별 OG 이미지 변형

---

## 데이터 소스

| 소스 | 용도 | 라이선스 |
|---|---|---|
| [CelesTrak](https://celestrak.org) | TLE 궤도 요소 + SATCAT 메타데이터 (운영국, 발사일, 객체 타입). GP JSON 형식으로 하루 두 번 수집 | 공개 무료, API 키 불필요 |
| [Natural Earth](https://www.naturalearthdata.com) | 위성-국가 교차 판정에 쓰는 국가 경계 폴리곤 | Public Domain |

Space-Track.org (US Space Force)는 보조적인 과거 TLE 소스로 검토 중이며 향후 단계에 추가될 가능성이 있습니다. 가입은 무료이나 등록이 필요합니다.

---

## 최근 마일스톤

- 🌐 **자체 도메인** (satlas.space) + 국가별 OG 이미지 미리보기 + 첫 방문 IP geo 언어 선택 — ADR-025
- 🔍 **SEO 기반 작업** — robots.txt, sitemap.xml, JSON-LD WebApplication 스키마, Google Search Console 등록
- 📋 **`/about` 페이지** — 친근한 소개, 데이터 소스, 한계, 개인정보 처리 안내
- 📊 **대시보드** — 전체 카탈로그, 카테고리 분포, 가장 자주 통과한 국가, 최근 발사
- 📅 **24시간 통과 일정 UI** — 1시간 / 6시간 / 24시간 그룹, 패널 탭 전환
- 💧 **청크 단위 recompute + Redis list 스키마** — 카탈로그 크기와 무관하게 메모리 상한 보장 — ADR-024
- 🚀 **공개 출시** — Fly.io + Vercel + GitHub Actions push 모델

---

## 대상 사용자

- 지금 머리 위로 무엇이 지나가는지 궁금한 우주·위성 관심자
- 궤도 역학, 위성 운용, 우주 상황 인식(SSA)을 공부하는 학생
- 특정 국가 상공 통과 패턴을 분석하려는 연구자

---

## 기여하기

기여 가이드는 향후 `CONTRIBUTING.md`에 정리됩니다.
버그 제보와 기능 제안은 [Issues](https://github.com/syk25/satlas/issues)로 환영합니다.

---

## 라이선스

[MIT](LICENSE)
