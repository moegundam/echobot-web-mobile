# Open-LLM-VTuber Reference Gap - 2026-04-29

## 中文版

### 決策

`Open-LLM-VTuber/Open-LLM-VTuber` 只作能力參考，不搬整套 backend。EchoBot 繼續作為主架構，差距用增量方式補齊。

### 差距矩陣

| 能力 | EchoBot 目前狀態 | 第一階段處理 | 下一步 |
|---|---|---|---|
| Live2D 內建模型載入 | 已有 hiyori / mao 內建模型 | 保留 | 真機檢查 lip sync 與 rendering |
| Live2D 上傳模型 | 已有資料夾上傳與 asset route | 保留 | 補大型模型/錯誤檔案 smoke |
| 表情 / 動作 / 熱鍵 | 已有 drawer 與 motion playback | 保留 | 後續評估情緒到表情映射 |
| Lip sync | 已有 TTS 播放時的基本 mouth 參數驅動 | 第一階段接受 | 真機播放驗證 |
| ASR provider | 已有 Sherpa SenseVoice / OpenAI Transcriptions provider 架構 | 保留，並完成 trusted user 隔離 | 補模型下載與 HTTPS WebSocket 實測 |
| VAD / 常開麥 | 已有 Silero VAD 與常開麥控制 | 保留 | 真機 Android 常開麥驗收 |
| TTS provider | 已有 Edge / Kokoro / OpenAI-compatible TTS | 保留 | 補 Kokoro 模型或改外部 TTS 預設 |
| TTS/ASR 協調 | 已做到 TTS 播放時暫停 ASR、播放後恢復，且停止語音會中斷 pending TTS request | 第一階段接受 | 真機驗證播放中斷與常開麥恢復 |
| 停止語音 | 只停止 TTS，不取消背景 Agent job | 符合需求 | 保留行為並補 UI 文案測試 |
| 桌寵 / VTube Studio 類體驗 | 未納入 | 第一階段不做 | 第二階段再評估 |
| 多使用者隔離 | 已隔離 session/job/history/attachments；本輪補上 ASR/TTS service instance 隔離 | 必做 | 10 人內測壓測 |

### 第一階段不做

- 不合併 Open-LLM-VTuber backend。
- 不做桌寵模式。
- 不做公開 SaaS 帳號系統；先用 Cloudflare Access trusted header。

## English version

### Decision

`Open-LLM-VTuber/Open-LLM-VTuber` is reference-only. Its backend will not be merged. EchoBot remains the main architecture, and gaps are closed incrementally.

### Gap Matrix

| Capability | Current EchoBot Status | Phase 1 Handling | Next Step |
|---|---|---|---|
| Built-in Live2D models | Built-in hiyori / mao models exist | Keep | Verify lip sync and rendering on real devices |
| Live2D uploaded models | Folder upload and asset routes exist | Keep | Add smoke coverage for large/bad model files |
| Expressions / motions / hotkeys | Drawer and motion playback exist | Keep | Later evaluate emotion-to-expression mapping |
| Lip sync | Basic mouth parameter driving during TTS playback exists | Accepted for phase 1 | Verify with real playback |
| ASR provider | Sherpa SenseVoice / OpenAI Transcriptions provider structure exists | Keep, with trusted-user isolation completed | Add model download and HTTPS WebSocket checks |
| VAD / always listening | Silero VAD and always-listen controls exist | Keep | Validate always-listen on Android Chrome |
| TTS provider | Edge / Kokoro / OpenAI-compatible TTS exist | Keep | Add Kokoro model or choose external TTS as default |
| TTS/ASR coordination | ASR pauses during TTS, resumes after playback, and stop speech aborts pending TTS requests | Accepted for phase 1 | Verify playback interruption and open-mic resume on real devices |
| Stop speech | Stops only TTS, not background Agent jobs | Matches requirement | Keep behavior and add UI copy tests |
| Desktop pet / VTube Studio-like mode | Not included | Out of scope for phase 1 | Re-evaluate in phase 2 |
| Multi-user isolation | Sessions/jobs/history/attachments are isolated; this round adds ASR/TTS service instance isolation | Required | Run 10-person test load |

### Out Of Scope For Phase 1

- Do not merge the Open-LLM-VTuber backend.
- Do not build desktop pet mode.
- Do not build a public SaaS account system; use Cloudflare Access trusted headers first.
