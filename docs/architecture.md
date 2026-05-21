# VoiceTutor — Architecture

GitHub renders the Mermaid block below natively. For the raw source (also editable in `mermaid.live` or `mmdc`), see [`architecture.mmd`](./architecture.mmd).

## High-level system

```mermaid
flowchart TB
  %% ── Client ─────────────────────────────────────────────────
  subgraph CLIENT["Browser Client · Next.js 14"]
    direction TB
    UI["Voice Orb · Transcript · Progress Panel"]
    WSClient["WebSocket Client<br/>(Web Audio + AudioWorklet)"]
    UI --> WSClient
  end

  %% ── Server ─────────────────────────────────────────────────
  subgraph SERVER["FastAPI Server · Python 3.11+"]
    direction TB
    WSServer["WebSocket Endpoint /ws"]

    subgraph PIPE["Pipecat Pipeline"]
      direction LR
      VAD["Silero VAD"]
      STT["AssemblyAI<br/>Universal-Streaming"]
      Probe["Latency Probe"]
      LLM["Groq<br/>Llama 3.3 70B"]
      Tools["Intent Router<br/>+ 4 LLM tools"]
      TTS["ElevenLabs<br/>Turbo v2.5"]

      VAD --> STT --> Probe --> LLM
      LLM --> Tools
      Tools --> LLM
      LLM --> TTS
    end

    WSServer --> VAD
    TTS --> WSServer
  end

  %% ── Agent Core ─────────────────────────────────────────────
  subgraph AGENT["Agent Core"]
    direction TB
    FSM["Mode FSM<br/>Teach · Quiz · Convo · Doubt"]
    Prompts["System Prompts<br/>(per mode + persona)"]
    Grader["Two-tier Semantic Grader"]
    Pron["Pronunciation Feedback"]
    Curriculum["Curriculum<br/>6 Spanish lessons"]
  end

  %% ── Memory ─────────────────────────────────────────────────
  subgraph MEM["Memory"]
    direction TB
    Short["Short-term<br/>in-mem SessionMemory"]
    Long["Long-term<br/>SQLite + FSRS-lite"]
  end

  %% ── Observability ──────────────────────────────────────────
  subgraph OBS["Observability"]
    direction TB
    Logger["Per-turn JSONL<br/>logs/turn_latency.jsonl"]
    Metrics["Rolling P50/P95<br/>/metrics endpoint"]
  end

  %% ── Cross-subgraph edges (node-to-node for GitHub) ─────────
  WSClient <-->|"PCM16 audio · JSON events"| WSServer

  Tools <--> FSM
  Tools <--> Grader
  Tools <--> Pron
  Tools <--> Curriculum
  Tools <--> Short
  Tools <--> Long

  LLM --> Prompts
  Probe --> Logger
  Probe --> Metrics

  %% ── Styles ─────────────────────────────────────────────────
  classDef ext   fill:#0ea5e9,stroke:#0369a1,color:#fff;
  classDef ours  fill:#a78bfa,stroke:#6d28d9,color:#fff;
  classDef store fill:#10b981,stroke:#047857,color:#fff;
  classDef obs   fill:#f59e0b,stroke:#b45309,color:#fff;

  class VAD,STT,LLM,TTS ext;
  class FSM,Prompts,Grader,Pron,Curriculum,Tools,Probe ours;
  class Short,Long store;
  class Logger,Metrics obs;
```

## Turn lifecycle (sequence)

```mermaid
sequenceDiagram
  autonumber
  participant Mic as 🎙 Mic
  participant Client as Browser Client
  participant Srv as FastAPI/WS
  participant VAD as Silero VAD
  participant STT as AssemblyAI STT
  participant LLM as Groq LLM
  participant Tool as Tool Runner
  participant TTS as ElevenLabs TTS
  participant Mem as SQLite

  Mic->>Client: PCM 48kHz
  Client->>Client: AudioWorklet → PCM16 16kHz
  Client->>Srv: WS binary chunks (~40ms)
  Srv->>VAD: InputAudioRawFrame
  VAD-->>Srv: UserStartedSpeakingFrame
  Note over Srv: TurnLog start
  VAD->>STT: forward audio
  STT-->>LLM: TranscriptionFrame (final)
  Note over Srv: stt_final_ms
  LLM-->>Tool: function_call(start_lesson)
  Tool->>Mem: upsert progress, log mistake
  Tool-->>LLM: result
  LLM-->>TTS: TextFrame stream
  Note over Srv: llm_first_token_ms
  TTS-->>Srv: OutputAudioRawFrame
  Srv-->>Client: WS binary (24kHz PCM16)
  Client->>Mic: scheduled playback
  Note over Srv: tts_first_audio_ms · TurnLog.write()
```

## Barge-in flow

```mermaid
flowchart LR
  A["User speaks<br/>while bot is talking"] --> B["Silero VAD<br/>UserStartedSpeakingFrame"]
  B --> C["Pipecat<br/>StartInterruptionFrame"]
  C --> D["TTS cancel WS<br/>drop pending audio"]
  C --> E["Serializer emits<br/>{type:interrupt}"]
  E --> F["Client flushPlayback()<br/>rebuild GainNode"]
  F --> G["Silence<br/>≤ 250 ms"]

  classDef warn fill:#ef4444,stroke:#991b1b,color:#fff;
  classDef ok   fill:#10b981,stroke:#047857,color:#fff;
  class A warn;
  class G ok;
```

## Mode FSM

```mermaid
stateDiagram-v2
  [*] --> Idle

  Idle --> Teaching: "teach me X"
  Idle --> Quiz: "quiz me"
  Idle --> Conversation: "let's roleplay"

  Teaching --> Quiz: switch_mode
  Quiz --> Teaching: switch_mode
  Conversation --> Idle: end

  Teaching --> Doubt: enter_doubt_mode (push)
  Quiz --> Doubt: enter_doubt_mode (push)
  Conversation --> Doubt: enter_doubt_mode (push)

  Doubt --> Teaching: exit_doubt_mode (pop)
  Doubt --> Quiz: exit_doubt_mode (pop)
  Doubt --> Conversation: exit_doubt_mode (pop)

  Teaching --> Idle: end_session
  Quiz --> Idle: end_session
```

## Lesson sub-state machine (within Teaching mode)

```mermaid
stateDiagram-v2
  [*] --> Intro
  Intro --> Explain: user "ready" / "yes"
  Explain --> Example: user reply
  Example --> Practice: user reply
  Practice --> Check: user reply
  Check --> Done: user reply
  Done --> [*]: end / move to quiz

  Intro --> Doubt: enter_doubt
  Explain --> Doubt: enter_doubt
  Example --> Doubt: enter_doubt
  Practice --> Doubt: enter_doubt
  Check --> Doubt: enter_doubt
  Doubt --> Intro: exit_doubt (resume)
  Doubt --> Explain: exit_doubt
  Doubt --> Example: exit_doubt
  Doubt --> Practice: exit_doubt
  Doubt --> Check: exit_doubt
```

## Use cases (actor & system view)

```mermaid
flowchart LR
  Learner((Learner))
  Sofia[VoiceTutor / Sofía]

  Learner -- "Hola, teach me food" --> UC1["Start Lesson"]
  Learner -- "Quiz me on numbers" --> UC2["Take Quiz"]
  Learner -- "Why is it me llamo?" --> UC3["Ask Doubt"]
  Learner -- "Let's roleplay a café" --> UC4["Practice Conversation"]
  Learner -- speaks during bot speech --> UC5["Barge in"]
  Learner -- clicks trash icon --> UC6["Reset Progress"]
  Learner -- reconnects later --> UC7["Resume Session"]

  UC1 --> Sofia
  UC2 --> Sofia
  UC3 --> Sofia
  UC4 --> Sofia
  UC5 --> Sofia
  UC6 --> Sofia
  UC7 --> Sofia

  Sofia -. "speaks Spanish vocab" .-> Learner
  Sofia -. "shows transcript & progress" .-> Learner
  Sofia -. "stops mid-sentence" .-> Learner
  Sofia -. "remembers last session" .-> Learner

  classDef actor fill:#a78bfa,stroke:#6d28d9,color:#fff;
  classDef system fill:#0ea5e9,stroke:#0369a1,color:#fff;
  class Learner actor;
  class Sofia system;
```

## Data model (entity-relationship)

```mermaid
erDiagram
  USERS ||--o{ PROGRESS : "has many"
  USERS ||--o{ VOCAB_MASTERY : "has many"
  USERS ||--o{ MISTAKES : "has many"

  USERS {
    text id PK "demo-user-001"
    text name
    text native_lang "en"
    text target_lang "es"
    text created_at
    text last_seen_at
  }
  PROGRESS {
    int id PK
    text user_id FK
    text lesson_id "greetings-001"
    text status "in_progress|completed"
    real score "0.0-1.0"
    int attempts
    text completed_at
  }
  VOCAB_MASTERY {
    int id PK
    text user_id FK
    text word
    text lang
    real ease "1.3-2.5"
    real interval_days
    int reps
    int lapses
    text last_review_at
    text next_review_at
  }
  MISTAKES {
    int id PK
    text user_id FK
    text lesson_id
    text kind "vocab|grammar|pronunciation"
    text expected
    text got
    text created_at
  }
```

## Component diagram

```mermaid
flowchart TB
  subgraph "Frontend (Next.js 14)"
    UI[Page components]
    VC[VoiceClient]
    AW[AudioWorklet<br/>PCM downsampler]
    UI --- VC
    VC --- AW
  end

  subgraph "Backend (FastAPI + Pipecat)"
    WS[WebSocket route /ws]
    BOT[LanguageTutorBot]
    subgraph "Pipeline (in order)"
      P1[VAD] --> P2[MicGate] --> P3[MicActivityProbe]
      P3 --> P4[AssemblyAI STT]
      P4 --> P5[TranscriptForwarder]
      P5 --> P6[StreamingEvaluator]
      P6 --> P7[LatencyProbe]
      P7 --> P8[IntentRouter]
      P8 --> P9[UserAggregator]
      P9 --> P10[GroqLLMService]
      P10 --> P11[ElevenLabsTTS]
      P11 --> P12[AssistantAggregator]
    end
    BOT --> WS
    BOT --> P1
    P12 --> WS
  end

  subgraph "Agent core (pure Python)"
    FSM[ModeFSM]
    PROMPTS[Prompts]
    GRADER[Grader]
    PRON[Pronunciation hints]
    PROSODY[ProsodyTracker]
    CURR[Curriculum loader]
  end

  subgraph "Memory"
    SESSION[SessionMemory<br/>in-mem]
    PERSIST[(SQLite DB)]
  end

  P8 -.-> FSM
  P8 -.-> CURR
  P8 -.-> GRADER
  P8 -.-> PRON
  P8 -.-> PROSODY
  P8 -.-> SESSION
  P8 -.-> PERSIST
  P10 -.-> PROMPTS
  P7 -.-> SESSION
  BOT -.-> PERSIST
```

