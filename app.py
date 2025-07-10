from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
import logging
import uuid
from supabase import create_client, Client
import sys

# Logging Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# 🔐 ENV
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ✅ Fonction de fallback UUID si ID invalide
def get_clean_user_id(user_id):
    try:
        uuid.UUID(user_id)
        return user_id
    except:
        return "00000000-0000-0000-0000-000000000000"

# 🧠 THREAD MANAGEMENT
def get_or_create_thread(user_id):
    user_id = get_clean_user_id(user_id)
    try:
        response = supabase.table("threads").select("*").eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]["thread_id"]
        thread = client.beta.threads.create()
        supabase.table("threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id
    except Exception as e:
        logging.error(f"Erreur get_or_create_thread: {e}")
        return client.beta.threads.create().id

# 🧠 MÉMOIRE AFFECTIVE
def update_memory(user_id, memory_data):
    try:
        user_id = get_clean_user_id(user_id)
        supabase.table("user_memory").upsert({
            "user_id": user_id,
            **memory_data
        }).execute()
    except Exception as e:
        logging.error(f"Erreur update_memory Supabase: {e}")

# 🔥 ROUTE /chat
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        message = data.get("message", "")
        user_id = get_clean_user_id(data.get("user_id", ""))
        preferences = data.get("preferences", {})
        premium = data.get("premium", False)

        # 🔍 Extraction mémoire (basique ici)
        extracted_memory = {}
        if "je l'aime" in message.lower():
            extracted_memory["intention"] = "reconquête"
        if "marie" in message.lower():
            extracted_memory["prenom_aime"] = "Marie"

        if extracted_memory:
            update_memory(user_id, extracted_memory)

        # Assistant selon premium
        assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        # Message utilisateur
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)

        # Lancement IA
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=json.dumps(preferences)
        )

        # Réponse IA
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        for msg in reversed(messages.data):
            if msg.role == "assistant":
                return jsonify({"response": msg.content[0].text.value})
        return jsonify({"response": "Une erreur est survenue, je n'ai pas pu répondre."})
    except Exception as e:
        logging.error(f"💥 ERREUR /chat : {e}")
        return jsonify({"error": str(e)}), 500

# 🧠 ROUTE /update_memory
@app.route("/update_memory", methods=["POST"])
def update_memory_route():
    try:
        data = request.json
        user_id = get_clean_user_id(data.get("user_id", ""))
        memory_data = data.get("memory", {})
        update_memory(user_id, memory_data)
        return jsonify({"status": "Mémoire mise à jour"})
    except Exception as e:
        logging.error(f"💥 ERREUR /update_memory : {e}")
        return jsonify({"error": str(e)}), 500

# ✅ ROUTE /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# 🚀 MAIN
if __name__ == "__main__":
    app.run(debug=True)
