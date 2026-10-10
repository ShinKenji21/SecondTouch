import os

COMMENTARY_TEMPLATES = {
    "ANALYST": {
        "Saka": "Saka isolates the fullback on the right flank, generating a 0.34 xG opportunity.",
        "Ødegaard": "Ødegaard bypasses City's mid-block with a sharp line-breaking diagonal ball.",
        "default": "Tactical structure shifts as team maintains 58.2m defensive line height."
    },
    "CASUAL": {
        "Saka": "Saka charges down the wing and leaves his defender behind!",
        "Ødegaard": "WHAT A PASS! Ødegaard slices right through the defense!",
        "default": "High-intensity pressure building up in the final third!"
    },
    "PLAYER_CAM": {
        "Saka": "Saka reaches a top sprint speed of 31.2 km/h on that transition run.",
        "Ødegaard": "Ødegaard completes his 12th line-breaking pass of the half.",
        "default": "Player tracking active: maintaining spatial discipline in middle third."
    }
}

def generate_ai_commentary(event_data: dict, mode: str = "ANALYST", focus_player: str = "Saka") -> str:
    player = event_data.get("player", focus_player)
    
    # Optional Azure OpenAI Integration
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                api_key=api_key,
                api_version="2024-02-01",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": f"You are an AI football commentator. Mode: {mode}. Player Focus: {focus_player}. Write 1 concise sentence."},
                    {"role": "user", "content": f"Event: {event_data}"}
                ],
                max_tokens=60
            )
            return response.choices[0].message.content.strip()
        except Exception:
            pass

    # Local Fallback Engine
    mode_dict = COMMENTARY_TEMPLATES.get(mode, COMMENTARY_TEMPLATES["ANALYST"])
    return mode_dict.get(player, mode_dict["default"])