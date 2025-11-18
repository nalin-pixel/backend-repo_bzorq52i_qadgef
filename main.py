import os
from typing import List, Optional, Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="OTT Streaming API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class ContentIn(BaseModel):
    title: str
    description: Optional[str] = None
    type: Literal["movie", "series"]
    genres: List[str] = Field(default_factory=list)
    year: Optional[int] = Field(None, ge=1900, le=2100)
    rating: Optional[float] = Field(None, ge=0, le=10)
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    trailer_url: Optional[str] = None
    stream_url: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=1)
    cast: List[str] = Field(default_factory=list)
    director: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    is_published: bool = True

class ContentOut(ContentIn):
    id: str

class UserProfileIn(BaseModel):
    uid: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None

class UserProfileOut(UserProfileIn):
    favorites: List[str] = Field(default_factory=list)
    history: List[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)

# ---------- Helpers ----------

def to_id(doc: dict) -> dict:
    if not doc:
        return doc
    d = doc.copy()
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d

# ---------- Routes ----------

@app.get("/")
def root():
    return {"service": "OTT API", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["connection_status"] = "Connected"
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# ---- Content Catalog ----
@app.get("/api/content", response_model=List[ContentOut])
def list_content(
    q: Optional[str] = None,
    genre: Optional[str] = None,
    type: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=20, le=100)
):
    if db is None:
        return []
    filt = {"is_published": True}
    if q:
        # Simple title search
        filt["title"] = {"$regex": q, "$options": "i"}
    if genre:
        filt["genres"] = genre
    if type:
        filt["type"] = type
    cursor = db["content"].find(filt).skip(skip).limit(limit).sort("created_at", -1)
    return [to_id(x) for x in cursor]

@app.post("/api/content", response_model=dict)
def create_content(payload: ContentIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    new_id = create_document("content", payload.model_dump())
    return {"id": new_id}

@app.get("/api/content/{content_id}", response_model=ContentOut)
def get_content(content_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        doc = db["content"].find_one({"_id": ObjectId(content_id)})
    except Exception:
        raise HTTPException(404, "Invalid id")
    if not doc:
        raise HTTPException(404, "Not found")
    return to_id(doc)

@app.delete("/api/content/{content_id}")
def delete_content(content_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        res = db["content"].delete_one({"_id": ObjectId(content_id)})
    except Exception:
        raise HTTPException(404, "Invalid id")
    if res.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}

# ---- User Profiles ----
@app.get("/api/users/{uid}", response_model=UserProfileOut)
def get_user(uid: str):
    if db is None:
        raise HTTPException(500, "Database not configured")
    prof = db["userprofile"].find_one({"uid": uid})
    if not prof:
        # Auto-create minimal profile
        profile = UserProfileOut(uid=uid)
        create_document("userprofile", profile.model_dump())
        prof = db["userprofile"].find_one({"uid": uid})
    return UserProfileOut(**{
        "uid": prof.get("uid"),
        "display_name": prof.get("display_name"),
        "avatar_url": prof.get("avatar_url"),
        "favorites": prof.get("favorites", []),
        "history": prof.get("history", []),
        "preferences": prof.get("preferences", {}),
    })

@app.post("/api/users/{uid}/favorites")
def toggle_favorite(uid: str, content_id: str):
    if db is None:
        raise HTTPException(500, "Database not configured")
    prof = db["userprofile"].find_one({"uid": uid})
    if not prof:
        raise HTTPException(404, "Profile not found")
    favs = set(prof.get("favorites", []))
    if content_id in favs:
        favs.remove(content_id)
        action = "removed"
    else:
        favs.add(content_id)
        action = "added"
    db["userprofile"].update_one({"uid": uid}, {"$set": {"favorites": list(favs)}})
    return {"status": "ok", "action": action}

class WatchEntry(BaseModel):
    content_id: str
    progress: float = Field(ge=0, le=1)

@app.post("/api/users/{uid}/history")
def update_history(uid: str, entry: WatchEntry):
    if db is None:
        raise HTTPException(500, "Database not configured")
    prof = db["userprofile"].find_one({"uid": uid})
    if not prof:
        raise HTTPException(404, "Profile not found")
    history = prof.get("history", [])
    # upsert by content_id
    found = False
    for h in history:
        if h.get("content_id") == entry.content_id:
            h["progress"] = entry.progress
            found = True
            break
    if not found:
        history.append({"content_id": entry.content_id, "progress": entry.progress})
    db["userprofile"].update_one({"uid": uid}, {"$set": {"history": history}})
    return {"status": "ok"}

# ---- Recommendations (simple) ----
@app.get("/api/recommendations", response_model=List[ContentOut])
def recommendations(uid: Optional[str] = None, limit: int = 12):
    if db is None:
        return []
    # naive: use favorites genres if any, else latest
    filt = {"is_published": True}
    if uid:
        prof = db["userprofile"].find_one({"uid": uid})
        fav_ids = set((prof or {}).get("favorites", []))
        if fav_ids:
            fav_docs = db["content"].find({"_id": {"$in": [ObjectId(i) for i in fav_ids if ObjectId.is_valid(i)]}})
            genres = set()
            for d in fav_docs:
                for g in d.get("genres", []):
                    genres.add(g)
            if genres:
                filt["genres"] = {"$in": list(genres)}
    cursor = db["content"].find(filt).limit(limit).sort("created_at", -1)
    return [to_id(x) for x in cursor]

# ---- Admin analytics (basic) ----
@app.get("/api/admin/metrics")
def admin_metrics():
    if db is None:
        return {"content_count": 0, "users": 0, "favorites": 0}
    content_count = db["content"].count_documents({})
    users = db["userprofile"].count_documents({})
    favs = 0
    for u in db["userprofile"].find({}, {"favorites": 1}):
        favs += len(u.get("favorites", []))
    return {"content_count": content_count, "users": users, "favorites": favs}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
