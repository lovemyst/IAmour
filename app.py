from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Pour logs Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# Init Flask
app = Flask(__name__)
CORS(app)

# Clés API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Clients
client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# THREAD
def get_or_create_thread(user_id):
    response = supabase.table("user_threads").select("thread_id").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    thread = client.beta.threads.create()
    supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
    return thread.id

# EXTRACTION MÉMOIRE
def extract_memory_data(message):
    memory = {}
    lower = message.lower()
    if "je l’aime" in lower or "prénom" in lower:
        memory["prenom_aime"] = message.split()[-1]
    if "je suis célibataire" in lower or "en couple" in lower:
        memory["situation_amoureuse"] = "célibataire" if "célibataire" in lower else "en couple"
    if "je veux" in lower:
        if "relation sérieuse" in lower:
            memory["intention"] = "relation sérieuse"
        elif "jeux" in lower or "drague" in lower:
            memory["intention"] = "séduction légère"
    return memory

# ROUTE CHAT
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_id = data.get("user_id")
        message = data.get("message")
        preferences = data.get("preferences", {})
        premium = data.get("premium", False)

        assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        memory_data = extract_memory_data(message)
        if memory_data:
            for key, value in memory_data.items():
                supabase.table("user_memory").upsert({
                    "user_id": user_id,
                    "key": key,
                    "value": value
                }, on_conflict=["user_id", "key"]).execute()

        instructions = f"""
Tu es IAmour V6, une intelligence émotionnelle incarnée. Adapte-toi aux préférences suivantes :
- Tonalité : {preferences.get('tonalite')}
- Intensité émotionnelle : {preferences.get('intensite')}
- Longueur : {preferences.get('longueur')}
- Personnalité IA : {preferences.get('personnalite')}
- Humeur : {preferences.get('humeur')}
"""

        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        while run.status not in ["completed", "failed"]:
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            response = messages.data[0].content[0].text.value
            return jsonify({"response": response})
        else:
            return jsonify({"error": "Run failed"}), 500

    except Exception as e:
        logging.exception("Erreur dans /chat")
        return jsonify({"error": str(e)}), 500

# ROUTE MÉMOIRE
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.json
        user_id = data.get("user_id")
        memory_data = data.get("memory", {})
        for key, value in memory_data.items():
            supabase.table("user_memory").upsert({
                "user_id": user_id,
                "key": key,
                "value": value
            }, on_conflict=["user_id", "key"]).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        logging.exception("Erreur dans /update_memory")
        return jsonify({"error": str(e)}), 500

# ROUTE HEALTH
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)
