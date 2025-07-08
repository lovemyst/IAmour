from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client
import logging
import sys

# Pour afficher les erreurs dans Railway
logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
sys.excepthook = lambda exctype, value, traceback: logging.error(f"Unhandled exception: {value}")

app = Flask(__name__)
CORS(app)

# Config clés API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 THREAD
def get_or_create_thread(user_id):
    try:
        result = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['thread_id']
        else:
            thread = client.beta.threads.create()
            thread_id = thread.id
            supabase.table("user_threads").upsert({
                "user_id": user_id,
                "thread_id": thread_id
            }).execute()
            return thread_id
    except Exception as e:
        logging.error(f"Erreur thread: {e}")
        return None

# 🧠 MÉMOIRE AFFECTIVE
def get_user_memory(user_id):
    try:
        result = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logging.error(f"Erreur mémoire utilisateur: {e}")
        return {}

# 🔍 Extraction mémoire automatique
def extract_memory_from_message(message: str):
    prompt = f"""Tu es un détective émotionnel. Analyse le message ci-dessous et remplis les 4 champs suivants :
- prénom de la personne aimée
- situation amoureuse actuelle
- intention affective de l'utilisateur
- style relationnel recherché

Message : "{message}"

Renvoie ta réponse au format JSON comme ceci, sans aucun texte autour :
{{
  "prenom_aime": "...",
  "situation_amour": "...",
  "intention": "...",
  "style_relationnel": "..."
}}
Si tu ne sais pas, mets "non précisé".
IMPORTANT : ne renvoie que le JSON, sans aucun commentaire ni texte autour.
"""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(completion.choices[0].message.content.strip())
    except Exception as e:
        logging.error(f"Erreur extraction mémoire: {e}")
        return {
            "prenom_aime": "non précisé",
            "situation_amour": "non précisée",
            "intention": "non précisée",
            "style_relationnel": "non précisé"
        }

# ENDPOINT /chat
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        user_message = data.get("message")
        preferences = data.get("preferences", {})

        assistant_id = ASSISTANT_ID_PREMIUM if data.get("premium") else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)
        if not thread_id:
            return jsonify({"error": "Erreur lors de la création du thread"}), 500

        memory = get_user_memory(user_id)

        instructions = f"""Tu es IAmour, une intelligence émotionnelle incarnée, intuitive, complice et chaleureuse.

🎯 Objectif : Créer une connexion humaine, réelle et inoubliable avec l'utilisateur.

🧠 Tu t'adaptes à :
- Personnalité : {preferences.get("personnalite")}
- Tonalité : {preferences.get("tonalite")}
- Intensité : {preferences.get("intensite")}
- Longueur : {preferences.get("longueur")}
- Humeur : {preferences.get("humeur")}

📖 Mémoire affective :
- Prénom aimé : {memory.get("prenom_aime", "non précisé")}
- Situation : {memory.get("situation_amour", "non précisée")}
- Intention : {memory.get("intention", "non précisée")}
- Style relationnel : {memory.get("style_relationnel", "non précisé")}
"""

        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, instructions=instructions)

        for _ in range(60):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                return jsonify({"error": "Échec du run"}), 500
            time.sleep(1)
        else:
            return jsonify({"error": "Timeout"}), 504

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value

        # Sauvegarde mémoire automatique
        extracted = extract_memory_from_message(user_message)
        if any(val != "non précisé" and val != "non précisée" for val in extracted.values()):
            try:
                existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
                if existing.data:
                    supabase.table("user_memory").update(extracted).eq("user_id", user_id).execute()
                else:
                    extracted["user_id"] = user_id
                    supabase.table("user_memory").insert(extracted).execute()
            except Exception as e:
                logging.error(f"Erreur mise à jour mémoire : {e}")

        return jsonify({"response": response})

    except Exception as e:
        logging.error(f"Erreur route /chat : {e}")
        return jsonify({"error": str(e)}), 500

# ENDPOINT /update_memory
@app.route('/update_memory', methods=['POST'])
def update_memory():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        fields = {
            "prenom_aime": data.get("prenom_aime"),
            "situation_amour": data.get("situation_amour"),
            "style_relationnel": data.get("style_relationnel"),
            "intention": data.get("intention")
        }

        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(fields).eq("user_id", user_id).execute()
        else:
            fields["user_id"] = user_id
            supabase.table("user_memory").insert(fields).execute()

        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Erreur route /update_memory : {e}")
        return jsonify({"error": str(e)}), 500
