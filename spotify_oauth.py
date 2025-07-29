from flask import Flask, request, redirect, session, render_template_string
import requests
import urllib.parse

app = Flask(__name__)
app.secret_key = 'replace_with_a_real_secret_key'  # ← change this to anything long & random

# Spotify credentials & redirect URI
client_id = '51277946d04c44bbafd86d27783987f5'
client_secret = 'bdfc543f37bb416d912e75bfa428e32f'
redirect_uri = 'https://spotify-converter-1jgs.onrender.com/callback'
scope = 'playlist-modify-private playlist-modify-public'

SPOTIFY_AUTH_URL  = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API       = 'https://api.spotify.com/v1'

login_page = '<a href="/">Login with Spotify</a>'
input_page = '''
  <h2>Paste your songs here (one per line, “Title – Artist”):</h2>
  <form method="POST" action="/create_playlist">
    <textarea name="song_list" rows="10" cols="60"
      placeholder="Cruel Summer – Taylor Swift\nBad Habits – Ed Sheeran\n…"
      required></textarea><br>
    <button type="submit">Create Spotify Playlist</button>
  </form>
'''
result_page = '''
  <h2>Playlist created!</h2>
  <p><a href="{{ playlist_url }}" target="_blank">Open Spotify playlist</a></p>
  {% if unmatched %}
    <h3>These tracks weren’t found:</h3>
    <ul>{% for t in unmatched %}<li>{{ t }}</li>{% endfor %}</ul>
  {% endif %}
'''

@app.route('/')
def login():
    return redirect(
      SPOTIFY_AUTH_URL + '?' + urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': client_id,
        'scope': scope,
        'redirect_uri': redirect_uri,
        'show_dialog': 'true'
      })
    )

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
      return "No code returned."

    token_data = requests.post(
      SPOTIFY_TOKEN_URL,
      data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret
      }
    ).json()

    token = token_data.get('access_token')
    if not token:
      return f"Error fetching token: {token_data}"

    session['token'] = token
    return render_template_string(input_page)

def search_track(token, song, artist):
    q = f"track:{song} artist:{artist}" if artist else song
    res = requests.get(
      f"{SPOTIFY_API}/search",
      headers={'Authorization':f'Bearer {token}'},
      params={'q':q, 'type':'track','limit':1}
    ).json()
    items = res.get('tracks', {}).get('items')
    return items[0]['uri'] if items else None

@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    token = session.get('token')
    if not token:
      return redirect('/')

    # Parse pasted lines
    raw   = request.form['song_list'].strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    songs = []
    for l in lines:
        if '–' in l:
            title, artist = map(str.strip, l.split('–',1))
        else:
            title, artist = l, ''
        songs.append((title, artist))

    # Get current user ID
    me = requests.get(f"{SPOTIFY_API}/me",
      headers={'Authorization':f'Bearer {token}'}).json()
    user_id = me.get('id')

    # Create new playlist
    p = requests.post(
      f"{SPOTIFY_API}/users/{user_id}/playlists",
      headers={'Authorization':f'Bearer {token}'},
      json={'name':'Apple Music Converted Playlist',
            'description':'Converted via app','public':False}
    ).json()
    pid = p.get('id')
    url = p.get('external_urls',{}).get('spotify')

    # Search tracks & collect URIs
    uris, unmatched = [], []
    for title, artist in songs:
        uri = search_track(token, title, artist)
        if uri:
            uris.append(uri)
        else:
            unmatched.append(f"{title} – {artist}")

    # Add tracks in batches
    for i in range(0, len(uris), 100):
        chunk = uris[i:i+100]
        requests.post(
          f"{SPOTIFY_API}/playlists/{pid}/tracks",
          headers={'Authorization':f'Bearer {token}'},
          json={'uris':chunk}
        )

    return render_template_string(result_page,
      playlist_url=url, unmatched=unmatched)

if __name__ == '__main__':
    app.run(debug=True, port=5002)
