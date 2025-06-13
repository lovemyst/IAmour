
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
from module_iaamour_comprehension import analyse_profil_utilisateur

app = Flask(__name__)
CORS(app)

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Threads simulés pour tests
user_threads = {}

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")

    # Préférences émotionnelles depuis le frontend Lovable
    tonalite = data.get("tonalite", "douce")
    intensite = data.get("intensite", "moderee")
    longueur = data.get("longueur", "moyenne")
    personnalite = data.get("personnalite", "voix intérieure")
    humeur = data.get("humeur", "calme")

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    # Analyse du message utilisateur pour enrichir les instructions
    profil = analyse_profil_utilisateur(user_message)

    # Gestion premium
    PREMIUM_USER_IDS = ["anonymous_user", "test_admin", "user_1747692922028"]
    is_premium = user_id in PREMIUM_USER_IDS
    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE

    print("👤 USER_ID reçu :", user_id)
    print("✨ Premium activé ?", is_premium)
    print("🧠 Assistant utilisé :", assistant_id)
    print("🔎 Profil comportemental détecté :", profil)

    # Gestion du thread utilisateur
    if user_id in user_threads:
        thread_id = user_threads[user_id]
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        user_threads[user_id] = thread_id

    # Envoi du message utilisateur
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Enrichissement des instructions
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        instructions=f'''
Préférences utilisateur (via interface Lovable) :
- Tonalité : {tonalite}
- Intensité émotionnelle : {intensite}
- Longueur des réponses : {longueur}
- Personnalité IA : {personnalite}
- Humeur : {humeur}

Profil comportemental détecté (via IA interne) :
- Âge estimé : {profil['âge_estimé']}
- Niveau de langage : {profil['niveau_langage']}
- Ton émotionnel : {profil['ton']}
- Style IA recommandé : {profil['style']}
- Besoin implicite : {profil['besoin']}
- Tendance émotionnelle globale : {profil['tendance']}

⚠️ Ces éléments doivent être utilisés pour personnaliser **chaque mot de la réponse**.
'''
    )

    # Attente de la complétion
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "L'assistant a échoué."}), 500
        time.sleep(1)
        attempts += 1

    if attempts == max_attempts:
        return jsonify({"error": "Temps d’attente dépassé."}), 504

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    print("💬 Réponse brute :", last_message)
    return jsonify({"response": last_message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
