import os

import requests

url = os.environ.get("OLLAMA_URL")


def get_response(messages):
    request = {
        # "model": "qwen2.5:14b",
        "model": "qwen2.5:14b-instruct-q4_1",
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.0,
        },
    }

    response = requests.post(url + "/chat", json=request)
    if response.status_code != 200:
        raise Exception(response.text)
    return response.json()
