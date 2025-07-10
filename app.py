from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Setup log Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Env variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Route /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# Fonction thread
def get_or_create_thread(user_id):
    try:
        response = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["thread_id"]
        else:
            thread = client.beta.threads.create()
            supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
            return thread.id
    except Exception as e:
        logging.error(f"Erreur get_or_create_thread: {e}")
        raise e

# Fonction mÃ©moire Ã©motionnelle
def store_memory(user_id, memory):
    try:
        supabase.table("user_memory").upsert({
            "user_id": user_id,
            "prenom_aime": memory.get("prenom_aime"),
            "situation_amoureuse": memory.get("situation_amoureuse"),
            "intention_relationnelle": memory.get("intention_relationnelle"),
            "style_relationnel": memory.get("style_relationnel")
        }).execute()
    except Exception as e:
        logging.error(f"Erreur mÃ©moire Supabase: {e}")

@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        memory = data.get("memory", {})
        store_memory(user_id, memory)
        return jsonify({"status": "MÃ©moire mise Ã  jour"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        message = data.get("message", "")
        user_id = data.get("user_id", "")
        premium = data.get("premium", False)
        preferences = data.get("preferences", {})

        if not message or not user_id:
            return jsonify({"error": "Message ou user_id manquant"}), 400

        assistant_id = ASSISTANT_ID_PREMIUM if premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)

        # Construction du prompt dynamique
        instructions = f"""Tu es l'IA IAmour, spÃ©cialisÃ©e dans les Ã©motions humaines. 
Tu dois t'adapter au style suivant :
- PersonnalitÃ© : {preferences.get("personnalite", "lover")}
- TonalitÃ© : {preferences.get("tonalite", "doux")}
- IntensitÃ© : {preferences.get("intensite", "moyenne")}
- Longueur : {preferences.get("longueur", "moyenne")}
- Humeur : {preferences.get("humeur", "calme")}
RÃ©ponds de maniÃ¨re profondÃ©ment humaine, intuitive, chaleureuse et adaptÃ©e."""

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
                return jsonify({"error": "Ãchec de gÃ©nÃ©ration OpenAI"}), 500
            time.sleep(0.5)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_response = next((m for m in reversed(messages.data) if m.role == "assistant"), None)

        if not last_response:
            return jsonify({"error": "Aucune rÃ©ponse gÃ©nÃ©rÃ©e"}), 500

        return jsonify({"response": last_response.content[0].text.value}), 200

    except Exception as e:
        logging.error(f"ð¥ ERREUR /chat: {str(e)}")
        return jsonify({"error": str(e)}), 500
