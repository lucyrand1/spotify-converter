from flask import Flask, request, redirect, session, render_template_string
import requests, urllib.parse
from requests_html import HTMLSession

app = Flask(__name__)
app.secret_key = 'ee8767622ff17f9f5860267c2192d5d3c3a412cb4930a9b2'

# Spotify API credentials
client_id     = '51277946d04c44bbafd86d27783987f5'
client_secret = 'bdfc543f37bb416d912e75bfa428e32f'
redirect_uri  = 'https://spotify-converter-1jgs.onrender.com/callback'
scope         = 'playlist-modify-private playlist-modify-public'

SPOTIFY_AUTH_URL  = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE  = 'https://api.spotify.com/v1'

# --- simple HTML templates ---
login_page = '''
  <h2>Login with Spotify to start conversion</h2>
  <a href="/">→ Login</a>
'''

input_page = '''
  <h2>Paste your Apple Music playlist URL</h2>
  <form method="POST" action="/create_playlist">
    <input name="apple_url" style="width:400px" placeholder="https://music.apple.com/…" required/>
    <button type="submit">Convert</button>
  </form>
'''

result_page = '''
  <h2>✅ Playlist created!</h2>
  <p><a href="{{ playlist_url }}" target="_blank">Open on Spotify</a></p>
  {% if unmatched %}
    <h3>These couldn’t be found:</h3>
    <ul>{% for t in unmatched %}<li>{{ t }}</li>{% endfor %}</ul>
  {% endif %}
'''

# --- ROUTES ---
@app.route('/')
def login():
    return redirect(
      SPOTIFY_AUTH_URL + '?' + urllib.parse.urlencode({
        'response_type': 'code',
        'client_id':     client_id,
        'scope':         scope,
        'redirect_uri':  redirect_uri,
        'show_dialog':   'true'
      })
    )

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
      return "Error: no code returned."
    # Exchange code for token
    data = {
      'grant_type':    'authorization_code',
      'code':          code,
      'redirect_uri':  redirect_uri,
      'client_id':     client_id,
      'client_secret': client_secret
    }
    tk = requests.post(SPOTIFY_TOKEN_URL, data=data).json()
    token = tk.get('access_token')
    if not token:
      return f"Error fetching token: {tk}"
    session['token'] = token
    return render_template_string(input_page)

@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    token     = session.get('token')
    apple_url = request.form.get('apple_url','').strip()
    if not token:
      return redirect('/')
    # 1) scrape Apple Music for (title,artist) pairs
    session2 = HTMLSession()
    r = session2.get(apple_url)
    r.html.render(timeout=20)
    titles  = r.html.find('div.songs-list-row__song-name')
    artists = r.html.find('div.songs-list-row__by-line')
    if not titles or not artists or len(titles)!=len(artists):
      return "Could not parse songs from Apple Music page."
    songs = [(t.text.strip(), a.text.strip()) for t,a in zip(titles,artists)]

    # 2) get Spotify user id
    me = requests.get(f"{SPOTIFY_API_BASE}/me",
      headers={'Authorization':f'Bearer {token}'}).json()
    user_id = me.get('id') or ''
    if not user_id:
      return "Failed to get Spotify user ID."

    # 3) create new playlist
    p = requests.post(
      f"{SPOTIFY_API_BASE}/users/{user_id}/playlists",
      headers={'Authorization':f'Bearer {token}'},
      json={'name':'Apple Music Converted Playlist',
            'description':'Converted via app','public':False}
    ).json()
    pid = p.get('id')
    playlist_url = p.get('external_urls',{}).get('spotify')
    if not pid:
      return f"Failed to create playlist: {p}"

    # 4) search each song and collect URIs
    uris, unmatched = [], []
    for title,artist in songs:
        q = f"track:{title} artist:{artist}"
        res = requests.get(
          f"{SPOTIFY_API_BASE}/search",
          headers={'Authorization':f'Bearer {token}'},
          params={'q':q,'type':'track','limit':1}
        ).json()
        items = res.get('tracks',{}).get('items',[])
        if items:
          uris.append(items[0]['uri'])
        else:
          unmatched.append(f"{title} – {artist}")

    # 5) add URIs in batches of 100
    for i in range(0,len(uris),100):
      chunk = uris[i:i+100]
      requests.post(
        f"{SPOTIFY_API_BASE}/playlists/{pid}/tracks",
        headers={'Authorization':f'Bearer {token}'},
        json={'uris':chunk}
      )

    return render_template_string(result_page,
      playlist_url=playlist_url, unmatched=unmatched)

if __name__ == '__main__':
    app.run(debug=True, port=5002)
