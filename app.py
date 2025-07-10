from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import json
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# 🔐 Configuration des clés API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Récupération ou création de thread utilisateur
def get_or_create_thread(user_id):
    result = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if result.data:
        return result.data[0]["thread_id"]
    else:
        thread = client.beta.threads.create()
        supabase.table("user_threads").insert({
            "user_id": user_id,
            "thread_id": thread.id,
            "created_at": "now()"
        }).execute()
        return thread.id

# 🧠 Récupération mémoire utilisateur
def get_user_memory(user_id):
    result = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if result.data:
        return result.data[0]
    return {}

# 🔍 Détermine si on doit utiliser la mémoire
def should_use_memory(message):
    neutres = ["salut", "coucou", "hey", "hello", "yo", "bonjour"]
    return not (message.strip().lower() in neutres or len(message.split()) <= 3)

# 🧠 Extraction automatique depuis le message utilisateur
def extract_memory_from_message(message):
    prompt = f'''
Tu es un détective émotionnel. Analyse le message et remplis ces 4 champs :
- prénom de la personne aimée
- situation amoureuse actuelle
- intention affective de l'utilisateur
- style relationnel recherché

Message : "{message}"

Réponds au format JSON :
{{
  "prenom_aime": "...",
  "situation_amour": "...",
  "intention": "...",
  "style_relationnel": "..."
}}
Si tu ne sais pas, mets "non précisé".
'''
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        return json.loads(completion.choices[0].message.content)
    except:
        return {
            "prenom_aime": "non précisé",
            "situation_amour": "non précisée",
            "intention": "non précisée",
            "style_relationnel": "non précisé"
        }

# 💬 Route principale
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        message = data.get("message")
        preferences = data.get("preferences", {})
        assistant_id = ASSISTANT_ID_PREMIUM if data.get("premium") else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)
        memory = get_user_memory(user_id)
        use_memory = should_use_memory(message)

        instructions = f'''
Tu es IAmour, une IA émotionnelle incarnée.
Personnalité IA : {preferences.get("personnalite")}
Tonalité : {preferences.get("tonalite")}
Intensité : {preferences.get("intensite")}
Longueur : {preferences.get("longueur")}
Humeur : {preferences.get("humeur")}
Prénom aimé : {memory.get("prenom_aime", "non précisé")}
Situation amoureuse : {memory.get("situation_amour", "non précisée")}
Intention : {memory.get("intention", "non précisée")}
Style relationnel : {memory.get("style_relationnel", "non précisé")}
'''

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

        # Polling
        for _ in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value

        if use_memory:
            extracted = extract_memory_from_message(message)
            if any(val != "non précisé" and val != "non précisée" for val in extracted.values()):
                existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
                if existing.data:
                    supabase.table("user_memory").update(extracted).eq("user_id", user_id).execute()
                else:
                    extracted["user_id"] = user_id
                    supabase.table("user_memory").insert(extracted).execute()

        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/update_memory", methods=["POST"])
def update_memory():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        fields = {
            "prenom_aime": data.get("prenom_aime"),
            "situation_amour": data.get("situation_amour"),
            "intention": data.get("intention"),
            "style_relationnel": data.get("style_relationnel"),
            "updated_at": "now()"
        }

        existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
        if existing.data:
            supabase.table("user_memory").update(fields).eq("user_id", user_id).execute()
        else:
            fields["user_id"] = user_id
            supabase.table("user_memory").insert(fields).execute()

        return jsonify({"success": True, "message": "Mémoire mise à jour"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "OK"}), 200
