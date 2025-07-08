from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Logger pour Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

# Initialisation app Flask
app = Flask(__name__)
CORS(app)

# Configuration API & Supabase
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Thread user
def get_or_create_thread(user_id):
    response = supabase.table("threads").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("threads").insert({"user_id": user_id, "thread_id": thread.id}).execute()
        return thread.id

# RÃ©cupÃ©ration des prÃ©fÃ©rences utilisateur
def get_user_settings(user_id):
    response = supabase.table("user_settings").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        return {}

# ROUTE /chat
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_id = data.get("user_id")
        user_message = data.get("message", "")
        settings = data.get("settings", {})
        use_premium = data.get("use_premium", False)

        assistant_id = ASSISTANT_ID_PREMIUM if use_premium else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)
        user_settings = get_user_settings(user_id)

        instructions = json.dumps({
            "preferences": settings,
            "memory": {
                "relation_intent": user_settings.get("relation_intent"),
                "love_name": user_settings.get("love_name"),
                "love_style": user_settings.get("love_style"),
                "status": user_settings.get("status")
            }
        })

        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        # Attente de la rÃ©ponse
        for _ in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_message = messages.data[0].content[0].text.value if messages.data else "Aucune rÃ©ponse gÃ©nÃ©rÃ©e."

        return jsonify({"response": last_message})

    except Exception as e:
        logging.error(f"Erreur /chat : {e}")
        return jsonify({"error": str(e)}), 500

# ROUTE /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ROUTE /update_memory
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.json
        user_id = data.get("user_id")
        memory_fields = {
            "relation_intent": data.get("relation_intent"),
            "love_name": data.get("love_name"),
            "love_style": data.get("love_style"),
            "status": data.get("status")
        }

        response = supabase.table("user_settings").upsert({**memory_fields, "user_id": user_id}).execute()
        return jsonify({"status": "success", "data": response.data})
    except Exception as e:
        logging.error(f"Erreur /update_memory : {e}")
        return jsonify({"error": str(e)}), 500

# ExÃ©cution locale pour debug ou via Gunicorn en prod
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
