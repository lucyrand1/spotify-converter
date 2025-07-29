from flask import Flask, request, redirect, session
import requests
import urllib.parse

app = Flask(__name__)
app.secret_key = 'replace_this_with_a_real_secret_key'  # Use a strong secret key here

# Spotify API credentials — your actual values:
client_id = '51277946d04c44bbafd86d27783987f5'
client_secret = 'bdfc543f37bb416d912e75bfa428e32f'
redirect_uri = 'https://spotify-converter-1jgs.onrender.com/callback'  # Your Render app's URL + /callback

scope = 'playlist-modify-private playlist-modify-public'

@app.route('/')
def login():
    auth_url = (
        'https://accounts.spotify.com/authorize?'
        + urllib.parse.urlencode({
            'response_type': 'code',
            'client_id': client_id,
            'scope': scope,
            'redirect_uri': redirect_uri,
            'show_dialog': 'true'
        })
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Error: No authorization code returned."

    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret
    }

    response = requests.post(token_url, data=payload)
    token_data = response.json()
    access_token = token_data.get('access_token')

    if not access_token:
        return f"Error fetching token: {token_data}"

    session['access_token'] = access_token
    return "✅ Logged in! Access token saved in session."

if __name__ == '__main__':
    app.run(debug=True, port=5002)
