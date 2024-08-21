import replicate, spotipy, instructor
import base64, os, requests, urllib, time, datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from openai import OpenAI
from pydantic import BaseModel
from typing import List
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
key: str = os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')
supabase: Client = create_client(url, key)

class Track(BaseModel):
    track: str
    artist: str
    track_id: str
    artist_id: str

class Analysis(BaseModel):
    description: str
    sample_tracks: List[Track]

# open ai client
client = instructor.from_openai(OpenAI())

load_dotenv()
app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")
app = FastAPI()

# cors config must be after instantiation of FastAPI instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://playscene.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/", tags=["Root"])
async def read_root() -> dict:
    return {
        "message": "fastapi-vercel example"
    }

@app.get("/login")
def login():
    auth_options = {
        "response_type": "code",
        "client_id": os.getenv("CLIENT_ID"),
        "redirect_uri": os.getenv("API_SERVICE") + "/callback",
        "scope": "streaming playlist-modify-public user-top-read user-library-modify user-read-email user-read-private",
        "show_dialog": "true"
    }
    
    auth_url = "https://accounts.spotify.com/authorize/?" + urllib.parse.urlencode(auth_options)
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(req: Request):
    global access_token
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    cred = f"{client_id}:{client_secret}"
    cred_b64 = base64.b64encode(cred.encode()).decode()

    form = {
        "code": req.query_params.get('code'),
        "redirect_uri": os.getenv("API_SERVICE") + "/callback", 
        "grant_type": "authorization_code" 
    }
    headers = {
        'content-type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {cred_b64}'
    }

    response = requests.post("https://accounts.spotify.com/api/token", data=form, headers=headers)
    response_json = response.json()

    if "access_token" in response_json:
        access_token = response_json["access_token"]
        redirect_url = os.getenv("CLIENT_SERVICE") + "/?access_token=" + access_token
        return RedirectResponse(redirect_url)
    
@app.post("/upload")
async def upload(imagePath: str = Form(...), accessToken: str = Form(...)):
    global sample_tracks, res, token
    token = accessToken
    res = supabase.storage.from_('playscene').get_public_url(f'uploads/{imagePath}')
    response = await get_sample_tracks_gpt4(res)
    sample_tracks = response.sample_tracks
    return {'description': response.description}

@app.get("/get_playlist")
async def get_playlist():
    print(f'\nGetting playlist endpoint...')
    return generate_playlist(sample_tracks, token, res)

# use gpt-4o-mini for both vision and track generator
async def get_sample_tracks_gpt4(imagePath: str):
    print('Running the gpt 4o mini model...')
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=Analysis,
        messages= [
            {
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the vibe of this image with as comma separated short descriptors using Gen-Z slang. Return only the descriptors and generate 5 tracks that would fit the mood. Return first the vibe of the image as the description and the artist and title of each track."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": imagePath
                        }
                    }
                ]
            }
        ]
    )
    print(response)
    return response

# call Spotify API for recs
def generate_playlist(sample_tracks: list, token: str, imagePath: str):
    print('Running the spotify recs...')
    # auth spotify
    sp = spotipy.Spotify(auth=token)

    # get spotify ids of each track using search endpoint
    for track in sample_tracks:
        query_str = urllib.parse.quote(f'track:{track.track} artist:{track.artist}', safe='')
        response = sp.search(f'q:{query_str}', type='track')
        if not response['tracks']['items']:
            continue
        else:
            track.track_id = response['tracks']['items'][0]['id']
            #print(f'track_id: {track.track_id}')
        
    # call spotify api recommendations endpoint - takes up to 5 seeds
    track_ids = [track.track_id for track in sample_tracks][:5]
    rec_response = sp.recommendations(seed_tracks=track_ids)
    rec_tracks =  [track['id'] for track in rec_response['tracks']]

    # get user id
    user_response = sp.me()
    user_id = user_response['id']

    # create playlist
    create_playlist = sp.user_playlist_create(user_id, f'{user_id}\'s playlist')
    playlist_id = create_playlist['id']

    # add to playlist
    add_tracks = sp.playlist_add_items(playlist_id, rec_tracks)

    # get playlist image
    #cover_image = sp.playlist_cover_image(playlist_id)[1]['url']
    print(f'\nplaylist_id: {playlist_id}')
    return {'playlist': playlist_id, 'cover_image': imagePath, 'user': 'playscene'}



