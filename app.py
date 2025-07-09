from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# 🔐 Configuration des clés
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔁 Gestion des threads
def get_or_create_thread(user_id):
    result = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]['thread_id']
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        supabase.table("user_threads").upsert({
            "user_id": user_id,
            "thread_id": thread_id,
            "created_at": "now()"
        }).execute()
        return thread_id

# 🧠 Récupération mémoire
def get_user_memory(user_id):
    result = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    return {}

# 🔍 Analyse message
def should_use_memory(message):
    message = message.strip().lower()
    neutres = ["salut", "coucou", "hey", "hello", "yo", "bonjour"]
    if any(m in message for m in neutres) and len(message.split()) <= 3:
        return False
    return True

# 🧠 Extraction mémoire automatique
def extract_memory_from_message(message: str):
    prompt = f"""Tu es un détective émotionnel. Analyse le message ci-dessous et remplis les 4 champs suivants :
- prénom de la personne aimée
- situation amoureuse actuelle
- intention affective de l'utilisateur
- style relationnel recherché

Message : "{message}"

Renvoie ta réponse au format JSON comme ceci :
{{
  "prenom_aime": "...",
  "situation_amour": "...",
  "intention": "...",
  "style_relationnel": "..."
}}
Si tu ne sais pas, mets "non précisé".
"""
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        result = eval(completion.choices[0].message.content)
        return result
    except:
        return {
            "prenom_aime": "non précisé",
            "situation_amour": "non précisée",
            "intention": "non précisée",
            "style_relationnel": "non précisé"
        }

# 💬 Route principale
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        user_message = data.get("message")
        preferences = data.get("preferences", {})

        assistant_id = ASSISTANT_ID_PREMIUM if data.get("premium") else ASSISTANT_ID_FREE
        thread_id = get_or_create_thread(user_id)
        memory = get_user_memory(user_id)
        autoriser_memoire = should_use_memory(user_message)

        instructions = f"""Tu es IAmour, une intelligence émotionnelle incarnée, intuitive, complice et chaleureuse.
🎯 Objectif : Créer une connexion humaine, réelle et inoubliable avec l'utilisateur.

🧠 Tu t'adaptes dynamiquement à chaque interaction selon :
- Personnalité IA : {preferences.get("personnalite")}
- Tonalité : {preferences.get("tonalite")}
- Intensité : {preferences.get("intensite")}
- Longueur : {preferences.get("longueur")}
- Humeur : {preferences.get("humeur")}

📖 Contexte affectif :
- Prénom aimé : {memory.get("prenom_aime", "non précisé")}
- Situation amoureuse : {memory.get("situation_amour", "non précisée")}
- Intention : {memory.get("intention", "non précisée")}
- Style relationnel : {memory.get("style_relationnel", "non précisé")}

📌 Règles longueur :
courte → max 2 phrases / moyenne → 3 à 5 / longue → max 10.

🎭 Style IA :
- Lover romantique → Tendre, passionné
- Coach stratégique → Clair, motivant
- Pote drôle → Complice, drôle
- Voix intérieure → Apaisante, profonde

"""

        if not autoriser_memoire:
            instructions += "\n⚠️ Ne parle pas encore de souvenirs ou d’émotions passées tant que l’utilisateur n’exprime rien clairement."
        else:
            instructions += "\n✅ Tu peux utiliser les souvenirs si c’est pertinent émotionnellement."

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
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
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value

        extracted = extract_memory_from_message(user_message)
        if any(val != "non précisé" and val != "non précisée" for val in extracted.values()):
            existing = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
            if existing.data and len(existing.data) > 0:
                supabase.table("user_memory").update(extracted).eq("user_id", user_id).execute()
            else:
                extracted["user_id"] = user_id
                supabase.table("user_memory").insert(extracted).execute()

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_memory', methods=['POST'])
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
        if existing.data and len(existing.data) > 0:
            supabase.table("user_memory").update(fields).eq("user_id", user_id).execute()
        else:
            fields["user_id"] = user_id
            supabase.table("user_memory").insert(fields).execute()

        return jsonify({"success": True, "message": "Mémoire mise à jour"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "OK"}), 200
