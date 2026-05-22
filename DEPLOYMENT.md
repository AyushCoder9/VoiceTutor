# 🚀 VoiceTutor — Deployment & Production Guide

This guide provides a comprehensive, step-by-step walkthrough to deploy **VoiceTutor** to production. The stack is split into two components:
1. **Backend (FastAPI + Pipecat)**: Deployed as a persistent containerized Web Service on **Railway** (or **Render**), enabling real-time full-duplex WebSockets and secure persistence.
2. **Frontend (Next.js 14)**: Deployed on **Vercel** with a global CDN, fast serverless compilation, and instant updates.

---

## 📐 Production Architecture Overview

```mermaid
graph LR
    User([Learner Voice + UI]) <-->|HTTPS / WSS| Vercel[Next.js Frontend\n(Vercel CDN)]
    User <-->|WebSocket wss://.../ws| Railway[FastAPI Backend\n(Railway / Docker)]
    Railway <-->|SQLite WAL| Volume[(Persistent Disk\n/app/data)]
    Railway <-->|Streaming Audio| ElevenLabs[ElevenLabs TTS]
    Railway <-->|Streaming Audio| AssemblyAI[AssemblyAI STT]
    Railway <-->|Structured JSON| Groq[Groq Llama 3.3]
```

### Key Production Requirements:
* **WebSockets**: The voice agent transport (`/ws`) requires long-lived, stable WebSocket support with zero timeouts. Serverless runtimes (like Vercel Serverless Functions) **cannot** host the backend.
* **Database Persistence**: VoiceTutor uses a SQLite database to save user lessons, mistakes, and FSRS-lite spaced repetition memory. PaaS containers (like Render/Railway) have ephemeral filesystems by default. We must attach a **Persistent Volume** (Disk) to prevent data loss on server restarts.

---

## 🛠️ Phase 1: Deploying the Backend (FastAPI + Pipecat)

We highly recommend **Railway** because it supports persistent storage volumes on their developer tier and handles Dockerfiles automatically. **Render** is also covered as a secondary option.

### Option A: Deployed on Railway (Recommended)

#### Step 1: Create a Railway Account & Connect GitHub
1. Go to [Railway.app](https://railway.app/) and sign up.
2. Click **Login** and authenticate with your **GitHub** account.

#### Step 2: Start a New Project
1. In your Railway dashboard, click **+ New Project** in the top-right corner.
2. Select **Deploy from GitHub repo**.
3. Select your repository: `AyushCoder9/VoiceTutor`.

#### Step 3: Configure Subdirectory & Dockerfile
By default, Railway will look at the root directory. Since this is a monorepo, we need to point it to the `/backend` subdirectory:
1. Click on the newly created service block to open its settings.
2. Go to the **Settings** tab.
3. Scroll down to the **General** section.
4. Set the **Root Directory** to `/backend`.
5. Railway will automatically detect the production `Dockerfile` inside `/backend` and use it to build the service.

#### Step 4: Attach a Persistent Disk (Volume) for SQLite
Without this step, your learner's progress will reset every time you push code or the server restarts!
1. In your project canvas, click the **+ New** button in the top right.
2. Select **Volume** from the dropdown.
3. Set the volume size (e.g., `1 GB` — SQLite databases are tiny, this will last for millions of lessons).
4. Click **Create**.
5. Once created, click on the **Volume** card, go to **Settings**, and select **Mount Volume**.
6. Set the **Mount Path** to `/app/data`.
7. Link it to your `voicetutor-backend` service.

#### Step 5: Configure Environment Variables
1. Click on your `voicetutor-backend` service card and navigate to the **Variables** tab.
2. Click **+ New Variable** and add the following keys. Make sure to paste your actual keys:

| Environment Variable | Value | Description |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | `gsk_...` | Groq console API key |
| `ASSEMBLYAI_API_KEY` | `...` | AssemblyAI console API key |
| `ELEVENLABS_API_KEY` | `...` | ElevenLabs API key |
| `TTS_PROVIDER` | `elevenlabs` | Keep as `elevenlabs` (or `deepgram` if preferred) |
| `SQLITE_PATH` | `/app/data/voicetutor.db` | Points database to the **Persistent Volume** mount |
| `HOST` | `0.0.0.0` | Bind to all interfaces |
| `PORT` | `8000` | Railway will automatically map this to the public internet |

*Railway will automatically trigger a new deployment once the variables are saved. After it deploys successfully, you'll see a generated URL under **Settings** → **Service Domains** (e.g., `https://backend-production-xxx.up.railway.app`).*
*Note this URL down! You'll need it for your frontend.*

---

### Option B: Deployed on Render

*Note: Render's free tier has ephemeral disks (data clears on restart) and has a 15-minute spin-down on inactivity. To avoid data reset on Render, you must upgrade to a Paid Web Service ($7/mo) to mount a persistent disk, or configure a remote PostgreSQL database.*

#### Step 1: Create a Render Account
1. Go to [Render.com](https://render.com/) and sign up.
2. Authenticate with your GitHub account.

#### Step 2: Create a Web Service
1. Click **New +** in the top dashboard and select **Web Service**.
2. Connect your GitHub repository `AyushCoder9/VoiceTutor`.

#### Step 3: Configure Settings
Fill out the creation form with these exact values:
* **Name**: `voicetutor-backend`
* **Region**: Select the one closest to you (or your users) for lowest audio latency
* **Branch**: `main`
* **Root Directory**: `backend`
* **Runtime**: `Docker` *(Render will automatically build using the production `Dockerfile` in the `/backend` folder)*
* **Instance Type**: `Free` (or `Starter` if you want a Persistent Disk)

#### Step 4: Configure Advanced Environment Variables
Scroll down and click **Advanced** to add environment variables:
1. Click **Add Environment Variable** and populate:
   - `GROQ_API_KEY` = (Your Key)
   - `ASSEMBLYAI_API_KEY` = (Your Key)
   - `ELEVENLABS_API_KEY` = (Your Key)
   - `TTS_PROVIDER` = `elevenlabs`
   - `SQLITE_PATH` = `/opt/render/project/src/backend/data/voicetutor.db` (if on Free tier) OR if you added a Render disk, mount it to `/app/data` and use `/app/data/voicetutor.db`.
2. Click **Create Web Service**.

*Once the deploy finishes, Render will provide a public URL like `https://voicetutor-backend.onrender.com`.*

---

## 💻 Phase 2: Deploying the Frontend (Next.js 14)

Vercel is the native platform for Next.js, and deploying takes less than a minute.

### Step 1: Sign up on Vercel
1. Go to [Vercel.com](https://vercel.com/) and click **Sign Up**.
2. Select **Continue with GitHub** to connect your account.

### Step 2: Import the Project
1. In the Vercel dashboard, click **Add New...** and select **Project**.
2. Select your repository: `AyushCoder9/VoiceTutor` and click **Import**.

### Step 3: Configure Project Settings
In the configuration screen, adjust the following parameters:
1. **Framework Preset**: `Next.js` (automatically detected).
2. **Root Directory**: Click **Edit** and choose the `frontend` folder, then click **OK**.
3. **Environment Variables**: Expand this section and add the two variables pointing to your backend URL deployed in Phase 1:

| Key | Value Example (Railway) | Value Example (Render) |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | `https://backend-production-xxx.up.railway.app` | `https://voicetutor-backend.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://backend-production-xxx.up.railway.app/ws` | `wss://voicetutor-backend.onrender.com/ws` |

*⚠️ CRITICAL: Make sure the WebSocket URL uses `wss://` (secure WebSocket) instead of `ws://`!*

### Step 4: Click Deploy!
1. Click the **Deploy** button.
2. Vercel will compile the Next.js pages, bundle Tailwind styles, optimize TypeScript, and push the build to its global edge network.
3. Within 30 seconds, you'll receive a **"Congratulations!"** screen with a screenshot of your live website and a public URL (e.g., `https://voicetutor-frontend.vercel.app`).

---

## 🔍 Phase 3: Post-Deployment Verification

Let's test that both services are fully connected and functional:

1. **Test the Backend Status API**:
   Open a browser and visit: `https://your-backend-url.up.railway.app/`
   * It should return a JSON response listing the status `"ok"` and the curriculum lessons:
   ```json
   {
     "service": "voicetutor",
     "status": "ok",
     "target_lang": "es",
     "lessons": [...]
   }
   ```

2. **Test the Metrics endpoint**:
   Visit: `https://your-backend-url.up.railway.app/metrics`
   * It should return a JSON structure displaying latency tracking blocks.

3. **Launch the Frontend Web Interface**:
   Go to your deployed Vercel URL.
   * Verify that the UI successfully fetches the lesson list in the sidebar (this proves `NEXT_PUBLIC_API_URL` is working).
   * Click on the **Voice Orb** in the center. Give permission to the microphone.
   * Speak to the orb (e.g., *"Hola!"* or *"Teach me Spanish"*).
   * Verify that:
     1. The orb visualizes your voice waves.
     2. The voice agent replies in real-time with crystal clear audio.
     3. The live transcript updates live on-screen.
     4. Your progress updates in the dashboard (this proves SQLite persistence and FSRS are functioning).
