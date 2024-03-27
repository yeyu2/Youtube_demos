from flask import Flask, request, send_file
import io
from flask_cors import CORS  # Necessary for cross-domain requests

app = Flask(__name__)
CORS(app)  # This is used to allow cross-domain requests during development

from openai import OpenAI
from groq import Groq

from texttospeech import text_to_speech
# gets API Key from environment variable OPENAI_API_KEY
client = Groq(
  api_key="Your_Groq_Key",
)
openai_client = OpenAI(api_key="Your_OpenAI_KEY")

INIT_MESG=[
            {
            "role": "user",
            "content": """
                You are a voice chatbot that responds to human user's speech input.
                The speech input texts are sometimes broken or hard stop due to the listening mechinism,
                If the message you read is not complete, please ask the user to repeat or complete politely and consicely.
                Remember you are speaking not writing, so please use oral expression in plain language.
                """,
            },
            {
            "role": "assistant",
            "content": """
                OK, I understood.

                """,
            },
        ]
history_messages = INIT_MESG

@app.route('/synthesize-speech', methods=['POST'])
def synthesize_speech():
    data = request.json
    text = data['text']

    # Create an audio buffer
    #sound = io.BytesIO()

    sound = "output.mp3"
    
    voice_response = openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )

    voice_response.stream_to_file(sound)
    
    #text_to_speech(text, sound)
    return send_file(
        sound,
        mimetype="audio/mpeg"
    )

@app.route('/process-speech', methods=['POST'])
def process_speech():

    data = request.json
    user_text = data['text']
    history_messages.append({"role":"user", "content":user_text})
    completion = client.chat.completions.create(

        model="mixtral-8x7b-32768",
        messages=history_messages,
        
        )
    ai_response = completion.choices[0].message.content
    history_messages.append({"role":"assistant", "content":ai_response})
    #ai_response = user_text

    return {'response': ai_response}

@app.route('/start-speech', methods=['POST'])
def start_speech():

    history_messages = INIT_MESG
    return {'response': 'OK'}

if __name__ == '__main__':
    app.run(debug=True)