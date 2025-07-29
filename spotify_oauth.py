from flask import Flask, request, redirect, session, url_for, render_template_string
import requests
import urllib.parse
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = 'replace_this_with_a_real_secret_key'

# Spotify API credentials
client_id = '51277946d04c44bbafd86d27783987f5'
client_secret = 'bdfc543f37bb416d912e75bfa428e32f'
redirect_uri = 'https://spotify-converter-1jgs.onrender.com/callback'
scope = 'playlist-modify-private playlist-modify-public'

SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE_URL = 'https://api.spotify.com/v1'

# Basic HTML templates embedded here for simplicity
login_page = '''
    <h2>Login to Spotify to start</h2>
    <a href="/">Login with Spotify</a>
'''

input_page = '''
    <h2>Paste your Apple Music playlist URL</h2>
    <form method="POST" action="/create_playlist">
      <input name="apple_url" style="width:400px" placeholder="Apple Music Playlist URL" required/>
      <button type="submit">Convert to Spotify Playlist</button>
    </form>
'''

result_page = '''
<h2>Playlist created!</h2>
<p><a href="{{ playlist_url }}" target="_blank">Open your Spotify playlist</a></p>
{% if unmatched %}
<h3>These songs were not found on Spotify:</h3>
<ul>{% for s in unmatched %}<li>{{ s }}</li>{% endfor %}</ul>
{% endif %}
'''

@app.route('/')
def login():
    auth_url = (
        SPOTIFY_AUTH_URL + '?' + urllib.parse.urlencode({
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

    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret
    }

    r = requests.post(SPOTIFY_TOKEN_URL, data=payload)
    token_data = r.json()
    access_token = token_data.get('access_token')

    if not access_token:
        return f"Error fetching token: {token_data}"

    session['access_token'] = access_token
    return render_template_string(input_page)

def parse_apple_music_playlist(apple_url):
    """
    Simple parser for Apple Music playlist to extract song names and artists.
    This scrapes the playlist page — might break if Apple changes their site.
    """
    res = requests.get(apple_url)
    if res.status_code != 200:
        return [], "Failed to fetch Apple Music playlist page."

    soup = BeautifulSoup(res.text, 'html.parser')
    songs = []
    # Apple Music playlist pages contain <meta name="twitter:title" content="..."> with playlist name and songs in the page
    # But better to look for song info in the page — let's find all song titles and artist names:
    # Apple Music renders songs in <div class="songs-list-row__song-name"> and artist in <div class="songs-list-row__by-line">
    # This is a rough approach and might need updates if Apple changes their HTML

    song_titles = soup.select('div.songs-list-row__song-name')
    artist_names = soup.select('div.songs-list-row__by-line')

    if not song_titles or not artist_names:
        return [], "Could not parse songs from Apple Music page."

    for title, artist in zip(song_titles, artist_names):
        song = title.text.strip()
        artist_text = artist.text.strip()
        songs.append((song, artist_text))

    return songs, None

def search_spotify_track(token, song, artist):
    query = f'track:{song} artist:{artist}'
    url = f"{SPOTIFY_API_BASE_URL}/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": 1}
    r = requests.get(url, headers=headers, params=params)
    results = r.json()
    tracks = results.get('tracks', {}).get('items', [])
    if tracks:
        return tracks[0]['uri']
    else:
        return None

@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    if 'access_token' not in session:
        return redirect('/')

    access_token = session['access_token']
    apple_url = request.form.get('apple_url')
    if not apple_url:
        return "Please provide an Apple Music playlist URL."

    songs, error = parse_apple_music_playlist(apple_url)
    if error:
        return error

    # Get user ID
    url = f"{SPOTIFY_API_BASE_URL}/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    user_data = r.json()
    user_id = user_data.get('id')

    if not user_id:
        return "Failed to get Spotify user ID."

    # Create playlist
    create_url = f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists"
    payload = {
        "name": "Apple Music Converted Playlist",
        "description": "Playlist converted from Apple Music",
        "public": False
    }
    r = requests.post(create_url, json=payload, headers=headers)
    playlist_data = r.json()
    playlist_id = playlist_data.get('id')
    playlist_url = playlist_data.get('external_urls', {}).get('spotify')

    if not playlist_id:
        return "Failed to create Spotify playlist."

    # Search songs and collect URIs
    track_uris = []
    unmatched = []
    for song, artist in songs:
        uri = search_spotify_track(access_token, song, artist)
        if uri:
            track_uris.append(uri)
        else:
            unmatched.append(f"{song} by {artist}")

    # Add songs to playlist in batches of 100 (Spotify limit)
    for i in range(0, len(track_uris), 100):
        add_url = f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks"
        chunk = track_uris[i:i+100]
        r = requests.post(add_url, json={"uris": chunk}, headers=headers)
        if r.status_code not in (200, 201):
            return f"Failed to add tracks: {r.json()}"

    return render_template_string(result_page, playlist_url=playlist_url, unmatched=unmatched)

if __name__ == '__main__':
    app.run(debug=True, port=5002)
