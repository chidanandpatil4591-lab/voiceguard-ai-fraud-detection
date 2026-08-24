# VoiceGuard AI

VoiceGuard AI is a local hackathon MVP for real-time voice integrity assessment and voice impersonation risk detection.

## MVP Status

The local MVP includes protected audio upload, real Librosa feature extraction, an honest deterministic demo detector, voice and contextual risk scoring, SQLite history, and a React dashboard. The detector is labeled `demo` because no trained anti-spoofing dataset or model is bundled.

## Project Structure

```text
voiceguard-ai/
|-- backend/
|   |-- main.py
|   |-- requirements.txt
|   |-- .env
|   |-- uploads/
|   `-- models/
|-- frontend/src/
|   |-- components/
|   |-- pages/
|   `-- services/
|-- data/
|   |-- real/
|   `-- synthetic/
|-- tests/
|-- .gitignore
`-- README.md
```

## Windows Setup in VS Code

Open the integrated PowerShell terminal at the `voiceguard-ai` folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

If PowerShell blocks script activation, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## Run the Backend

```powershell
cd voiceguard-ai
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Test the Health Endpoint

In a second VS Code terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected response:

```text
status service
------ -------
ok     VoiceGuard AI
```

The JSON response is:

```json
{
  "status": "ok",
  "service": "VoiceGuard AI"
}
```

FastAPI's interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Test Audio Feature Extraction

Use the Swagger page at `http://127.0.0.1:8000/docs` and send a WAV, MP3, M4A, FLAC, OGG, or WebM file to `POST /api/analyze`. The response includes numerical acoustic features and the decoded sample rate. The raw upload is deleted after the response. Files over 25 MB, empty files, unsupported extensions, mismatched MIME types, and undecodable recordings are rejected with a friendly `400` response.

## Real-Time Processing

The dashboard's **Start live capture** control sends mono float32 PCM frames to the backend WebSocket at `/api/realtime`. The browser sends a JSON start message first:

```json
{"type":"start","sample_rate":48000}
```

It then sends binary PCM frames. The backend returns a rolling JSON assessment every second using up to the latest four seconds of audio; the first update is available after one second. The stream is limited to 120 seconds and sample rates from 8 kHz through 48 kHz. Send `{"type":"end"}` to close a session. Live assessments are not written to history. When capture stops, the browser prepares a WebM file; the user selects **Analyze voice** to run the final analysis and save it to history.

## Frontend Setup

In a second VS Code PowerShell terminal:

```powershell
cd voiceguard-ai\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Start the backend first so the dashboard can load history and analyze recordings.

## API Endpoints

- `GET /api/health` checks backend availability.
- `POST /api/analyze` accepts a multipart field named `file`, extracts features, runs the demo detector, calculates voice risk, stores the result, and deletes the raw recording.
- `WS /api/realtime` accepts float32 PCM audio frames and returns rolling voice-risk assessments during microphone capture.
- `GET /api/history` returns the latest 25 stored analysis results.
- `POST /api/analyze/context` combines voice risk with caller, transaction, urgency, and sensitive-information context.

## Detection and Risk Methodology

The detector measures actual extracted features and returns `detection_mode: "demo"`. It considers pitch variation, spectral stability, MFCC variation, high-frequency activity, and silence patterns. It does not generate random probabilities or claim certainty.

Voice risk combines synthetic probability and acoustic anomaly score. Levels are `LOW` (0-30), `MEDIUM` (31-60), `HIGH` (61-80), and `CRITICAL` (81-100). Contextual risk adds factors such as unknown callers, high-value transactions, urgent requests, and sensitive information requests.

## Privacy and Limitations

Raw audio is written only to `backend/uploads` during a request and deleted in the route cleanup block. SQLite stores analysis metadata, indicators, and results, not recordings or raw feature arrays.

This is a hackathon baseline, not a production anti-spoofing system. Real deployment requires multilingual data, trained anti-spoofing models, replay and adversarial testing, calibration, monitoring, and continuous updates. An AI-generated voice probability is not proof that a voice is cloned.

## Demo Flow

1. Start both local servers.
2. Select **Start live capture**, speak for at least one second, and watch the rolling assessment update.
3. Stop capture, then select **Analyze voice** to save the completed assessment to history.
4. Alternatively, upload a supported recording and select **Analyze voice**.
5. Review probability, confidence, risk, indicators, feature telemetry, and history.
6. In Transaction Protection Mode, use the example CEO, unknown caller, fund transfer, INR 1,500,000, urgent request, and sensitive-information request.
7. Review the combined contextual verdict and recommended action.

## Tests

```powershell
cd voiceguard-ai
.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers health, uploads, invalid files, feature extraction, risk thresholds, contextual analysis, and raw-file cleanup.

## Deployment

Deployment-ready Docker and frontend environment configuration are included. See [DEPLOYMENT.md](DEPLOYMENT.md) for host setup.

## VS Code Tasks

Open the `voiceguard-ai` folder in VS Code, then use **Terminal > Run Task** and choose **VoiceGuard: Start Backend** or **VoiceGuard: Start Frontend**. Both tasks use the local project environment and require no Docker or cloud services.

## Technology Direction

The completed MVP will use FastAPI, React + Vite, JavaScript, SQLite, Librosa, NumPy, SciPy, and a deterministic baseline ML or clearly labeled demo detector when no trained model is available. It will not claim perfect or universal cloned-voice detection. Raw recordings will be temporary and will not be stored permanently.
