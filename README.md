<div align="center">

![Profile banner](./docs/logo.png)

---

# Syncly

#### **Split. Sync. Simplify. Smarten.**

**Syncly** is a next-generation **unified cloud file management platform**, designed to **split**, **upload**, **search**, and **manage** massive files across multiple cloud services — all in one place. With intelligent AI support and seamless multi-platform access, **Syncly** empowers you to store, retrieve, and interact with your data effortlessly.

---

## Features

### 🔹 Core File Management

**Multi-Cloud Support:**
- Connects with **Google Drive** and **Dropbox**.
- Unified view and management of files across all accounts ("buckets").

**File Splitting & Uploading:**
- Automatically selects the drive with the most free space for uploads.
- Handles intelligent file routing and secure storage distribution.

**File Listing & Downloading:**
- View and paginate through all your files.
- Download files directly via the Web UI.

**Powerful Search:**
- Search across all connected cloud accounts.
- Provider-specific full-text search integration.

**Storage Aggregation:**
- Displays total, used, and free storage across all connected drives.

---

### 🔹 Secure User Management

**Registration and Login:**
- Secure account creation with password hashing (SHA256 + Base64).
- JWT-powered sessions for Web UI and Bot.

**Bot Authentication:**
- Seamless Telegram Bot login via secure, temporary links.
- Automatic account association with Telegram ID after login.

**Logout and Session Management:**
- Full control over sessions for enhanced security.

---

### 🔹 Cloud Storage Integration (Bucket Management)

**Adding New Buckets:**
- Connect multiple Google Drive or Dropbox accounts.
- OAuth 2.0 flows securely handled.

**Token Management:**
- Securely stores and refreshes tokens for continued access.

---

### 🧪 AI-Powered Assistant

**Conversational AI Interface:**
- Engage with a powerful AI through the Telegram bot.

**Smart Search Assistant:**
- Extracts keywords from your questions.
- Contextually searches your files for matching content.
- Extracts relevant snippets from PDFs, DOCX, TXT, and code files.

**Memory & Reset:**
- Maintains rolling conversation history per Telegram user.
- /reset command available to clear AI memory when needed.

**Context-Aware Responses:**
- Synthesizes detailed answers based on your files and questions.

---

### 🛸 Multi-Platform Access

**Web Interface:**
- FastAPI-served HTML, CSS, and JavaScript frontend.
- Access file management, uploads, downloads, and bucket management.

**Telegram Bot:**
- Command-line style interaction.
- Upload, search, manage storage, and chat with AI right from Telegram.

---

## 👨‍💻 Tech Stack (Updated)

- **Frontend:** Vite + React (Web) | Java (Mobile)
- **Backend:** Python (FastAPI)
- **Database:** MongoDB (Secure storage of user and token data)
- **Cloud Storage:** Google Drive, Dropbox APIs
- **AI/LLM Integration:** Groq API (Llama 3.1 8B/70B models)
- **Version Control:** Git with GitHub
- **Deployment:** Railway (Planned)
- **Project Management:** Trello

---

## 🗂️ Project Structure

</div>

```
Syncly/
├── 📂 frontend/      # Vite + React (TypeScript) Web Application
├── 📂 mobile/        # Android App (Kotlin/Java) (Planned)
├── 📂 backend/       # API Backend (FastAPI)
├── 📂 bot/           # Telegram Bot
├── 📂 docs/          # Documentation
├── 📂 tests/         # Automated Tests
└── 📄 README.md      # This file
```

<div align="center">

---

- Instructor: [Dr. Nabeel Mohammed](https://ece.northsouth.edu/people/dr-nabeel-mohammed/)
- Trello Board: [Syncly Project Board](https://trello.com/b/o5OcT4uj/syncly)

---

## License

This project is licensed under the **MIT License**.

---

## 👥 The Team:

| Name              | Institution             | ID | GitHub | Followers |
|-------------------|--------------------------|----|--------|-----------|
| **Rajin Khan**    | North South University   | 2212708042 | [![Rajin's GitHub](https://img.shields.io/badge/-rajin--khan-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/rajin-khan) | ![Followers](https://img.shields.io/github/followers/rajin-khan?label=Follow&style=social) |
| **Ahnaf Ojayer**  | North South University   | 2121949042 | [![Ahnaf's GitHub](https://img.shields.io/badge/-0jayer-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/0jayer) | ![Followers](https://img.shields.io/github/followers/0jayer?label=Follow&style=social) |
| **Rihal Mahmood** | North South University   | 2132378042 | [![Rihal's GitHub](https://img.shields.io/badge/-RihalMahmood-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/RihalMahmood) | ![Followers](https://img.shields.io/github/followers/RihalMahmood?label=Follow&style=social) |

</div>