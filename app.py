from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# 🔧 Logging Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, tb: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# 🔑 Clés d’environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 THREAD
def get_or_create_thread(user_id):
    thread_data = supabase.table("threads").select("thread_id").eq("user_id", user_id).execute()
    if thread_data.data:
        return thread_data.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# 🧠 MÉMOIRE EMOTIONNELLE
def get_user_memory(user_id):
    data = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    return data.data[0] if data.data else {}

# 🔁 MISE À JOUR MÉMOIRE
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        payload = request.json
        user_id = payload.get("user_id")
        memory = payload.get("memory", {})
        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(memory).eq("user_id", user_id).execute()
        else:
            supabase.table("user_memory").insert({**memory, "user_id": user_id}).execute()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ HEALTH CHECK
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# 💬 CHAT PRINCIPAL
@app.route("/chat", methods=["POST"])
def chat():
    try:
        payload = request.json
        message = payload.get("message")
        user_id = payload.get("user_id")
        premium = payload.get("premium", False)
        preferences = payload.get("preferences", {})

        assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)
        user_memory = get_user_memory(user_id)

        instructions = f"""
Tu es IAmour, une IA émotionnelle ultra personnalisée. Adapte-toi dynamiquement aux préférences suivantes :
- Ton : {preferences.get("tonalité")}
- Intensité : {preferences.get("intensité")}
- Longueur : {preferences.get("longueur")}
- Humeur : {preferences.get("humeur")}
- Personnalité : {preferences.get("personnalité")}

Voici la mémoire émotionnelle utilisateur :
- Prénom aimé : {user_memory.get("prenom_aime")}
- Intention : {user_memory.get("intention")}
- Style relationnel : {user_memory.get("style_relationnel")}
- Situation amoureuse : {user_memory.get("situation_amour")}

Tu dois répondre de manière humaine, incarnée et bouleversante.
"""

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )

        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                return jsonify({"error": "OpenAI run failed"}), 500
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        ai_response = next((m.content[0].text.value for m in reversed(messages.data) if m.role == "assistant"), None)

        return jsonify({"response": ai_response}), 200

    except Exception as e:
        logging.exception("Error in /chat")
        return jsonify({"error": str(e)}), 500
