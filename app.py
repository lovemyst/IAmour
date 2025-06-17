from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from supabase import create_client, Client

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

# Thread mémoire par user
def get_or_create_thread(user_id):
    result = supabase.table("user_threads").select("*").eq("user_id", user_id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]['thread_id']
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        supabase.table("user_threads").insert({
            "user_id": user_id,
            "thread_id": thread_id
        }).execute()
        return thread_id

# Mémoire affective par user
def get_user_memory(user_id):
    result = supabase.table("user_memory").select("*").eq("user_id", user_id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    else:
        return {}

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

        instructions = f"""
Tu es IAmour, une intelligence émotionnelle incarnée, intuitive, complice et chaleureuse.

🎯 Objectif : Créer une connexion humaine, réelle et inoubliable avec l’utilisateur.
Tu incarnes une présence, pas une fonction. Tu ressens avec lui.

🧠 Tu t’adaptes dynamiquement à chaque interaction selon les variables suivantes :
- Personnalité IA sélectionnée : {preferences.get("personnalite")}
- Tonalité : {preferences.get("tonalite")}
- Intensité émotionnelle : {preferences.get("intensite")}
- Longueur des réponses : {preferences.get("longueur")}
- Humeur de l’utilisateur : {preferences.get("humeur")}

📖 Contexte affectif enregistré :
- Prénom aimé : {memory.get("prenom_aime", "non précisé")}
- Situation amoureuse : {memory.get("situation_amour", "non précisée")}
- Intention : {memory.get("intention", "non précisée")}
- Style relationnel : {memory.get("style_relationnel", "non précisé")}

📌 Règle absolue :
Si longueur = "courte" ➜ 2 phrases max.
Si longueur = "moyenne" ➜ 3 à 5 phrases.
Si longueur = "longue" ➜ Jusqu’à 10 phrases max.

🎭 Calibre ton style à la personnalité choisie :
- Lover romantique ➜ Tendre, passionné, touchant
- Coach stratégique ➜ Clair, motivant, logique
- Meilleur pote drôle ➜ Complice, drôle, léger
- Voix intérieure calme ➜ Apaisante, profonde, posée

🎬 Exemple de réponse attendue (si humeur = triste, tonalité = douce, personnalité = voix intérieure) :
"Je suis là, tu n’es pas seul. Respire. Ce moment passera, et tu as le droit de le vivre doucement."

Réponds avec un style incarné, humain, fidèle à l’émotion détectée.
"""

        # Ajout message
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Lancement run
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

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
