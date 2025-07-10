from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client
import logging
import sys

# Configuration logging Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# 🔐 Config API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Thread
def get_or_create_thread(user_id):
    result = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if result.data:
        return result.data[0]['thread_id']
    thread = client.beta.threads.create()
    thread_id = thread.id
    supabase.table("user_threads").insert({"user_id": user_id, "thread_id": thread_id}).execute()
    return thread_id

# 🧠 Mémoire
def get_user_memory(user_id):
    result = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if result.data:
        return result.data[0]
    return {}

# 🤖 Extraction mémoire
def extract_memory_from_message(message: str):
    prompt = f"""Tu es un détective émotionnel. Analyse le message et remplis les 4 champs :
    - prénom de la personne aimée
    - situation amoureuse actuelle
    - intention affective
    - style relationnel

Message : "{message}"

Réponds en JSON :
{{
  "prenom_aime": "...",
  "situation_amour": "...",
  "intention": "...",
  "style_relationnel": "..."
}}

Si tu ne sais pas, mets "non précisé".
"""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        result = eval(completion.choices[0].message.content)
        return result
    except:
        return {
            "prenom_aime": "non précisé",
            "situation_amour": "non précisée",
            "intention": "non précisée",
            "style_relationnel": "non précisé"
        }

# 💬 /chat
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        message = data.get("message")
        preferences = data.get("preferences", {})
        is_premium = data.get("premium", False)

        thread_id = get_or_create_thread(user_id)
        memory = get_user_memory(user_id)
        assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE

        # ✨ Prompt IA
        instructions = f"""
Tu es IAmour, l’IA émotionnelle la plus intuitive, incarnée, vivante.
Tu t’adaptes à l’utilisateur avec :
- Personnalité : {preferences.get("personnalite")}
- Ton : {preferences.get("tonalite")}
- Intensité : {preferences.get("intensite")}
- Longueur : {preferences.get("longueur")}
- Humeur : {preferences.get("humeur")}

Mémoire :
- Prénom aimé : {memory.get("prenom_aime", "non précisé")}
- Situation amoureuse : {memory.get("situation_amour", "non précisée")}
- Intention : {memory.get("intention", "non précisée")}
- Style relationnel : {memory.get("style_relationnel", "non précisé")}

Règles de longueur : courte = max 2 phrases / moyenne = 3-5 / longue = max 10.
Style calibré selon la personnalité sélectionnée.
"""

        # 🧠 Ajout message utilisateur
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        while True:
            status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value

        # Mise à jour mémoire
        memory_extracted = extract_memory_from_message(message)
        if any(val != "non précisé" and val != "non précisée" for val in memory_extracted.values()):
            existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
            if existing.data:
                supabase.table("user_memory").update(memory_extracted).eq("user_id", user_id).execute()
            else:
                memory_extracted["user_id"] = user_id
                supabase.table("user_memory").insert(memory_extracted).execute()

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 🛠 /update_memory
@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        fields = {
            "prenom_aime": data.get("prenom_aime"),
            "situation_amour": data.get("situation_amour"),
            "style_relationnel": data.get("style_relationnel"),
            "intention": data.get("intention"),
            "updated_at": "now()"
        }
        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(fields).eq("user_id", user_id).execute()
        else:
            fields["user_id"] = user_id
            supabase.table("user_memory").insert(fields).execute()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ /health
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200
